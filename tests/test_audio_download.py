import io
import shutil
import sys
import tempfile
import threading
import unittest
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import requests

sys.path.insert(0, str(Path('src').resolve()))
from audio_resolver import AudioResolver


@unittest.skipUnless(shutil.which('ffmpeg'), 'actual download and conversion run in remote CI')
class AudioDownloadTests(unittest.TestCase):
    def setUp(self):
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(8000)
            audio.writeframes(b'\x00\x00' * 8000)
        content = buffer.getvalue()
        self.requests = []
        seen = self.requests

        class Handler(BaseHTTPRequestHandler):
            def do_HEAD(self):
                self.respond(False)

            def do_GET(self):
                self.respond(True)

            def respond(self, body):
                seen.append((self.path, self.headers.get('Cookie'), self.headers.get('User-Agent')))
                if self.path == '/missing.wav':
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header('Content-Type', 'audio/wav')
                if self.path != '/unknown.wav':
                    self.send_header('Content-Length', str(len(content)))
                self.end_headers()
                if body:
                    self.wfile.write(content)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.session = requests.Session()
        self.session.trust_env = False
        self.config = SimpleNamespace(audio_authorized_video_ids={'abcdefghijk'}, audio_quality='best', audio_format='mp3')
        self.youtube = SimpleNamespace(base_headers={'User-Agent': 'TGMusic-Audio-Test'},
                                       cookies=[{'name': 'fixture', 'value': 'yes', 'domain': '127.0.0.1',
                                                 'path': '/', 'secure': False}])
        self.resolver = AudioResolver(self.youtube, self.session, self.config)

    def tearDown(self):
        self.session.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def song(self, path='/source.wav'):
        return SimpleNamespace(video_id='abcdefghijk', url=f'http://127.0.0.1:{self.server.server_port}{path}')

    def test_real_yt_dlp_download_and_ffmpeg_conversion_preserve_cookie_and_user_agent(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.resolver.resolve(self.song(), directory)
            self.assertIsNotNone(result)
            self.assertEqual(result.suffix, '.mp3')
            self.assertGreater(result.stat().st_size, 0)
        self.assertTrue(self.requests)
        self.assertTrue(all(cookie == 'fixture=yes' and user_agent == 'TGMusic-Audio-Test'
                            for _, cookie, user_agent in self.requests))

    def test_unauthorized_sample_never_contacts_source(self):
        self.config.audio_authorized_video_ids = set()
        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(self.resolver.resolve(self.song(), directory))
        self.assertEqual(self.requests, [])

    def test_rejected_source_falls_back_without_producing_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(self.resolver.resolve(self.song('/missing.wav'), directory))
            self.assertEqual(list(Path(directory).glob('*.mp3')), [])

    def test_size_limit_covers_known_and_unknown_content_length(self):
        for path in ['/source.wav', '/unknown.wav']:
            with self.subTest(path=path), tempfile.TemporaryDirectory() as directory, \
                    patch('audio_resolver.MAX_AUDIO_BYTES', 128):
                self.assertIsNone(self.resolver.resolve(self.song(path), directory))
                self.assertEqual(list(Path(directory).glob('*.mp3')), [])

    def test_failed_explicit_proxy_does_not_fall_back_to_direct_download(self):
        self.session.proxies = {'https': 'http://127.0.0.1:1', 'http': 'http://127.0.0.1:1'}
        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(self.resolver.resolve(self.song(), directory))
        self.assertEqual(self.requests, [])
