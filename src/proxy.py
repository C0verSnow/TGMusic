import logging
import os
import socket
import subprocess
import time
from urllib.parse import quote

import requests
import yaml

from models import SyncError


class Network:
    def __init__(self, config):
        self.config = config
        self.process = None
        self.runtime_config_written = False
        self.proxy_url = None
        self.session = requests.Session()
        self.session.trust_env = False

    def start(self):
        if self.config.mihomo_enabled != "true" and self.reachable():
            logging.info("Runner can reach YouTube Music directly")
            return self.session
        if self.config.mihomo_enabled == "false":
            raise SyncError("Runner cannot reach YouTube Music and Mihomo is disabled")
        self.enable_proxy()
        return self.session

    def enable_proxy(self):
        self.proxy_url = self.config.mihomo_proxy_url
        self.session.proxies = {"http": self.proxy_url, "https": self.proxy_url}
        self.start_mihomo()
        self.select_us_node()
        if not self.reachable():
            raise SyncError("Mihomo connectivity check failed; no direct fallback")
        logging.info("Mihomo US exit verified; explicit proxy remains mandatory for requests and Chromium")

    def reachable(self):
        try:
            response = self.session.get("https://music.youtube.com/", timeout=20)
            ready = "INNERTUBE_CONTEXT" in response.text
            if response.status_code != 200 or not ready:
                logging.warning("YouTube connectivity check: HTTP %d, page configuration present=%s",
                                response.status_code, ready)
            return response.status_code == 200 and ready
        except requests.RequestException as error:
            logging.warning("YouTube connectivity check: %s", type(error).__name__)
            return False

    def start_mihomo(self):
        if not self.config.mihomo_config_yaml:
            raise SyncError("YouTube is blocked; MIHOMO_CONFIG_YAML is required for fallback")
        if not os.path.exists("/dev/net/tun"):
            raise SyncError("TUN device unavailable")
        try:
            data = yaml.safe_load(self.config.mihomo_config_yaml)
            tun = data.get("tun", {})
            if not tun.get("enable") or tun.get("stack") != "mixed" or not tun.get("auto-route") or not tun.get("auto-detect-interface"):
                raise SyncError("Mihomo YAML requires TUN mixed/auto-route/auto-detect-interface")
            if data.get("mode", "rule").lower() != "rule" or not data.get("rules"):
                raise SyncError("Mihomo rule mode and rules are required")
        except (yaml.YAMLError, AttributeError):
            raise SyncError("Invalid MIHOMO_CONFIG_YAML") from None
        self.controller_headers = {"Authorization": f"Bearer {data.get('secret', '')}"}
        path = self.config.mihomo_config_path
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.write_text(self.config.mihomo_config_yaml)
        path.chmod(0o600)
        self.runtime_config_written = True
        self.process = subprocess.Popen(["sudo", "-n", "mihomo", "-d", str(path.parent), "-f", str(path)],
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                        start_new_session=True)
        controller = requests.Session()
        controller.trust_env = False
        self.controller = controller
        for _ in range(20):
            if self.process.poll() is not None:
                raise SyncError("Mihomo exited during startup")
            try:
                status = controller.get(self.config.mihomo_controller_url + "/version", headers=self.controller_headers, timeout=2)
                if status.ok:
                    break
            except requests.RequestException:
                pass
            time.sleep(1)
        else:
            raise SyncError("Mihomo controller unavailable")
        rules = controller.get(self.config.mihomo_controller_url + "/rules", headers=self.controller_headers, timeout=5)
        if not rules.ok or not rules.json().get("rules"):
            raise SyncError("Mihomo rules did not load")
        interface = tun.get("device", "Meta")
        if not os.path.exists("/sys/class/net/" + interface):
            raise SyncError("Mihomo TUN interface unavailable")
        socket.getaddrinfo("music.youtube.com", 443)
        routes = subprocess.run(["ip", "route", "show", "table", "all"], capture_output=True, text=True, check=True)
        if interface not in routes.stdout:
            raise SyncError("Mihomo TUN routes unavailable")

    def select_us_node(self):
        if not self.config.mihomo_select_group or not self.config.mihomo_us_node:
            raise SyncError("Set MIHOMO_SELECT_GROUP and MIHOMO_US_NODE to an explicit US node")
        url = self.config.mihomo_controller_url + "/proxies/" + quote(self.config.mihomo_select_group, safe="")
        try:
            response = self.controller.put(url, headers=self.controller_headers,
                                           json={"name": self.config.mihomo_us_node}, timeout=5)
            response.raise_for_status()
            selected = self.controller.get(url, headers=self.controller_headers, timeout=5).json()
            if selected.get("now") != self.config.mihomo_us_node:
                raise SyncError("Mihomo US selection not applied")
            probe = requests.Session()
            probe.trust_env = False
            probe.proxies = {"https": self.config.mihomo_proxy_url}
            response = probe.get("https://www.cloudflare.com/cdn-cgi/trace", timeout=15)
            response.raise_for_status()
            if "loc=US" not in response.text.splitlines():
                raise SyncError("Mihomo exit country is not US")
        except (requests.RequestException, ValueError):
            raise SyncError("Mihomo US exit verification failed") from None

    def close(self):
        if self.process and self.process.poll() is None:
            subprocess.run(["sudo", "-n", "kill", "-TERM", "--", f"-{self.process.pid}"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        if self.runtime_config_written and self.config.mihomo_config_path.exists():
            self.config.mihomo_config_path.unlink()
        self.session.close()
