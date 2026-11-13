import json
import logging
import tempfile
import time

from history import delivery_complete, receipt_data, receipt_key
from models import SendRejected, SendUncertain
from utils import safe_label


def sync_targets(history, r2, telegram, resolver, songs, config, deadline=None, target_chat_ids=None):
    summary = {"total": len(songs), "already_sent": 0, "new": 0, "success": 0, "failed": 0,
               "held": 0, "remaining": 0, "paused": [], "targets": []}
    budget = config.sync_max_songs
    rate_limited = False
    for target in history.targets():
        chat_id = target["chat_id"]
        if target_chat_ids is not None and chat_id not in target_chat_ids:
            continue
        summary["targets"].append(chat_id)
        records = history.records(chat_id)
        if not target["initialized"]:
            history.initialize_target(target)
        for song in songs:
            previous = records.get(song.video_id)
            if delivery_complete(previous, target["send_mode"]):
                summary["already_sent"] += 1
                continue
            if previous and previous["status"] == "pending":
                receipt = r2.get(receipt_key(chat_id, song.video_id), optional=True)
                if receipt and (target["send_mode"] == "link" or json.loads(receipt[0])["mode"] == "audio"):
                    history.sent(chat_id, song.video_id, json.loads(receipt[0]))
                else:
                    summary["held"] += 1
                    logging.warning("Pending delivery held: %s / %s", chat_id, song.video_id)
                continue
            summary["new"] += 1
            if rate_limited or budget <= 0 or (deadline is not None and time.monotonic() >= deadline):
                continue
            history.assert_lease()
            budget -= 1
            with tempfile.TemporaryDirectory(prefix="tgmusic-audio-") as directory:
                audio = resolver.resolve(song, directory) if target["send_mode"] == "audio" else None
                if deadline is not None and time.monotonic() >= deadline:
                    continue
                history.assert_lease()
                old_receipt = r2.get(receipt_key(chat_id, song.video_id), optional=True)
                history.pending(chat_id, song)
                if target["send_mode"] == "audio" and audio is None:
                    history.failed(chat_id, song.video_id, "Audio unavailable; no link sent; retry required")
                    summary["failed"] += 1
                    continue
                logging.info("Sending %s to %s", safe_label(song.title), chat_id)
                try:
                    mode, message_id = telegram.send_song(chat_id, song, audio)
                except SendRejected as error:
                    history.failed(chat_id, song.video_id, str(error))
                    summary["failed"] += 1
                    logging.error("%s", error)
                    if error.code == 429:
                        rate_limited = True
                    if error.code == 403:
                        history.pause_target(chat_id)
                        summary["paused"].append(chat_id)
                        logging.error("Target %s paused after Telegram denied access; restore access and /enable", chat_id)
                        break
                    continue
                except SendUncertain:
                    summary["held"] += 1
                    logging.error("Telegram delivery uncertain: %s / %s; reconcile before retry", chat_id, song.video_id)
                    continue
                receipt = receipt_data(mode, message_id)
                r2.put(receipt_key(chat_id, song.video_id), json.dumps(receipt).encode(),
                       etag=old_receipt[1] if old_receipt else None, create=old_receipt is None)
                history.sent(chat_id, song.video_id, receipt)
                summary["success"] += 1
                logging.info("Sent %s (%s)", song.video_id, mode)
        records = history.records(chat_id)
        summary["remaining"] += sum(
            not delivery_complete(records.get(song.video_id), target["send_mode"]) for song in songs)
    logging.info("Sync summary: %s", summary)
    return summary
