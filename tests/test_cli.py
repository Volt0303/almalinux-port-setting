"""Tests for cli.py wiring — commit mode with fake applier/reader (no nmcli)."""
import csv
import io
import os
import sys
import tempfile
import unittest
from collections import namedtuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ipset import cli  # noqa: E402
from ipset.core import loader  # noqa: E402
from ipset.core.applier import Applier, RunResult  # noqa: E402
from ipset.core.logwriter import LogWriter  # noqa: E402
from ipset.core.reader import Reader  # noqa: E402

Proc = namedtuple("Proc", "returncode stdout stderr")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE = os.path.join(ROOT, "IPsetting_sample.csv")
PORT_MAP = {"LAN1": "enp3s0", "LAN2": "enp4s0", "LAN3": "enp1s0f3",
            "LAN4": "enp1s0f2", "LAN5": "enp1s0f1", "LAN6": "enp1s0f0"}
CLOCK = lambda: __import__("datetime").datetime(2026, 7, 30, 10, 0, 0)  # noqa: E731


def apply_ok(argv):
    if "connection show" in " ".join(argv):
        return RunResult(argv=argv, returncode=0, stdout="")
    return RunResult(argv=argv, returncode=0, stdout="ok")


class ReaderFake:
    """Return each interface's address; optionally corrupt one ifname."""
    def __init__(self, ip_by_if, corrupt=None):
        self.ip_by_if = ip_by_if
        self.corrupt = corrupt

    def __call__(self, argv):
        if argv[0] == "ip":
            ifname = argv[-1]
            cidr = self.ip_by_if.get(ifname, "")
            if ifname == self.corrupt:
                cidr = "10.0.0.1/24"  # wrong
            out = ("x: %s inet %s scope global %s\n" % (ifname, cidr, ifname)) if cidr else ""
            return Proc(0, out, "")
        return Proc(0, "", "")  # nmcli gw/dns: empty


def machine():
    return loader.load(SAMPLE).machines["F30126E001"]


def expected_ips():
    return {p.ifname or PORT_MAP[p.con_name]: p.ip_address + "/24"
            for p in machine().ports}


class TestCommitPipeline(unittest.TestCase):
    def _run(self, corrupt=None):
        fd, logpath = tempfile.mkstemp(suffix=".csv")
        os.close(fd); os.remove(logpath)
        self.addCleanup(lambda: os.path.exists(logpath) and os.remove(logpath))
        out = io.StringIO()
        applier = Applier(runner=apply_ok, dry_run=False)
        reader = Reader(runner=ReaderFake(expected_ips(), corrupt=corrupt))
        lw = LogWriter(logpath, clock=CLOCK)
        code = cli.run_pipeline(machine(), PORT_MAP, True, applier, reader, lw, out)
        return code, out.getvalue(), logpath

    def test_all_ok_pass_and_log_written(self):
        code, text, logpath = self._run()
        self.assertEqual(code, 0)
        self.assertIn("PASS", text)
        with open(logpath, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.reader(f))
        self.assertEqual(len(rows), 7)  # header + 6 ports
        self.assertTrue(all(r[8] == "OK" for r in rows[1:]))

    def test_one_ng_fails(self):
        code, text, logpath = self._run(corrupt="enp1s0f3")  # LAN3
        self.assertEqual(code, 1)
        self.assertIn("FAIL", text)
        with open(logpath, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.reader(f))
        ng = [r for r in rows[1:] if r[8] == "NG"]
        self.assertEqual(len(ng), 1)
        self.assertEqual(ng[0][2], "LAN3")


class TestSelectMachine(unittest.TestCase):
    def test_explicit_serial(self):
        res = loader.load(SAMPLE)
        m, err = cli.select_machine(res, "F30126E002")
        self.assertIsNone(err)
        self.assertEqual(m.sn, "F30126E002")

    def test_ambiguous_requires_serial(self):
        res = loader.load(SAMPLE)
        m, err = cli.select_machine(res, None, detect_runner=lambda a: Proc(1, "", ""))
        self.assertIsNone(m)
        self.assertIn("choices", err)

    def test_detect_serial_filters_bogus(self):
        r = lambda a: Proc(0, "To be filled by O.E.M.", "")  # noqa: E731
        self.assertIsNone(cli.detect_serial(r))

    def test_detect_serial_valid(self):
        r = lambda a: Proc(0, "F30126E001\n", "")  # noqa: E731
        self.assertEqual(cli.detect_serial(r), "F30126E001")


class TestMainList(unittest.TestCase):
    def test_list_mode(self):
        out = io.StringIO()
        code = cli.main([SAMPLE, "--list"], out=out)
        self.assertEqual(code, 0)
        self.assertIn("F30126E001", out.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
