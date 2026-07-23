"""Tests for logwriter.py."""
import csv
import os
import sys
import tempfile
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ipset.core.compare import compare_port  # noqa: E402
from ipset.core.logwriter import HEADER, LogWriter, build_rows  # noqa: E402
from ipset.core.reader import PortState  # noqa: E402


class Expected:
    def __init__(self, con_name, ifname, cidr, gateway="", dns=""):
        self.con_name, self.ifname, self.cidr = con_name, ifname, cidr
        self.gateway, self.dns = gateway, dns


FIXED = lambda: datetime(2026, 7, 30, 10, 0, 1)  # noqa: E731


class TestLogWriter(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        os.remove(self.path)  # start non-existent
        self.addCleanup(lambda: os.path.exists(self.path) and os.remove(self.path))

    def _read(self):
        with open(self.path, encoding="utf-8-sig", newline="") as f:
            return list(csv.reader(f))

    def _pairs(self):
        e_ok = Expected("LAN1", "enp3s0", "192.168.1.100/24")
        a_ok = PortState("enp3s0", found=True, addresses=["192.168.1.100/24"])
        e_ng = Expected("LAN3", "enp1s0f3", "192.168.3.100/24")
        a_ng = PortState("enp1s0f3", found=True, addresses=["192.168.3.101/24"])
        return [(e_ok, compare_port(e_ok, a_ok)), (e_ng, compare_port(e_ng, a_ng))]

    def test_header_and_rows(self):
        lw = LogWriter(self.path, clock=FIXED)
        rows = build_rows("F30126E001", self._pairs(), lw.now())
        lw.write(rows)
        data = self._read()
        self.assertEqual(data[0], HEADER)
        self.assertEqual(len(data), 3)  # header + 2 rows

    def test_row_content_and_splitcidr(self):
        lw = LogWriter(self.path, clock=FIXED)
        lw.write(build_rows("F30126E001", self._pairs(), lw.now()))
        data = self._read()
        ok_row = data[1]
        self.assertEqual(ok_row[0], "2026/07/30 10:00:01")
        self.assertEqual(ok_row[1], "F30126E001")
        self.assertEqual(ok_row[2], "LAN1")
        self.assertEqual(ok_row[3], "192.168.1.100")
        self.assertEqual(ok_row[4], "255.255.255.0")  # subnet derived from /24
        self.assertEqual(ok_row[8], "OK")
        self.assertEqual(ok_row[9], "")

    def test_ng_row_has_reason(self):
        lw = LogWriter(self.path, clock=FIXED)
        lw.write(build_rows("F30126E001", self._pairs(), lw.now()))
        ng_row = self._read()[2]
        self.assertEqual(ng_row[8], "NG")       # result column
        self.assertIn("IP mismatch", ng_row[9])  # error column

    def test_append_does_not_duplicate_header(self):
        lw = LogWriter(self.path, clock=FIXED)
        lw.write(build_rows("A", self._pairs(), lw.now()))
        lw.write(build_rows("B", self._pairs(), lw.now()))
        data = self._read()
        self.assertEqual(data[0], HEADER)
        self.assertEqual(sum(1 for r in data if r == HEADER), 1)
        self.assertEqual(len(data), 5)  # header + 2 + 2


if __name__ == "__main__":
    unittest.main(verbosity=2)
