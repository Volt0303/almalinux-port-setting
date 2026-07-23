"""Tests for compare.py."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ipset.core.compare import compare_port, summarize  # noqa: E402
from ipset.core.reader import PortState  # noqa: E402


class Expected:
    """Lightweight ResolvedPort stand-in."""
    def __init__(self, con_name, ifname, cidr, gateway="", dns=""):
        self.con_name = con_name
        self.ifname = ifname
        self.cidr = cidr
        self.gateway = gateway
        self.dns = dns


class TestComparePort(unittest.TestCase):
    def test_ip_match_ok(self):
        exp = Expected("LAN1", "enp3s0", "192.168.1.100/24")
        act = PortState("enp3s0", found=True, addresses=["192.168.1.100/24"])
        c = compare_port(exp, act)
        self.assertTrue(c.ok)
        self.assertEqual(c.reason, "-")

    def test_ip_mismatch_ng(self):
        exp = Expected("LAN3", "enp1s0f3", "192.168.3.100/24")
        act = PortState("enp1s0f3", found=True, addresses=["192.168.3.101/24"])
        c = compare_port(exp, act)
        self.assertFalse(c.ok)
        self.assertIn("IP mismatch", c.reason)

    def test_interface_not_found_ng(self):
        exp = Expected("LAN5", "enp1s0f1", "192.168.5.100/24")
        act = PortState("enp1s0f1", found=False, error="does not exist")
        c = compare_port(exp, act)
        self.assertFalse(c.ok)
        self.assertIn("not found", c.reason)

    def test_up_but_no_ip_ng(self):
        exp = Expected("LAN2", "enp4s0", "192.168.2.100/24")
        act = PortState("enp4s0", found=True, addresses=[])
        c = compare_port(exp, act)
        self.assertFalse(c.ok)
        self.assertIn("IP mismatch", c.reason)

    def test_gateway_checked_only_when_expected(self):
        # expected gateway empty -> actual gateway presence is ignored
        exp = Expected("LAN1", "enp3s0", "192.168.1.100/24", gateway="")
        act = PortState("enp3s0", found=True, addresses=["192.168.1.100/24"],
                        gateway="192.168.1.254")
        self.assertTrue(compare_port(exp, act).ok)

    def test_gateway_mismatch_ng(self):
        exp = Expected("LAN1", "enp3s0", "192.168.1.100/24", gateway="192.168.1.1")
        act = PortState("enp3s0", found=True, addresses=["192.168.1.100/24"],
                        gateway="192.168.1.254")
        c = compare_port(exp, act)
        self.assertFalse(c.ok)
        self.assertIn("GW mismatch", c.reason)

    def test_dns_match_multi(self):
        exp = Expected("LAN1", "enp3s0", "192.168.1.100/24", dns="8.8.8.8,8.8.4.4")
        act = PortState("enp3s0", found=True, addresses=["192.168.1.100/24"],
                        dns=["8.8.8.8", "8.8.4.4"])
        self.assertTrue(compare_port(exp, act).ok)

    def test_dns_missing_ng(self):
        exp = Expected("LAN1", "enp3s0", "192.168.1.100/24", dns="8.8.8.8")
        act = PortState("enp3s0", found=True, addresses=["192.168.1.100/24"], dns=[])
        c = compare_port(exp, act)
        self.assertFalse(c.ok)
        self.assertIn("DNS mismatch", c.reason)


class TestSummarize(unittest.TestCase):
    def test_counts(self):
        exp = Expected("LAN1", "e", "1.1.1.1/24")
        good = compare_port(exp, PortState("e", found=True, addresses=["1.1.1.1/24"]))
        bad = compare_port(exp, PortState("e", found=True, addresses=["2.2.2.2/24"]))
        ok, ng, all_ok = summarize([good, good, bad])
        self.assertEqual((ok, ng, all_ok), (2, 1, False))


if __name__ == "__main__":
    unittest.main(verbosity=2)
