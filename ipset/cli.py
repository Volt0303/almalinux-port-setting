"""cli.py - headless entry point: load -> resolve -> apply -> readback -> compare -> log.

Modes:
    --dry-run (default)  print the nmcli commands that WOULD run; touch nothing
    --commit             actually apply, read back, compare, and log

Serial selection:
    --serial SN          use this machine's row set
    (auto)               else try `dmidecode -s system-serial-number`;
                         else if the file has exactly one machine, use it;
                         else list choices and stop.

Exit codes: 0 = all OK, 1 = one or more NG / load error, 2 = usage error.
Python 3.9 compatible.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from typing import List, Optional

from .core import detect, loader, pipeline
from .core.applier import Applier, load_port_map
from .core.compare import PortComparison, summarize
from .core.logwriter import LogWriter, build_rows
from .core.reader import Reader

CONFIG_DIR = "config"


# --------------------------------------------------------------------------
# Serial detection / machine selection
# --------------------------------------------------------------------------
def detect_serial(runner=None) -> Optional[str]:
    """Best-effort read of the system serial via dmidecode (needs root)."""
    runner = runner or (lambda argv: subprocess.run(argv, capture_output=True, text=True))
    try:
        proc = runner(["dmidecode", "-s", "system-serial-number"])
    except (OSError, FileNotFoundError):
        return None
    if getattr(proc, "returncode", 1) != 0:
        return None
    val = (proc.stdout or "").strip()
    bogus = {"", "to be filled by o.e.m.", "system serial number", "default string", "none"}
    return None if val.lower() in bogus else val


def auto_config(config_dir: str = CONFIG_DIR, out=sys.stdout):
    """Pick the board config matching this machine. Returns (path, error)."""
    match = detect.detect_config(config_dir)
    if match:
        print("Board config: %s (%s: %d/%d ports matched)" % (
            match.path, match.board or "unnamed", match.matched, match.total),
            file=out)
        return match.path, None

    # Nothing matched perfectly - explain what was found so the operator can fix it.
    ranked = detect.evaluate_configs(config_dir)
    if not ranked:
        return None, ("no usable config found in %s (use --config)" % config_dir)
    lines = ["no config matches this machine's interfaces; specify --config.",
             "  candidates:"]
    for m in ranked:
        lines.append("    %s (%s) %d/%d matched; missing: %s" % (
            m.path, m.board or "unnamed", m.matched, m.total,
            ", ".join(m.missing) or "-"))
    return None, "\n".join(lines)


def select_machine(res: loader.LoadResult, serial: Optional[str], detect_runner=None):
    """Return (machine, error_message)."""
    if serial:
        m = res.machines.get(serial)
        return (m, None) if m else (None, "serial %r not found in file" % serial)
    auto = detect_serial(detect_runner)
    if auto and auto in res.machines:
        return res.machines[auto], None
    if len(res.machines) == 1:
        return res.machine_list()[0], None
    choices = ", ".join(sorted(res.machines))
    hint = " (auto-detected %r not in file)" % auto if auto else ""
    return None, "specify --serial%s; choices: %s" % (hint, choices)


# --------------------------------------------------------------------------
# Pipeline
# --------------------------------------------------------------------------
def run_pipeline(machine, port_map, commit, applier: Applier, reader: Reader,
                 logwriter: Optional[LogWriter], out=sys.stdout) -> int:
    """Core pipeline for one machine. Returns exit code (0 ok / 1 NG)."""
    print("Machine SN: %s   (%s mode)" % (
        machine.sn, "COMMIT" if commit else "DRY-RUN"), file=out)

    # --- DRY-RUN: just show the planned commands, change nothing ---
    if not commit:
        for con_name, rp, cmds, err in pipeline.dry_plan(machine, port_map, applier):
            if err:
                print("  %-5s SKIP (invalid): %s" % (con_name, err), file=out)
                continue
            for w in rp.warnings:
                print("  ! %s" % w, file=out)
            print("  %-5s -> %s  %s" % (rp.con_name, rp.ifname, rp.cidr), file=out)
            for c in cmds:
                print("      $ %s" % c, file=out)
        print("\n(dry-run: no changes applied, no comparison performed)", file=out)
        return 0

    # --- COMMIT: apply, read back, compare, log ---
    pairs = pipeline.commit_machine(machine, port_map, applier, reader)
    expecteds = [e for e, _ in pairs]
    comparisons: List[PortComparison] = [c for _, c in pairs]

    _print_table(machine.sn, comparisons, out)

    if logwriter is not None:
        rows = build_rows(machine.sn, list(zip(expecteds, comparisons)), logwriter.now())
        logwriter.write(rows)
        print("Log saved: %s" % logwriter.path, file=out)

    _, _, all_ok = summarize(comparisons)
    return 0 if all_ok else 1


def _print_table(sn, comparisons, out):
    print("\n%-6s %-20s %-20s %-4s %s" %
          ("Port", "expected", "actual", "res", "reason"), file=out)
    print("-" * 78, file=out)
    for c in comparisons:
        print("%-6s %-20s %-20s %-4s %s" % (
            c.con_name, c.expected, c.actual,
            "OK" if c.ok else "NG", "" if c.ok else c.reason), file=out)
    ok, ng, all_ok = summarize(comparisons)
    print("-" * 78, file=out)
    print("Result: %s   (OK=%d  NG=%d)" %
          ("PASS" if all_ok else "FAIL", ok, ng), file=out)


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ipset", description="6-port LAN IP set & verify")
    p.add_argument("file", help="supply CSV/xlsx file")
    p.add_argument("--config", default=None,
                   help="port-map INI (default: auto-detect from config/ by "
                        "matching this machine's interfaces)")
    p.add_argument("--serial", help="target serial number (else auto-detect)")
    p.add_argument("--commit", action="store_true", help="actually apply (default is dry-run)")
    p.add_argument("--log", default=os.path.join("logs", "result.csv"), help="CSV log path")
    p.add_argument("--list", action="store_true", help="list serials in the file and exit")
    return p


def main(argv: Optional[List[str]] = None, out=sys.stdout) -> int:
    args = build_parser().parse_args(argv)

    res = loader.load(args.file)
    for w in res.warnings:
        print("WARNING: %s" % w, file=out)
    if not res.ok:
        for e in res.errors:
            print("ERROR: %s" % e, file=out)
        return 1

    if args.list:
        for sn in sorted(res.machines):
            print("%s  (%d ports)" % (sn, len(res.machines[sn].ports)), file=out)
        return 0

    config_path = args.config
    if config_path is None:
        config_path, err = auto_config(out=out)
        if err:
            print("ERROR: %s" % err, file=out)
            return 2

    try:
        port_map = load_port_map(config_path)
    except (FileNotFoundError, ValueError) as e:
        print("ERROR: %s" % e, file=out)
        return 2

    machine, err = select_machine(res, args.serial)
    if err:
        print("ERROR: %s" % err, file=out)
        return 2

    applier = Applier(dry_run=not args.commit)
    reader = Reader()
    logwriter = LogWriter(args.log) if args.commit else None
    return run_pipeline(machine, port_map, args.commit, applier, reader, logwriter, out)


if __name__ == "__main__":
    sys.exit(main())
