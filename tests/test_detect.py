"""Tests for detect.py - board config auto-detection (no real /sys access)."""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ipset.core import detect  # noqa: E402

INTEL = """[board]
name = INTEL-DEV

[port_map]
LAN1 = enp3s0
LAN2 = enp4s0
LAN3 = enp1s0f3
LAN4 = enp1s0f2
LAN5 = enp1s0f1
LAN6 = enp1s0f0
"""

AMD = """[board]
name = AMD-QC

[port_map]
LAN1 = enp3s0
LAN2 = enp2s0
LAN3 = enp1s0f3
LAN4 = enp1s0f2
LAN5 = enp1s0f1
LAN6 = enp1s0f0
"""

# Real capture from the AMD production board (enp4s0 does NOT exist there).
AMD_IFACES = {"enp1s0f0", "enp1s0f1", "enp1s0f2", "enp1s0f3", "enp2s0", "enp3s0"}
INTEL_IFACES = {"enp1s0f0", "enp1s0f1", "enp1s0f2", "enp1s0f3", "enp3s0", "enp4s0"}


class TestDetect(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        for name, body in (("config_intel.ini", INTEL), ("config_amd.ini", AMD)):
            with open(os.path.join(self.dir, name), "w", encoding="utf-8") as f:
                f.write(body)
        # a template that must be ignored
        with open(os.path.join(self.dir, "config_intel.ini.example"), "w",
                  encoding="utf-8") as f:
            f.write(INTEL)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_picks_amd_on_amd_board(self):
        m = detect.detect_config(self.dir, ifaces=AMD_IFACES)
        self.assertIsNotNone(m)
        self.assertTrue(m.path.endswith("config_amd.ini"))
        self.assertEqual(m.board, "AMD-QC")
        self.assertTrue(m.perfect)

    def test_picks_intel_on_intel_board(self):
        m = detect.detect_config(self.dir, ifaces=INTEL_IFACES)
        self.assertIsNotNone(m)
        self.assertTrue(m.path.endswith("config_intel.ini"))
        self.assertEqual(m.board, "INTEL-DEV")

    def test_no_match_returns_none(self):
        """An unknown board must NOT silently get a partially-matching config."""
        m = detect.detect_config(self.dir, ifaces={"eth0", "eth1"})
        self.assertIsNone(m)

    def test_ignores_example_templates(self):
        paths = detect.find_config_files(self.dir)
        self.assertTrue(all(not p.endswith(".example") for p in paths))
        self.assertEqual(len(paths), 2)

    def test_reports_missing_ifaces(self):
        ranked = detect.evaluate_configs(self.dir, ifaces=AMD_IFACES)
        by_name = {os.path.basename(m.path): m for m in ranked}
        # on the AMD board the Intel config is missing exactly enp4s0
        self.assertEqual(by_name["config_intel.ini"].missing, ["enp4s0"])
        self.assertEqual(by_name["config_amd.ini"].missing, [])

    def test_best_match_ranked_first(self):
        ranked = detect.evaluate_configs(self.dir, ifaces=AMD_IFACES)
        self.assertTrue(ranked[0].path.endswith("config_amd.ini"))

    def test_empty_dir(self):
        empty = tempfile.mkdtemp()
        try:
            self.assertIsNone(detect.detect_config(empty, ifaces=AMD_IFACES))
            self.assertEqual(detect.evaluate_configs(empty, ifaces=AMD_IFACES), [])
        finally:
            shutil.rmtree(empty, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
