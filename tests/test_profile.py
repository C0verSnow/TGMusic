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
    def test_encrypted_roundtrip_and_excludes_runtime_files(self):
        with tempfile.TemporaryDirectory() as root:
            source = Path(root)/'source'
            (source/'Default').mkdir(parents=True)
            (source/'Default'/'Cookies').write_bytes(b'private-cookie')
            (source/'SingletonLock').write_text('lock')
            (source/'Default'/'Cache').mkdir()
            (source/'Default'/'Cache'/'data').write_text('cached')
            raw = archive_profile(source)
            with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
                self.assertEqual(archive.getnames(), ['Default/Cookies'])
            key = Fernet.generate_key()
            metadata = {'schema':'1','sha256':hashlib.sha256(raw).hexdigest()}
            r2 = SimpleNamespace(get=lambda *args: (Fernet(key).encrypt(raw),'etag',metadata))
            destination = Path(root)/'destination'
            config = SimpleNamespace(profile_encryption_key=key.decode(), r2_profile_object='profile', browser_user_data_path=destination)
            browser = BrowserSession(config,r2)
            browser.restore()
            self.assertEqual(profile_digest(source),profile_digest(destination))
            self.assertEqual((destination/'Default'/'Cookies').read_bytes(),b'private-cookie')
            with self.assertRaises(SyncError): browser.backup()
            metadata['sha256']='corrupt'
            with self.assertRaises(SyncError): browser.restore()
