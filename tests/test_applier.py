"""Tests for applier.py — all use a fake runner; no real nmcli is invoked."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ipset.core import loader  # noqa: E402
from ipset.core.applier import (  # noqa: E402
    Applier, RunResult, load_port_map, resolve_port,
)
from ipset.core.loader import PortRow  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE = os.path.join(ROOT, "IPsetting_sample.csv")
CONFIG = os.path.join(ROOT, "config", "config_intel.ini")

PORT_MAP = {
    "LAN1": "enp3s0", "LAN2": "enp4s0", "LAN3": "enp1s0f3",
    "LAN4": "enp1s0f2", "LAN5": "enp1s0f1", "LAN6": "enp1s0f0",
}


class FakeRunner:
    """Records argv and returns canned results keyed by a substring match."""
    def __init__(self, fail_contains=None):
        self.calls = []
        self.fail_contains = fail_contains

    def __call__(self, argv):
        self.calls.append(argv)
        joined = " ".join(argv)
        if "connection show" in joined:
            return RunResult(argv=argv, returncode=0, stdout="")  # nothing exists
        if self.fail_contains and self.fail_contains in joined:
            return RunResult(argv=argv, returncode=4, stderr="boom")
        return RunResult(argv=argv, returncode=0, stdout="ok")


class TestResolve(unittest.TestCase):
    def test_config_wins_and_warns_on_mismatch(self):
        row = PortRow(sn="X", con_name="LAN1", ip_address="192.168.1.100",
                      subnet="255.255.255.0", ifname="wrongif")
        rp = resolve_port(row, {"LAN1": "enp3s0"})
        self.assertEqual(rp.ifname, "enp3s0")
        self.assertEqual(rp.cidr, "192.168.1.100/24")
        self.assertTrue(any("mismatch" not in w and "using config" in w for w in rp.warnings))

    def test_falls_back_to_csv_ifname(self):
        row = PortRow(sn="X", con_name="LANX", ip_address="10.0.0.1",
                      subnet="255.0.0.0", ifname="ethz")
        rp = resolve_port(row, {})
        self.assertEqual(rp.ifname, "ethz")
        self.assertEqual(rp.cidr, "10.0.0.1/8")

    def test_unresolvable_raises(self):
        row = PortRow(sn="X", con_name="LANX", ip_address="10.0.0.1",
                      subnet="255.0.0.0", ifname="")
        self.assertRaises(ValueError, resolve_port, row, {})

    def test_bad_ip_raises(self):
        row = PortRow(sn="X", con_name="LAN1", ip_address="999.1.1.1",
                      subnet="255.255.255.0", ifname="e")
        self.assertRaises(Exception, resolve_port, row, {"LAN1": "e"})


class TestPlan(unittest.TestCase):
    def test_add_when_absent(self):
        row = PortRow(sn="X", con_name="LAN1", ip_address="192.168.1.100",
                      subnet="255.255.255.0")
        rp = resolve_port(row, PORT_MAP)
        cmds = Applier(dry_run=True).plan_port(rp, exists=False)
        self.assertIn("add", cmds[0])
        self.assertIn("192.168.1.100/24", cmds[0])
        self.assertIn("enp3s0", cmds[0])
        self.assertEqual(cmds[1][:3], ["nmcli", "connection", "up"])

    def test_modify_when_present(self):
        row = PortRow(sn="X", con_name="LAN1", ip_address="192.168.1.100",
                      subnet="255.255.255.0")
        rp = resolve_port(row, PORT_MAP)
        cmds = Applier(dry_run=True).plan_port(rp, exists=True)
        self.assertIn("modify", cmds[0])


class TestApplyMachine(unittest.TestCase):
    def _machine(self):
        res = loader.load(SAMPLE)
        return res.machines["F30126E001"]

    def test_dry_run_all_ports_ok_no_real_calls(self):
        applier = Applier(dry_run=True)
        results = applier.apply_machine(self._machine(), PORT_MAP)
        self.assertEqual(len(results), 6)
        self.assertTrue(all(r.ok for r in results))
        # 2 commands per port (add + up)
        self.assertTrue(all(len(r.commands) == 2 for r in results))

    def test_fake_runner_executes_expected_argv(self):
        fake = FakeRunner()
        applier = Applier(runner=fake, dry_run=False)
        results = applier.apply_machine(self._machine(), PORT_MAP)
        self.assertTrue(all(r.ok for r in results))
        added = [c for c in fake.calls if "add" in c]
        self.assertEqual(len(added), 6)

    def test_per_port_failure_isolated(self):
        # Fail only LAN3's 'up'; the other five must still succeed.
        fake = FakeRunner(fail_contains="up LAN3")
        applier = Applier(runner=fake, dry_run=False)
        results = applier.apply_machine(self._machine(), PORT_MAP)
        by_name = {r.con_name: r for r in results}
        self.assertFalse(by_name["LAN3"].ok)
        self.assertTrue(by_name["LAN1"].ok)
        self.assertTrue(by_name["LAN6"].ok)


class TestConfigLoad(unittest.TestCase):
    def test_reads_intel_config(self):
        pm = load_port_map(CONFIG)
        self.assertEqual(pm["LAN1"], "enp3s0")
        self.assertEqual(len(pm), 6)


if __name__ == "__main__":
    unittest.main(verbosity=2)
