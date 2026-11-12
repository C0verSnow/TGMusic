import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
sys.path.insert(0, str(Path('src').resolve()))
from telegram_bot import TelegramBot
from models import SendRejected, SendUncertain


class TelegramTests(unittest.TestCase):
    def setUp(self):
        self.responses = []
        self.requests = []
        parent = self
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                parent.requests.append(self.rfile.read(int(self.headers['Content-Length'])))
                status, body = parent.responses.pop(0)
                self.send_response(status)
                self.end_headers()
                self.wfile.write(json.dumps(body).encode())
            def log_message(self, *args):
                pass
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.delays = []
        self.bot = TelegramBot('test-token', sleep=self.delays.append)
        self.bot.url = f'http://127.0.0.1:{self.server.server_port}/'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def test_retry_after_and_multipart_rewind(self):
        import io
        self.responses = [(429, {'ok': False, 'error_code': 429, 'parameters': {'retry_after': 2}}),
                          (200, {'ok': True, 'result': {'message_id': 4}})]
        self.assertEqual(self.bot.call('sendAudio', {'chat_id': 123}, {'audio': io.BytesIO(b'actual-audio')})['message_id'], 4)
        self.assertEqual(self.delays, [2])
        self.assertTrue(all(b'actual-audio' in body for body in self.requests))

    def test_explicit_failure_and_unknown_result(self):
        self.responses = [(403, {'ok': False, 'error_code': 403})]
        with self.assertRaises(SendRejected): self.bot.call('sendMessage', {})
        self.responses = [(500, {'ok': False, 'error_code': 500})]
        with self.assertRaises(SendUncertain): self.bot.call('sendMessage', {})
