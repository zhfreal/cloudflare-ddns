import unittest
from unittest.mock import MagicMock, patch
import argparse
import pytest

from src.cloudflare_ddns import (
    CloudFlare,
    str2bool,
    parse_raw_line,
    split_content_list,
    print_logs,
)


class TestCloudFlareHelperFunctions(unittest.TestCase):
    def test_str2bool(self):
        self.assertTrue(str2bool(True))
        self.assertTrue(str2bool("true"))
        self.assertTrue(str2bool("True"))
        self.assertTrue(str2bool("yes"))
        self.assertTrue(str2bool("1"))
        self.assertTrue(str2bool("t"))

        self.assertFalse(str2bool(False))
        self.assertFalse(str2bool("false"))
        self.assertFalse(str2bool("False"))
        self.assertFalse(str2bool("no"))
        self.assertFalse(str2bool("0"))
        self.assertFalse(str2bool("f"))

        with self.assertRaises(argparse.ArgumentTypeError):
            str2bool("invalid")

    def test_parse_raw_line(self):
        line1 = "sub,A,1.2.3.4,60,false"
        parsed1 = parse_raw_line(line1)
        self.assertEqual(parsed1, ["sub", "A", "1.2.3.4", "60", "false"])

        line2 = "sub;AAAA;2001:db8::1;300;true"
        parsed2 = parse_raw_line(line2)
        self.assertEqual(parsed2, ["sub", "AAAA", "2001:db8::1", "300", "true"])

        line3 = "sub|CNAME|target.com|auto|false"
        parsed3 = parse_raw_line(line3)
        self.assertEqual(parsed3, ["sub", "CNAME", "target.com", "auto", "false"])

    def test_split_content_list(self):
        res = split_content_list(["1.1.1.1, 2.2.2.2", "3.3.3.3"])
        self.assertIn("1.1.1.1", res)
        self.assertIn("2.2.2.2", res)
        self.assertIn("3.3.3.3", res)
        self.assertEqual(len(res), 3)

        txt_res = split_content_list(["v=spf1 include:_spf.google.com ~all"], dns_type="TXT")
        self.assertEqual(txt_res, ["v=spf1 include:_spf.google.com ~all"])

    def test_print_logs_no_crash(self):
        u = {("sub", "A", "1.1.1.1"): "record1"}
        c = [("sub2", "AAAA", "2001::1")]
        d = []
        k = []
        # Should not raise exception
        print_logs(u, c, d, k)


class TestCloudFlareClassMethods(unittest.TestCase):
    def setUp(self):
        # Instantiate CloudFlare with dummy zones mocked out
        with patch.object(CloudFlare, '__init_zones__', return_value=None):
            self.cf = CloudFlare(email="test@example.com", api_key="dummy_key")
            self.cf.zones = {
                "example.com": {"id": "zone123"},
                "sub.domain.co.uk": {"id": "zone456"},
            }

    def test_split_domain_root_zone(self):
        # Root zone should return ("", "example.com")
        res = self.cf.split_domain("example.com")
        self.assertEqual(res, ("", "example.com"))

    def test_split_domain_subdomain(self):
        res = self.cf.split_domain("www.example.com")
        self.assertEqual(res, ("www", "example.com"))

        res2 = self.cf.split_domain("a.b.c.example.com")
        self.assertEqual(res2, ("a.b.c", "example.com"))

    def test_has_root_zone(self):
        self.assertTrue(self.cf.has_root_zone("example.com"))
        self.assertTrue(self.cf.has_root_zone("sub.example.com"))
        self.assertFalse(self.cf.has_root_zone("otherdomain.org"))

    def test_get_full_name(self):
        self.assertEqual(CloudFlare.get_full_name("example.com", "example.com"), "example.com")
        self.assertEqual(CloudFlare.get_full_name("www", "example.com"), "www.example.com")
        self.assertEqual(CloudFlare.get_full_name("www.example.com", "example.com"), "www.example.com")


if __name__ == "__main__":
    unittest.main()
