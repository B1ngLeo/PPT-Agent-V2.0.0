"""Bounded, low-cardinality API metrics and OpenTelemetry tracing."""

from __future__ import annotations

import os
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from fastapi import FastAPI, Request, Response
from instant_ppt_domain.models import (
    Artifact,
    AuditLog,
    ExportJob,
    GenerationJob,
    GenerationJobSlide,
    JobEvent,
    ObjectReconciliationRun,
    OutboxEvent,
    ProjectCleanupJob,
    ProviderCall,
    Source,
    UsageLedger,
    UsageReservation,
    WorkflowAgentToolCall,
    WorkflowAgentTurn,
    WorkflowRun,
)
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from prometheus_client.core import GaugeMetricFamily, SummaryMetricFamily
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker


class DatabaseMetricsCollector:
    """Aggregate durable state without tenant or resource identifiers in labels."""

    def __init__(self, factory: sessionmaker[Session]) -> None:
        self.factory = factory

    @staticmethod
    def _grouped(session: Session, model: Any, *columns: Any) -> list[tuple[Any, ...]]:
        return list(session.execute(select(*columns, func.count(model.id)).group_by(*columns)))

    def collect(self):
        with self.factory() as session:
            jobs = GaugeMetricFamily(
                "instant_ppt_generation_jobs",
                "Durable generation jobs by status and stage.",
                labels=["status", "stage"],
            )
            for status, stage, count in self._grouped(
                session, GenerationJob, GenerationJob.status, GenerationJob.stage
            ):
                jobs.add_metric([status, stage], count)
            yield jobs

            authoring_runs = GaugeMetricFamily(
                "instant_ppt_authoring_runs",
                "Durable presentation authoring runs by explicit mode and status.",
                labels=["mode", "status"],
            )
            for profile, status, count in self._grouped(
                session, WorkflowRun, WorkflowRun.profile, WorkflowRun.status
            ):
                mode = (
                    "agent-authoring"
                    if profile == "default-agentic"
                    else "deterministic-template"
                    if profile == "deterministic-template"
                    else "quick-engineering"
                )
                authoring_runs.add_metric([mode, status], count)
            yield authoring_runs

            authoring_decisions = GaugeMetricFamily(
                "instant_ppt_authoring_decisions",
                "Durable authoring decisions used for fallback and manual-intervention rates.",
                labels=["decision"],
            )
            authoring_decisions.add_metric(
                ["fallback"],
                int(
                    session.scalar(
                        select(func.count(WorkflowRun.id)).where(
                            WorkflowRun.profile == "deterministic-template"
                        )
                    )
                    or 0
                ),
            )
            authoring_decisions.add_metric(
                ["needs_manual"],
                int(
                    session.scalar(
                        select(func.count(WorkflowRun.id)).where(
                            WorkflowRun.status == "needs_manual"
                        )
                    )
                    or 0
                ),
            )
            yield authoring_decisions

            agent_turns = GaugeMetricFamily(
                "instant_ppt_agent_turns",
                "Durable Main Presentation Agent turns by role and status.",
                labels=["role", "status"],
            )
            for role, status, count in self._grouped(
                session,
                WorkflowAgentTurn,
                WorkflowAgentTurn.role,
                WorkflowAgentTurn.status,
            ):
                agent_turns.add_metric([role, status], count)
            yield agent_turns

            agent_tokens = GaugeMetricFamily(
                "instant_ppt_agent_tokens",
                "Durable Main Presentation Agent token usage by role and direction.",
                labels=["role", "direction"],
            )
            agent_cost = GaugeMetricFamily(
                "instant_ppt_agent_cost_microunits",
                "Durable Main Presentation Agent cost by role.",
                labels=["role"],
            )
            for role, input_tokens, output_tokens, cost in session.execute(
                select(
                    WorkflowAgentTurn.role,
                    func.coalesce(func.sum(WorkflowAgentTurn.input_tokens), 0),
                    func.coalesce(func.sum(WorkflowAgentTurn.output_tokens), 0),
                    func.coalesce(func.sum(WorkflowAgentTurn.cost_microunits), 0),
                ).group_by(WorkflowAgentTurn.role)
            ):
                agent_tokens.add_metric([role, "input"], input_tokens)
                agent_tokens.add_metric([role, "output"], output_tokens)
                agent_cost.add_metric([role], cost)
            yield agent_tokens
            yield agent_cost

            def phase_kind(phase_id: str) -> str:
                if phase_id == "strategist":
                    return "strategist"
                if phase_id.startswith("visual-review-"):
                    return "review"
                if phase_id.startswith("visual-repair-"):
                    return "repair"
                if phase_id.startswith("executor-"):
                    return "executor"
                return "other"

            phase_totals: dict[tuple[str, str], tuple[int, float]] = {}
            for phase_id, status, count, total in session.execute(
                select(
                    WorkflowAgentTurn.phase_id,
                    WorkflowAgentTurn.status,
                    func.count(WorkflowAgentTurn.id),
                    func.sum(WorkflowAgentTurn.elapsed_seconds),
                ).group_by(WorkflowAgentTurn.phase_id, WorkflowAgentTurn.status)
            ):
                key = (phase_kind(phase_id), status)
                previous_count, previous_total = phase_totals.get(key, (0, 0.0))
                phase_totals[key] = (
                    previous_count + int(count),
                    previous_total + float(total or 0),
                )
            agent_duration = SummaryMetricFamily(
                "instant_ppt_agent_phase_duration_seconds",
                "Durable Main Presentation Agent turn duration by bounded phase and status.",
                labels=["phase", "status"],
            )
            for (phase, status), (count, total) in phase_totals.items():
                agent_duration.add_metric([phase, status], count, total)
            yield agent_duration

            agent_tools = GaugeMetricFamily(
                "instant_ppt_agent_tool_calls",
                "Durable Main Presentation Agent tool calls by allowlisted tool and status.",
                labels=["tool", "status"],
            )
            for tool_name, status, count in self._grouped(
                session,
                WorkflowAgentToolCall,
                WorkflowAgentToolCall.tool_name,
                WorkflowAgentToolCall.status,
            ):
                agent_tools.add_metric([tool_name, status], count)
            yield agent_tools

            agent_pages = GaugeMetricFamily(
                "instant_ppt_agent_page_writes",
                "Durable Agent-authored page write attempts and outcomes.",
                labels=["status"],
            )
            for status, count in session.execute(
                select(
                    WorkflowAgentToolCall.status,
                    func.count(WorkflowAgentToolCall.id),
                )
                .where(
                    WorkflowAgentToolCall.tool_name == "write_or_patch_slide_svg",
                    WorkflowAgentToolCall.current_pnn.is_not(None),
                )
                .group_by(WorkflowAgentToolCall.status)
            ):
                agent_pages.add_metric([status], count)
            yield agent_pages

            agent_repairs = GaugeMetricFamily(
                "instant_ppt_agent_repairs",
                "Durable page repair attempts after the first authoring attempt.",
                labels=["kind"],
            )
            repairs = int(
                session.scalar(
                    select(func.count(WorkflowAgentToolCall.id)).where(
                        WorkflowAgentToolCall.tool_name
                        == "write_or_patch_slide_svg",
                        WorkflowAgentToolCall.author_attempt > 1,
                    )
                )
                or 0
            )
            agent_repairs.add_metric(["page"], repairs)
            yield agent_repairs

            oldest_running = GaugeMetricFamily(
                "instant_ppt_oldest_generation_running_seconds",
                "Age of the oldest generation job still running.",
            )
            oldest_running.add_metric(
                [],
                float(
                    session.scalar(
                        select(
                            func.coalesce(
                                func.extract(
                                    "epoch", func.now() - func.min(GenerationJob.updated_at)
                                ),
                                0,
                            )
                        ).where(GenerationJob.status == "running")
                    )
                    or 0
                ),
            )
            yield oldest_running

            generation_duration = SummaryMetricFamily(
                "instant_ppt_generation_duration_seconds",
                "Completed generation duration from durable creation to terminal state.",
                labels=["processor", "status"],
            )
            for processor, status, count, total in session.execute(
                select(
                    GenerationJob.processor,
                    GenerationJob.status,
                    func.count(GenerationJob.id),
                    func.sum(
                        func.extract(
                            "epoch", GenerationJob.terminal_at - GenerationJob.created_at
                        )
                    ),
                )
                .where(GenerationJob.terminal_at.is_not(None))
                .group_by(GenerationJob.processor, GenerationJob.status)
            ):
                generation_duration.add_metric(
                    [processor, status], int(count), float(total or 0)
                )
            yield generation_duration

            started_events = (
                select(
                    JobEvent.job_id,
                    func.min(JobEvent.occurred_at).label("first_occurred_at"),
                )
                .where(JobEvent.event_type == "job.started")
                .group_by(JobEvent.job_id)
                .subquery()
            )
            queue_latency = SummaryMetricFamily(
                "instant_ppt_generation_queue_latency_seconds",
                "Generation queue latency from job creation to first durable start event.",
                labels=["processor"],
            )
            for processor, count, total in session.execute(
                select(
                    GenerationJob.processor,
                    func.count(GenerationJob.id),
                    func.sum(
                        func.extract(
                            "epoch",
                            started_events.c.first_occurred_at - GenerationJob.created_at,
                        )
                    ),
                )
                .join(started_events, started_events.c.job_id == GenerationJob.id)
                .group_by(GenerationJob.processor)
            ):
                queue_latency.add_metric([processor], int(count), float(total or 0))
            yield queue_latency

            preview_events = (
                select(
                    JobEvent.job_id,
                    func.min(JobEvent.occurred_at).label("first_occurred_at"),
                )
                .where(JobEvent.event_type == "slide.ready")
                .group_by(JobEvent.job_id)
                .subquery()
            )
            first_preview = SummaryMetricFamily(
                "instant_ppt_first_preview_seconds",
                "Time from job creation to first durable ready slide event.",
                labels=["processor"],
            )
            for processor, count, total in session.execute(
                select(
                    GenerationJob.processor,
                    func.count(GenerationJob.id),
                    func.sum(
                        func.extract(
                            "epoch",
                            preview_events.c.first_occurred_at - GenerationJob.created_at,
                        )
                    ),
                )
                .join(preview_events, preview_events.c.job_id == GenerationJob.id)
                .group_by(GenerationJob.processor)
            ):
                first_preview.add_metric([processor], int(count), float(total or 0))
            yield first_preview

            slides = GaugeMetricFamily(
                "instant_ppt_generation_slides",
                "Durable generation slides by status and stage.",
                labels=["status", "stage"],
            )
            for status, stage, count in self._grouped(
                session,
                GenerationJobSlide,
                GenerationJobSlide.status,
                GenerationJobSlide.stage,
            ):
                slides.add_metric([status, stage], count)
            yield slides

            sources = GaugeMetricFamily(
                "instant_ppt_sources",
                "Sources by pipeline status.",
                labels=["status", "scan_status", "parse_status"],
            )
            for status, scan, parse, count in self._grouped(
                session, Source, Source.status, Source.scan_status, Source.parse_status
            ):
                sources.add_metric([status, scan, parse], count)
            yield sources

            oldest_source = GaugeMetricFamily(
                "instant_ppt_oldest_source_processing_seconds",
                "Age of the oldest source that has not reached a terminal pipeline state.",
            )
            oldest_source.add_metric(
                [],
                float(
                    session.scalar(
                        select(
                            func.coalesce(
                                func.extract("epoch", func.now() - func.min(Source.updated_at)),
                                0,
                            )
                        ).where(
                            Source.status.in_(
                                ("upload_pending", "uploaded", "scanning", "parsing")
                            )
                        )
                    )
                    or 0
                ),
            )
            yield oldest_source

            source_duration = SummaryMetricFamily(
                "instant_ppt_source_stage_duration_seconds",
                "Source scan and parse duration from source creation to durable completion.",
                labels=["stage", "status"],
            )
            for stage, status_column, completed_column in (
                ("scan", Source.scan_status, Source.scan_completed_at),
                ("parse", Source.parse_status, Source.parse_completed_at),
            ):
                for status, count, total in session.execute(
                    select(
                        status_column,
                        func.count(Source.id),
                        func.sum(
                            func.extract("epoch", completed_column - Source.created_at)
                        ),
                    )
                    .where(completed_column.is_not(None))
                    .group_by(status_column)
                ):
                    source_duration.add_metric(
                        [stage, status], int(count), float(total or 0)
                    )
            yield source_duration

            exports = GaugeMetricFamily(
                "instant_ppt_export_jobs",
                "Exact-revision export jobs by status and stage.",
                labels=["status", "stage"],
            )
            for status, stage, count in self._grouped(
                session, ExportJob, ExportJob.status, ExportJob.stage
            ):
                exports.add_metric([status, stage], count)
            yield exports

            artifacts = GaugeMetricFamily(
                "instant_ppt_artifacts",
                "Artifact records by bounded type and status.",
                labels=["artifact_type", "status"],
            )
            for artifact_type, status, count in self._grouped(
                session, Artifact, Artifact.artifact_type, Artifact.status
            ):
                artifacts.add_metric([artifact_type, status], count)
            yield artifacts

            outbox = GaugeMetricFamily(
                "instant_ppt_outbox_events",
                "Outbox events by dispatch status and kind.",
                labels=["status", "kind"],
            )
            for status, kind, count in self._grouped(
                session, OutboxEvent, OutboxEvent.status, OutboxEvent.kind
            ):
                outbox.add_metric([status, kind], count)
            yield outbox

            oldest_outbox = GaugeMetricFamily(
                "instant_ppt_oldest_outbox_pending_seconds",
                "Age of the oldest pending transactional outbox event.",
            )
            oldest_outbox.add_metric(
                [],
                float(
                    session.scalar(
                        select(
                            func.coalesce(
                                func.extract(
                                    "epoch", func.now() - func.min(OutboxEvent.created_at)
                                ),
                                0,
                            )
                        ).where(OutboxEvent.status == "pending")
                    )
                    or 0
                ),
            )
            yield oldest_outbox

            reservations = GaugeMetricFamily(
                "instant_ppt_usage_reservations",
                "Usage reservations by status.",
                labels=["status"],
            )
            for status, count in self._grouped(
                session, UsageReservation, UsageReservation.status
            ):
                reservations.add_metric([status], count)
            yield reservations

            usage = GaugeMetricFamily(
                "instant_ppt_usage_quantity",
                "Durable settled usage by metric.",
                labels=["metric"],
            )
            for metric, quantity in session.execute(
                select(
                    UsageLedger.metric,
                    func.coalesce(func.sum(UsageLedger.quantity), 0),
                ).group_by(UsageLedger.metric)
            ):
                usage.add_metric([metric], quantity)
            yield usage

            provider_calls = GaugeMetricFamily(
                "instant_ppt_provider_calls",
                "Durable provider calls by bounded provider, purpose, and status.",
                labels=["provider", "purpose", "status"],
            )
            for provider, purpose, status, count in self._grouped(
                session,
                ProviderCall,
                ProviderCall.provider,
                ProviderCall.purpose,
                ProviderCall.status,
            ):
                provider_calls.add_metric([provider, purpose, status], count)
            yield provider_calls

            provider_tokens = GaugeMetricFamily(
                "instant_ppt_provider_tokens",
                "Durable provider token usage by provider, purpose, and direction.",
                labels=["provider", "purpose", "direction"],
            )
            for provider, purpose, input_tokens, output_tokens in session.execute(
                select(
                    ProviderCall.provider,
                    ProviderCall.purpose,
                    func.coalesce(func.sum(ProviderCall.input_tokens), 0),
                    func.coalesce(func.sum(ProviderCall.output_tokens), 0),
                ).group_by(ProviderCall.provider, ProviderCall.purpose)
            ):
                provider_tokens.add_metric([provider, purpose, "input"], input_tokens)
                provider_tokens.add_metric([provider, purpose, "output"], output_tokens)
            yield provider_tokens

            provider_duration = SummaryMetricFamily(
                "instant_ppt_provider_duration_seconds",
                "Durable provider call duration.",
                labels=["provider", "purpose", "status"],
            )
            for provider, purpose, status, count, total in session.execute(
                select(
                    ProviderCall.provider,
                    ProviderCall.purpose,
                    ProviderCall.status,
                    func.count(ProviderCall.id),
                    func.sum(
                        func.extract(
                            "epoch", ProviderCall.finished_at - ProviderCall.started_at
                        )
                    ),
                ).group_by(
                    ProviderCall.provider, ProviderCall.purpose, ProviderCall.status
                )
            ):
                provider_duration.add_metric(
                    [provider, purpose, status], int(count), float(total or 0)
                )
            yield provider_duration

            audit_events = GaugeMetricFamily(
                "instant_ppt_audit_events",
                "Durable security and mutation audit events by bounded action and outcome.",
                labels=["action", "outcome"],
            )
            for action, outcome, count in self._grouped(
                session, AuditLog, AuditLog.action, AuditLog.outcome
            ):
                audit_events.add_metric([action, outcome], count)
            yield audit_events

            cleanup = GaugeMetricFamily(
                "instant_ppt_cleanup_jobs",
                "Project cleanup jobs by status.",
                labels=["status"],
            )
            for status, count in self._grouped(
                session, ProjectCleanupJob, ProjectCleanupJob.status
            ):
                cleanup.add_metric([status], count)
            yield cleanup

            reconciliation = GaugeMetricFamily(
                "instant_ppt_reconciliation_runs",
                "Object reconciliation runs by status.",
                labels=["status"],
            )
            for status, count in self._grouped(
                session, ObjectReconciliationRun, ObjectReconciliationRun.status
            ):
                reconciliation.add_metric([status], count)
            yield reconciliation


