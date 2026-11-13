import base64
import os
from pathlib import Path

import requests

from models import StorageError


API_URL = "https://api.github.com"


def publish_latest(data):
    path = Path("docs/latest.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    if os.getenv("GITHUB_ACTIONS") != "true":
        return
    repository, branch, token = github_settings()
    url = f"{API_URL}/repos/{repository}/contents/docs/latest.md"
    headers = {"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28"}
    try:
        response = requests.get(url, params={"ref": branch}, headers=headers, timeout=40)
        body = {"message": "docs: update Telegram song sync ledger", "branch": branch,
                "content": base64.b64encode(data).decode()}
        if response.status_code != 404:
            response.raise_for_status()
            previous = response.json()
            if base64.b64decode(previous["content"]) == data:
                return
            body["sha"] = previous["sha"]
        response = requests.put(url, headers=headers, json=body, timeout=40)
        response.raise_for_status()
    except (requests.RequestException, ValueError, KeyError):
        raise StorageError("docs/latest.md publication failed; delivery records preserved; sync not complete") from None


def github_settings():
    values = tuple(os.getenv(key) for key in ("GITHUB_REPOSITORY", "GITHUB_REF_NAME", "GITHUB_TOKEN"))
    if not all(values) or os.getenv("GITHUB_REF_TYPE") != "branch":
        raise StorageError("Publishing docs/latest.md requires a branch and GITHUB_TOKEN with contents: write")
    return values
