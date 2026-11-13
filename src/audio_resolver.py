import logging
import subprocess
from pathlib import Path

import requests

from models import SyncError

MAX_AUDIO_BYTES = 49_000_000


class AudioResolver:
    def __init__(self, youtube, session, config):
        self.youtube = youtube
        self.session = session
        self.config = config

    def resolve(self, song, directory):
        if song.video_id not in self.config.audio_authorized_video_ids:
            return None
        try:
            for attempt in range(2):
                data = self.youtube.player(song.video_id)
                if data.get("playabilityStatus", {}).get("status") != "OK":
                    return None
                stream = choose_stream(data, self.config.audio_quality)
                if stream is None:
                    return None
                source = Path(directory) / (song.video_id + ".source")
                try:
                    if not self.download(stream, source):
                        return None
                    return self.convert(source, directory, song.video_id)
                except requests.HTTPError as error:
                    if attempt == 0 and error.response.status_code in {403, 410}:
                        continue
                    return None
        except (requests.RequestException, SyncError, subprocess.SubprocessError, OSError):
            logging.warning("Audio unavailable; falling back to original link")
        return None

    def download(self, stream, path):
        if int(stream.get("contentLength", 0)) > MAX_AUDIO_BYTES:
            return False
        size = 0
        # Only media hosts receive stream requests; Google account cookies stay on music.youtube.com.
        with self.session.get(stream["url"], stream=True, timeout=60) as response:
            response.raise_for_status()
            with path.open("wb") as output:
                for chunk in response.iter_content(65536):
                    size += len(chunk)
                    if size > MAX_AUDIO_BYTES:
                        return False
                    output.write(chunk)
        return size > 0

    def convert(self, source, directory, video_id):
        target = Path(directory) / (video_id + "." + self.config.audio_format)
        codec = ["-c:a", "libmp3lame", "-b:a", "192k"] if self.config.audio_format == "mp3" else ["-c:a", "aac", "-b:a", "192k"]
        subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", str(source),
                        "-vn", *codec, str(target)], check=True, timeout=180,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return target if target.stat().st_size <= MAX_AUDIO_BYTES else None


def choose_stream(data, quality):
    formats = data.get("streamingData", {}).get("adaptiveFormats", [])
    candidates = [row for row in formats if row.get("mimeType", "").startswith("audio/")
                  and row.get("url", "").startswith("https://")]
    # Ciphered streams need a player implementation; never pretend they are downloadable URLs.
    if not candidates:
        return None
    return sorted(candidates, key=lambda row: row.get("bitrate", 0), reverse=quality == "best")[0]
