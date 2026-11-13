import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import requests
sys.path.insert(0, str(Path('src').resolve()))
from proxy import Network
from models import SyncError


class ProxyTests(unittest.TestCase):
    def test_http_200_without_client_configuration_stays_direct(self):
        network = Network(SimpleNamespace(mihomo_enabled='auto', mihomo_config_yaml='',
                                          mihomo_proxy_url='http://127.0.0.1:1'))
        response = requests.Response()
        response.status_code = 200
        response._content = b'<html><body>YouTube Music</body></html>'
        try:
            with patch.object(network.session, 'get', return_value=response):
                self.assertIs(network.start(), network.session)
            self.assertIsNone(network.proxy_url)
            self.assertEqual(network.session.proxies, {})
        finally:
            network.close()

    def test_non_200_does_not_pass_connectivity_check(self):
        network = Network(SimpleNamespace(mihomo_enabled='false'))
        response = requests.Response()
        response.status_code = 503
        response._content = b'INNERTUBE_CONTEXT'
        try:
            with patch.object(network.session, 'get', return_value=response):
                with self.assertRaises(SyncError):
                    network.start()
            self.assertIsNone(network.proxy_url)
        finally:
            network.close()

    def test_failed_proxy_start_keeps_requests_bound_to_proxy(self):
        network = Network(SimpleNamespace(mihomo_proxy_url='http://127.0.0.1:1'))
        def unavailable():
            raise SyncError('proxy failed')
        network.start_mihomo = unavailable
        with self.assertRaises(SyncError): network.enable_proxy()
        self.assertEqual(network.session.proxies, {'http':'http://127.0.0.1:1','https':'http://127.0.0.1:1'})
        self.assertFalse(network.session.trust_env)
