"""applier.py - apply per-port IPv4 settings via NetworkManager (nmcli).

Flow per port:
  1. resolve LAN label -> ifname (config port_map is authoritative; CSV
     ifname is cross-checked and a mismatch is warned about)
  2. build ip/prefix via netmask.to_cidr
  3. modify-or-add the connection profile (ipv4.method manual, addresses,
     optional gateway/dns), then `con up`

Safety:
  * dry_run=True records the exact argv WITHOUT executing (used on the
    Ubuntu dev box so the real network is never touched)
  * a per-port failure is isolated and does not abort the others (spec 12)

subprocess only; Python 3.9 compatible.
"""
from __future__ import annotations

import configparser
import subprocess
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from . import netmask
from .loader import Machine, PortRow


@dataclass
class RunResult:
    argv: List[str]
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0


@dataclass
class ResolvedPort:
    con_name: str
    ifname: str
    cidr: str
    gateway: str = ""
    dns: str = ""
    source_line: int = 0
    warnings: List[str] = field(default_factory=list)


@dataclass
class PortApplyResult:
    con_name: str
    ifname: str
    ok: bool
    commands: List[RunResult] = field(default_factory=list)
    error: str = ""


# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------
def load_port_map(path: str) -> Dict[str, str]:
    """Read [port_map] from an INI config into {LAN label: ifname}."""
    cp = configparser.ConfigParser()
    cp.optionxform = str  # preserve LAN1 case
    if not cp.read(path, encoding="utf-8"):
        raise FileNotFoundError("config not found: %s" % path)
    if not cp.has_section("port_map"):
        raise ValueError("config missing [port_map]: %s" % path)
    return {k: v.strip() for k, v in cp.items("port_map")}


# --------------------------------------------------------------------------
# Resolution (pure - no network)
# --------------------------------------------------------------------------
def resolve_port(row: PortRow, port_map: Dict[str, str]) -> ResolvedPort:
    """Resolve one PortRow into a ResolvedPort, raising ValueError on bad data."""
    cfg_ifname = port_map.get(row.con_name, "")
    ifname = cfg_ifname or row.ifname
    if not ifname:
        raise ValueError(
            "cannot resolve interface for %s (not in config port_map, no CSV ifname)"
            % row.con_name
        )
    warnings: List[str] = []
    if cfg_ifname and row.ifname and cfg_ifname != row.ifname:
        warnings.append(
            "%s: config maps to %s but CSV says %s - using config"
            % (row.con_name, cfg_ifname, row.ifname)
        )
    cidr = netmask.to_cidr(row.ip_address, row.subnet)  # raises on bad ip/mask
    gw = netmask.validate_ipv4(row.gateway) if row.gateway else ""
    dns = row.dns.strip()
    return ResolvedPort(
        con_name=row.con_name, ifname=ifname, cidr=cidr, gateway=gw, dns=dns,
        source_line=row.source_line, warnings=warnings,
    )


# --------------------------------------------------------------------------
# Applier
# --------------------------------------------------------------------------
class Applier:
    def __init__(self, runner: Optional[Callable[[List[str]], RunResult]] = None,
                 dry_run: bool = False):
        self.dry_run = dry_run
        self._runner = runner or self._subprocess_runner

    def _subprocess_runner(self, argv: List[str]) -> RunResult:
        proc = subprocess.run(argv, capture_output=True, text=True)
        return RunResult(argv=argv, returncode=proc.returncode,
                         stdout=proc.stdout, stderr=proc.stderr)

    def _run(self, argv: List[str]) -> RunResult:
        if self.dry_run:
            return RunResult(argv=argv, returncode=0, stdout="[dry-run]")
        return self._runner(argv)

    def _connection_exists(self, con_name: str) -> bool:
        if self.dry_run:
            return False  # plan as 'add'
        res = self._runner(["nmcli", "-t", "-f", "NAME", "connection", "show"])
        if not res.ok:
            return False
        names = {ln.strip() for ln in res.stdout.splitlines()}
        return con_name in names

    def plan_port(self, rp: ResolvedPort, exists: bool) -> List[List[str]]:
        """Build the nmcli argv list(s) for one port (no execution)."""
        props = [
            "ipv4.method", "manual",
            "ipv4.addresses", rp.cidr,
        ]
        # gateway/dns are optional; only emit when supplied (avoids blank-value
        # nmcli quirks and the multi-default-gateway trap when left unset)
        if rp.gateway:
            props += ["ipv4.gateway", rp.gateway]
        if rp.dns:
            props += ["ipv4.dns", rp.dns]
        if exists:
            cmds = [["nmcli", "connection", "modify", rp.con_name,
                     "connection.interface-name", rp.ifname] + props]
        else:
            cmds = [["nmcli", "connection", "add", "type", "ethernet",
                     "con-name", rp.con_name, "ifname", rp.ifname,
                     "autoconnect", "yes"] + props]
        cmds.append(["nmcli", "connection", "up", rp.con_name])
        return cmds

    def apply_port(self, rp: ResolvedPort) -> PortApplyResult:
        exists = self._connection_exists(rp.con_name)
        result = PortApplyResult(con_name=rp.con_name, ifname=rp.ifname, ok=True)
        for argv in self.plan_port(rp, exists):
            rr = self._run(argv)
            result.commands.append(rr)
            if not rr.ok:
                result.ok = False
                result.error = "nmcli failed: %s :: %s" % (
                    " ".join(argv), (rr.stderr or rr.stdout).strip())
                break  # stop this port; other ports continue (caller loop)
        return result

    def apply_machine(self, machine: Machine,
                      port_map: Dict[str, str]) -> List[PortApplyResult]:
        """Apply all ports of a machine, isolating per-port failures (spec 12)."""
        results: List[PortApplyResult] = []
        for row in machine.ports:
            try:
                rp = resolve_port(row, port_map)
            except (ValueError, netmask.ValidationError) as e:
                results.append(PortApplyResult(
                    con_name=row.con_name, ifname=row.ifname, ok=False,
                    error="resolve failed (line %d): %s" % (row.source_line, e)))
                continue
            results.append(self.apply_port(rp))
        return results
