"""compare.py - compare expected settings vs actual applied state (spec 13).

Produces one PortComparison per port with an OK/NG verdict and a reason,
feeding both the on-screen result table and the CSV log.

Rules:
  * IP address is the primary check: expected cidr must be present in the
    interface's actual addresses.
  * gateway / DNS are checked ONLY when an expected value was supplied
    (so the current empty-gateway supply data does not false-NG).
  * a missing interface / no address is NG.

No third-party deps; decoupled from applier via duck typing (expected object
just needs .con_name/.ifname/.cidr/.gateway/.dns). Python 3.9 compatible.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class PortComparison:
    con_name: str
    ifname: str
    expected: str          # display: expected cidr
    actual: str            # display: actual address(es)
    ok: bool
    reason: str = ""       # "-" style empty when OK
    details: List[str] = field(default_factory=list)  # per-field notes


def compare_port(expected, actual) -> PortComparison:
    """Compare one expected port (ResolvedPort-like) vs actual PortState."""
    exp_cidr = expected.cidr
    act_display = ", ".join(actual.addresses) if actual.addresses else "(none)"

    details: List[str] = []
    ok = True

    # --- interface presence ---
    if not actual.found:
        return PortComparison(
            con_name=expected.con_name, ifname=expected.ifname,
            expected=exp_cidr, actual="(interface not found)", ok=False,
            reason="interface %s not found" % expected.ifname,
            details=[actual.error] if actual.error else [],
        )

    # --- IP address (primary) ---
    if exp_cidr in actual.addresses:
        details.append("IP OK")
    else:
        ok = False
        details.append("IP mismatch: expected %s, actual %s" % (exp_cidr, act_display))

    # --- gateway (only when expected) ---
    exp_gw = getattr(expected, "gateway", "") or ""
    if exp_gw:
        if actual.gateway == exp_gw:
            details.append("GW OK")
        else:
            ok = False
            details.append("GW mismatch: expected %s, actual %s"
                           % (exp_gw, actual.gateway or "(none)"))

    # --- dns (only when expected) ---
    exp_dns = getattr(expected, "dns", "") or ""
    if exp_dns:
        want = [d.strip() for d in exp_dns.replace(";", ",").split(",") if d.strip()]
        missing = [d for d in want if d not in actual.dns]
        if not missing:
            details.append("DNS OK")
        else:
            ok = False
            details.append("DNS mismatch: missing %s, actual %s"
                           % (", ".join(missing), ", ".join(actual.dns) or "(none)"))

    reason = "-" if ok else "; ".join(d for d in details if "OK" not in d)
    return PortComparison(
        con_name=expected.con_name, ifname=expected.ifname,
        expected=exp_cidr, actual=act_display, ok=ok, reason=reason, details=details,
    )


def summarize(comparisons: List[PortComparison]) -> "tuple[int, int, bool]":
    """Return (ok_count, ng_count, all_ok)."""
    ok_count = sum(1 for c in comparisons if c.ok)
    ng_count = len(comparisons) - ok_count
    return ok_count, ng_count, ng_count == 0
