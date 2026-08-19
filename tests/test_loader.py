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

    # -- same-subnet detection (customer request: multi-port connectivity) ----
    def _subnet_warnings(self, res):
        return [w for w in res.warnings if "同一サブネット" in w]

    def test_warns_when_ports_share_a_subnet(self):
        p = self._write(
            "SN,con_name,ip_address,subnet\n"
            "A,LAN1,192.168.1.101,255.255.255.0\n"
            "A,LAN2,192.168.1.102,255.255.255.0\n"
            "A,LAN3,192.168.1.103,255.255.255.0\n"
        )
        res = loader.load(p)
        self.assertTrue(res.ok, res.errors)
        warns = self._subnet_warnings(res)
        self.assertEqual(len(warns), 1, warns)
        for lan in ("LAN1", "LAN2", "LAN3"):
            self.assertIn(lan, warns[0])
        self.assertIn("192.168.1.0/24", warns[0])

    def test_no_warning_when_subnets_differ(self):
        p = self._write(
            "SN,con_name,ip_address,subnet\n"
            "B,LAN1,192.168.1.100,255.255.255.0\n"
            "B,LAN2,192.168.2.100,255.255.255.0\n"
        )
        res = loader.load(p)
        self.assertEqual(self._subnet_warnings(res), [])

    def test_subnet_grouping_is_per_machine(self):
        """Two machines reusing the same plan must not warn against each other."""
        p = self._write(
            "SN,con_name,ip_address,subnet\n"
            "M1,LAN1,192.168.1.100,255.255.255.0\n"
            "M2,LAN1,192.168.1.100,255.255.255.0\n"
        )
        res = loader.load(p)
        self.assertEqual(self._subnet_warnings(res), [])

    def test_invalid_rows_do_not_break_subnet_check(self):
        p = self._write(
            "SN,con_name,ip_address,subnet\n"
            "C,LAN1,not-an-ip,255.255.255.0\n"
            "C,LAN2,192.168.1.102,255.255.255.0\n"
        )
        res = loader.load(p)          # must not raise
        self.assertEqual(self._subnet_warnings(res), [])

    def test_warns_once_per_subnet_group(self):
        """Different subnets each get their own single warning."""
        p = self._write(
            "SN,con_name,ip_address,subnet\n"
            "D,LAN1,192.168.1.101,255.255.255.0\n"
            "D,LAN2,192.168.1.102,255.255.255.0\n"
            "D,LAN3,10.0.0.1,255.255.255.0\n"
            "D,LAN4,10.0.0.2,255.255.255.0\n"
        )
        res = loader.load(p)
        self.assertEqual(len(self._subnet_warnings(res)), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
