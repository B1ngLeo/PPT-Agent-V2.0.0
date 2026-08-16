"""Deterministic artifact metadata helpers."""

import hashlib
import mimetypes
from pathlib import Path

from instant_ppt_worker.models import ArtifactRef


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_ref(root: Path, path: Path, kind: str, mime_type: str | None = None) -> ArtifactRef:
    return ArtifactRef(
        kind=kind,
        key=path.resolve().relative_to(root.resolve()).as_posix(),
        sha256=sha256_file(path),
        size_bytes=path.stat().st_size,
        mime_type=mime_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream",
    )
