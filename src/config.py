import os
from dataclasses import dataclass
from pathlib import Path

from models import SyncError


@dataclass(frozen=True)
class Config:
    r2_endpoint: str
    r2_bucket: str
    r2_access_key_id: str
    r2_secret_access_key: str
    cloudflare_account_id: str
    cloudflare_d1_database_id: str
    cloudflare_api_token: str
    profile_encryption_key: str
    telegram_bot_token: str
    telegram_owner_id: int
    telegram_default_chat_id: int
    browser_user_data_path: Path
    browser_ini_path: str
    browser_headless: bool
    browser_path: str
    r2_profile_object: str
    youtube_playlist_id: str
    youtube_reader: str
    initial_sync_mode: str
    sync_max_songs: int
    sync_interval_minutes: int
    audio_authorized_video_ids: frozenset
    audio_format: str
    audio_quality: str
    mihomo_enabled: str
    mihomo_config_yaml: str
    mihomo_config_path: Path
    mihomo_proxy_url: str
    mihomo_controller_url: str
    mihomo_select_group: str
    mihomo_us_node: str

    @classmethod
    def load(cls):
        required = ["R2_ENDPOINT", "R2_BUCKET", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY",
                    "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_D1_DATABASE_ID", "CLOUDFLARE_API_TOKEN",
                    "PROFILE_ENCRYPTION_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_OWNER_ID",
                    "TELEGRAM_DEFAULT_CHAT_ID"]
        missing = [key for key in required if not os.environ.get(key)]
        if missing:
            raise SyncError("Missing configuration: " + ", ".join(missing))
        mode = choice("INITIAL_SYNC_MODE", "baseline", {"baseline", "all"})
        reader = choice("YOUTUBE_READER", "innertube", {"innertube", "ytmusicapi"})
        proxy = choice("MIHOMO_ENABLED", "auto", {"auto", "true", "false"})
        audio_format = choice("AUDIO_FORMAT", "mp3", {"mp3", "m4a"})
        quality = choice("AUDIO_QUALITY", "best", {"best", "worst"})
        profile = Path(os.getenv("BROWSER_USER_DATA_PATH", "/tmp/youtube-sync/chrome-profile")).resolve()
        if profile == Path.home() or profile == Path("/"):
            raise SyncError("BROWSER_USER_DATA_PATH must be a dedicated directory")
        return cls(
            *(os.environ[key] for key in required[:9]),
            integer("TELEGRAM_OWNER_ID", positive=True), integer("TELEGRAM_DEFAULT_CHAT_ID"),
            profile, os.getenv("BROWSER_INI_PATH", "config/browser.ini"),
            choice("BROWSER_HEADLESS", "false", {"true", "false"}) == "true",
            os.getenv("BROWSER_PATH", "/usr/bin/google-chrome"),
            os.getenv("R2_PROFILE_OBJECT", "auth/google-profile.tar.enc"),
            os.getenv("YOUTUBE_PLAYLIST_ID", "LM"), reader, mode,
            integer("SYNC_MAX_SONGS", 20, positive=True),
            integer("SYNC_INTERVAL_MINUTES", 60, positive=True),
            frozenset(filter(None, os.getenv("AUDIO_AUTHORIZED_VIDEO_IDS", "").split(","))),
            audio_format, quality, proxy, os.getenv("MIHOMO_CONFIG_YAML", ""),
            Path(os.getenv("MIHOMO_CONFIG_PATH", "/tmp/mihomo/config.yaml")),
            os.getenv("MIHOMO_PROXY_URL", "http://127.0.0.1:7890"),
            os.getenv("MIHOMO_CONTROLLER_URL", "http://127.0.0.1:9090"),
            os.getenv("MIHOMO_SELECT_GROUP", ""), os.getenv("MIHOMO_US_NODE", ""),
        )


def integer(key, default=None, positive=False):
    try:
        value = int(os.environ.get(key, default))
    except (ValueError, TypeError):
        raise SyncError(f"{key} must be an integer") from None
    if value == 0 or (positive and value < 0):
        raise SyncError(f"{key} has an invalid value")
    return value


def choice(key, default, values):
    value = os.getenv(key, default).strip() or default
    if value not in values:
        raise SyncError(f"Invalid {key}")
    return value
