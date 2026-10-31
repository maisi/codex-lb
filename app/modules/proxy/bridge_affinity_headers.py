"""Lossless affinity transport; this codec grants no forwarding authority."""

from __future__ import annotations

import base64
from collections.abc import Mapping

HTTP_BRIDGE_AFFINITY_KEY_HEADER = "x-codex-bridge-affinity-key"
HTTP_BRIDGE_AFFINITY_KEY_B64_HEADER = "x-codex-bridge-affinity-key-b64"


def encode_bridge_affinity_key(key: str) -> tuple[str, str]:
    """Escape identities that the legacy reader's strip() would change."""
    if key != key.strip():
        return HTTP_BRIDGE_AFFINITY_KEY_B64_HEADER, base64.urlsafe_b64encode(key.encode("utf-8")).decode("ascii")
    return HTTP_BRIDGE_AFFINITY_KEY_HEADER, key


def decode_bridge_affinity_key(headers: Mapping[str, str]) -> str | None:
    """Read one unambiguous key, raising ValueError for malformed transport."""
    # Mapping.items() retains duplicates for Starlette Headers / CIMultiDict.
    values = [
        (name.lower(), value)
        for name, value in headers.items()
        if name.lower() in {HTTP_BRIDGE_AFFINITY_KEY_HEADER, HTTP_BRIDGE_AFFINITY_KEY_B64_HEADER}
    ]
    if len(values) > 1:
        raise ValueError("Ambiguous bridge affinity key")
    if not values:
        return None
    name, value = values[0]
    if name == HTTP_BRIDGE_AFFINITY_KEY_HEADER:
        # Legacy raw keys stay literal, including any "b64:" prefix.
        return value.strip() or None
    encoded = value
    if not encoded:
        raise ValueError("Empty bridge affinity key")
    decoded = base64.b64decode(encoded, altchars=b"-_", validate=True)
    if base64.urlsafe_b64encode(decoded).decode("ascii") != encoded:
        raise ValueError("Noncanonical bridge affinity key")
    return decoded.decode("utf-8")
