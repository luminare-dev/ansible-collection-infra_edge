"""Static checks of the nginx role: the input patterns that keep inventory values from adding
nginx or nftables directives, and the settings that the trust model depends on.

The Molecule scenario proves the behaviour on a host; these tests catch a loosened pattern or a
changed default before a scenario runs. The patterns are the ones assert.yml uses (Ansible's
"match" test is Python's re.match). They need PyYAML (requirements-test.txt).
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - only without the test requirements
    yaml = None

ROOT = Path(__file__).resolve().parent.parent
ROLE = ROOT / "roles" / "nginx"


def load_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@unittest.skipIf(yaml is None, "PyYAML is not installed (pip install -r requirements-test.txt)")
class NginxInputPatternTest(unittest.TestCase):
    def setUp(self):
        self.vars = load_yaml(ROLE / "vars" / "main.yml")

    def check(self, name: str, good: list[str], bad: list[str]):
        pattern = re.compile(self.vars[name])
        for value in good:
            self.assertTrue(pattern.match(value), f"{name} should accept {value!r}")
        for value in bad:
            self.assertFalse(pattern.match(value), f"{name} should refuse {value!r}")

    def test_site_listeners_stay_on_the_loopback_interface(self):
        self.check("nginx_loopback_listen_pattern",
                   ["127.0.0.1:8080", "127.0.0.2:80", "[::1]:8443"],
                   ["8080", "0.0.0.0:8080", "192.0.2.10:8080", "[::]:8080", "localhost:8080",
                    "127.0.0.1:8080 default_server", "127.0.0.1:8080;", "127.0.0.1"])

    def test_upstreams_are_plain_urls(self):
        self.check("nginx_upstream_url_pattern",
                   ["http://127.0.0.1:9000", "http://app.internal:3000/", "http://[::1]:3000/base/"],
                   ["https://127.0.0.1:9000", "127.0.0.1:9000", "http://127.0.0.1:9000;",
                    "http://127.0.0.1:9000 }", "http://a b", "http://x/$host", "http://x/'y'"])

    def test_relay_listeners_and_targets(self):
        self.check("nginx_stream_listen_pattern",
                   ["30120", "192.0.2.10:30120", "[2001:db8::1]:30120"],
                   ["30120 udp", "30120;", "host.example.com:30120", ""])
        self.check("nginx_upstream_address_pattern",
                   ["192.0.2.13:30120", "game.example.com:30120", "[2001:db8::13]:30120"],
                   ["192.0.2.13", "192.0.2.13:30120;", "192.0.2.13:30120 backup"])

    def test_names_and_server_names(self):
        self.check("nginx_name_pattern", ["demo", "lab-status", "api_v2"],
                   ["Demo", "../etc", "a b", "-x", ""])
        self.check("nginx_server_name_pattern",
                   ["demo.example.com", "*.example.com", "a.example.com b.example.com", "_"],
                   ["demo.example.com;", "a  b", "x{", ""])

    def test_addresses_sizes_and_times(self):
        self.check("nginx_cidr_pattern", ["127.0.0.1", "198.51.100.0/24", "::/0", "2001:db8::/32"],
                   ["127.0.0.1;", "unix:", "198.51.100.0/24 1", ""])
        self.check("nginx_size_pattern", ["16m", "1g", "512k", "1024"], ["16 m", "16mb", "-1"])
        self.check("nginx_time_pattern", ["1h", "60s", "500ms", "30"], ["1 h", "1h;", "h"])

    def test_header_names_and_values(self):
        self.check("nginx_header_name_pattern", ["X-Frame-Options", "Permissions-Policy"],
                   ["X Frame", "X-Frame:", ""])
        self.check("nginx_header_value_pattern",
                   ["SAMEORIGIN", "default-src 'self'; img-src *", "max-age=0"],
                   ['a"b', "a\\b", "$host", "a\nb", ""])


@unittest.skipIf(yaml is None, "PyYAML is not installed (pip install -r requirements-test.txt)")
class NginxTrustModelTest(unittest.TestCase):
    def setUp(self):
        self.defaults = load_yaml(ROLE / "defaults" / "main.yml")
        self.main_conf = (ROLE / "templates" / "nginx.conf.j2").read_text(encoding="utf-8")
        self.site = (ROLE / "templates" / "site.conf.j2").read_text(encoding="utf-8")

    def test_defaults(self):
        self.assertEqual(self.defaults["nginx_real_ip_from"], ["127.0.0.1"])
        self.assertEqual(self.defaults["nginx_real_ip_header"], "CF-Connecting-IP")
        self.assertEqual(self.defaults["nginx_server_tokens"], "off")
        self.assertIs(self.defaults["nginx_remove_default_site"], True)
        self.assertIs(self.defaults["nginx_stream_enabled"], False)
        # CONTRACT: a drop-in role writes its file only where /etc/nftables.d exists, unless told to.
        self.assertIs(self.defaults["nginx_firewall_manage"], False)
        headers = {name.lower() for name in self.defaults["nginx_security_headers"]}
        self.assertEqual(headers, {"x-content-type-options", "x-frame-options", "referrer-policy"})

    def test_client_address_is_not_taken_from_a_forwarded_list(self):
        self.assertIn("real_ip_recursive off;", self.main_conf)
        self.assertIn("server_tokens {{ nginx_server_tokens }};", self.main_conf)
        self.assertNotIn("$proxy_add_x_forwarded_for", self.site)
        for line in ("proxy_set_header X-Real-IP $remote_addr;",
                     "proxy_set_header X-Forwarded-For $remote_addr;",
                     "proxy_set_header {{ nginx_real_ip_header }} $remote_addr;",
                     "proxy_set_header X-Forwarded-Proto $edge_forwarded_proto;",
                     'proxy_set_header Forwarded "";'):
            self.assertIn(line, self.site)

    def test_firewall_dropin_only_accepts(self):
        """The base role's convention: number 20, only "add rule inet filter input ... accept" lines."""
        self.assertEqual(load_yaml(ROLE / "vars" / "main.yml")["nginx_firewall_dropin"], "/etc/nftables.d/20-nginx.nft")
        text = (ROLE / "templates" / "20-nginx.nft.j2").read_text(encoding="utf-8")
        rules = [ln for ln in text.splitlines() if ln and not ln.lstrip().startswith(("#", "{%"))]
        self.assertTrue(rules)
        for line in rules:
            self.assertTrue(line.startswith("add rule inet filter input "), line)
            self.assertIn(" accept comment ", line)
            self.assertNotRegex(line, r"\b(drop|reject|policy|flush)\b")

    def test_security_headers_reach_error_pages(self):
        add_header = [ln.strip() for ln in self.main_conf.splitlines() if ln.strip().startswith("add_header")]
        self.assertEqual(add_header, ["add_header {{ name }} $edge_header_{{ var }} always;"])

    def test_site_files_carry_the_marker_and_a_loopback_default(self):
        marker = load_yaml(ROLE / "vars" / "main.yml")["nginx_site_marker"]
        self.assertEqual(self.site.splitlines()[0], "{{ nginx_site_marker }}")
        self.assertTrue(marker.startswith("# "))
        self.assertIn("listen {{ item.listen | default('127.0.0.1:8080', true) }};", self.site)

    def test_reload_only_after_the_check(self):
        """The check runs as a task on every run, before the handlers flush."""
        main = load_yaml(ROLE / "tasks" / "main.yml")
        order = [task["ansible.builtin.import_tasks"] for task in main]
        self.assertLess(order.index("config.yml"), order.index("service.yml"))
        service = load_yaml(ROLE / "tasks" / "service.yml")
        check = next(task for task in service if task.get("ansible.builtin.command") == "nginx -t")
        self.assertIs(check["changed_when"], False)
        self.assertNotIn("notify", check)
        handlers = load_yaml(ROLE / "handlers" / "main.yml")
        reload = next(h for h in handlers if h["name"] == "Reload nginx")
        self.assertEqual(reload["ansible.builtin.systemd_service"]["state"], "reloaded")


if __name__ == "__main__":
    unittest.main()
