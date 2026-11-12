import logging
import os
import re
from datetime import datetime, timezone


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def configure_logging():
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    for name in ("urllib3", "botocore", "boto3", "DrissionPage"):
        logging.getLogger(name).setLevel(logging.CRITICAL)


def mask_actions_secrets():
    if os.getenv("GITHUB_ACTIONS") != "true":
        return
    for key, value in os.environ.items():
        if any(word in key.upper() for word in ("TOKEN", "SECRET", "KEY", "COOKIE", "CONFIG_YAML")):
            for line in value.splitlines():
                if line:
                    escaped = line.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
                    print(f"::add-mask::{escaped}", flush=True)


def safe_label(text):
    return re.sub(r"[\r\n\x00-\x1f]", " ", text)[:100]
