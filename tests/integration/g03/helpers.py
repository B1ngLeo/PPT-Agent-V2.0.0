from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from urllib.parse import quote

from instant_ppt_domain.artifacts import ObjectStat


@dataclass(slots=True)
class MemoryObjectStore:
    objects: dict[str, bytes] = field(default_factory=dict)

    def stat(self, object_key: str) -> ObjectStat:
        return ObjectStat(size_bytes=len(self.objects[object_key]), etag="memory-etag")

    def presign_get(self, object_key: str, *, expires: timedelta) -> str:
        return (
            f"https://private.invalid/{quote(object_key)}"
            f"?X-Amz-Expires={int(expires.total_seconds())}&X-Amz-Signature=redacted"
        )


def identity_headers(subject: str, **extra: str) -> dict[str, str]:
    return {
        "X-Dev-User-Subject": subject,
        "X-Dev-User-Email": f"{subject}@example.test",
        "X-Dev-User-Name": subject.title(),
        **extra,
    }
