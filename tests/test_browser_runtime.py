import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path('src').resolve()))
from browser_session import BrowserSession
from cryptography.fernet import Fernet


@unittest.skipUnless(os.getenv('TGMUSIC_BROWSER_TEST') == 'true', 'headed browser runs in remote CI')
class BrowserRuntimeTests(unittest.TestCase):
    def test_headed_browser_encrypted_profile_roundtrip(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header('Content-Type','text/html')
                self.end_headers()
                self.wfile.write(b"<html><script>window.ytcfg={get:k=>({LOGGED_IN:true,INNERTUBE_CONTEXT:{client:{}}})[k]};</script>Test origin</html>")
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread = threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        class ArchiveStore:
            def versioned_put(self,key,data,etag,metadata):
                self.value=(data,'new-etag',metadata)
                return 'new-etag'
            def get(self,key):
                return self.value
        store=ArchiveStore()
        browser=None
        try:
            with tempfile.TemporaryDirectory() as root:
                config=SimpleNamespace(profile_encryption_key=Fernet.generate_key().decode(),
                    r2_profile_object='profile', browser_user_data_path=Path(root)/'first',
                    browser_ini_path='config/browser.ini', browser_path='/usr/bin/google-chrome',
                    browser_headless=False)
                origin=f'http://127.0.0.1:{server.server_port}/'
                browser=BrowserSession(config,store)
                browser.start(origin)
                self.assertFalse(browser.page.run_js("return navigator.userAgent.includes('HeadlessChrome')"))
                self.assertEqual(browser.detect_auth(),'VALID')
                browser.page.run_js("document.cookie='tgmusic_test=persistent; Max-Age=3600; Path=/'")
                browser.close()
                browser.backup()
                self.assertNotIn(b'tgmusic_test',store.value[0])
                config.browser_user_data_path=Path(root)/'restored'
                browser=BrowserSession(config,store)
                browser.restore()
                browser.start(origin)
                self.assertIn('tgmusic_test=persistent',browser.page.run_js('return document.cookie'))
                browser.page.run_js("window.ytcfg.get=k=>({LOGGED_IN:false,INNERTUBE_CONTEXT:{client:{}}})[k]")
                self.assertEqual(browser.detect_auth(),'EXPIRED')
                browser.page.run_js('window.ytcfg=undefined')
                self.assertEqual(browser.detect_auth(),'UNKNOWN')
                browser.close()
        finally:
            if browser:browser.close()
            server.shutdown()
            server.server_close()
            thread.join()
