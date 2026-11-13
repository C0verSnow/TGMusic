import hashlib
import io
import logging
import json
import os
import tempfile
from pathlib import Path
import shutil
import tarfile

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
        import sqlite3
        for cookie_path in (destination / "Default" / "Cookies", destination / "Default" / "Network" / "Cookies"):
            if cookie_path.is_file() and os.getenv("GITHUB_WORKFLOW") == "YouTube Music Sync":
                with sqlite3.connect(f"file:{cookie_path}?mode=ro", uri=True) as db:
                    counts = db.execute("SELECT hex(substr(encrypted_value,1,3)),count(*) FROM cookies "
                                        "WHERE host_key LIKE '%youtube.com' OR host_key LIKE '%google.com' "
                                        "GROUP BY 1").fetchall()
                logging.warning("[DEBUG-issue3] Archived Google/YouTube cookie encryption prefix counts: %s", counts)

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
        runtime_version = self.page.run_js("return navigator.userAgent")
        logging.warning("[DEBUG-issue3] Archived browser=%s; Runner browser=%s", self.browser_version, runtime_version)
        self.browser_version = runtime_version
        return self.page

    def detect_auth(self):
        self.auth_state = detect_auth(self.page)
        logging.info("Google auth: %s", self.auth_state)
        if self.auth_state != "VALID" and os.getenv("GITHUB_WORKFLOW") == "YouTube Music Sync":
            context = self.page.run_js("return {host:location.hostname, logged:window.ytcfg?.get('LOGGED_IN'),"
                                       " ready:!!window.ytcfg?.get('INNERTUBE_CONTEXT')};")
            cookies = self.page.cookies(all_domains=True, all_info=True)
            count = sum(c["name"] in {"SID", "HSID", "SSID", "SAPISID", "APISID", "__Secure-3PAPISID"}
                        for c in cookies)
            logging.warning("[DEBUG-issue3] Browser auth context=%s; loaded auth cookie count=%d", context, count)
            import time
            time.sleep(5)
            logging.warning("[DEBUG-issue3] Auth after waiting=%s", detect_auth(self.page))
            self.page.refresh()
            time.sleep(5)
            logging.warning("[DEBUG-issue3] Auth after reload=%s", detect_auth(self.page))
            self.page.get("https://myaccount.google.com/")
            time.sleep(2)
            logging.warning("[DEBUG-issue3] Google account landing host=%s",
                            self.page.run_js("return location.hostname"))
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
