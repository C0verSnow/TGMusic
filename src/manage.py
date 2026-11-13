"""Explicit setup and recovery operations; normal sync never initializes missing storage."""
import argparse
import json
import os
import sys
import uuid
from pathlib import Path

from browser_session import BrowserSession
from cloudflare_storage import D1, R2
from config import Config
from history import History, receipt_data, receipt_key
from models import SyncError
from proxy import Network
from telegram_bot import TelegramBot
from utils import configure_logging, mask_actions_secrets


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("bootstrap")
    sub.add_parser("login")
    sub.add_parser("rotate-profile-key")
    reconcile = sub.add_parser("reconcile")
    reconcile.add_argument("chat_id", type=int)
    reconcile.add_argument("video_id")
    group = reconcile.add_mutually_exclusive_group(required=True)
    group.add_argument("--sent-message-id", type=int)
    group.add_argument("--retry", action="store_true")
    reconcile.add_argument("--mode", choices=["audio", "link"], default="link")
    admin = sub.add_parser("grant-admin")
    admin.add_argument("user_id", type=int)
    admin.add_argument("chat_id", type=int, nargs="+")
    webhook = sub.add_parser("set-webhook")
    webhook.add_argument("url")
    profile = sub.add_parser("set-bot-profile")
    profile.add_argument("--name", default="TGMusic")
    profile.add_argument("--username", default="C0verSnow_TGMusic_bot",
                         help="Expected existing username, not a rename operation")
    profile.add_argument("--photo", type=Path, default=Path("assets/bot-avatar.jpg"))
    args = parser.parse_args()
    configure_logging()
    mask_actions_secrets()
    if args.command == "set-bot-profile":
        set_bot_profile(args)
        return
    config = Config.load()
    db, r2 = D1(config), R2(config)
    if args.command == "bootstrap":
        bootstrap(config, db, r2)
    elif args.command == "login":
        login(config, db, r2)
    elif args.command == "rotate-profile-key":
        rotate_profile_key(config, db, r2)
    elif args.command == "set-webhook":
        secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET")
        if not secret or not args.url.startswith("https://"):
            raise SyncError("HTTPS URL and TELEGRAM_WEBHOOK_SECRET are required")
        TelegramBot(config.telegram_bot_token).call("setWebhook", {
            "url": args.url, "secret_token": secret, "allowed_updates": json.dumps(["message"]),
        })
        print("Webhook registered")
    else:
        history = History(db)
        r2.verify_installation(history.installation()["installation_id"])
        history.acquire()
        try:
            if args.command == "grant-admin":
                grant_admin(db, args.user_id, args.chat_id)
            else:
                reconcile(history, r2, args)
        finally:
            history.release()


def set_bot_profile(args):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token or not 1 <= len(args.name) <= 64:
        raise SyncError("TELEGRAM_BOT_TOKEN and a name of 1-64 characters are required")
    if not args.photo.is_file() or args.photo.suffix.lower() not in {".jpg", ".jpeg"}:
        raise SyncError("Bot profile photo must be a local JPG file")
    bot = TelegramBot(token)
    identity = bot.call("getMe", {})
    if identity["username"].lower() != args.username.lstrip("@").lower():
        raise SyncError("Token belongs to another bot; create/select the expected bot in BotFather first")
    bot.call("setMyName", {"name": args.name})
    with args.photo.open("rb") as photo:
        bot.call("setMyProfilePhoto", {"photo": json.dumps({"type": "static", "photo": "attach://avatar"})},
                 {"avatar": photo})
    print(f"Bot profile updated: {args.name} (@{identity['username']})")


