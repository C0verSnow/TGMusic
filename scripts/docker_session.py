import argparse
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace
from urllib.request import urlopen

from browser_session import BrowserSession, detect_auth
from cloudflare_storage import R2
from models import SyncError
from utils import configure_logging

STATE = Path("/state")
PROFILE = STATE / "browser-config" / ".config" / "chromium"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["prepare", "observe", "upload", "probe"])
    args = parser.parse_args()
    configure_logging()
    if args.mode == "probe":
        probe()
        return
    if args.mode == "observe":
        observe()
        return
    config = load_upload_config()
    r2 = R2(config)
    if args.mode == "prepare":
        existing = r2.get(config.r2_profile_object, optional=True)
        (STATE / "preflight.json").write_text(json.dumps({"etag": existing[1] if existing else None}))
        (STATE / "login-ready.json").unlink(missing_ok=True)
        print("R2 连接和加密密钥已检查；开始人工登录。", flush=True)
        BrowserSession(config, r2)
    else:
        upload(config, r2)


def connect_browser():
    from DrissionPage import ChromiumOptions, ChromiumPage
    for _ in range(90):
        try:
            with urlopen("http://127.0.0.1:9222/json/version", timeout=2) as response:
                version = json.load(response)["Browser"]
            break
        except OSError:
            time.sleep(1)
    else:
        raise SyncError("Chromium 调试连接未就绪；未上传任何档案。")
    options = ChromiumOptions(read_file=False).set_address("127.0.0.1:9222").existing_only(True)
    page = ChromiumPage(options)
    return page, version


def probe():
    page, version = connect_browser()
    with urlopen("http://127.0.0.1:3000/", timeout=10) as response:
        if response.status != 200:
            raise SyncError("Docker browser GUI is unavailable")
    if "HeadlessChrome" in page.run_js("return navigator.userAgent"):
        raise SyncError("Expected a headed browser")
    print("Prebuilt Docker GUI and DevTools attachment verified: " + version, flush=True)


def observe():
    page, version = connect_browser()
    page.get("https://music.youtube.com/")
    deadline = time.monotonic() + int(os.getenv("TGMUSIC_LOGIN_TIMEOUT", "1800"))
    previous = None
    while time.monotonic() < deadline:
        state = detect_auth(page)
        if state != previous:
            print("Google 登录状态：" + state, flush=True)
            previous = state
        if state == "VALID":
            (STATE / "login-ready.json").write_text(json.dumps({"state": state, "browser_version": version}))
            # 宿主随后停止整个浏览器容器，避免镜像的守护进程在归档时重新启动 Chromium。
            print("登录已验证，正在关闭浏览器并自动归档。", flush=True)
            return
        time.sleep(3)
    raise SyncError("等待登录超时；未上传失效或空白档案。")


def load_upload_config():
    required = ["R2_ENDPOINT", "R2_BUCKET", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "PROFILE_ENCRYPTION_KEY"]
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise SyncError("上传配置缺失：" + ", ".join(missing))
    return SimpleNamespace(**{key.lower(): os.environ[key] for key in required},
                           r2_profile_object=os.getenv("R2_PROFILE_OBJECT") or "auth/google-profile.tar.enc",
                           browser_user_data_path=PROFILE, browser_ini_path="/input/browser.ini")


def upload(config, r2):
    ready = json.loads((STATE / "login-ready.json").read_text())
    preflight = json.loads((STATE / "preflight.json").read_text())
    browser = BrowserSession(config, r2)
    browser.auth_state = ready["state"]
    browser.browser_version = ready["browser_version"]
    browser.etag = preflight["etag"]
    browser.backup(encrypted_copy=STATE / "google-profile.latest.enc")
    (STATE / "upload-result.json").write_text(json.dumps({"object": config.r2_bucket + "/" + config.r2_profile_object,
                                                        "etag": browser.etag, "schema": 2}))


if __name__ == "__main__":
    os.umask(0o077)
    try:
        main()
    except Exception as error:
        print(str(error) if isinstance(error, SyncError) else "Docker 登录任务未完成：" + type(error).__name__ + "；敏感详情已隐藏。", file=sys.stderr)
        sys.exit(1)
