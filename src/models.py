from dataclasses import dataclass


@dataclass(frozen=True)
class Song:
    video_id: str
    title: str
    artist: str
    duration: int = 0
    album: str = ""
    thumbnail: str = ""

    @property
    def url(self):
        return f"https://music.youtube.com/watch?v={self.video_id}"


class SyncError(RuntimeError):
    """An error whose message is safe to show in logs."""


class StorageError(SyncError):
    pass


class SendRejected(SyncError):
    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code


class SendUncertain(SyncError):
    pass
