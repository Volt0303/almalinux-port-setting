"""logwriter.py - persist run results to a CSV log (spec 14).

Columns (matching spec 14.1):
    datetime, serial, lan, ip, subnet, gateway, dns, actual, result, error

Append-safe (writes the header only when the file is new), UTF-8 with BOM so
the CSV opens cleanly in Excel. Injectable clock for deterministic tests.
Python 3.9 compatible; stdlib only.
"""
from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, List, Optional

from . import netmask

HEADER = ["datetime", "serial", "lan", "ip", "subnet",
          "gateway", "dns", "actual", "result", "error"]
TS_FMT = "%Y/%m/%d %H:%M:%S"


@dataclass
class LogRow:
    timestamp: str
    serial: str
    lan: str
    ip: str
    subnet: str
    gateway: str
    dns: str
    actual: str
    result: str      # "OK" / "NG"
    error: str

    def as_list(self) -> List[str]:
        return [self.timestamp, self.serial, self.lan, self.ip, self.subnet,
                self.gateway, self.dns, self.actual, self.result, self.error]


def _split_cidr(cidr: str) -> "tuple[str, str]":
    """'192.168.1.100/24' -> ('192.168.1.100', '255.255.255.0')."""
    if "/" not in cidr:
        return cidr, ""
    ip, _, prefix = cidr.partition("/")
    try:
        return ip, netmask.prefix_to_netmask(int(prefix))
    except (ValueError, netmask.ValidationError):
        return ip, prefix


def build_rows(serial: str, pairs, timestamp: str) -> List[LogRow]:
    """Build LogRows from (expected, comparison) pairs for one machine.

    `expected` is a ResolvedPort-like object (.gateway/.dns); `comparison`
    is a compare.PortComparison (.expected cidr, .actual, .ok, .reason).
    """
    rows: List[LogRow] = []
    for expected, comp in pairs:
        ip, subnet = _split_cidr(comp.expected)
        rows.append(LogRow(
            timestamp=timestamp,
            serial=serial,
            lan=comp.con_name,
            ip=ip,
            subnet=subnet,
            gateway=getattr(expected, "gateway", "") or "",
            dns=getattr(expected, "dns", "") or "",
            actual=comp.actual,
            result="OK" if comp.ok else "NG",
            error="" if comp.ok else comp.reason,
        ))
    return rows


class LogWriter:
    def __init__(self, path: str, clock: Optional[Callable[[], datetime]] = None):
        self.path = path
        self._clock = clock or datetime.now

    def now(self) -> str:
        return self._clock().strftime(TS_FMT)

    def write(self, rows: List[LogRow]) -> None:
        """Append rows, creating the file + header if it does not exist."""
        d = os.path.dirname(self.path)
        if d:
            os.makedirs(d, exist_ok=True)
        new_file = not os.path.exists(self.path) or os.path.getsize(self.path) == 0
        with open(self.path, "a", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            if new_file:
                w.writerow(HEADER)
            for r in rows:
                w.writerow(r.as_list())
