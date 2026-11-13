import hashlib
import io
import logging
import json
import os
import tempfile
from pathlib import Path
import shutil
import tarfile
import time
from urllib.parse import urlsplit

from cryptography.fernet import Fernet, InvalidToken

from models import SyncError


class BrowserSession:
    def __init__(self, config, r2, proxy_url=None):
        self.config = config
        self.r2 = r2
        self.proxy_url = proxy_url
        self.page = None
        self.etag = None
        self.digest = None
        self.auth_state = "UNKNOWN"
        self.restored_directory = False
        self.bundle_directory = None
        self.ini_path = Path(config.browser_ini_path)
        self.browser_version = ""
        try:
            self.cipher = Fernet(config.profile_encryption_key.encode())
        except ValueError:
            raise SyncError("Invalid PROFILE_ENCRYPTION_KEY") from None

    def restore(self):
        obj = self.r2.get(self.config.r2_profile_object)
        encrypted, self.etag, metadata = obj
        try:
            raw = self.cipher.decrypt(encrypted)
        except InvalidToken:
            raise SyncError("Profile decryption failed; backup preserved") from None
        digest = hashlib.sha256(raw).hexdigest()
        if metadata.get("sha256") != digest or metadata.get("schema") not in {"1", "2"}:
            raise SyncError("Profile integrity/version check failed")
        destination = self.config.browser_user_data_path
        if destination.exists() and any(destination.iterdir()):
            raise SyncError("Restore requires an empty dedicated browser directory")
        destination.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.restored_directory = True
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:*") as archive:
            if metadata["schema"] == "1":
                archive.extractall(destination, filter="data")
            else:
                self.bundle_directory = tempfile.TemporaryDirectory(prefix="tgmusic-bundle-", dir=destination.parent)
                unpacked = Path(self.bundle_directory.name)
                archive.extractall(unpacked, filter="data")
                self.ini_path = unpacked / "config" / "browser.ini"
                if not self.ini_path.is_file() or not (unpacked / "user-data").is_dir():
                    raise SyncError("Incomplete browser bundle; backup preserved")
                manifest = json.loads((unpacked / "manifest.json").read_text())
                self.browser_version = manifest.get("browser_version", "")
                os.replace(unpacked / "user-data", destination)
        self.digest = profile_digest(destination, self.ini_path)

    def start(self, initial_url="https://music.youtube.com/"):
        from DrissionPage import ChromiumOptions, ChromiumPage
        options = ChromiumOptions(ini_path=str(self.ini_path))
        options.set_user_data_path(str(self.config.browser_user_data_path))
        options.set_browser_path(self.config.browser_path)
        options.headless(self.config.browser_headless)
        options.set_argument("--no-sandbox")
        options.set_argument("--password-store=basic")
        if self.proxy_url:
            options.set_proxy(self.proxy_url)
        self.page = ChromiumPage(options)
        self.page.get(initial_url)
        self.browser_version = self.page.run_js("return navigator.userAgent")
        return self.page

    def detect_auth(self):
        if urlsplit(self.page.url).hostname == "consent.youtube.com":
            dismiss_youtube_consent(self.page)
        self.auth_state = detect_auth(self.page)
        if self.auth_state == "EXPIRED" and urlsplit(self.page.url).hostname == "music.youtube.com":
            self.auth_state = resume_youtube_sign_in(self.page)
        logging.info("Google auth: %s", self.auth_state)
        return self.auth_state

    def close(self):
        if self.page is not None:
            self.page.quit()
            self.page = None

    def cleanup(self):
        self.close()
        if self.restored_directory:
            shutil.rmtree(self.config.browser_user_data_path)
            self.restored_directory = False
        if self.bundle_directory:
            self.bundle_directory.cleanup()
            self.bundle_directory = None

    def backup(self, encrypted_copy=None):
        if self.page is not None or self.auth_state != "VALID":
            raise SyncError("Only a closed, verified profile can be backed up")
        directory = self.config.browser_user_data_path
        digest = profile_digest(directory, self.ini_path)
        if digest == self.digest:
            logging.info("Browser profile unchanged")
            return
        if not (directory / "Default" / "Cookies").exists() and not (directory / "Default" / "Network" / "Cookies").exists():
            raise SyncError("Empty profile refused; backup preserved")
        raw = archive_profile(directory, self.ini_path, self.browser_version)
        metadata = {"sha256": hashlib.sha256(raw).hexdigest(), "schema": "2", "content-sha256": digest}
        encrypted = self.cipher.encrypt(raw)
        if encrypted_copy is not None:
            Path(encrypted_copy).write_bytes(encrypted)
            Path(encrypted_copy).chmod(0o600)
        self.etag = self.r2.versioned_put(self.config.r2_profile_object, encrypted, self.etag, metadata)
        self.digest = digest


def dismiss_youtube_consent(page):
    reject = page.ele('css:button[aria-label="Reject all"]', timeout=5)
    if not reject:
        raise SyncError("YouTube consent page requires manual review")
    logging.info("Rejecting optional YouTube cookies before checking sign-in")
    reject.click(by_js=True)
    if not page.wait.url_change("consent.youtube.com", exclude=True, timeout=20, raise_err=False):
        raise SyncError("YouTube consent page did not finish; manual review required")
    page.wait.doc_loaded(timeout=20)


def resume_youtube_sign_in(page, timeout=20):
    sign_in = page.ele('css:a[href*="ServiceLogin"]', timeout=5)
    if not sign_in:
        return "EXPIRED"
    logging.info("Resuming YouTube sign-in with the restored Google session")
    page.get(sign_in.link)
    deadline = time.monotonic() + timeout
    while True:
        state = detect_auth(page)
        if state == "VALID" or time.monotonic() >= deadline:
            return state
        time.sleep(0.5)


def detect_auth(page):
    try:
        data = page.run_js("return {url:location.href, logged:window.ytcfg?.get('LOGGED_IN'),"
                           " ready:!!window.ytcfg?.get('INNERTUBE_CONTEXT')};")
        if data["ready"] and data["logged"] is True:
            return "VALID"
        if "accounts.google.com" in data["url"] or (data["ready"] and data["logged"] is False):
            return "EXPIRED"
    except Exception:
        pass
    return "UNKNOWN"


def profile_files(directory):
    for path in sorted(directory.rglob("*")):
        relative = path.relative_to(directory)
        if any(part.startswith("Singleton") or part == "DevToolsActivePort" for part in relative.parts):
            continue
        yield path, relative


def profile_digest(directory, ini_path):
    digest = hashlib.sha256(Path(ini_path).read_bytes())
    for path, relative in profile_files(directory):
        digest.update(str(relative).encode() + b"\x00")
        if path.is_symlink():
            digest.update(b"link:" + os.readlink(path).encode())
        elif path.is_file():
            digest.update(hashlib.sha256(path.read_bytes()).digest())
        else:
            digest.update(b"directory")
    return digest.hexdigest()


def archive_profile(directory, ini_path, browser_version=""):
    buffer = io.BytesIO()
    manifest = json.dumps({"schema": 2, "browser_version": browser_version,
                           "archive": "tar.gz", "profile": "user-data", "ini": "config/browser.ini"}).encode()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        info = tarfile.TarInfo("manifest.json")
        info.size = len(manifest)
        info.mode = 0o600
        archive.addfile(info, io.BytesIO(manifest))
        archive.add(ini_path, arcname="config/browser.ini", recursive=False)
        archive.add(directory, arcname="user-data", recursive=False)
        for path, relative in profile_files(directory):
            archive.add(path, arcname="user-data/" + str(relative), recursive=False)
    return buffer.getvalue()
