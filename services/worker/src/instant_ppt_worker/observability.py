"""OpenTelemetry task spans with allowlisted, non-content attributes."""

from __future__ import annotations

import logging
import os
from typing import Any

from celery import Task
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import SpanKind, Status, StatusCode

_logger = logging.getLogger("instant_ppt_worker.task")


def _provider() -> TracerProvider:
    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": "instant-ppt-worker",
                "service.version": "2.1.0",
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
    return provider


_tracer_provider = _provider()
_tracer = _tracer_provider.get_tracer("instant_ppt_worker.tasks")


class ObservedTask(Task):
    """Celery task base that never records document bodies, prompts, or credentials."""

    abstract = True

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        attributes: dict[str, str] = {
            "messaging.system": "celery",
            "messaging.operation.name": "process",
            "celery.task.name": self.name or type(self).__name__,
            "celery.task.id": str(getattr(self.request, "id", "unknown")),
        }
        if args:
            attributes["instant_ppt.resource_id"] = str(args[0])
        if len(args) > 1:
            attributes["instant_ppt.organization_id"] = str(args[1])
        with _tracer.start_as_current_span(
            self.name or type(self).__name__,
            kind=SpanKind.CONSUMER,
            attributes=attributes,
        ) as span:
            try:
                result = super().__call__(*args, **kwargs)
            except BaseException as error:
                span.record_exception(error, attributes={"exception.escaped": True})
                span.set_status(Status(StatusCode.ERROR, type(error).__name__))
                raise
            context = span.get_span_context()
            _logger.info(
                "task_completed task=%s task_id=%s trace_id=%032x",
                self.name,
                getattr(self.request, "id", "unknown"),
                context.trace_id,
            )
            return result
