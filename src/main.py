import logging
import sys
import time

from audio_resolver import AudioResolver
from browser_session import BrowserSession
from cloudflare_storage import D1, R2
from config import Config
from history import History
from models import SyncError
from proxy import Network
from sync import sync_targets
from telegram_bot import TelegramBot
from utils import configure_logging, mask_actions_secrets
from youtube_client import CollectionError, YouTubeClient


def main():
    configure_logging()
    mask_actions_secrets()
    config = Config.load()
    network = Network(config)
    browser = None
    history = None
    leased = False
    telegram = TelegramBot(config.telegram_bot_token, network.session)
    try:
        logging.info("Sync started")
        db = D1(config)
        history = History(db)
        installation = history.installation()
        if (not is_manual()) and time.time() - installation["last_success"] < config.sync_interval_minutes * 60:
            logging.info("SYNC_INTERVAL_MINUTES has not elapsed")
            return 0
        history.acquire()
        leased = True
        r2 = R2(config)
        r2.verify_installation(installation["installation_id"])
        browser = BrowserSession(config, r2)
        browser.restore()
        session = network.start()
        db.session = session
        telegram.session = session
        r2 = R2(config, network.proxy_url)
        browser.r2 = r2
        browser.proxy_url = network.proxy_url
        youtube, songs = load_collection(config, browser, network, history)
        r2 = browser.r2
        logging.info("Fetched %d YouTube Music songs", len(songs))
        history.set_auth("VALID")
        resolver = AudioResolver(youtube, session, config)
        summary = sync_targets(history, r2, telegram, resolver, songs, config, time.monotonic() + 1200,
                               target_chat_ids=config.sync_target_chat_ids)
        history.assert_lease()
        export = r2.get("sync/latest.md", optional=True)
        r2.put("sync/latest.md", history.export(), etag=export[1] if export else None, create=export is None)
        browser.close()
        browser.backup()
        if config.sync_target_chat_ids is None:
            history.completed()
        if summary["held"] or summary["failed"]:
            telegram.notify(config.telegram_owner_id, f"TGMusic: {summary['failed']} 项失败，{summary['held']} 项结果待核对；暂停目标：{summary['paused']}。请查看 Actions 日志。")
            return 1
        return 0
    except Exception as error:
        message = str(error) if isinstance(error, SyncError) else type(error).__name__ + "; details suppressed"
        logging.error("%s", message)
        try:
            telegram.notify(config.telegram_owner_id, "TGMusic stopped: " + message)
        except Exception:
            logging.error("Owner notification unavailable")
        return 1
    finally:
        if browser:
            try:
                browser.cleanup()
            except Exception:
                logging.error("Browser cleanup failed; no profile uploaded")
        if history and leased:
            try:
                history.release()
            except Exception:
                logging.error("Lease release failed; will expire automatically")
        network.close()


def load_collection(config, browser, network, history):
    browser.start()
    state = browser.detect_auth()
    if state == "UNKNOWN" and can_use_fallback(config, network):
        logging.warning("Browser auth could not be determined on direct exit; trying Mihomo")
        switch_browser_exit(config, browser, network)
        state = browser.detect_auth()
    require_valid_auth(state, history)
    youtube = YouTubeClient(browser.page, network.session)
    try:
        songs = youtube.songs(config.youtube_playlist_id, config.youtube_reader)
    except CollectionError:
        if not can_use_fallback(config, network):
            raise
        logging.warning("YouTube API unavailable on direct exit; trying Mihomo")
        switch_browser_exit(config, browser, network)
        require_valid_auth(browser.detect_auth(), history)
        youtube = YouTubeClient(browser.page, network.session)
        songs = youtube.songs(config.youtube_playlist_id, config.youtube_reader)
    return youtube, songs


def can_use_fallback(config, network):
    return not network.proxy_url and config.mihomo_enabled == "auto"


def switch_browser_exit(config, browser, network):
    browser.close()
    network.enable_proxy()
    browser.proxy_url = network.proxy_url
    browser.r2 = R2(config, network.proxy_url)
    browser.start()


def require_valid_auth(state, history):
    if state == "VALID":
        return
    if state == "EXPIRED":
        history.set_auth(state)
    raise SyncError("Google auth " + state + "; sync stopped; existing backup preserved")


def is_manual():
    import os
    return os.getenv("GITHUB_EVENT_NAME", "workflow_dispatch") != "schedule"


if __name__ == "__main__":
    sys.exit(main())