@dataclass(slots=True)
class ApiMetrics:
    """All process-local metrics use bounded labels and an isolated registry."""

    registry: CollectorRegistry
    requests: Counter
    request_latency: Histogram
    active_requests: Gauge
    sse_active: Gauge
    sse_connections: Counter
    sse_replays: Counter
    sse_reconnects: Counter
    sse_resets: Counter
    authorization_denials: Counter

    def render(self) -> Response:
        return Response(generate_latest(self.registry), media_type=CONTENT_TYPE_LATEST)


@dataclass(slots=True)
class Observability:
    metrics: ApiMetrics
    tracer_provider: TracerProvider

    def shutdown(self) -> None:
        self.tracer_provider.shutdown()


def _metrics(factory: sessionmaker[Session]) -> ApiMetrics:
    registry = CollectorRegistry()
    registry.register(DatabaseMetricsCollector(factory))
    return ApiMetrics(
        registry=registry,
        requests=Counter(
            "instant_ppt_http_requests_total",
            "Completed HTTP requests.",
            ("method", "route", "status_class"),
            registry=registry,
        ),
        request_latency=Histogram(
            "instant_ppt_http_request_duration_seconds",
            "HTTP request duration without external asynchronous work.",
            ("method", "route"),
            buckets=(0.01, 0.025, 0.05, 0.1, 0.2, 0.3, 0.5, 1.0, 2.0, 5.0),
            registry=registry,
        ),
        active_requests=Gauge(
            "instant_ppt_http_active_requests",
            "HTTP requests currently executing.",
            registry=registry,
        ),
        sse_active=Gauge(
            "instant_ppt_sse_active_connections",
            "Active SSE connections.",
            registry=registry,
        ),
        sse_connections=Counter(
            "instant_ppt_sse_connections_total",
            "SSE connections opened.",
            registry=registry,
        ),
        sse_replays=Counter(
            "instant_ppt_sse_replayed_events_total",
            "Durable PostgreSQL events replayed to SSE clients.",
            registry=registry,
        ),
        sse_reconnects=Counter(
            "instant_ppt_sse_reconnections_total",
            "SSE connections carrying a Last-Event-ID cursor.",
            registry=registry,
        ),
        sse_resets=Counter(
            "instant_ppt_sse_resets_total",
            "SSE cursors rejected because the durable sequence is unavailable.",
            registry=registry,
        ),
        authorization_denials=Counter(
            "instant_ppt_authorization_denials_total",
            "Authorization failures grouped by externally visible status.",
            ("status",),
            registry=registry,
        ),
    )


