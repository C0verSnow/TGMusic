import html
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

    def pause_target(self, chat_id):
        self.db.query("UPDATE targets SET enabled=0 WHERE chat_id=?", (chat_id,))

    def records(self, chat_id):
        rows = self.db.query("SELECT * FROM history WHERE chat_id=?", (chat_id,))
        expected = self.db.query("SELECT history_count FROM targets WHERE chat_id=?", (chat_id,))[0]
        if len(rows) != expected["history_count"]:
            raise StorageError("History is incomplete; restore D1 instead of initializing")
        return {row["video_id"]: row for row in rows}

    def initialize_target(self, target):
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

    def export(self, songs=(), checked_chat_ids=()):
        lines = ["# Telegram 歌曲同步清单", "", "<!-- 由 History.export 自动生成，请勿手工修改。 -->", "",
                 "依据机器人发送成功记录与 Telegram 消息 ID 核对；不是完整聊天历史，也不检测消息被删除。",
                 "音频目标只有 audio 算完成，旧 link 会补音频；旧 baseline 算未发送，待核对项目不会自动重发。", "",
                 "清单生成时间（UTC）：" + utc_now(), ""]
        labels = {"sent": "已发送", "baseline": "未发送", "pending": "待核对", "failed": "发送失败"}
        playlist_ids = {song.video_id for song in songs}
        targets = self.db.query("SELECT * FROM targets WHERE removed=0 ORDER BY chat_id")
        for target in targets:
            chat_id = target["chat_id"]
            checked = chat_id in checked_chat_ids
            records = self.records(chat_id)
            entries = dict(records)
            if checked:
                for song in songs:
                    entries.setdefault(song.video_id, {**vars(song), "status": "baseline"})
            lines.extend([f"## 聊天 {chat_id}", "",
                          ("启用" if target["enabled"] else "暂停") + "；" +
                          ("本次已核对歌单" if checked else "本次未核对歌单，仅保留已有记录"), "",
                          "| video_id | 歌曲 | 歌手 | 发送状态 | 类型 | Telegram 消息 ID | 发送时间（UTC） | 本次歌单 |",
                          "|---|---|---|---|---|---|---|---|"])
            for video_id, row in sorted(entries.items()):
                values = (video_id, row["title"], row["artist"], ("待补音频" if row["status"] == "sent" and not delivery_complete(row, target["send_mode"])
                           else labels[row["status"]]),
                          row.get("delivery_mode"), row.get("message_id"), row.get("sent_at"),
                          ("是" if video_id in playlist_ids else "否") if checked else "未核对")
                lines.append("| " + " | ".join(markdown_cell(value) for value in values) + " |")
            lines.append("")
        if not targets:
            lines.append("暂无已授权目标。")
        return ("\n".join(lines) + "\n").encode()


def markdown_cell(value):
    return html.escape(str(value) if value is not None else "").replace("|", "&#124;").replace("\r", " ").replace("\n", " ")


def receipt_key(chat_id, video_id):
    return f"sync/receipts/{chat_id}/{video_id}.json"


def receipt_data(mode, message_id):
    return {"mode": mode, "message_id": message_id, "sent_at": utc_now()}


def delivery_complete(record, send_mode):
    return bool(record and record['status'] == 'sent' and
                (send_mode == 'link' or record['delivery_mode'] == 'audio'))
