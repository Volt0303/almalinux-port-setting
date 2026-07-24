"""pipeline.py — shared orchestration used by both cli.py and gui.py.

Keeps the load -> resolve -> apply -> readback -> compare sequence in ONE
place so the GUI is a thin view over the same logic as the CLI.
Python 3.9 compatible.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from .applier import Applier, resolve_port
from .compare import PortComparison, compare_port
from .reader import Reader


def resolve_failure_row(row) -> PortComparison:
    return PortComparison(
        con_name=row.con_name, ifname=row.ifname or "?",
        expected=row.ip_address, actual="(resolve error)", ok=False,
        reason="invalid data (line %d)" % row.source_line,
    )


def dry_plan(machine, port_map, applier: Applier):
    """Return [(con_name, resolved_or_None, [cmd_str,...], error_or_None)]."""
    out = []
    for row in machine.ports:
        try:
            rp = resolve_port(row, port_map)
        except Exception as e:  # noqa: BLE001
            out.append((row.con_name, None, [], str(e)))
            continue
        cmds = [" ".join(a) for a in applier.plan_port(rp, exists=False)]
        out.append((rp.con_name, rp, cmds, None))
    return out


def commit_machine(machine, port_map, applier: Applier, reader: Reader
                   ) -> List[Tuple[Optional[object], PortComparison]]:
    """Apply, read back and compare every port. Returns [(expected, comparison)]."""
    pairs = []
    for row in machine.ports:
        try:
            rp = resolve_port(row, port_map)
        except Exception:  # noqa: BLE001 — bad ip/mask/unresolvable interface
            pairs.append((None, resolve_failure_row(row)))
            continue
        apply_res = applier.apply_port(rp)
        state = reader.read_port(rp.ifname)
        comp = compare_port(rp, state)
        if not apply_res.ok and comp.ok:
            comp.ok = False
            comp.reason = apply_res.error
        pairs.append((rp, comp))
    return pairs
