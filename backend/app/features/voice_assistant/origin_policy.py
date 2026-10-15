"""Shared origin syntax policy; callers additionally enforce operator allowlists."""

import ipaddress
from urllib.parse import urlsplit


def service_origin(value: str) -> str:
    parsed = urlsplit(value)
    try:
        port = parsed.port
    except ValueError:
        raise ValueError("Use a valid service origin and port.") from None
    if port == 0:
        raise ValueError("Service port must be between 1 and 65535.")
    host = parsed.hostname or ""
    if (
        parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ValueError("Use an origin without credentials, path, query or fragment.")
    loopback = host in {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme != "https" and not (parsed.scheme == "http" and loopback):
        raise ValueError("Use HTTPS; plain HTTP is allowed only for loopback services.")
    if not host or len(host) > 253 or "%" in host or any(c.isspace() for c in value):
        raise ValueError("Use a valid service hostname or address.")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if (
        address
        and not loopback
        and (
            address.is_link_local
            or address.is_multicast
            or address.is_unspecified
            or address.is_reserved
        )
    ):
        raise ValueError("Metadata, link-local, multicast and reserved addresses are prohibited.")
    netloc = f"[{host}]" if ":" in host else host
    if port and port != (443 if parsed.scheme == "https" else 80):
        netloc += f":{port}"
    return f"{parsed.scheme}://{netloc}"
