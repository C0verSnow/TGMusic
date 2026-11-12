import json
import time
import uuid

from models import StorageError
from utils import utc_now


class History:
    def __init__(self, db):
        self.db = db
        self.owner = uuid.uuid4().hex

    def installation(self):
        rows = self.db.query("SELECT * FROM installation WHERE id=1")
        if not rows:
            raise StorageError("Installation missing; use explicit bootstrap or restore D1")
        return rows[0]

    def acquire(self):
        rows = self.db.query(
            "UPDATE installation SET lease_owner=?, lease_until=? WHERE id=1 AND lease_until<? RETURNING id",
            (self.owner, int(time.time()) + 2100, int(time.time())))
        if not rows:
            raise StorageError("Another sync holds the lease")

    def assert_lease(self):
        rows = self.db.query("SELECT id FROM installation WHERE id=1 AND lease_owner=? AND lease_until>?",
                             (self.owner, int(time.time())))
        if not rows:
            raise StorageError("Sync lease expired")

    def release(self):
        self.db.query("UPDATE installation SET lease_owner=NULL, lease_until=0 WHERE id=1 AND lease_owner=?",
                      (self.owner,))

    def targets(self):
        return self.db.query("SELECT * FROM targets WHERE enabled=1 AND removed=0 ORDER BY chat_id")

    def records(self, chat_id):
        rows = self.db.query("SELECT * FROM history WHERE chat_id=?", (chat_id,))
        expected = self.db.query("SELECT history_count FROM targets WHERE chat_id=?", (chat_id,))[0]
        if len(rows) != expected["history_count"]:
            raise StorageError("History is incomplete; restore D1 instead of initializing")
        return {row["video_id"]: row for row in rows}

    def initialize_target(self, target, songs, mode):
        if mode == "baseline":
            # json_each keeps the entire baseline atomic without one request per song.
            self.db.query(
                "INSERT OR IGNORE INTO history(chat_id,video_id,title,artist,status) "
                "SELECT ?,json_extract(value,'$.video_id'),json_extract(value,'$.title'),"
                "json_extract(value,'$.artist'),'baseline' FROM json_each(?)",
                (target["chat_id"], json.dumps([vars(song) for song in songs])))
        self.db.query("UPDATE targets SET initialized=1 WHERE chat_id=?", (target["chat_id"],))

    def pending(self, chat_id, song):
        self.db.query(
            "INSERT INTO history(chat_id,video_id,title,artist,status,attempts) VALUES(?,?,?,?,'pending',1) "
            "ON CONFLICT(chat_id,video_id) DO UPDATE SET status='pending',attempts=attempts+1,error=NULL",
            (chat_id, song.video_id, song.title, song.artist))

    def failed(self, chat_id, video_id, reason):
        self.db.query("UPDATE history SET status='failed',error=? WHERE chat_id=? AND video_id=?",
                      (reason, chat_id, video_id))

    def sent(self, chat_id, video_id, receipt):
        self.db.query(
            "UPDATE history SET status='sent',delivery_mode=?,message_id=?,sent_at=?,error=NULL "
            "WHERE chat_id=? AND video_id=?",
            (receipt["mode"], receipt["message_id"], receipt["sent_at"], chat_id, video_id))

    def set_auth(self, state):
        self.db.query("UPDATE installation SET auth_state=? WHERE id=1", (state,))

    def completed(self):
        self.db.query("UPDATE installation SET last_success=? WHERE id=1", (int(time.time()),))

    def export(self):
        rows = self.db.query("SELECT chat_id,video_id,status,delivery_mode,sent_at FROM history ORDER BY chat_id,video_id")
        lines = ["# Telegram Sync History", "", "| chat_id | video_id | status | delivery_mode | sent_at |",
                 "|---------|----------|--------|---------------|---------|"]
        for row in rows:
            lines.append("| " + " | ".join(str(row[k] or "") for k in
                         ("chat_id", "video_id", "status", "delivery_mode", "sent_at")) + " |")
        return ("\n".join(lines) + "\n").encode()


def receipt_key(chat_id, video_id):
    return f"sync/receipts/{chat_id}/{video_id}.json"


def receipt_data(mode, message_id):
    return {"mode": mode, "message_id": message_id, "sent_at": utc_now()}
