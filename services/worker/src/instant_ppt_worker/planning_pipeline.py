"""Durable execution pipeline for asynchronous planning jobs."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from instant_ppt_domain.ids import new_ulid
from instant_ppt_domain.models import Artifact, SourceArtifact
from instant_ppt_domain.planning_jobs import (
    finish_planning_failure,
    finish_planning_success,
    get_planning_job,
    start_planning_attempt,
)
from instant_ppt_domain.workspace import (
    WorkspaceConflict,
    get_intent_revision,
    get_outline_revision,
    serialize_intent_revision,
    serialize_outline_revision,
)
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from instant_ppt_worker.planning import PlanningService
from instant_ppt_worker.providers import (
    ProviderConfigurationError,
    ProviderRequestError,
)
from instant_ppt_worker.source_pipeline import (
    SourceObjectError,
    WorkerObjectSettings,
    WorkerObjectStore,
)

PLANNING_SOURCE_CONTEXT_MAX_CHARS = 200_000


@dataclass(frozen=True, slots=True)
class PlanningResult:
    data: dict[str, Any]
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    repair_count: int = 0


class PlanningExecutor(Protocol):
    def infer_intent(
        self, *, topic: str, source_refs: list[str], language: str
    ) -> Any: ...

    def generate_outline(
        self,
        *,
        intent: dict[str, Any],
        existing: dict[str, Any] | None,
        instruction: str,
        action: str,
        target_slide_id: str | None,
        source_context: dict[str, Any] | None = None,
    ) -> Any: ...

    def close(self) -> None: ...


class DeterministicPlanningExecutor:
    """Offline executor retained for local contracts and browser E2E."""

    provider = "fake"
    model = "deterministic-fake-v1"

    @staticmethod
    def _tokens(value: Any) -> int:
        return max(1, len(str(value)) // 2)

    def close(self) -> None:
        return None

    def infer_intent(
        self, *, topic: str, source_refs: list[str], language: str = "zh-CN"
    ) -> PlanningResult:
        title = (topic.strip().splitlines()[0] if topic.strip() else "文档演示")[:200]
        data = {
            "title": title,
            "audience": "管理层" if language == "zh-CN" else "Leadership team",
            "goal": "策略决策" if language == "zh-CN" else "Strategic decision",
            "targetSlideCount": 8,
            "language": language,
            "contentDepth": "conclusion_first",
            "visualPreference": "data_first",
            "notes": (
                "先给结论，再解释证据与行动。"
                if language == "zh-CN"
                else "Lead with conclusions."
            ),
            "sourceRefs": source_refs,
        }
        return PlanningResult(
            data=data,
            provider=self.provider,
            model=self.model,
            input_tokens=self._tokens({"topic": topic, "sourceRefs": source_refs}),
            output_tokens=self._tokens(data),
        )

    def generate_outline(
        self,
        *,
        intent: dict[str, Any],
        existing: dict[str, Any] | None,
        instruction: str,
        action: str,
        target_slide_id: str | None,
        source_context: dict[str, Any] | None = None,
    ) -> PlanningResult:
        del source_context
        count = int(intent["targetSlideCount"])
        language = str(intent["language"])
        if existing:
            slides = [dict(slide) for slide in existing["slides"]]
            story = str(existing["storySummary"])
            if action == "rewrite_slide" and target_slide_id:
                matched = False
                for slide in slides:
                    if slide["outlineSlideId"] == target_slide_id:
                        suffix = instruction.strip()[:80] or (
                            "强化结论与证据"
                            if language == "zh-CN"
                            else "Sharpen the evidence"
                        )
                        slide["keyPoints"] = [suffix, *slide["keyPoints"][:2]]
                        matched = True
                if not matched:
                    raise ValueError("target outline slide does not exist")
            else:
                suffix = instruction.strip()[:120] or (
                    "强化结论、证据与行动的衔接"
                    if language == "zh-CN"
                    else "Strengthen conclusion, evidence, and action"
                )
                story = f"{story.rstrip('。.')}；{suffix}。"
                slides[0] = {
                    **slides[0],
                    "keyPoints": [suffix, *slides[0]["keyPoints"][:2]],
                }
        else:
            zh_titles = [
                "封面与核心命题",
                "一页结论",
                "现状与关键数据",
                "问题拆解",
                "原因与洞察",
                "策略选择",
                "行动路线图",
                "收束与下一步",
            ]
            en_titles = [
                "Cover and thesis",
                "Executive conclusion",
                "Current state and evidence",
                "Problem framing",
                "Root causes",
                "Strategic choices",
                "Action roadmap",
                "Next steps",
            ]
            titles = zh_titles if language == "zh-CN" else en_titles
            roles = (
                ("content", "data", "comparison", "content", "risk_action", "timeline")
                if intent.get("sourceRefs")
                else ("content", "comparison", "timeline", "risk_action")
            )
            slides = [
                {
                    "outlineSlideId": new_ulid(),
                    "type": (
                        "cover"
                        if index == 0
                        else "closing" if index == count - 1 else roles[(index - 1) % len(roles)]
                    ),
                    "title": titles[index % len(titles)],
                    "keyPoints": [
                        (
                            f"围绕“{intent['title']}”给出第 {index + 1} 个清晰论点"
                            if language == "zh-CN"
                            else f"Make argument {index + 1} for {intent['title']}"
                        )
                    ],
                    "sourceCitations": list(intent.get("sourceRefs") or []),
                }
                for index in range(count)
            ]
            story = (
                "从核心结论出发，以证据解释原因，并落到可执行行动。"
                if language == "zh-CN"
                else "Move from conclusion through evidence to executable action."
            )
        data = {"storySummary": story, "targetSlideCount": count, "slides": slides}
        return PlanningResult(
            data=data,
            provider=self.provider,
            model=self.model,
            input_tokens=self._tokens(
                {"intent": intent, "instruction": instruction, "action": action}
            ),
            output_tokens=self._tokens(data),
        )


def create_planning_executor() -> PlanningExecutor:
    if os.getenv("PLANNING_BACKEND", "fake").strip().lower() == "fake":
        return DeterministicPlanningExecutor()
    return PlanningService.from_env()


class RetryablePlanningFailure(RuntimeError):
    pass


class PlanningSourceFailure(RuntimeError):
    pass


class PlanningSourceObjectStore(Protocol):
    def download(self, object_key: str, target: Path, *, max_bytes: int) -> str: ...


@dataclass(frozen=True, slots=True)
class PlanningSourceRecord:
    source_ref: str
    object_key: str
    sha256: str
    size_bytes: int


def _inputs(
    session: Session, job_id: str, organization_id: str
) -> tuple[str, dict[str, Any]]:
    job = get_planning_job(session, job_id, organization_id)
    payload = dict(job.request_payload)
    if job.operation == "intent_infer":
        return job.operation, payload
    intent_id = str(payload["intentRevisionId"])
    intent = serialize_intent_revision(
        get_intent_revision(session, intent_id, organization_id)
    )
    existing_id = payload.get("existingOutlineRevisionId")
    existing = (
        serialize_outline_revision(
            session,
            get_outline_revision(session, str(existing_id), organization_id),
        )
        if existing_id
        else None
    )
    return job.operation, {**payload, "intent": intent, "existing": existing}


def _planning_source_records(
    session: Session,
    organization_id: str,
    source_refs: list[str],
) -> list[PlanningSourceRecord]:
    if not source_refs:
        return []
    rows = session.execute(
        select(SourceArtifact, Artifact)
        .join(Artifact, Artifact.id == SourceArtifact.artifact_id)
        .where(
            SourceArtifact.organization_id == organization_id,
            SourceArtifact.kind == "markdown",
            SourceArtifact.artifact_id.in_(source_refs),
            Artifact.organization_id == organization_id,
            Artifact.status == "published",
        )
    ).all()
    by_ref: dict[str, PlanningSourceRecord] = {}
    for _source_artifact, artifact in rows:
        if artifact.retention_expires_at <= datetime.now(UTC):
            raise PlanningSourceFailure("planning source retention pin expired")
        if artifact.media_type not in {"text/markdown", "text/plain"}:
            continue
        by_ref[artifact.id] = PlanningSourceRecord(
            source_ref=artifact.id,
            object_key=artifact.object_key,
            sha256=artifact.sha256,
            size_bytes=artifact.size_bytes,
        )
    return [by_ref[value] for value in source_refs if value in by_ref]


def _load_planning_source_context(
    records: list[PlanningSourceRecord],
    object_store: PlanningSourceObjectStore,
) -> dict[str, Any] | None:
    if not records:
        return None
    remaining = int(
        os.getenv(
            "PLANNING_SOURCE_CONTEXT_MAX_CHARS",
            str(PLANNING_SOURCE_CONTEXT_MAX_CHARS),
        )
    )
    if not 10_000 <= remaining <= 600_000:
        raise PlanningSourceFailure(
            "PLANNING_SOURCE_CONTEXT_MAX_CHARS must be between 10000 and 600000"
        )
    documents: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="instant-ppt-planning-") as directory:
        root = Path(directory)
        for record in records:
            if remaining <= 0:
                break
            target = root / f"{record.source_ref}.md"
            actual_sha256 = object_store.download(
                record.object_key,
                target,
                max_bytes=record.size_bytes,
            )
            if actual_sha256 != record.sha256:
                raise PlanningSourceFailure("planning source bytes changed")
            text = target.read_text(encoding="utf-8")
            excerpt = text[:remaining]
            remaining -= len(excerpt)
            documents.append(
                {
                    "sourceRef": record.source_ref,
                    "sha256": record.sha256,
                    "text": excerpt,
                    "truncated": len(excerpt) < len(text),
                }
            )
    if not documents:
        raise PlanningSourceFailure("approved planning source has no usable text")
    return {"documents": documents}


def process_planning_job(
    session_factory: sessionmaker[Session],
    job_id: str,
    organization_id: str,
    *,
    executor: PlanningExecutor | None = None,
    source_object_store: PlanningSourceObjectStore | None = None,
) -> str:
    source_records: list[PlanningSourceRecord] = []
    with session_factory.begin() as session:
        job = start_planning_attempt(session, job_id, organization_id)
        if job.status in {"succeeded", "failed"}:
            return job.status
        operation, inputs = _inputs(session, job_id, organization_id)
        if operation != "intent_infer":
            source_records = _planning_source_records(
                session,
                organization_id,
                [str(item) for item in inputs["intent"].get("sourceRefs") or []],
            )

    planner: PlanningExecutor | None = None
    owns_planner = executor is None
    try:
        source_context = None
        if source_records:
            store = source_object_store or WorkerObjectStore(
                WorkerObjectSettings.from_env()
            )
            source_context = _load_planning_source_context(source_records, store)
        planner = executor or create_planning_executor()
        if operation == "intent_infer":
            result = planner.infer_intent(
                topic=str(inputs["topic"]),
                source_refs=[str(item) for item in inputs.get("sourceRefs") or []],
                language=str(inputs.get("language") or "zh-CN"),
            )
        else:
            result = planner.generate_outline(
                intent=dict(inputs["intent"]),
                existing=(dict(inputs["existing"]) if inputs.get("existing") else None),
                instruction=str(inputs.get("instruction") or ""),
                action=str(inputs.get("action") or "generate"),
                target_slide_id=(
                    str(inputs["targetSlideId"]) if inputs.get("targetSlideId") else None
                ),
                source_context=source_context,
            )
    except (PlanningSourceFailure, SourceObjectError):
        with session_factory.begin() as session:
            finish_planning_failure(
                session,
                job_id,
                organization_id,
                error_code="PLANNING_SOURCE_UNAVAILABLE",
                retryable=False,
            )
        return "failed"
    except ProviderRequestError as error:
        code = error.upstream_code or error.failure_kind or "PROVIDER_UNAVAILABLE"
        with session_factory.begin() as session:
            job = finish_planning_failure(
                session,
                job_id,
                organization_id,
                error_code=code,
                retryable=bool(error.retryable),
            )
        if job.status == "retrying":
            raise RetryablePlanningFailure(code) from error
        return "failed"
    except ProviderConfigurationError:
        with session_factory.begin() as session:
            finish_planning_failure(
                session,
                job_id,
                organization_id,
                error_code="PROVIDER_NOT_CONFIGURED",
                retryable=False,
            )
        return "failed"
    except (KeyError, TypeError, ValueError):
        with session_factory.begin() as session:
            finish_planning_failure(
                session,
                job_id,
                organization_id,
                error_code="PLANNING_SCHEMA_INVALID",
                retryable=False,
            )
        return "failed"
    except Exception as error:
        with session_factory.begin() as session:
            job = finish_planning_failure(
                session,
                job_id,
                organization_id,
                error_code="PLANNING_INTERNAL_ERROR",
                retryable=True,
            )
        if job.status == "retrying":
            raise RetryablePlanningFailure("PLANNING_INTERNAL_ERROR") from error
        return "failed"
    finally:
        if owns_planner and planner is not None:
            try:
                planner.close()
            except Exception:
                pass

    try:
        with session_factory.begin() as session:
            finish_planning_success(
                session,
                job_id,
                organization_id,
                result=dict(result.data),
                provider=str(result.provider),
                model=str(result.model),
                input_tokens=int(result.input_tokens),
                output_tokens=int(result.output_tokens),
                repair_count=int(result.repair_count),
            )
    except WorkspaceConflict:
        with session_factory.begin() as session:
            finish_planning_failure(
                session,
                job_id,
                organization_id,
                error_code="PLANNING_BASE_REVISION_STALE",
                retryable=False,
            )
        return "failed"
    return "succeeded"
