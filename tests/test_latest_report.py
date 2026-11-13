import base64
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path('src').resolve()))
from latest_report import publish_latest
from models import StorageError


class LatestReportTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.previous_cwd = Path.cwd()
        os.chdir(self.directory.name)
        self.addCleanup(os.chdir, self.previous_cwd)
        self.existing = None
        self.write_status = 201
        self.calls = []
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                fixture.calls.append(('GET', self.path, self.headers.get('Authorization')))
                self.send_response(200 if fixture.existing else 404)
                self.end_headers()
                self.wfile.write(json.dumps(fixture.existing or {}).encode())

            def do_PUT(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                fixture.calls.append(('PUT', self.path, body))
                self.send_response(fixture.write_status)
                self.end_headers()
                self.wfile.write(b'{}')

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.environment = {'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': 'owner/repo',
                            'GITHUB_REF_NAME': 'feature/issue-7', 'GITHUB_REF_TYPE': 'branch',
                            'GITHUB_TOKEN': 'test-token'}
        self.env_patch = patch.dict(os.environ, self.environment, clear=True)
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        self.api_patch = patch('latest_report.API_URL', f'http://127.0.0.1:{self.server.server_port}')
        self.api_patch.start()
        self.addCleanup(self.api_patch.stop)

    def stop_server(self):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()

    def test_first_report_creates_only_docs_latest_on_running_branch(self):
        publish_latest(b'# Latest\n')
        self.assertEqual(Path('docs/latest.md').read_bytes(), b'# Latest\n')
        method, path, body = self.calls[-1]
        self.assertEqual((method, path), ('PUT', '/repos/owner/repo/contents/docs/latest.md'))
        self.assertEqual(body['branch'], 'feature/issue-7')
        self.assertEqual(base64.b64decode(body['content']), b'# Latest\n')
        self.assertNotIn('sha', body)
        self.assertIn('ref=feature%2Fissue-7', self.calls[0][1])
        self.assertEqual(self.calls[0][2], 'Bearer test-token')

    def test_update_uses_previous_sha_and_unchanged_report_skips_commit(self):
        self.existing = {'sha': 'old-sha', 'content': base64.b64encode(b'old').decode()}
        publish_latest(b'new')
        self.assertEqual(self.calls[-1][2]['sha'], 'old-sha')
        self.existing['content'] = base64.b64encode(b'new').decode()
        self.calls.clear()
        publish_latest(b'new')
        self.assertEqual(len(self.calls), 1)

    def test_conflict_or_denied_write_stops_without_force_or_retry(self):
        for status in [403, 409]:
            with self.subTest(status=status):
                self.write_status = status
                self.calls.clear()
                with self.assertRaises(StorageError):
                    publish_latest(b'new')
                self.assertEqual(len(self.calls), 2)

    def test_missing_token_or_nonbranch_is_rejected_before_http(self):
        for changes in [{'GITHUB_TOKEN': ''}, {'GITHUB_REF_TYPE': 'tag'}]:
            with patch.dict(os.environ, changes), self.assertRaises(StorageError):
                publish_latest(b'new')
        self.assertEqual(self.calls, [])

    def test_manual_local_export_only_writes_document(self):
        with patch.dict(os.environ, {'GITHUB_ACTIONS': 'false'}):
            publish_latest(b'local')
        self.assertEqual(Path('docs/latest.md').read_bytes(), b'local')
        self.assertEqual(self.calls, [])
