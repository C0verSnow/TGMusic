import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path('src').resolve()))
from main import load_collection
from models import SyncError


class CollectionFlowTests(unittest.TestCase):
    def config(self):
        return SimpleNamespace(mihomo_enabled='auto', youtube_playlist_id='LM', youtube_reader='innertube')

    def test_unknown_browser_retries_once_with_proxy_before_fetching(self):
        browser = Mock()
        browser.detect_auth.side_effect = ['UNKNOWN', 'VALID']
        network = SimpleNamespace(proxy_url=None, session=object())
        def enable(): network.proxy_url = 'http://127.0.0.1:7890'
        network.enable_proxy = Mock(side_effect=enable)
        history = Mock()
        with patch('main.R2'), patch('main.YouTubeClient') as client:
            client.return_value.songs.return_value = []
            load_collection(self.config(), browser, network, history)
        network.enable_proxy.assert_called_once()
        self.assertEqual(browser.start.call_count, 2)
        history.set_auth.assert_not_called()

    def test_expired_login_does_not_switch_exit_or_fetch(self):
        browser = Mock()
        browser.detect_auth.return_value = 'EXPIRED'
        network = SimpleNamespace(proxy_url=None, session=object(), enable_proxy=Mock())
        history = Mock()
        with patch('main.YouTubeClient') as client:
            with self.assertRaises(SyncError): load_collection(self.config(), browser, network, history)
        client.assert_not_called()
        network.enable_proxy.assert_not_called()
        history.set_auth.assert_called_once_with('EXPIRED')
