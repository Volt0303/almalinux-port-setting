"""reader.py — read back the ACTUAL applied IPv4 state per interface.

Addresses are read from the kernel (`ip -o -4 addr show dev <if>`), which is
the ground truth of what is really applied (catches the spec-15 case where
nmcli reports success but nothing took effect). Gateway/DNS are read from
NetworkManager (`nmcli -t -f ... device show <if>`).

Injectable runner for testing; read-only, so safe on any machine.
Python 3.9 compatible.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from typing import Callable, List, Optional


@dataclass
class PortState:
    ifname: str
    found: bool = False           # interface exists / returned data
    addresses: List[str] = field(default_factory=list)  # e.g. ['192.168.1.100/24']
    gateway: str = ""
    dns: List[str] = field(default_factory=list)
    error: str = ""

    def has_address(self, cidr: str) -> bool:
        return cidr in self.addresses


def _default_runner(argv: List[str]):
    return subprocess.run(argv, capture_output=True, text=True)


class Reader:
    def __init__(self, runner: Optional[Callable[[List[str]], object]] = None):
        # runner returns an object with .returncode/.stdout/.stderr
        self._runner = runner or _default_runner

    def read_addresses(self, ifname: str) -> "tuple[bool, List[str], str]":
        """Return (found, [cidr, ...], error) from `ip -o -4 addr`."""
        proc = self._runner(["ip", "-o", "-4", "addr", "show", "dev", ifname])
        if proc.returncode != 0:
            return False, [], (proc.stderr or "").strip()
        addrs = []
        for line in proc.stdout.splitlines():
            toks = line.split()
            # ... inet 192.168.1.100/24 brd ... scope global enp3s0
            if "inet" in toks:
                cidr = toks[toks.index("inet") + 1]
                addrs.append(cidr)
        return True, addrs, ""

    def read_gateway_dns(self, ifname: str) -> "tuple[str, List[str]]":
        """Return (gateway, [dns, ...]) from `nmcli device show`."""
        proc = self._runner(
            ["nmcli", "-t", "-f", "IP4.GATEWAY,IP4.DNS", "device", "show", ifname])
        if proc.returncode != 0:
            return "", []
        gateway, dns = "", []
        for line in proc.stdout.splitlines():
            if ":" not in line:
                continue
            key, _, val = line.partition(":")
            val = val.strip()
            if not val or val == "--":
                continue
            if key.startswith("IP4.GATEWAY"):
                gateway = val
            elif key.startswith("IP4.DNS"):
                dns.append(val)
        return gateway, dns

    def read_port(self, ifname: str) -> PortState:
        found, addrs, err = self.read_addresses(ifname)
        st = PortState(ifname=ifname, found=found, addresses=addrs, error=err)
        if found:
            st.gateway, st.dns = self.read_gateway_dns(ifname)
        return st
