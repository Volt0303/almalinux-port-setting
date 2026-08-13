"""detect.py - choose the right board config automatically.

Production machines differ by board model (the Intel dev box and the AMD
IMB-A8000M enumerate their 6 LAN ports under different ifnames). Making the
operator pick the correct config/*.ini on 400 units is error-prone, so this
module picks it by evidence: it compares each config's [port_map] against
the interfaces that actually exist on this machine and returns the best fit.

Read-only (lists /sys/class/net); safe on any machine. Injectable iface
lister and port-map loader keep it unit-testable. Python 3.9 compatible.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Set

SYS_NET = "/sys/class/net"


@dataclass
class ConfigMatch:
    path: str
    board: str
    matched: int          # how many mapped ifnames exist on this machine
    total: int            # how many ports the config maps
    missing: List[str]    # mapped ifnames that do NOT exist here

    @property
    def ratio(self) -> float:
        return (self.matched / self.total) if self.total else 0.0

    @property
    def perfect(self) -> bool:
        return self.total > 0 and self.matched == self.total


def list_physical_ifaces(sys_net: str = SYS_NET) -> Set[str]:
    """Names of physical Ethernet interfaces (skips lo and virtual devices)."""
    found = set()
    try:
        names = os.listdir(sys_net)
    except OSError:
        return found
    for name in names:
        if name == "lo":
            continue
        # a real NIC has a 'device' symlink (PCI/USB backing)
        if os.path.islink(os.path.join(sys_net, name, "device")):
            found.add(name)
    return found


def find_config_files(config_dir: str) -> List[str]:
    """All candidate INI files in config_dir (skips *.example templates)."""
    try:
        names = sorted(os.listdir(config_dir))
    except OSError:
        return []
    out = []
    for n in names:
        if not n.endswith(".ini") or n.endswith(".example"):
            continue
        out.append(os.path.join(config_dir, n))
    return out


def _board_name(path: str, cp_reader) -> str:
    try:
        return cp_reader(path)
    except Exception:  # noqa: BLE001
        return ""


def score_config(port_map: Dict[str, str], ifaces: Set[str]) -> "tuple":
    """Return (matched, total, missing) for one port_map against the machine."""
    total = len(port_map)
    missing = [v for v in port_map.values() if v not in ifaces]
    return total - len(missing), total, missing


def evaluate_configs(config_dir: str,
                     ifaces: Optional[Set[str]] = None,
                     load_port_map: Optional[Callable] = None,
                     board_reader: Optional[Callable] = None
                     ) -> List[ConfigMatch]:
    """Score every config in config_dir against this machine's interfaces."""
    if load_port_map is None:
        from .applier import load_port_map as _lpm
        load_port_map = _lpm
    if board_reader is None:
        board_reader = _read_board_name
    if ifaces is None:
        ifaces = list_physical_ifaces()

    results: List[ConfigMatch] = []
    for path in find_config_files(config_dir):
        try:
            pm = load_port_map(path)
        except Exception:  # noqa: BLE001 - unreadable/invalid config is just skipped
            continue
        matched, total, missing = score_config(pm, ifaces)
        results.append(ConfigMatch(path=path, board=_board_name(path, board_reader),
                                   matched=matched, total=total, missing=missing))
    # best fit first; stable, deterministic ordering on ties
    results.sort(key=lambda m: (-m.ratio, -m.matched, m.path))
    return results


def _read_board_name(path: str) -> str:
    import configparser
    cp = configparser.ConfigParser(inline_comment_prefixes=("#", ";"))
    cp.optionxform = str
    cp.read(path, encoding="utf-8")
    if cp.has_section("board"):
        return cp.get("board", "name", fallback="").strip()
    return ""


def detect_config(config_dir: str,
                  ifaces: Optional[Set[str]] = None,
                  load_port_map: Optional[Callable] = None
                  ) -> Optional[ConfigMatch]:
    """Best-matching config for this machine, or None if nothing matches.

    Only a PERFECT match (every mapped ifname exists) is returned, so a
    partially-matching config is never silently used on the wrong board.
    """
    ranked = evaluate_configs(config_dir, ifaces=ifaces, load_port_map=load_port_map)
    if ranked and ranked[0].perfect:
        # ambiguous only if another config is also perfect AND maps differently
        return ranked[0]
    return None
