from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from instant_ppt_domain.ids import new_ulid
from instant_ppt_domain.models import (
    Artifact,
    GenerationJobSlide,
    GenerationSnapshot,
    Source,
    SourceArtifact,
)
from instant_ppt_worker.approved_sources import resolve_approved_sources
from instant_ppt_worker.default_generation_pipeline import (
    _scoped_image_environment,
    _scoped_text_environment,
)
from instant_ppt_worker.default_workflow_request import build_default_workflow_request
from instant_ppt_worker.errors import AdapterError


class QueueSession:
    def __init__(self, values: list[Any]) -> None:
        self.values = iter(values)

    def scalar(self, _statement: object) -> Any:
        return next(self.values)


class MemoryReader:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def download(self, _object_key: str, target: Path, *, max_bytes: int) -> str:
        assert len(self.content) <= max_bytes
        target.write_bytes(self.content)
        return hashlib.sha256(self.content).hexdigest()


def _snapshot(*, organization_id: str, payload: dict[str, Any]) -> GenerationSnapshot:
    return GenerationSnapshot(
        id=new_ulid(),
        organization_id=organization_id,
        draft_id=new_ulid(),
        approval_id=new_ulid(),
        intent_revision_id=new_ulid(),
        outline_revision_id=new_ulid(),
        template_version_id=new_ulid(),
        snapshot_sha256="a" * 64,
        payload=payload,
    )


def test_no_source_requires_explicit_limited_draft_decision(tmp_path: Path) -> None:
    organization_id = new_ulid()
    snapshot = _snapshot(
        organization_id=organization_id,
        payload={"sourceSummary": {"sourceId": None}},
    )

    with pytest.raises(AdapterError, match="explicit limited-draft decision"):
        resolve_approved_sources(
            QueueSession([]),  # type: ignore[arg-type]
            snapshot,
            object_store=MemoryReader(b""),
            workspace=tmp_path,
        )

    snapshot.payload["sourceDecision"] = "continue-limited-general-draft"
    manifest = resolve_approved_sources(
        QueueSession([]),  # type: ignore[arg-type]
        snapshot,
        object_store=MemoryReader(b""),
        workspace=tmp_path,
    )
    assert manifest.mode == "no-source-limited"
    assert manifest.continue_limited_draft is True
    assert manifest.artifacts == []


def test_pinned_markdown_is_verified_and_fragmented(tmp_path: Path) -> None:
    organization_id = new_ulid()
    source_id = new_ulid()
    source_artifact_id = new_ulid()
    artifact_id = new_ulid()
    markdown = "# Page 1\n\n## 市场结论\n\n- 增长来自存量客户\n- 风险来自交付周期"
    content = markdown.encode("utf-8")
    digest = hashlib.sha256(content).hexdigest()
    now = datetime.now(UTC)
    source = Source(
        id=source_id,
        organization_id=organization_id,
        status="parsed",
        parse_status="succeeded",
        source_sha256="b" * 64,
        parse_completed_at=now,
        updated_at=now,
    )
    source_artifact = SourceArtifact(
        id=source_artifact_id,
        source_id=source_id,
        organization_id=organization_id,
        artifact_id=artifact_id,
        kind="markdown",
    )
    artifact = Artifact(
        id=artifact_id,
        organization_id=organization_id,
        artifact_type="source_markdown",
        object_key=f"sources/{artifact_id}.md",
        sha256=digest,
        media_type="text/markdown",
        size_bytes=len(content),
        status="published",
        retention_expires_at=now + timedelta(days=7),
    )
    snapshot = _snapshot(
        organization_id=organization_id,
        payload={
            "sourceSummary": {
                "sourceId": source_id,
                "sha256": source.source_sha256,
                "artifactDescriptors": [
                    {
                        "sourceArtifactId": source_artifact_id,
                        "artifactId": artifact_id,
                        "kind": "markdown",
                        "sha256": digest,
                        "mediaType": "text/markdown",
                        "sizeBytes": len(content),
                    }
                ],
            }
        },
    )

    manifest = resolve_approved_sources(
        QueueSession([source, source_artifact, artifact]),  # type: ignore[arg-type]
        snapshot,
        object_store=MemoryReader(content),
        workspace=tmp_path,
    )

    assert manifest.mode == "approved-artifacts"
    assert manifest.artifacts[0].object_sha256 == digest
    assert [fragment.kind for fragment in manifest.artifacts[0].fragments] == [
        "heading",
        "heading",
        "list",
    ]
    assert all(fragment.text_sha256 for fragment in manifest.artifacts[0].fragments)


