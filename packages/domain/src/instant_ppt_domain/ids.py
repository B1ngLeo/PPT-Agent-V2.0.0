"""Monotonic ULID generation matching ADR-001."""

from __future__ import annotations

import secrets
import threading
import time

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_lock = threading.Lock()
_last_millisecond = -1
_last_random = 0


def _encode(value: int, length: int) -> str:
    characters = ["0"] * length
    for index in range(length - 1, -1, -1):
        characters[index] = _ALPHABET[value & 31]
        value >>= 5
    return "".join(characters)


def new_ulid() -> str:
    """Return a canonical, process-local monotonic ULID."""
    global _last_millisecond, _last_random
    with _lock:
        millisecond = time.time_ns() // 1_000_000
        if millisecond > _last_millisecond:
            random_value = secrets.randbits(80)
        else:
            millisecond = _last_millisecond
            random_value = (_last_random + 1) & ((1 << 80) - 1)
            if random_value == 0:
                while millisecond <= _last_millisecond:
                    millisecond = time.time_ns() // 1_000_000
                random_value = secrets.randbits(80)
        _last_millisecond = millisecond
        _last_random = random_value
    return f"{_encode(millisecond, 10)}{_encode(random_value, 16)}"
