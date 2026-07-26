"""netmask.py - IPv4 validation and netmask <-> CIDR normalization.

nmcli wants addresses as ip/prefix (e.g. 192.168.1.100/24). The supply file
gives dotted netmasks (255.255.255.0). This module bridges the two and
enforces spec section 15 ("IPアドレス形式不正").

Pure stdlib (ipaddress). Python 3.9 compatible.
"""
from __future__ import annotations

import ipaddress


class ValidationError(ValueError):
    """Raised when an address or netmask is not valid IPv4."""


def validate_ipv4(addr: str) -> str:
    """Return the normalized dotted IPv4 string, or raise ValidationError.

    Rejects empty, prefixed ('1.2.3.4/24'), IPv6, and out-of-range values.
    """
    s = (addr or "").strip()
    if not s:
        raise ValidationError("empty IPv4 address")
    if "/" in s:
        raise ValidationError("unexpected prefix in address: %r" % addr)
    try:
        return str(ipaddress.IPv4Address(s))
    except ipaddress.AddressValueError as e:
        raise ValidationError("invalid IPv4 address %r: %s" % (addr, e)) from e


def parse_prefix(subnet: str) -> int:
    """Parse a subnet spec into a prefix length (0-32).

    Accepts: '24', '/24', '255.255.255.0'. Rejects non-contiguous masks
    (e.g. 255.0.255.0) and out-of-range values.
    """
    s = (subnet or "").strip().lstrip("/")
    if not s:
        raise ValidationError("empty subnet")
    # Plain prefix number.
    if s.isdigit():
        n = int(s)
        if 0 <= n <= 32:
            return n
        raise ValidationError("prefix out of range: %s" % subnet)
    # Dotted netmask -> prefix (ipaddress rejects non-contiguous masks).
    try:
        net = ipaddress.IPv4Network("0.0.0.0/%s" % s)
        return net.prefixlen
    except (ipaddress.NetmaskValueError, ipaddress.AddressValueError, ValueError) as e:
        raise ValidationError("invalid subnet mask %r: %s" % (subnet, e)) from e


def prefix_to_netmask(prefix: int) -> str:
    """Return dotted netmask for a prefix length (for readback comparison)."""
    if not (0 <= prefix <= 32):
        raise ValidationError("prefix out of range: %s" % prefix)
    return str(ipaddress.IPv4Network("0.0.0.0/%d" % prefix).netmask)


def to_cidr(ip_address: str, subnet: str) -> str:
    """Combine an IPv4 address and a subnet spec into 'ip/prefix' for nmcli."""
    ip = validate_ipv4(ip_address)
    prefix = parse_prefix(subnet)
    return "%s/%d" % (ip, prefix)
