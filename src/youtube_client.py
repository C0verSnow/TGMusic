import hashlib
import logging
import re
import time

import requests

from models import Song, SyncError


class CollectionError(SyncError):
    pass


class YouTubeClient:
    def __init__(self, page, session):
        self.session = session
        bootstrap = page.run_js("return {context:ytcfg.get('INNERTUBE_CONTEXT'),"
                                "key:ytcfg.get('INNERTUBE_API_KEY'), user:ytcfg.get('SESSION_INDEX') || '0'};")
        self.context = bootstrap["context"]
        self.api_key = bootstrap["key"]
        self.cookies = [cookie for cookie in page.cookies(all_domains=True, all_info=True)
                        if cookie.get("domain", "").lstrip(".") in {"youtube.com", "music.youtube.com"}]
        music_cookies = {c["name"]: c["value"] for c in self.cookies}
        self.sapisid = music_cookies.get("SAPISID") or music_cookies.get("__Secure-3PAPISID")
        if not self.sapisid or not self.context:
            raise SyncError("Google credentials unavailable")
        self.base_headers = {
            "Origin": "https://music.youtube.com", "Referer": "https://music.youtube.com/",
            "User-Agent": page.run_js("return navigator.userAgent"),
            "X-Goog-AuthUser": str(bootstrap["user"]),
            "X-Youtube-Client-Name": "67",
            "X-Youtube-Client-Version": self.context["client"]["clientVersion"],
            "Cookie": "; ".join(f"{key}={value}" for key, value in music_cookies.items()),
        }

    def headers(self):
        timestamp = str(int(time.time()))
        signature = hashlib.sha1(f"{timestamp} {self.sapisid} https://music.youtube.com".encode()).hexdigest()
        return {**self.base_headers, "Authorization": f"SAPISIDHASH {timestamp}_{signature}"}

    def request(self, endpoint, payload):
        try:
            response = self.session.post(f"https://music.youtube.com/youtubei/v1/{endpoint}",
                                         params={"key": self.api_key, "prettyPrint": "false"},
                                         headers=self.headers(), json={"context": self.context, **payload}, timeout=40)
            response.raise_for_status()
            data = response.json()
            if "error" in data:
                raise CollectionError("YouTube API rejected request")
            return data
        except (requests.RequestException, ValueError):
            raise CollectionError("YouTube request failed") from None

    def songs(self, playlist_id, reader="innertube"):
        if reader == "ytmusicapi":
            return self.fallback_songs(playlist_id)
        try:
            return self.innertube_songs(playlist_id)
        except CollectionError:
            logging.warning("Innertube list unavailable; trying ytmusicapi with the same browser credentials")
            return self.fallback_songs(playlist_id)

    def innertube_songs(self, playlist_id):
        browse_id = playlist_id if playlist_id.startswith("VL") else "VL" + playlist_id
        payload = {"browseId": browse_id}
        songs = {}
        seen_tokens = set()
        for _ in range(500):
            data = self.request("browse", payload)
            items, token = playlist_page(data)
            for item in items:
                song = parse_song(item)
                if song:
                    songs[song.video_id] = song
            if not token:
                return list(songs.values())
            if token in seen_tokens:
                raise CollectionError("YouTube continuation repeated; partial list discarded")
            seen_tokens.add(token)
            payload = {"continuation": token}
        raise CollectionError("YouTube pagination incomplete; partial list discarded")

    def fallback_songs(self, playlist_id):
        from ytmusicapi import YTMusic
        try:
            client = YTMusic(auth={key.lower(): value for key, value in self.headers().items()},
                             requests_session=self.session)
            result = client.get_playlist(playlist_id.removeprefix("VL"), limit=None)
            songs = {}
            for row in result["tracks"]:
                if not row.get("videoId"):
                    logging.warning("Skipped playlist item without videoId")
                    continue
                song = Song(row["videoId"], row.get("title") or "Unknown title",
                            ", ".join(artist["name"] for artist in row.get("artists", [])) or "Unknown artist",
                            row.get("duration_seconds") or 0,
                            (row.get("album") or {}).get("name", ""),
                            (row.get("thumbnails") or [{}])[-1].get("url", ""))
                songs[song.video_id] = song
            return list(songs.values())
        except Exception:
            raise CollectionError("Both YouTube list readers failed; no state changed") from None

    def player(self, video_id):
        return self.request("player", {"videoId": video_id, "contentCheckOk": True, "racyCheckOk": True})


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def playlist_page(data):
    for name in ("musicPlaylistShelfRenderer", "musicShelfRenderer"):
        for node in walk(data.get("contents", {})):
            if name in node:
                shelf = node[name]
                return shelf.get("contents", []), continuation(shelf)
    for node in walk(data.get("continuationContents", {})):
        for name in ("musicPlaylistShelfContinuation", "musicShelfContinuation"):
            if name in node:
                shelf = node[name]
                return shelf.get("contents", []), continuation(shelf)
    for action in data.get("onResponseReceivedActions", []) + data.get("onResponseReceivedEndpoints", []):
        append = action.get("appendContinuationItemsAction")
        if append is not None:
            items = append.get("continuationItems", [])
            return items, continuation({"contents": items})
    raise CollectionError("YouTube playlist response unrecognized; refusing an empty baseline")


def continuation(shelf):
    for node in walk(shelf.get("continuations", [])):
        if "nextContinuationData" in node:
            return node["nextContinuationData"].get("continuation")
    for item in shelf.get("contents", []):
        renderer = item.get("continuationItemRenderer", {})
        endpoint = renderer.get("continuationEndpoint", {})
        token = endpoint.get("continuationCommand", {}).get("token")
        if token:
            return token
    return None


def parse_song(item):
    row = item.get("musicResponsiveListItemRenderer")
    if row is None:
        return None
    columns = [column["musicResponsiveListItemFlexColumnRenderer"].get("text", {}).get("runs", [])
               for column in row.get("flexColumns", [])]
    title_runs = columns[0] if columns else []
    video_id = row.get("playlistItemData", {}).get("videoId")
    if not video_id:
        for node in walk(title_runs + [row.get("overlay", {})]):
            video_id = node.get("watchEndpoint", {}).get("videoId")
            if video_id:
                break
    if not video_id or not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        logging.warning("Skipped playlist item without a valid videoId")
        return None
    artists, album = [], ""
    for runs in columns[1:]:
        for run in runs:
            browse = run.get("navigationEndpoint", {}).get("browseEndpoint", {}).get("browseId", "")
            if browse.startswith("UC"):
                artists.append(run.get("text", ""))
            elif browse.startswith("MPRE"):
                album = run.get("text", "")
    duration = 0
    for node in walk(row.get("fixedColumns", [])):
        text = node.get("text")
        if isinstance(text, str) and re.fullmatch(r"\d+(?::\d{2}){1,2}", text):
            duration = 0
            for part in text.split(":"):
                duration = duration * 60 + int(part)
            break
    thumbnails = row.get("thumbnail", {}).get("musicThumbnailRenderer", {}).get("thumbnail", {}).get("thumbnails", [])
    return Song(video_id, "".join(run.get("text", "") for run in title_runs) or "Unknown title",
                ", ".join(artists) or "Unknown artist", duration, album,
                thumbnails[-1]["url"] if thumbnails else "")
