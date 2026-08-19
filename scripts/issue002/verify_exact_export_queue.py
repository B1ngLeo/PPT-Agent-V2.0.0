from __future__ import annotations

import argparse
import hashlib
import io
import json
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from instant_ppt_domain.config import DomainSettings
from instant_ppt_domain.database import create_domain_engine, create_session_factory
from instant_ppt_domain.models import Artifact, EffectiveDesignSpecRevision, ExportJob
from sqlalchemy import select

_DRAWING_NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}t"
_FORBIDDEN = (
    "Editable native presentation baseline",
    "AI 重生成指令：",
)


def _request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: dict | None = None,
) -> dict:
    payload = (
        json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if body is not None
        else None
    )
    request_headers = {"Accept": "application/json", **(headers or {})}
    if payload is not None:
        request_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=payload, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} failed: {error.code} {detail}") from error


def _visible_text(pptx: bytes) -> list[str]:
    values: list[str] = []
    with zipfile.ZipFile(io.BytesIO(pptx)) as archive:
        slides = sorted(
            name
            for name in archive.namelist()
            if name.startswith("ppt/slides/slide") and name.endswith(".xml")
        )
        for slide in slides:
            root = ElementTree.fromstring(archive.read(slide))
            values.extend(node.text or "" for node in root.iter(_DRAWING_NS))
    return values


def verify(
    *,
    base_url: str,
    subject: str,
    presentation_id: str,
    revision_id: str,
    timeout_seconds: int,
) -> dict:
    nonce = str(time.time_ns())
    headers = {
        "X-Dev-User-Subject": subject,
        "X-Dev-User-Name": "ISSUE-002 Runtime E2E",
        "Idempotency-Key": f"issue002-exact-export-{nonce}",
    }
    queued = _request(
        "POST",
        f"{base_url}/v1/presentations/{presentation_id}/exports",
        headers=headers,
        body={
            "schemaVersion": 1,
            "data": {
                "presentationRevisionId": revision_id,
                "filename": f"issue002-runtime-{nonce}.pptx",
            },
            "baseRevisionId": revision_id,
        },
    )["data"]
    export_id = queued["exportId"]
    deadline = time.monotonic() + timeout_seconds
    completed = queued
    while time.monotonic() < deadline:
        completed = _request(
            "GET",
            f"{base_url}/v1/exports/{export_id}",
            headers={key: value for key, value in headers.items() if key != "Idempotency-Key"},
        )["data"]
        if completed["status"] in {"succeeded", "failed", "cancelled"}:
            break
        time.sleep(0.25)
    if completed["status"] != "succeeded":
        raise RuntimeError(f"queued exact export did not succeed: {completed}")

    engine = create_domain_engine(DomainSettings.from_env().database_url)
    factory = create_session_factory(engine)
    try:
        with factory() as session:
            effective = session.scalar(
                select(EffectiveDesignSpecRevision).where(
                    EffectiveDesignSpecRevision.presentation_revision_id == revision_id
                )
            )
            if effective is None:
                raise RuntimeError("presentation revision has no effective Default spec")
            canonical_id = effective.payload["canonicalArtifacts"]["pptxArtifactId"]
            canonical = session.get(Artifact, canonical_id)
            export = session.get(ExportJob, export_id)
            if canonical is None or export is None:
                raise RuntimeError("canonical or export database row is missing")
            if export.artifact_id != canonical.id:
                raise RuntimeError("exact export rebuilt instead of reusing canonical PPTX")
            canonical_sha256 = canonical.sha256
            canonical_size = canonical.size_bytes
    finally:
        engine.dispose()

    authorization = _request(
        "POST",
        f"{base_url}/v1/artifacts/{completed['artifactId']}:authorize-download",
        headers={**headers, "Idempotency-Key": f"issue002-download-{nonce}"},
        body={"schemaVersion": 1, "data": {}, "baseRevisionId": None},
    )["data"]
    with urllib.request.urlopen(authorization["downloadUrl"], timeout=30) as response:
        pptx = response.read()
    downloaded_sha256 = hashlib.sha256(pptx).hexdigest()
    if downloaded_sha256 != canonical_sha256:
        raise RuntimeError("downloaded exact export bytes differ from canonical PPTX")
    texts = _visible_text(pptx)
    leaked = [value for value in texts if any(token in value for token in _FORBIDDEN)]
    if leaked:
        raise RuntimeError(f"legacy engineering text leaked into export: {leaked}")

    return {
        "schemaVersion": 1,
        "status": "passed",
        "presentationId": presentation_id,
        "presentationRevisionId": revision_id,
        "exportId": export_id,
        "artifactId": completed["artifactId"],
        "canonicalArtifactId": canonical_id,
        "canonicalSha256": canonical_sha256,
        "downloadedSha256": downloaded_sha256,
        "sizeBytes": canonical_size,
        "visibleTextCount": len(texts),
        "forbiddenTextMatches": leaked,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--subject", default="local-web-user")
    parser.add_argument("--presentation-id", required=True)
    parser.add_argument("--revision-id", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=120)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = verify(
        base_url=args.base_url.rstrip("/"),
        subject=args.subject,
        presentation_id=args.presentation_id,
        revision_id=args.revision_id,
        timeout_seconds=args.timeout_seconds,
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
