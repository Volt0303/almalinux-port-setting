"""Tests for reader.py using canned `ip`/`nmcli` output (no real commands)."""
import os
import sys
import unittest
from collections import namedtuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ipset.core.reader import Reader  # noqa: E402

Proc = namedtuple("Proc", "returncode stdout stderr")

IP_OK = ("3: enp3s0    inet 192.168.1.100/24 brd 192.168.1.255 scope global "
         "enp3s0\\       valid_lft forever preferred_lft forever\n")
NMCLI_OK = "IP4.GATEWAY:192.168.1.1\nIP4.DNS[1]:8.8.8.8\nIP4.DNS[2]:8.8.4.4\n"
NMCLI_EMPTY = "IP4.GATEWAY:--\n"


class FakeRunner:
    def __init__(self, ip_proc, nmcli_proc=None):
        self.ip_proc = ip_proc
        self.nmcli_proc = nmcli_proc or Proc(0, NMCLI_EMPTY, "")
        self.calls = []

    def __call__(self, argv):
        self.calls.append(argv)
        if argv and argv[0] == "ip":
            return self.ip_proc
        return self.nmcli_proc


class TestReader(unittest.TestCase):
    def test_reads_address(self):
        r = Reader(runner=FakeRunner(Proc(0, IP_OK, "")))
        st = r.read_port("enp3s0")
        self.assertTrue(st.found)
        self.assertEqual(st.addresses, ["192.168.1.100/24"])
        self.assertTrue(st.has_address("192.168.1.100/24"))

    def test_reads_gateway_and_dns(self):
        r = Reader(runner=FakeRunner(Proc(0, IP_OK, ""), Proc(0, NMCLI_OK, "")))
        st = r.read_port("enp3s0")
        self.assertEqual(st.gateway, "192.168.1.1")
        self.assertEqual(st.dns, ["8.8.8.8", "8.8.4.4"])

    def test_missing_interface(self):
        r = Reader(runner=FakeRunner(Proc(1, "", "Device \"enpX\" does not exist.")))
        st = r.read_port("enpX")
        self.assertFalse(st.found)
        self.assertIn("does not exist", st.error)

    def test_interface_up_but_no_ip(self):
        r = Reader(runner=FakeRunner(Proc(0, "", "")))
        st = r.read_port("enp3s0")
        self.assertTrue(st.found)
        self.assertEqual(st.addresses, [])
        self.assertFalse(st.has_address("192.168.1.100/24"))

    def test_empty_gateway_skipped(self):
        r = Reader(runner=FakeRunner(Proc(0, IP_OK, ""), Proc(0, NMCLI_EMPTY, "")))
        st = r.read_port("enp3s0")
        self.assertEqual(st.gateway, "")
        self.assertEqual(st.dns, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
