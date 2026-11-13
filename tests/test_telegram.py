import json
import tempfile
from unittest.mock import patch
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
        self.now = 0
        self.clock = patch('telegram_bot.time.monotonic', lambda: self.now)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.bot = TelegramBot('test-token', sleep=self.advance)
        self.bot.url = f'http://127.0.0.1:{self.server.server_port}/'

    def advance(self, delay):
        self.delays.append(delay)
        self.now += delay

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def test_retry_after_and_multipart_rewind(self):
        import io
        self.responses = [(429, {'ok': False, 'error_code': 429, 'parameters': {'retry_after': 2}}),
                          (200, {'ok': True, 'result': {'message_id': 4}})]
        self.assertEqual(self.bot.call('sendAudio', {'chat_id': 123}, {'audio': io.BytesIO(b'actual-audio')})['message_id'], 4)
        self.assertEqual(self.delays, [30])
        self.assertTrue(all(b'actual-audio' in body for body in self.requests))

    def test_explicit_failure_and_unknown_result(self):
        self.responses = [(403, {'ok': False, 'error_code': 403})]
        with self.assertRaises(SendRejected): self.bot.call('sendMessage', {})
        self.responses = [(500, {'ok': False, 'error_code': 500})]
        with self.assertRaises(SendUncertain): self.bot.call('sendMessage', {})

    def test_connection_timeout_retries_before_request_was_sent(self):
        import requests
        class ConnectTwice(requests.Session):
            def __init__(self):
                super().__init__()
                self.attempts = 0
            def post(self, *args, **kwargs):
                self.attempts += 1
                if self.attempts < 3:
                    raise requests.ConnectTimeout()
                return super().post(*args, **kwargs)
        self.bot.session = ConnectTwice()
        self.responses = [(200, {'ok':True, 'result':{'message_id':9}})]
        self.assertEqual(self.bot.call('sendMessage', {})['message_id'], 9)
        self.assertEqual(self.now, 60)
        self.assertEqual(len(self.requests), 1)

    def test_song_uploads_and_following_notification_are_spaced_globally(self):
        from models import Song
        song = Song('abcdefghijk', 'Song', 'Artist')
        self.responses = [(200, {'ok': True, 'result': {'message_id': n}}) for n in range(3)]
        with tempfile.TemporaryDirectory() as directory:
            audio = Path(directory) / 'sample.mp3'
            audio.write_bytes(b'fixture-audio')
            self.assertEqual(self.bot.send_song(-100, song, audio), ('audio', 0))
            self.assertEqual(self.bot.send_song(123, song, audio), ('audio', 1))
        self.bot.notify(123, 'finished')
        self.assertEqual(self.delays, [30, 30])
        self.assertTrue(all(b'fixture-audio' in body for body in self.requests[:2]))

    def test_long_retry_after_is_obeyed_and_not_cut_to_sixty_seconds(self):
        self.responses = [(429, {'ok': False, 'error_code': 429, 'parameters': {'retry_after': 90}}),
                          (200, {'ok': True, 'result': {'message_id': 4}})]
        self.assertEqual(self.bot.call('sendAudio', {})['message_id'], 4)
        self.assertEqual(self.delays, [90])

    def test_exhausted_429_keeps_cooldown_for_next_request(self):
        self.responses = [(429, {'ok': False, 'error_code': 429, 'parameters': {'retry_after': 45}})] * 3
        with self.assertRaises(SendRejected) as caught:
            self.bot.call('sendAudio', {})
        self.assertEqual(caught.exception.code, 429)
        self.responses = [(200, {'ok': True, 'result': {'message_id': 4}})]
        self.bot.notify(123, 'rate limited')
        self.assertEqual(self.delays, [45, 45, 45])
