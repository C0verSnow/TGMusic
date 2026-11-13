import json
import os

import requests

from models import SyncError


API_URL = "https://api.github.com"


def queue_next_sync(config):
    if os.getenv("GITHUB_ACTIONS") != "true":
        return False
    repository, branch, token = dispatch_settings()
    inputs = {"operation": "sync", "target_chat_ids":
              json.dumps(sorted(config.sync_target_chat_ids)) if config.sync_target_chat_ids is not None else "",
              "reply_chat_id": str(config.sync_reply_chat_id) if config.sync_reply_chat_id is not None else ""}
    try:
        response = requests.post(f"{API_URL}/repos/{repository}/actions/workflows/sync.yml/dispatches",
                                 headers={"Authorization": "Bearer " + token,
                                          "Accept": "application/vnd.github+json",
                                          "X-GitHub-Api-Version": "2022-11-28"},
                                 json={"ref": branch, "inputs": inputs}, timeout=40)
        response.raise_for_status()
    except requests.RequestException:
        # Dispatch may have reached GitHub even if its response was lost; do not blindly retry.
        raise SyncError("Could not confirm next sync was queued; check Actions before sending /sync again") from None
    return True


def dispatch_settings():
    values = tuple(os.getenv(key) for key in ("GITHUB_REPOSITORY", "GITHUB_REF_NAME", "GITHUB_TOKEN"))
    if not all(values) or os.getenv("GITHUB_REF_TYPE") != "branch":
        raise SyncError("Automatic continuation requires a branch and GITHUB_TOKEN with actions: write")
    return values
