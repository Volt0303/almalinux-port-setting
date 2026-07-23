"""Tests for netmask.py."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ipset.core import netmask as nm  # noqa: E402


class TestValidateIPv4(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(nm.validate_ipv4(" 192.168.1.100 "), "192.168.1.100")

    def test_rejects_empty(self):
        self.assertRaises(nm.ValidationError, nm.validate_ipv4, "")

    def test_rejects_prefixed(self):
        self.assertRaises(nm.ValidationError, nm.validate_ipv4, "192.168.1.1/24")

    def test_rejects_out_of_range(self):
        self.assertRaises(nm.ValidationError, nm.validate_ipv4, "192.168.1.300")

    def test_rejects_garbage(self):
        self.assertRaises(nm.ValidationError, nm.validate_ipv4, "abc")


class TestParsePrefix(unittest.TestCase):
    def test_dotted_mask(self):
        self.assertEqual(nm.parse_prefix("255.255.255.0"), 24)
        self.assertEqual(nm.parse_prefix("255.255.0.0"), 16)
        self.assertEqual(nm.parse_prefix("255.255.255.252"), 30)

    def test_plain_and_slashed_number(self):
        self.assertEqual(nm.parse_prefix("24"), 24)
        self.assertEqual(nm.parse_prefix("/24"), 24)

    def test_rejects_noncontiguous_mask(self):
        self.assertRaises(nm.ValidationError, nm.parse_prefix, "255.0.255.0")

    def test_rejects_out_of_range(self):
        self.assertRaises(nm.ValidationError, nm.parse_prefix, "33")

    def test_rejects_empty(self):
        self.assertRaises(nm.ValidationError, nm.parse_prefix, "")


class TestRoundTrip(unittest.TestCase):
    def test_prefix_to_netmask(self):
        self.assertEqual(nm.prefix_to_netmask(24), "255.255.255.0")
        self.assertEqual(nm.prefix_to_netmask(16), "255.255.0.0")

    def test_to_cidr_from_sample_values(self):
        self.assertEqual(nm.to_cidr("192.168.1.100", "255.255.255.0"), "192.168.1.100/24")

    def test_to_cidr_propagates_bad_ip(self):
        self.assertRaises(nm.ValidationError, nm.to_cidr, "bad", "255.255.255.0")


if __name__ == "__main__":
    unittest.main(verbosity=2)
