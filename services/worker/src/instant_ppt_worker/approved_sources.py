"""Resolve approved source descriptors into immutable same-tenant workflow fragments."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from instant_ppt_domain.models import Artifact, GenerationSnapshot, Source, SourceArtifact
from instant_ppt_domain.service import canonical_sha256
from sqlalchemy import select
from sqlalchemy.orm import Session

from instant_ppt_worker.errors import RENDER_FAILED, AdapterError
from instant_ppt_worker.workflow_models import (
    ApprovedSourceArtifact,
    SourceFragment,
    SourceManifest,
)


class SourceObjectReader(Protocol):
    def download(self, object_key: str, target: Path, *, max_bytes: int) -> str: ...


def _fragment_kind(text: str) -> str:
    stripped = text.lstrip()
    if stripped.startswith("#"):
        return "heading"
    if "|" in stripped and "\n" in stripped:
        return "table"
    if re.match(r"^(?:[-*+] |\d+[.)] )", stripped):
        return "list"
    return "paragraph"


def _markdown_fragments(markdown: str, source_artifact_id: str) -> list[SourceFragment]:
    blocks = [value.strip() for value in re.split(r"\n\s*\n", markdown) if value.strip()]
    if not blocks:
        raise AdapterError(RENDER_FAILED, "approved markdown source has no usable text")
    fragments: list[SourceFragment] = []
    page: int | None = None
    for index, block in enumerate(blocks[:256], start=1):
        page_match = re.match(r"^#{1,3}\s+Page\s+(\d+)\b", block, re.IGNORECASE)
        if page_match:
            page = int(page_match.group(1))
        text = block[:16000]
        fragments.append(
            SourceFragment(
                fragment_id=f"{source_artifact_id}:fragment-{index:03d}",
                page=page,
                kind=_fragment_kind(text),
                text=text,
                text_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            )
        )
    return fragments


def resolve_approved_sources(
    session: Session,
    snapshot: GenerationSnapshot,
    *,
    object_store: SourceObjectReader,
    workspace: Path,
) -> SourceManifest:
    summary = snapshot.payload.get("sourceSummary") or {}
    source_id = summary.get("sourceId")
    if not source_id:
        if snapshot.payload.get("sourceDecision") != "continue-limited-general-draft":
            raise AdapterError(
                RENDER_FAILED,
                "no-source generation requires an explicit limited-draft decision",
            )
        return SourceManifest(
            mode="no-source-limited",
            artifacts=[],
            manifest_sha256=canonical_sha256(
                {"mode": "no-source-limited", "snapshotSha256": snapshot.snapshot_sha256}
            ),
            continue_limited_draft=True,
        )
    source = session.scalar(
        select(Source).where(
            Source.id == source_id,
            Source.organization_id == snapshot.organization_id,
        )
    )
    if (
        source is None
        or source.status != "parsed"
        or source.parse_status != "succeeded"
        or source.source_sha256 != summary.get("sha256")
    ):
        raise AdapterError(RENDER_FAILED, "approved source identity or parse state changed")
    descriptors = summary.get("artifactDescriptors") or []
    markdown_descriptors = [item for item in descriptors if item.get("kind") == "markdown"]
    if not markdown_descriptors:
        raise AdapterError(RENDER_FAILED, "approved source has no pinned markdown descriptor")
    resolved: list[ApprovedSourceArtifact] = []
    for descriptor in markdown_descriptors:
        source_artifact = session.scalar(
            select(SourceArtifact).where(
                SourceArtifact.id == descriptor.get("sourceArtifactId"),
                SourceArtifact.source_id == source.id,
                SourceArtifact.organization_id == snapshot.organization_id,
                SourceArtifact.artifact_id == descriptor.get("artifactId"),
                SourceArtifact.kind == "markdown",
            )
        )
        artifact = session.scalar(
            select(Artifact).where(
                Artifact.id == descriptor.get("artifactId"),
                Artifact.organization_id == snapshot.organization_id,
                Artifact.status == "published",
            )
        )
        if source_artifact is None or artifact is None:
            raise AdapterError(RENDER_FAILED, "approved source artifact is unavailable")
        if artifact.retention_expires_at <= datetime.now(UTC):
            raise AdapterError(RENDER_FAILED, "approved source retention pin expired")
        if (
            artifact.sha256 != descriptor.get("sha256")
            or artifact.media_type != descriptor.get("mediaType")
            or artifact.size_bytes != descriptor.get("sizeBytes")
        ):
            raise AdapterError(RENDER_FAILED, "approved source artifact descriptor changed")
        target = workspace / f"{artifact.id}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        actual_sha256 = object_store.download(
            artifact.object_key,
            target,
            max_bytes=artifact.size_bytes,
        )
        if actual_sha256 != artifact.sha256:
            raise AdapterError(RENDER_FAILED, "approved source artifact bytes changed")
        markdown = target.read_text(encoding="utf-8")
        resolved.append(
            ApprovedSourceArtifact(
                source_artifact_id=source_artifact.id,
                source_id=source.id,
                organization_id=snapshot.organization_id,
                object_sha256=artifact.sha256,
                media_type=artifact.media_type,
                parsed_at=source.parse_completed_at or source.updated_at,
                fragments=_markdown_fragments(markdown, source_artifact.id),
            )
        )
    manifest_payload: dict[str, Any] = {
        "mode": "approved-artifacts",
        "snapshotSha256": snapshot.snapshot_sha256,
        "artifacts": [value.model_dump(by_alias=True, mode="json") for value in resolved],
    }
    return SourceManifest(
        mode="approved-artifacts",
        artifacts=resolved,
        manifest_sha256=canonical_sha256(manifest_payload),
        continue_limited_draft=False,
    )
