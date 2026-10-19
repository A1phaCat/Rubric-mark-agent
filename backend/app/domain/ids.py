"""Prefixed, lexicographically sortable ULID-like identifiers without external dependencies."""

from __future__ import annotations

import secrets
import time

ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _base32(value: int, width: int) -> str:
    chars = []
    for _ in range(width):
        chars.append(ALPHABET[value & 31])
        value >>= 5
    return "".join(reversed(chars))


def new_id(prefix: str) -> str:
    timestamp = int(time.time() * 1000)
    randomness = secrets.randbits(80)
    return f"{prefix}_{_base32(timestamp, 10)}{_base32(randomness, 16)}"
