import time

import requests

from models import SendRejected, SendUncertain


class TelegramBot:
    def __init__(self, token, session=None, sleep=time.sleep):
        self.url = f"https://api.telegram.org/bot{token}/"
        self.session = session or requests.Session()
        self.sleep = sleep

    def call(self, method, data, files=None):
        for attempt in range(3):
            if files:
                for value in files.values():
                    value.seek(0)
            try:
                response = self.session.post(self.url + method, data=data, files=files, timeout=(15, 120))
                result = response.json()
            except requests.ConnectTimeout:
                if attempt < 2:
                    self.sleep(attempt + 1)
                    continue
                raise SendRejected("Telegram connection timed out before sending") from None
            except (requests.RequestException, ValueError):
                # A timeout can happen after Telegram accepted the message. Hold for reconciliation.
                raise SendUncertain("Telegram result unknown; pending record held for review") from None
            if result.get("ok"):
                return result["result"]
            code = result.get("error_code", response.status_code)
            if code == 429 and attempt < 2:
                delay = int(result.get("parameters", {}).get("retry_after", 1))
                if delay > 60:
                    raise SendRejected("Telegram rate limit exceeds this run's retry budget")
                self.sleep(max(1, delay))
                continue
            if code >= 500:
                raise SendUncertain("Telegram server result unknown; pending record held for review")
            raise SendRejected(f"Telegram rejected request (code {code})")
        raise SendRejected("Telegram retry budget exhausted")

    def send_song(self, chat_id, song, audio=None):
        caption = f"{song.title}\n{song.artist}"
        if song.album:
            caption += f"\n{song.album}"
        caption = caption[:700] + "\n" + song.url
        if audio is None:
            result = self.call("sendMessage", {"chat_id": chat_id, "text": caption})
            return "link", result["message_id"]
        with audio.open("rb") as file:
            result = self.call("sendAudio", {"chat_id": chat_id, "title": song.title[:64],
                                             "performer": song.artist[:64], "duration": song.duration,
                                             "caption": caption}, {"audio": file})
        return "audio", result["message_id"]

    def notify(self, chat_id, text):
        self.call("sendMessage", {"chat_id": chat_id, "text": text[:4000]})
