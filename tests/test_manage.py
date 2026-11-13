import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path('src').resolve()))
from manage import bootstrap
from models import SyncError
from support import SQLiteD1
from test_sync import MemoryR2


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.db = SQLiteD1()
        self.db.query('DELETE FROM installation')
        self.r2 = MemoryR2()
        self.config = SimpleNamespace(telegram_default_chat_id=123, telegram_owner_id=123,
                                      initial_sync_mode='baseline')

    def tearDown(self):
        self.db.connection.close()

    def test_bootstrap_matches_installation_and_creates_owner_and_baseline_target(self):
        bootstrap(self.config, self.db, self.r2)
        installation = self.db.query('SELECT installation_id FROM installation')[0]
        self.assertEqual(json.loads(self.r2.objects['sync/installation.json']), installation)
        self.assertEqual(self.db.query('SELECT user_id,role FROM roles'), [{'user_id': 123, 'role': 'owner'}])
        target = self.db.query('SELECT * FROM targets')[0]
        self.assertEqual(target['chat_id'], 123)
        self.assertEqual(target['initial_mode'], 'baseline')
        self.assertEqual(target['initialized'], 0)
        self.assertEqual(self.db.query('SELECT * FROM history'), [])
        with self.assertRaises(SyncError):
            bootstrap(self.config, self.db, self.r2)
        self.assertEqual(self.db.query('SELECT installation_id FROM installation'), [installation])

    def test_partial_installation_is_preserved(self):
        self.r2.put('sync/installation.json', b'{"installation_id":"existing"}', create=True)
        with self.assertRaises(SyncError):
            bootstrap(self.config, self.db, self.r2)
        self.assertEqual(self.r2.objects['sync/installation.json'], b'{"installation_id":"existing"}')
        self.assertEqual(self.db.query('SELECT * FROM installation'), [])

    def test_existing_target_prevents_bootstrap(self):
        self.db.query("INSERT INTO targets(chat_id,type) VALUES(123,'user')")
        with self.assertRaises(SyncError):
            bootstrap(self.config, self.db, self.r2)
        self.assertEqual(self.r2.objects, {})
        self.assertEqual(self.db.query('SELECT * FROM installation'), [])

    def test_group_default_is_rejected_before_writing(self):
        self.config.telegram_default_chat_id = -100
        with self.assertRaises(SyncError):
            bootstrap(self.config, self.db, self.r2)
        self.assertEqual(self.r2.objects, {})
        self.assertEqual(self.db.query('SELECT * FROM installation'), [])
