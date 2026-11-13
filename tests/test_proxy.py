import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, str(Path('src').resolve()))
from proxy import Network
from models import SyncError


class ProxyTests(unittest.TestCase):
    def test_failed_proxy_start_keeps_requests_bound_to_proxy(self):
        network = Network(SimpleNamespace(mihomo_proxy_url='http://127.0.0.1:1'))
        def unavailable():
            raise SyncError('proxy failed')
        network.start_mihomo = unavailable
        with self.assertRaises(SyncError): network.enable_proxy()
        self.assertEqual(network.session.proxies, {'http':'http://127.0.0.1:1','https':'http://127.0.0.1:1'})
        self.assertFalse(network.session.trust_env)
