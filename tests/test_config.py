import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path('src').resolve()))
from config import Config
from models import SyncError


class ConfigTests(unittest.TestCase):
    def environment(self):
        return dict(R2_ENDPOINT='https://r2.invalid', R2_BUCKET='bucket', R2_ACCESS_KEY_ID='key',
                    R2_SECRET_ACCESS_KEY='secret', CLOUDFLARE_ACCOUNT_ID='account',
                    CLOUDFLARE_D1_DATABASE_ID='database', CLOUDFLARE_API_TOKEN='cloudflare',
                    PROFILE_ENCRYPTION_KEY='encryption', TELEGRAM_BOT_TOKEN='telegram',
                    TELEGRAM_OWNER_ID='123', TELEGRAM_DEFAULT_CHAT_ID='123')

    def test_configuration_maps_secrets_and_defaults(self):
        with patch.dict(os.environ, self.environment(), clear=True):
            config = Config.load()
        self.assertEqual(config.telegram_bot_token, 'telegram')
        self.assertEqual(config.profile_encryption_key, 'encryption')
        self.assertEqual(config.cloudflare_api_token, 'cloudflare')
        self.assertEqual(config.sync_interval_minutes, 60)
        self.assertEqual(config.mihomo_enabled, 'auto')
        self.assertFalse(config.browser_headless)

    def test_invalid_input_is_rejected_at_entry(self):
        for overrides in [{'TELEGRAM_OWNER_ID':'name'}, {'SYNC_MAX_SONGS':'0'}, {'INITIAL_SYNC_MODE':'invalid'}]:
            with patch.dict(os.environ, {**self.environment(), **overrides}, clear=True):
                with self.assertRaises(SyncError): Config.load()
