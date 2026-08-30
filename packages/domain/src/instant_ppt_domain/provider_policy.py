"""Provider endpoint policy shared by API snapshots and runtime workers."""

from __future__ import annotations

import os
from urllib.parse import urlsplit

DEFAULT_QWEN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

_OFFICIAL_QWEN_HOSTS = frozenset(
    {
        "dashscope.aliyuncs.com",
        "dashscope-intl.aliyuncs.com",
        "dashscope-us.aliyuncs.com",
    }
)


def is_official_qwen_base_url(value: str) -> bool:
    """Return whether a URL targets an official DashScope compatible endpoint."""

    try:
        parsed = urlsplit(value.strip())
        host = (parsed.hostname or "").lower()
        return (
            parsed.scheme == "https"
            and parsed.username is None
            and parsed.password is None
            and parsed.port in {None, 443}
            and not parsed.query
            and not parsed.fragment
            and parsed.path.rstrip("/") == "/compatible-mode/v1"
            and (host in _OFFICIAL_QWEN_HOSTS or host.endswith(".maas.aliyuncs.com"))
        )
    except ValueError:
        return False


def resolve_qwen_base_url(value: str | None) -> str:
    """Use an official Qwen endpoint, falling back from stale proxy settings."""

    candidate = (value or "").strip().rstrip("/")
    if candidate and is_official_qwen_base_url(candidate):
        return candidate
    return DEFAULT_QWEN_BASE_URL


def configured_qwen_base_url() -> str:
    """Resolve the configured official endpoint without trusting legacy proxy values."""

    preferred = os.getenv("QWEN_OFFICIAL_BASE_URL", "").strip()
    legacy = os.getenv("QWEN_BASE_URL", "").strip()
    return resolve_qwen_base_url(preferred or legacy)


def configured_qwen_api_key() -> str:
    """Prefer the key paired with the official endpoint configuration."""

    return os.getenv("QWEN_OFFICIAL_API_KEY", "").strip() or os.getenv("QWEN_API_KEY", "").strip()
