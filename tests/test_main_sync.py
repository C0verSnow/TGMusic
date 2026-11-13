import os
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path('src').resolve()))
from main import main
from models import Song
from support import SQLiteD1
from test_sync import MemoryR2, Sender


class MainSyncTests(unittest.TestCase):
    def test_scheduled_and_manual_runs_sync_after_recent_success_without_duplicates(self):
        db = SQLiteD1()
        r2 = MemoryR2()
        r2.verify_installation = Mock()
        sender = Sender()
        browser = Mock()
        browser.r2 = r2
        config = SimpleNamespace(telegram_bot_token='test', telegram_owner_id=123,
                                 sync_max_songs=20, sync_target_chat_ids=None,
                                 sync_interval_minutes=360)
        network = SimpleNamespace(session=object(), proxy_url=None, start=lambda: object(), close=lambda: None)
        songs = [Song('A' * 11, 'Old', 'Artist'), Song('B' * 11, 'New', 'Artist')]
        db.query("INSERT INTO targets(chat_id,type,initialized) VALUES(123,'user',1)")
        db.query("INSERT INTO history(chat_id,video_id,title,artist,status) VALUES(123,?,'Old','Artist','baseline')",
                 (songs[0].video_id,))
        db.query('UPDATE installation SET last_success=? WHERE id=1', (int(time.time()),))
        try:
            with patch('main.Config.load', return_value=config), patch('main.D1', return_value=db), \
                    patch('main.R2', return_value=r2), patch('main.Network', return_value=network), \
                    patch('main.BrowserSession', return_value=browser), \
                    patch('main.TelegramBot', return_value=sender), \
                    patch('main.AudioResolver', return_value=SimpleNamespace(resolve=lambda *args: None)), \
                    patch('main.load_collection', return_value=(object(), songs)):
                for event in ['schedule', 'workflow_dispatch']:
                    with patch.dict(os.environ, {'GITHUB_EVENT_NAME': event}):
                        self.assertEqual(main(), 0)
            self.assertEqual(sender.sent, [(123, songs[1].video_id)])
            self.assertEqual(browser.restore.call_count, 2)
            rows = db.query('SELECT status,message_id FROM history WHERE video_id=?', (songs[1].video_id,))
            self.assertEqual(rows, [{'status': 'sent', 'message_id': 1}])
            self.assertEqual(db.query('SELECT lease_until FROM installation')[0]['lease_until'], 0)
        finally:
            db.connection.close()
