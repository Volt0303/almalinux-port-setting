"""Tests for loader.py against the real sample CSV + synthetic edge cases."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ipset.core import loader  # noqa: E402

SAMPLE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "IPsetting_sample.csv",
)


class TestLoaderSample(unittest.TestCase):
    def setUp(self):
        self.res = loader.load(SAMPLE)

    def test_loads_without_errors(self):
        self.assertTrue(self.res.ok, self.res.errors)

    def test_three_machines_six_ports_each(self):
        self.assertEqual(len(self.res.machines), 3)
        for m in self.res.machine_list():
            self.assertEqual(len(m.ports), 6, "SN %s" % m.sn)

    def test_fields_parsed(self):
        m = loader.find_machine(self.res, "F30126E001")
        self.assertIsNotNone(m)
        lan1 = m.ports[0]
        self.assertEqual(lan1.con_name, "LAN1")
        self.assertEqual(lan1.ifname, "enp3s0")
        self.assertEqual(lan1.ip_address, "192.168.1.100")
        self.assertEqual(lan1.subnet, "255.255.255.0")
        self.assertEqual(lan1.gateway, "")

    def test_catches_row19_duplicate_ip(self):
        # F30126E003 LAN6 duplicates LAN5's 192.168.5.102 (source bug).
        dupes = [w for w in self.res.warnings if "F30126E003" in w and "192.168.5.102" in w]
        self.assertTrue(dupes, "expected duplicate-IP warning for row 19")


class TestLoaderEdgeCases(unittest.TestCase):
    def _write(self, text):
        fd, path = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        self.addCleanup(os.remove, path)
        return path

    def test_missing_required_column(self):
        p = self._write("SN,con_name,ip_address\nX,LAN1,1.2.3.4\n")
        res = loader.load(p)
        self.assertFalse(res.ok)
        self.assertIn("subnet", res.errors[0])

    def test_missing_value_reports_line(self):
        p = self._write("SN,con_name,ip_address,subnet\nX,LAN1,,255.255.255.0\n")
        res = loader.load(p)
        self.assertFalse(res.ok)
        self.assertIn("Line 2", res.errors[0])

    def test_header_aliases_and_bom(self):
        p = self._write("﻿serial,lan,ip,netmask\nX,LAN1,1.2.3.4,255.255.255.0\n")
        res = loader.load(p)
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(res.machines["X"].ports[0].ip_address, "1.2.3.4")

    def test_file_not_found(self):
        res = loader.load("/no/such/file.csv")
        self.assertFalse(res.ok)


if __name__ == "__main__":
    unittest.main(verbosity=2)
