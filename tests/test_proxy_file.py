"""Tests for proxy-file parsing in config.py."""
import os
import tempfile
import unittest

# Importing config requires TELEGRAM_BOT_TOKEN (from env or .env). A .env exists
# in the repo, but guard the import so the tests run in a bare environment too.
os.environ.setdefault('TELEGRAM_BOT_TOKEN', 'x')

from config import _normalize_proxy, _load_proxy_file


class NormalizeProxyTests(unittest.TestCase):
    def test_full_url_kept_as_is(self):
        self.assertEqual(
            _normalize_proxy('socks5://u:p@h:1080'),
            'socks5://u:p@h:1080',
        )

    def test_bare_host_port(self):
        self.assertEqual(
            _normalize_proxy('1.2.3.4:8080'),
            'http://1.2.3.4:8080',
        )

    def test_host_port_user_pass(self):
        self.assertEqual(
            _normalize_proxy('1.2.3.4:8080:user:pass'),
            'http://user:pass@1.2.3.4:8080',
        )

    def test_garbage_returns_none(self):
        self.assertIsNone(_normalize_proxy('garbage'))


class LoadProxyFileTests(unittest.TestCase):
    def test_parses_three_valid_forms_in_order(self):
        content = (
            "\n"
            "# comment\n"
            "\n"
            "socks5://u:p@h:1080\n"
            "1.2.3.4:8080\n"
            "1.2.3.4:8080:user:pass\n"
        )
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.txt', delete=False, encoding='utf-8'
        ) as f:
            f.write(content)
            path = f.name
        try:
            result = _load_proxy_file(path)
        finally:
            os.unlink(path)
        self.assertEqual(
            result,
            [
                'socks5://u:p@h:1080',
                'http://1.2.3.4:8080',
                'http://user:pass@1.2.3.4:8080',
            ],
        )

    def test_missing_file_returns_empty_list(self):
        self.assertEqual(
            _load_proxy_file('/nonexistent/path/does-not-exist.txt'),
            [],
        )


if __name__ == '__main__':
    unittest.main()
