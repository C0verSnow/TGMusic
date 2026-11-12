import hashlib
import io
import json
import logging
import tarfile
from pathlib import Path

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
        if metadata.get("sha256") != digest or metadata.get("schema") != "1":
            raise SyncError("Profile integrity/version check failed")
        destination = self.config.browser_user_data_path
        if destination.exists() and any(destination.iterdir()):
            raise SyncError("Restore requires an empty dedicated browser directory")
        destination.mkdir(parents=True, exist_ok=True, mode=0o700)
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
            archive.extractall(destination, filter="data")
        self.digest = profile_digest(destination)

    def start(self):
        from DrissionPage import ChromiumOptions, ChromiumPage
        options = ChromiumOptions(ini_path=self.config.browser_ini_path)
        options.set_user_data_path(str(self.config.browser_user_data_path))
        options.set_browser_path(self.config.browser_path)
        options.headless(self.config.browser_headless)
        options.set_argument("--no-sandbox")
        options.set_argument("--password-store=basic")
        if self.proxy_url:
            options.set_proxy(self.proxy_url)
        self.page = ChromiumPage(options)
        self.page.get("https://music.youtube.com/")
        return self.page

    def detect_auth(self):
        try:
            data = self.page.run_js("return {url:location.href, logged:window.ytcfg?.get('LOGGED_IN'),"
                                    " ready:!!window.ytcfg?.get('INNERTUBE_CONTEXT')};")
            if data["ready"] and data["logged"] is True:
                self.auth_state = "VALID"
            elif "accounts.google.com" in data["url"] or (data["ready"] and data["logged"] is False):
                self.auth_state = "EXPIRED"
            else:
                self.auth_state = "UNKNOWN"
        except Exception:
            self.auth_state = "UNKNOWN"
        logging.info("Google auth: %s", self.auth_state)
        return self.auth_state

    def close(self):
        if self.page is not None:
            self.page.quit()
            self.page = None

    def backup(self):
        if self.page is not None or self.auth_state != "VALID":
            raise SyncError("Only a closed, verified profile can be backed up")
        directory = self.config.browser_user_data_path
        digest = profile_digest(directory)
        if digest == self.digest:
            logging.info("Browser profile unchanged")
            return
        if not (directory / "Default" / "Cookies").exists() and not (directory / "Default" / "Network" / "Cookies").exists():
            raise SyncError("Empty profile refused; backup preserved")
        raw = archive_profile(directory)
        metadata = {"sha256": hashlib.sha256(raw).hexdigest(), "schema": "1", "content-sha256": digest}
        self.etag = self.r2.versioned_put(self.config.r2_profile_object, self.cipher.encrypt(raw), self.etag, metadata)
        self.digest = digest


def profile_files(directory):
    excluded = {"Cache", "Code Cache", "GPUCache", "DawnCache", "ShaderCache", "GrShaderCache",
                "Crashpad", "BrowserMetrics", "Service Worker"}
    for path in sorted(directory.rglob("*")):
        relative = path.relative_to(directory)
        if any(part in excluded or part.startswith("Singleton") for part in relative.parts):
            continue
        if path.is_file() and not path.is_symlink():
            yield path, relative


def profile_digest(directory):
    digest = hashlib.sha256()
    for path, relative in profile_files(directory):
        digest.update(str(relative).encode() + b"\x00")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def archive_profile(directory):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for path, relative in profile_files(directory):
            archive.add(path, arcname=str(relative), recursive=False)
    return buffer.getvalue()