def test_snapshot_maps_to_default_v2_without_opening_template_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization_id = new_ulid()
    approved_by = new_ulid()
    outline_revision_id = new_ulid()
    intent_revision_id = new_ulid()
    template_version_id = new_ulid()
    outline_slide_ids = [new_ulid(), new_ulid(), new_ulid()]
    slide_ids = [new_ulid(), new_ulid(), new_ulid()]
    snapshot = _snapshot(
        organization_id=organization_id,
        payload={
            "approval": {
                "approvedBy": approved_by,
                "approvedAt": "2026-08-18T12:00:00Z",
            },
            "intent": {
                "title": "季度经营复盘",
                "goal": "批准下一季度行动",
                "audience": "经营委员会",
                "language": "zh-CN",
            },
            "outline": {
                "slides": [
                    {
                        "outlineSlideId": outline_slide_ids[0],
                        "type": "cover",
                        "title": "经营复盘",
                    },
                    {
                        "outlineSlideId": outline_slide_ids[1],
                        "type": "data",
                        "title": "关键数据",
                    },
                    {
                        "outlineSlideId": outline_slide_ids[2],
                        "type": "closing",
                        "title": "下一步",
                    },
                ]
            },
            "templateCandidate": {
                "candidateId": template_version_id,
                "descriptorSha256": "c" * 64,
                "workspaceRoot": f"templates/catalog/{template_version_id}",
                "contentAccessed": False,
                "installed": False,
            },
            "providerConfiguration": {"planning": {"model": "kimi-k3"}},
            "authoringPolicy": {
                "mode": "agent-authoring",
                "policyVersion": "presentation-authoring@v1",
                "fallbackReason": None,
                "visualReview": {
                    "required": True,
                    "policyVersion": "visual-review@v1",
                    "maxRounds": 2,
                },
            },
        },
    )
    snapshot.intent_revision_id = intent_revision_id
    snapshot.outline_revision_id = outline_revision_id
    snapshot.template_version_id = template_version_id
    slides = [
        GenerationJobSlide(
            slide_id=slide_id,
            outline_slide_id=outline_slide_id,
            position=index,
            title=title,
        )
        for index, (slide_id, outline_slide_id, title) in enumerate(
            zip(
                slide_ids,
                outline_slide_ids,
                ["经营复盘", "关键数据", "下一步"],
                strict=True,
            ),
            start=1,
        )
    ]
    sources = {
        "mode": "no-source-limited",
        "artifacts": [],
        "manifestSha256": "d" * 64,
        "continueLimitedDraft": True,
    }

    workflow_run_id = new_ulid()
    request = build_default_workflow_request(
        snapshot,
        slides,
        workflow_run_id=workflow_run_id,
        sources=sources,
    )

    assert request.profile == "default-agentic"
    assert [slide.pnn for slide in request.outline] == ["P01", "P02", "P03"]
    assert [slide.role for slide in request.outline] == ["cover", "data", "ending"]
    assert request.template.mode == "free_design"
    assert request.template.active_template_version is None
    assert request.template.candidates[0].content_accessed is False
    assert request.template.candidates[0].installed is False

    slides[0].title = "published runtime title must not change recovery request"
    recovery_request = build_default_workflow_request(
        snapshot,
        slides,
        workflow_run_id=workflow_run_id,
        sources=sources,
    )
    assert recovery_request == request

    snapshot.payload["imagePolicy"] = {
        "scope": "cover_only",
        "usage": ["ai"],
        "notes": {"cover": "non-evidentiary editorial hero"},
        "aiPath": "auto",
        "aiPathChain": ["api", "manual"],
        "providedAssets": [],
        "officeNativeFallbacks": [],
    }
    image_request = build_default_workflow_request(
        snapshot,
        slides,
        workflow_run_id=new_ulid(),
        sources=sources,
    )
    assert image_request.profile == "default-agentic"
    assert image_request.image.scope == "cover_only"
    assert image_request.image.usage == ["ai"]
    assert image_request.image.ai_path_chain == ["api", "manual"]
    assert "provider-image" in image_request.runtime.allowed_tools

    snapshot.payload["providerConfiguration"] = {
        "planning": {
            "model": "kimi-k3",
            "baseUrl": "https://text.example/v1",
            "protocol": "openai",
            "reasoningEffort": "high",
            "timeoutSeconds": 123,
            "transportMaxRetries": 2,
            "retryBackoffSeconds": 3,
        },
        "image": {
            "enabled": True,
            "backend": "openai",
            "baseUrl": "https://frozen.example/v1",
            "model": "gpt-image-2",
            "outputFormat": "png",
            "size": "1536x1024",
            "quality": "low",
            "maxImagesPerDeck": 1,
        },
    }
    monkeypatch.setenv("OPENAI_API_KEY", "runtime-secret")
    environment = _scoped_image_environment(snapshot, image_request)
    assert environment["OPENAI_API_KEY"] == "runtime-secret"
    assert environment["OPENAI_BASE_URL"] == "https://frozen.example/v1"
    assert environment["IMAGE_MAX_PER_DECK"] == "1"
    assert "DATABASE_URL" not in environment

    monkeypatch.setenv("MOONSHOT_API_KEY", "moonshot-runtime-secret")
    text_environment = _scoped_text_environment(snapshot, image_request)
    assert text_environment == {
        "MOONSHOT_API_KEY": "moonshot-runtime-secret",
        "KIMI_BASE_URL": "https://text.example/v1",
        "KIMI_MODEL": "kimi-k3",
        "KIMI_PROTOCOL": "openai",
        "KIMI_REASONING_EFFORT": "high",
        "KIMI_TIMEOUT_SECONDS": "123.0",
        "KIMI_TRANSPORT_MAX_RETRIES": "2",
        "KIMI_RETRY_BACKOFF_SECONDS": "3.0",
    }