def bootstrap(config, db, r2):
    if db.query("SELECT id FROM installation") or r2.get("sync/installation.json", optional=True):
        raise SyncError("Installation already exists or is incomplete; inspect/restore instead of resetting")
    if db.query("SELECT chat_id FROM targets LIMIT 1") or db.query("SELECT chat_id FROM history LIMIT 1"):
        raise SyncError("Storage is not empty; bootstrap refused")
    target = config.telegram_default_chat_id
    if target < 0:
        raise SyncError("Bootstrap requires a private default target; authorize groups using /addtarget")
    installation_id = uuid.uuid4().hex
    r2.put("sync/installation.json", json.dumps({"installation_id": installation_id}).encode(), create=True)
    db.query("INSERT INTO installation(id,installation_id) VALUES(1,?)", (installation_id,))
    db.query("INSERT INTO roles(user_id,role) VALUES(?,'owner')", (config.telegram_owner_id,))
    db.query("INSERT INTO targets(chat_id,type,initial_mode) VALUES(?,'user','all')", (target,))
    print("Installation created. Import a valid browser profile before enabling the schedule.")


def login(config, db, r2):
    if config.browser_headless:
        raise SyncError("Login needs BROWSER_HEADLESS=false and a visible desktop")
    history = History(db)
    r2.verify_installation(history.installation()["installation_id"])
    history.acquire()
    network = Network(config)
    browser = BrowserSession(config, r2)
    try:
        network.start()
        browser.r2 = r2 = R2(config, network.proxy_url)
        browser.proxy_url = network.proxy_url
        existing = r2.get(config.r2_profile_object, optional=True)
        browser.etag = existing[1] if existing else None
        browser.start()
        input("请在独立 Chromium 窗口中登录 Google 并打开 YouTube Music，完成后按回车：")
        browser.page.get("https://music.youtube.com/")
        if browser.detect_auth() != "VALID":
            raise SyncError("Login not verified; existing profile backup preserved")
        browser.close()
        browser.backup()
        print("Verified profile encrypted and uploaded")
    finally:
        browser.close()
        network.close()
        history.release()


def grant_admin(db, user_id, chat_ids):
    for chat_id in chat_ids:
        if not db.query("SELECT chat_id FROM targets WHERE chat_id=? AND removed=0", (chat_id,)):
            raise SyncError("Admin scope contains an unauthorized target")
    db.query("INSERT INTO roles(user_id,role) VALUES(?,'admin') ON CONFLICT(user_id) DO NOTHING", (user_id,))
    for chat_id in chat_ids:
        db.query("INSERT OR IGNORE INTO admin_targets(user_id,chat_id) VALUES(?,?)", (user_id, chat_id))
    print("Admin scope saved")


def reconcile(history, r2, args):
    records = history.records(args.chat_id)
    row = records.get(args.video_id)
    if not row or row["status"] != "pending":
        raise SyncError("Only pending records can be reconciled")
    key = receipt_key(args.chat_id, args.video_id)
    existing = r2.get(key, optional=True)
    if existing:
        history.sent(args.chat_id, args.video_id, json.loads(existing[0]))
    elif args.retry:
        history.failed(args.chat_id, args.video_id, "Owner checked Telegram and explicitly requested retry")
    else:
        receipt = receipt_data(args.mode, args.sent_message_id)
        r2.put(key, json.dumps(receipt).encode(), create=True)
        history.sent(args.chat_id, args.video_id, receipt)
    print("Pending record reconciled")



def rotate_profile_key(config, db, r2):
    import hashlib
    import os
    from cryptography.fernet import Fernet
    old_key = os.environ.get("PROFILE_PREVIOUS_ENCRYPTION_KEY")
    if not old_key:
        raise SyncError("PROFILE_PREVIOUS_ENCRYPTION_KEY is required during rotation")
    history = History(db)
    r2.verify_installation(history.installation()["installation_id"])
    history.acquire()
    try:
        encrypted, etag, metadata = r2.get(config.r2_profile_object)
        raw = Fernet(old_key.encode()).decrypt(encrypted)
        if metadata.get("sha256") != hashlib.sha256(raw).hexdigest():
            raise SyncError("Profile integrity check failed")
        r2.versioned_put(config.r2_profile_object, Fernet(config.profile_encryption_key.encode()).encrypt(raw), etag, metadata)
        print("Profile key rotated; retain the old key for historical backup recovery")
    finally:
        history.release()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(str(error) if isinstance(error, SyncError) else "Management failed; sensitive output suppressed", file=sys.stderr)
        sys.exit(1)