def create_observability(
    factory: sessionmaker[Session], service_name: str = "instant-ppt-api"
) -> Observability:
    """Create per-app telemetry; exporters are opt-in through standard OTEL env vars."""
    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": service_name,
                "service.version": "0.0.0",
                "deployment.environment.name": os.getenv("APP_ENVIRONMENT", "local"),
            }
        )
    )
    exporter_enabled = os.getenv("OTEL_TRACES_EXPORTER", "otlp").strip().lower() != "none"
    endpoint_configured = bool(
        os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
        or os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
    )
    if exporter_enabled and endpoint_configured:
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    return Observability(metrics=_metrics(factory), tracer_provider=provider)


def configure_observability(application: FastAPI, observability: Observability) -> None:
    """Attach ASGI tracing without capturing request bodies or sensitive headers."""
    FastAPIInstrumentor.instrument_app(
        application,
        tracer_provider=observability.tracer_provider,
        excluded_urls="/internal/metrics",
        exclude_spans=["receive", "send"],
    )


def observe_request_start(metrics: ApiMetrics) -> float:
    metrics.active_requests.inc()
    return perf_counter()


def observe_request_end(
    metrics: ApiMetrics,
    *,
    started_at: float,
    method: str,
    route: str,
    status_code: int,
) -> None:
    metrics.active_requests.dec()
    if route == "/internal/metrics":
        return
    status_class = f"{status_code // 100}xx"
    metrics.requests.labels(method=method, route=route, status_class=status_class).inc()
    metrics.request_latency.labels(method=method, route=route).observe(
        max(0.0, perf_counter() - started_at)
    )
    if status_code in {401, 403, 404}:
        metrics.authorization_denials.labels(status=str(status_code)).inc()


def annotate_current_span(request: Request, *, status_code: int) -> str:
    """Return a W3C trace ID and add only allowlisted correlation attributes."""
    span = trace.get_current_span()
    context = span.get_span_context()
    trace_id = f"{context.trace_id:032x}" if context.is_valid else "0" * 32
    if span.is_recording():
        auth = getattr(request.state, "auth_context", None)
        attributes: dict[str, Any] = {
            "instant_ppt.request_id": request.state.request_id,
            "instant_ppt.response_status": status_code,
        }
        if auth is not None:
            attributes["instant_ppt.organization_id"] = auth.organization_id
            attributes["instant_ppt.actor_id"] = auth.user_id
        for key, value in attributes.items():
            span.set_attribute(key, value)
    return trace_id
