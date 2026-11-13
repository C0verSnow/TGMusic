import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path('src').resolve()))
from history import History, receipt_key
from models import Song, SendRejected, SendUncertain, StorageError
from sync import sync_targets
from support import SQLiteD1


class MemoryR2:
    def __init__(self):
        self.objects = {}

    def get(self, key, optional=False):
        data = self.objects.get(key)
        return (data, 'etag', {}) if data is not None else None

    def put(self, key, data, **kwargs):
        if kwargs.get('create') and key in self.objects:
            raise StorageError('conflict')
        self.objects[key] = data


class Sender:
    def __init__(self):
        self.sent = []
        self.rejected = set()
        self.uncertain = set()

    def send_song(self, chat_id, song, audio):
        key = (chat_id, song.video_id)
        if key in self.rejected:
            raise SendRejected('rejected')
        if key in self.uncertain:
            raise SendUncertain('unknown')
        self.sent.append(key)
        return 'link', len(self.sent)


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.db = SQLiteD1()
        self.history = History(self.db)
        self.history.acquire()
        self.r2 = MemoryR2()
        self.sender = Sender()
        self.config = SimpleNamespace(sync_max_songs=20)
        self.resolver = SimpleNamespace(resolve=lambda *args: None)
        self.songs = [Song(letter * 11, letter, 'Artist') for letter in 'ABCD']
        self.target(123)

    def target(self, chat_id, mode='baseline'):
        self.db.query('INSERT INTO targets(chat_id,type,send_mode,initial_mode) VALUES(?,?,?,?)',
                      (chat_id, 'group' if chat_id < 0 else 'user', 'link', mode))

    def run_sync(self, songs):
        return sync_targets(self.history, self.r2, self.sender, self.resolver, songs, self.config)

    def test_baseline_then_only_new_and_no_repeat(self):
        self.run_sync(self.songs[:2])
        self.assertEqual(self.sender.sent, [])
        self.run_sync(self.songs[:3])
        self.run_sync(self.songs[:3])
        self.assertEqual(self.sender.sent, [(123, 'C' * 11)])
        self.assertEqual(self.history.records(123)['C' * 11]['delivery_mode'], 'link')

    def test_failure_is_retried_without_resending_success(self):
        self.run_sync(self.songs[:2])
        self.sender.rejected.add((123, 'D' * 11))
        result = self.run_sync(self.songs)
        self.assertEqual(result['failed'], 1)
        self.assertEqual(self.history.records(123)['D' * 11]['status'], 'failed')
        self.sender.rejected.clear()
        self.run_sync(self.songs)
        self.assertEqual(self.sender.sent, [(123, 'C' * 11), (123, 'D' * 11)])

    def test_targets_are_independent_and_new_target_baselines(self):
        self.run_sync(self.songs[:2])
        self.target(-100)
        self.run_sync(self.songs[:3])
        self.assertEqual(self.sender.sent, [(123, 'C' * 11)])
        self.sender.rejected.add((-100, 'D' * 11))
        self.run_sync(self.songs)
        self.assertIn((123, 'D' * 11), self.sender.sent)
        self.assertEqual(self.history.records(-100)['D' * 11]['status'], 'failed')

    def test_all_mode_and_global_budget(self):
        self.db.query("UPDATE targets SET initial_mode='all' WHERE chat_id=123")
        self.config.sync_max_songs = 1
        self.run_sync(self.songs[:2])
        self.run_sync(self.songs[:2])
        self.assertEqual(self.sender.sent, [(123, 'A' * 11), (123, 'B' * 11)])

    def test_timeout_holds_pending_without_retry(self):
        self.run_sync(self.songs[:2])
        self.sender.uncertain.add((123, 'C' * 11))
        self.assertEqual(self.run_sync(self.songs[:3])['held'], 1)
        self.sender.uncertain.clear()
        self.assertEqual(self.run_sync(self.songs[:3])['held'], 1)
        self.assertEqual(self.sender.sent, [])

    def test_receipt_recovers_after_database_write_failure(self):
        self.run_sync(self.songs[:2])
        original = self.history.sent
        def unavailable(*args):
            raise StorageError('D1 unavailable')
        self.history.sent = unavailable
        with self.assertRaises(StorageError):
            self.run_sync(self.songs[:3])
        self.history.sent = original
        self.run_sync(self.songs[:3])
        self.assertEqual(self.sender.sent, [(123, 'C' * 11)])
        self.assertEqual(self.history.records(123)['C' * 11]['status'], 'sent')

    def test_lost_history_stops_instead_of_bulk_send(self):
        self.run_sync(self.songs[:2])
        self.db.query('DELETE FROM history WHERE video_id=?', ('A' * 11,))
        with self.assertRaises(StorageError):
            self.run_sync(self.songs)
        self.assertEqual(self.sender.sent, [])

    def test_lease_and_installation_missing(self):
        with self.assertRaises(StorageError):
            History(self.db).acquire()
        self.db.query('DELETE FROM installation')
        with self.assertRaises(StorageError):
            self.history.installation()

    def test_export_does_not_claim_baseline_as_sent(self):
        self.run_sync(self.songs[:2])
        text = self.history.export().decode()
        self.assertIn('baseline', text)
        self.assertNotIn('| sent |', text)

    def test_scoped_sync_does_not_touch_other_targets(self):
        self.run_sync(self.songs[:2])
        self.target(-100)
        self.run_sync(self.songs[:2])
        result = sync_targets(self.history, self.r2, self.sender, self.resolver,
                              self.songs[:3], self.config, target_chat_ids={-100})
        self.assertEqual(self.sender.sent, [(-100, 'C' * 11)])
        self.assertNotIn('C' * 11, self.history.records(123))

    def test_forbidden_target_is_paused_and_does_not_starve_other_targets(self):
        self.db.query("UPDATE targets SET initial_mode='all' WHERE chat_id=123")
        self.target(-100, 'all')
        parent = self.sender
        class ForbiddenGroup:
            def send_song(self, chat_id, song, audio):
                if chat_id == -100:
                    raise SendRejected('Telegram denied access', code=403)
                return parent.send_song(chat_id, song, audio)
        self.sender = ForbiddenGroup()
        self.config.sync_max_songs = 1
        first = self.run_sync(self.songs[:1])
        self.assertEqual(first['paused'], [-100])
        self.assertEqual(self.db.query('SELECT enabled FROM targets WHERE chat_id=-100')[0]['enabled'], 0)
        self.run_sync(self.songs[:1])
        self.assertEqual(parent.sent, [(123, 'A' * 11)])
