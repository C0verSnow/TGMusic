import hashlib
import io
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from cryptography.fernet import Fernet
sys.path.insert(0, str(Path('src').resolve()))
from browser_session import BrowserSession, archive_profile, profile_digest
from models import SyncError


class ProfileTests(unittest.TestCase):
    def test_complete_ini_and_profile_roundtrip_excludes_only_runtime_locks(self):
        with tempfile.TemporaryDirectory() as root:
            source = Path(root)/'source'
            (source/'Default'/'Cache').mkdir(parents=True)
            (source/'Default'/'Cookies').write_bytes(b'private-cookie')
            (source/'Default'/'Cache'/'data').write_text('cached')
            (source/'Empty directory').mkdir()
            (source/'SingletonLock').write_text('lock')
            (source/'DevToolsActivePort').write_text('runtime-port')
            ini = Path(root)/'original.ini'
            ini.write_bytes(b'[chromium_options]\narguments = []\n[custom]\nvalue = complete ini content\n')
            raw = archive_profile(source, ini, 'Chromium test')
            with tarfile.open(fileobj=io.BytesIO(raw), mode='r:*') as archive:
                names = archive.getnames()
                self.assertIn('user-data/Default/Cache/data', names)
                self.assertIn('user-data/Empty directory', names)
                self.assertNotIn('user-data/SingletonLock', names)
                self.assertNotIn('user-data/DevToolsActivePort', names)
                self.assertEqual(archive.extractfile('config/browser.ini').read(), ini.read_bytes())
            key = Fernet.generate_key()
            metadata = {'schema':'2','sha256':hashlib.sha256(raw).hexdigest()}
            r2 = SimpleNamespace(get=lambda *args: (Fernet(key).encrypt(raw),'etag',metadata))
            destination = Path(root)/'destination'
            config = SimpleNamespace(profile_encryption_key=key.decode(), r2_profile_object='profile',
                                     browser_user_data_path=destination, browser_ini_path=str(ini))
            browser = BrowserSession(config,r2)
            try:
                browser.restore()
                self.assertEqual(profile_digest(source,ini),profile_digest(destination,browser.ini_path))
                self.assertEqual(browser.ini_path.read_bytes(),ini.read_bytes())
                self.assertEqual((destination/'Default'/'Cookies').read_bytes(),b'private-cookie')
                with self.assertRaises(SyncError): browser.backup()
                metadata['sha256']='corrupt'
                with self.assertRaises(SyncError): browser.restore()
            finally:
                browser.cleanup()
            self.assertFalse(destination.exists())
            self.assertTrue(ini.exists())

    def test_old_profile_archive_remains_readable(self):
        with tempfile.TemporaryDirectory() as root:
            source=Path(root)/'source'
            (source/'Default').mkdir(parents=True)
            (source/'Default'/'Cookies').write_bytes(b'legacy-cookie')
            buffer=io.BytesIO()
            with tarfile.open(fileobj=buffer,mode='w') as archive:
                archive.add(source/'Default',arcname='Default')
            raw=buffer.getvalue()
            key=Fernet.generate_key()
            ini=Path(root)/'browser.ini';ini.write_text('[chromium_options]\narguments = []\n')
            metadata={'schema':'1','sha256':hashlib.sha256(raw).hexdigest()}
            r2=SimpleNamespace(get=lambda *args:(Fernet(key).encrypt(raw),'etag',metadata))
            destination=Path(root)/'restored'
            browser=BrowserSession(SimpleNamespace(profile_encryption_key=key.decode(),r2_profile_object='profile',
                 browser_user_data_path=destination,browser_ini_path=str(ini)),r2)
            try:
                browser.restore()
                self.assertEqual((destination/'Default'/'Cookies').read_bytes(),b'legacy-cookie')
            finally:browser.cleanup()

    def test_ini_change_is_an_effective_profile_change(self):
        with tempfile.TemporaryDirectory() as root:
            directory=Path(root)/'profile';directory.mkdir()
            ini=Path(root)/'browser.ini';ini.write_text('original ini')
            before=profile_digest(directory,ini)
            ini.write_text('changed ini')
            self.assertNotEqual(before,profile_digest(directory,ini))
