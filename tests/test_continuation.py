import json
import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path('src').resolve()))
from continuation import queue_next_sync
from models import SyncError


class ContinuationTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.status = 204
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                fixture.calls.append((self.path, self.headers.get('Authorization'), body))
                self.send_response(fixture.status)
                self.end_headers()

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        environment = {'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': 'owner/repo',
                       'GITHUB_REF_NAME': 'feature/issue-9', 'GITHUB_REF_TYPE': 'branch', 'GITHUB_TOKEN': 'fixture'}
        env = patch.dict(os.environ, environment, clear=True)
        env.start()
        self.addCleanup(env.stop)
        api = patch('continuation.API_URL', f'http://127.0.0.1:{self.server.server_port}')
        api.start()
        self.addCleanup(api.stop)
        self.config = SimpleNamespace(sync_target_chat_ids=frozenset({-100, 123}), sync_reply_chat_id=-100)

    def stop_server(self):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()

    def test_dispatch_preserves_branch_scope_and_reply_chat(self):
        self.assertTrue(queue_next_sync(self.config))
        path, auth, body = self.calls[0]
        self.assertEqual(path, '/repos/owner/repo/actions/workflows/sync.yml/dispatches')
        self.assertEqual(auth, 'Bearer fixture')
        self.assertEqual(body, {'ref': 'feature/issue-9', 'inputs': {'operation': 'sync',
                         'target_chat_ids': '[-100, 123]', 'reply_chat_id': '-100'}})

    def test_global_scheduled_run_remains_global_with_owner_reply(self):
        self.config.sync_target_chat_ids = None
        self.config.sync_reply_chat_id = None
        self.assertTrue(queue_next_sync(self.config))
        self.assertEqual(self.calls[0][2]['inputs']['target_chat_ids'], '')
        self.assertEqual(self.calls[0][2]['inputs']['reply_chat_id'], '')

    def test_denied_or_uncertain_dispatch_is_not_retried(self):
        for status in [403, 500]:
            self.status = status
            self.calls.clear()
            with self.assertRaises(SyncError):
                queue_next_sync(self.config)
            self.assertEqual(len(self.calls), 1)

    def test_missing_token_or_tag_fails_before_network(self):
        for changes in [{'GITHUB_TOKEN': ''}, {'GITHUB_REF_TYPE': 'tag'}]:
            with patch.dict(os.environ, changes), self.assertRaises(SyncError):
                queue_next_sync(self.config)
        self.assertEqual(self.calls, [])

    def test_outside_actions_does_not_dispatch(self):
        with patch.dict(os.environ, {'GITHUB_ACTIONS': 'false'}):
            self.assertFalse(queue_next_sync(self.config))
        self.assertEqual(self.calls, [])
