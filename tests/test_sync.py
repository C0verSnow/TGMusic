import sys
import unittest
from unittest.mock import patch
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path('src').resolve()))
from history import History
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
        self.addCleanup(self.db.connection.close)
        self.history = History(self.db)
        self.history.acquire()
        self.r2 = MemoryR2()
        self.sender = Sender()
        self.config = SimpleNamespace(sync_max_songs=20)
        self.resolver = SimpleNamespace(resolve=lambda *args: None)
        self.songs = [Song(letter * 11, letter, 'Artist') for letter in 'ABCD']
        self.target(123)
        for index, song in enumerate(self.songs[:2], 1):
            self.history.pending(123, song)
            self.history.sent(123, song.video_id, {'mode': 'link', 'message_id': index, 'sent_at': '2026-11-13T00:00:00Z'})

    def target(self, chat_id, mode='baseline'):
        self.db.query('INSERT INTO targets(chat_id,type,send_mode,initial_mode) VALUES(?,?,?,?)',
                      (chat_id, 'group' if chat_id < 0 else 'user', 'link', mode))

    def run_sync(self, songs):
        return sync_targets(self.history, self.r2, self.sender, self.resolver, songs, self.config)

    def test_sent_a_b_then_only_c_and_no_repeat(self):
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

    def test_targets_are_independent_and_new_target_sends_missing_songs(self):
        self.run_sync(self.songs[:2])
        self.target(-100)
        self.run_sync(self.songs[:3])
        self.assertEqual(set(self.sender.sent), {(-100, letter * 11) for letter in 'ABC'} | {(123, 'C' * 11)})
        self.sender.rejected.add((-100, 'D' * 11))
        self.run_sync(self.songs)
        self.assertIn((123, 'D' * 11), self.sender.sent)
        self.assertEqual(self.history.records(-100)['D' * 11]['status'], 'failed')

    def test_all_mode_and_global_budget(self):
        self.db.query("UPDATE targets SET initial_mode='all' WHERE chat_id=123")
        self.config.sync_max_songs = 1
        first = self.run_sync(self.songs[2:])
        self.assertEqual(first['remaining'], 1)
        self.assertEqual(first['success'], 1)
        second = self.run_sync(self.songs[2:])
        self.assertEqual(second['remaining'], 0)
        self.assertEqual(self.sender.sent, [(123, 'C' * 11), (123, 'D' * 11)])

    def test_timeout_holds_pending_without_retry(self):
        self.run_sync(self.songs[:2])
        self.sender.uncertain.add((123, 'C' * 11))
        self.assertEqual(self.run_sync(self.songs[:3])['held'], 1)
        self.sender.uncertain.clear()
        self.assertEqual(self.run_sync(self.songs[:3])['held'], 1)
        self.assertEqual(self.sender.sent, [])

    def test_expired_deadline_keeps_unsent_songs_in_remaining(self):
        result = sync_targets(self.history, self.r2, self.sender, self.resolver,
                              self.songs, self.config, deadline=-1)
        self.assertEqual(result['remaining'], 2)
        self.assertEqual(result['success'], 0)
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
        self.assertEqual(self.run_sync(self.songs[:3])['remaining'], 0)

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

    def test_legacy_baseline_is_unsent_and_is_backfilled_once(self):
        song = self.songs[2]
        self.db.query("INSERT INTO history(chat_id,video_id,title,artist,status) VALUES(123,?,?,?,'baseline')",
                      (song.video_id, song.title, song.artist))
        before = self.history.export(self.songs, [123]).decode()
        self.assertIn('| CCCCCCCCCCC | C | Artist | 未发送 |', before)
        self.run_sync(self.songs[:3])
        self.run_sync(self.songs[:3])
        self.assertEqual(self.sender.sent, [(123, song.video_id)])
        after = self.history.export(self.songs, [123]).decode()
        self.assertIn('| CCCCCCCCCCC | C | Artist | 已发送 | link | 1 |', after)

    def test_latest_includes_unsent_budget_skips_failures_and_pending(self):
        self.config.sync_max_songs = 1
        self.sender.rejected.add((123, 'C' * 11))
        result = self.run_sync(self.songs)
        self.assertEqual(result['remaining'], 2)
        text = self.history.export(self.songs, [123]).decode()
        self.assertIn('| CCCCCCCCCCC | C | Artist | 发送失败 |', text)
        self.assertIn('| DDDDDDDDDDD | D | Artist | 未发送 |', text)
        self.sender.rejected.clear()
        self.sender.uncertain.add((123, 'C' * 11))
        self.run_sync(self.songs)
        self.assertIn('| CCCCCCCCCCC | C | Artist | 待核对 |', self.history.export(self.songs, [123]).decode())

    def test_latest_preserves_other_chat_records_and_escapes_song_text(self):
        self.target(-100)
        special = Song('E' * 11, 'Song | <b>\nnext', 'A & B')
        self.config.sync_max_songs = 1
        sync_targets(self.history, self.r2, self.sender, self.resolver,
                     [special], self.config, target_chat_ids={-100})
        text = self.history.export([special], [-100]).decode()
        self.assertIn('Song &#124; &lt;b&gt; next', text)
        self.assertIn('A &amp; B', text)
        self.assertIn('| AAAAAAAAAAA | A | Artist | 已发送 |', text)
        self.assertEqual(text.count('EEEEEEEEEEE'), 1)
        self.assertIn('本次未核对歌单，仅保留已有记录', text)

    def test_songs_removed_from_playlist_remain_history_without_blocking_completion(self):
        self.db.query("INSERT INTO history(chat_id,video_id,title,artist,status) VALUES(123,?,'D','Artist','baseline')",
                      ('D' * 11,))
        self.assertEqual(self.run_sync(self.songs[:2])['remaining'], 0)
        text = self.history.export(self.songs[:2], [123]).decode()
        old = next(line for line in text.splitlines() if line.startswith('| DDDDDDDDDDD |'))
        self.assertTrue(old.endswith('| 否 |'))
        self.assertIn('| 未发送 |', old)
        self.assertIn('AAAAAAAAAAA', text)

    def test_scoped_sync_does_not_touch_other_targets(self):
        self.run_sync(self.songs[:2])
        self.target(-100)
        self.run_sync(self.songs[:2])
        self.sender.sent.clear()
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
        first = self.run_sync(self.songs[2:3])
        self.assertEqual(first['paused'], [-100])
        self.assertEqual(self.db.query('SELECT enabled FROM targets WHERE chat_id=-100')[0]['enabled'], 0)
        self.run_sync(self.songs[2:3])
        self.assertEqual(parent.sent, [(123, 'C' * 11)])

    def test_audio_target_upgrades_old_links_and_recovers_new_audio_receipt(self):
        import json
        from history import receipt_key
        self.db.query("UPDATE targets SET send_mode='audio' WHERE chat_id=123")
        for song in self.songs[:2]:
            self.r2.put(receipt_key(123, song.video_id), json.dumps(
                {'mode': 'link', 'message_id': 99, 'sent_at': 'old'}).encode(), create=True)
        self.resolver = SimpleNamespace(resolve=lambda *args: Path('fixture.mp3'))
        parent = self.sender
        class AudioSender:
            def send_song(self, chat_id, song, audio):
                parent.send_song(chat_id, song, audio)
                return 'audio', len(parent.sent)
        self.sender = AudioSender()
        original = self.history.sent
        with patch.object(self.history, 'sent', side_effect=StorageError('D1 offline')):
            with self.assertRaises(StorageError):
                self.run_sync(self.songs[:1])
        self.history.sent = original
        self.assertEqual(self.run_sync(self.songs[:2])['remaining'], 0)
        self.assertEqual(parent.sent, [(123, song.video_id) for song in self.songs[:2]])
        self.run_sync(self.songs[:2])
        self.assertEqual(len(parent.sent), 2)
        self.assertTrue(all(row['delivery_mode'] == 'audio' for row in self.history.records(123).values()))

    def test_missing_audio_is_failed_without_sending_another_link(self):
        self.db.query("UPDATE targets SET send_mode='audio' WHERE chat_id=123")
        result = self.run_sync(self.songs[:3])
        self.assertEqual(self.sender.sent, [])
        self.assertEqual(result['failed'], 3)
        self.assertEqual(result['remaining'], 3)

    def test_old_link_receipt_cannot_complete_uncertain_audio_upgrade(self):
        import json
        from history import receipt_key
        self.db.query("UPDATE targets SET send_mode='audio' WHERE chat_id=123")
        song = self.songs[0]
        self.history.pending(123, song)
        self.r2.put(receipt_key(123, song.video_id), json.dumps(
            {'mode': 'link', 'message_id': 99, 'sent_at': 'old'}).encode(), create=True)
        result = self.run_sync([song])
        self.assertEqual(result['held'], 1)
        self.assertEqual(result['remaining'], 1)
        self.assertEqual(self.history.records(123)[song.video_id]['status'], 'pending')

    def test_rate_limit_stops_other_songs_and_targets_for_this_run(self):
        self.target(-100)
        calls = []
        class RateLimited:
            def send_song(self, chat_id, song, audio):
                calls.append((chat_id, song.video_id))
                raise SendRejected('rate limited', code=429)
        self.sender = RateLimited()
        result = self.run_sync(self.songs)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result['failed'], 1)
        self.assertEqual(result['remaining'], 6)
