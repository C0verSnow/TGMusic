import os
import sys
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path('src').resolve()))
from main import main
from models import Song, StorageError
from support import SQLiteD1
from test_sync import MemoryR2, Sender


class MainSyncTests(unittest.TestCase):
    def setUp(self):
        self.db = SQLiteD1()
        self.addCleanup(self.db.connection.close)
        self.r2 = MemoryR2()
        self.r2.verify_installation = Mock()
        self.sender = Sender()
        self.sender.notify = Mock()
        self.browser = Mock()
        self.browser.r2 = self.r2
        self.config = SimpleNamespace(telegram_bot_token='test', telegram_owner_id=123,
                                      sync_max_songs=20, sync_target_chat_ids=None, sync_reply_chat_id=None)
        network = SimpleNamespace(session=object(), proxy_url=None, start=lambda: object(), close=lambda: None)
        self.songs = [Song(letter * 11, letter, 'Artist') for letter in 'ABC']
        self.db.query("INSERT INTO targets(chat_id,type,initialized,send_mode) VALUES(123,'user',1,'link')")
        self.db.query("INSERT INTO history(chat_id,video_id,title,artist,status,message_id,delivery_mode,sent_at) "
                      "VALUES(123,?,'A','Artist','sent',10,'link','2026-11-13T00:00:00Z')", (self.songs[0].video_id,))
        self.db.query("INSERT INTO history(chat_id,video_id,title,artist,status) VALUES(123,?,'B','Artist','baseline')",
                      (self.songs[1].video_id,))
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for name, value in [('Config.load', self.config), ('D1', self.db), ('R2', self.r2),
                            ('Network', network), ('BrowserSession', self.browser), ('TelegramBot', self.sender),
                            ('AudioResolver', SimpleNamespace(resolve=lambda *args: None)),
                            ('load_collection', (object(), self.songs))]:
            self.stack.enter_context(patch('main.' + name, return_value=value))
        self.publish = self.stack.enter_context(patch('main.publish_latest'))

    def test_scheduled_and_manual_runs_backfill_baseline_then_do_not_repeat(self):
        for event in ['schedule', 'workflow_dispatch']:
            with patch.dict(os.environ, {'GITHUB_EVENT_NAME': event}):
                self.assertEqual(main(), 0)
        self.assertEqual(self.sender.sent, [(123, song.video_id) for song in self.songs[1:]])
        self.assertEqual(self.browser.restore.call_count, 2)
        self.assertIn('| CCCCCCCCCCC | C | Artist | 已发送 |', self.r2.objects['sync/latest.md'].decode())
        self.assertEqual(self.publish.call_count, 2)
        self.assertGreater(self.db.query('SELECT last_success FROM installation')[0]['last_success'], 0)
        self.assertEqual(self.db.query('SELECT lease_until FROM installation')[0]['lease_until'], 0)
        self.assertTrue(all('同步完成' in call.args[1] for call in self.sender.notify.call_args_list))

    def test_budget_leaves_latest_unsent_and_never_marks_complete(self):
        self.config.sync_max_songs = 1
        self.assertEqual(main(), 1)
        self.assertEqual(self.db.query('SELECT last_success FROM installation')[0]['last_success'], 0)
        self.assertIn('| CCCCCCCCCCC | C | Artist | 未发送 |', self.publish.call_args.args[0].decode())
        self.assertIn('同步尚未完成', self.sender.notify.call_args.args[1])
        self.assertEqual(main(), 0)
        self.assertEqual(len(self.sender.sent), 2)

    def test_report_publication_failure_preserves_delivery_and_does_not_complete(self):
        self.publish.side_effect = StorageError('Publication failed')
        self.assertEqual(main(), 1)
        self.assertEqual(self.db.query('SELECT last_success FROM installation')[0]['last_success'], 0)
        self.assertNotIn('同步完成', self.sender.notify.call_args.args[1])
        self.publish.side_effect = None
        self.assertEqual(main(), 0)
        self.assertEqual(len(self.sender.sent), 2)

    def test_rejected_and_uncertain_deliveries_are_not_completion(self):
        self.sender.rejected.add((123, self.songs[1].video_id))
        self.sender.uncertain.add((123, self.songs[2].video_id))
        self.assertEqual(main(), 1)
        self.assertEqual(self.db.query('SELECT last_success FROM installation')[0]['last_success'], 0)
        report = self.publish.call_args.args[0].decode()
        self.assertIn('发送失败', report)
        self.assertIn('待核对', report)
        self.assertIn('同步尚未完成', self.sender.notify.call_args.args[1])

    def test_group_result_returns_to_origin_after_publication_and_backup(self):
        self.config.sync_target_chat_ids = frozenset({-100})
        self.config.sync_reply_chat_id = -100
        self.db.query("INSERT INTO targets(chat_id,type,send_mode) VALUES(-100,'group','link')")
        order = []
        self.publish.side_effect = lambda data: order.append('published')
        self.browser.backup.side_effect = lambda: order.append('backed_up')
        self.sender.notify.side_effect = lambda *args: order.append('notified')
        self.assertEqual(main(), 0)
        self.assertEqual(order, ['published', 'backed_up', 'notified'])
        self.assertEqual(self.sender.notify.call_args.args[0], -100)
        self.assertEqual(self.sender.sent, [(-100, song.video_id) for song in self.songs])
        self.assertEqual(self.db.query('SELECT last_success FROM installation')[0]['last_success'], 0)
        self.assertEqual(len(self.db.query('SELECT * FROM history WHERE chat_id=123')), 2)

    def test_disabled_requested_target_does_not_claim_completion(self):
        self.config.sync_target_chat_ids = frozenset({123})
        self.db.query('UPDATE targets SET enabled=0')
        self.assertEqual(main(), 1)
        self.assertEqual(self.sender.sent, [])
        self.assertIn('同步尚未完成', self.sender.notify.call_args.args[1])
