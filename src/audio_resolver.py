import logging
import subprocess
from pathlib import Path

import requests
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

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
            source = self.download(song, directory)
            return self.convert(source, directory, song.video_id) if source else None
        except (DownloadError, SyncError, subprocess.SubprocessError, OSError):
            logging.warning("Audio unavailable; falling back to original link")
            return None

    def download(self, song, directory):
        options = {
            "format": "bestaudio/best" if self.config.audio_quality == "best" else "worstaudio/worst",
            "outtmpl": str(Path(directory) / (song.video_id + ".%(ext)s")),
            "noplaylist": True, "cachedir": False, "quiet": True, "no_warnings": True,
            "logger": logging.getLogger("yt_dlp"),
            "proxy": self.session.proxies.get("https", ""),
            "http_headers": {"User-Agent": self.youtube.base_headers["User-Agent"]},
            "js_runtimes": {"node": {}}, "remote_components": [],
            "max_filesize": MAX_AUDIO_BYTES, "progress_hooks": [limit_download],
            "socket_timeout": 60, "retries": 1, "fragment_retries": 1,
            "skip_unavailable_fragments": False,
        }
        # yt-dlp owns YouTube extraction; retain the restored browser's cookie domains.
        with YoutubeDL(options) as downloader:
            for cookie in self.youtube.cookies:
                downloader.cookiejar.set_cookie(requests.cookies.create_cookie(
                    cookie["name"], cookie["value"], domain=cookie["domain"],
                    path=cookie["path"], secure=cookie["secure"],
                    expires=cookie["expires"] if cookie.get("expires", -1) > 0 else None))
            result = downloader.extract_info(song.url, download=True)
            source = Path(downloader.prepare_filename(result))
        return source if source.is_file() else None

    def convert(self, source, directory, video_id):
        target = Path(directory) / (video_id + "." + self.config.audio_format)
        codec = ["-c:a", "libmp3lame", "-b:a", "192k"] if self.config.audio_format == "mp3" else ["-c:a", "aac", "-b:a", "192k"]
        subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", str(source),
                        "-vn", *codec, str(target)], check=True, timeout=180,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return target if target.stat().st_size <= MAX_AUDIO_BYTES else None


def limit_download(progress):
    if progress.get("downloaded_bytes", 0) > MAX_AUDIO_BYTES:
        raise DownloadError("Audio exceeds the download size limit")
