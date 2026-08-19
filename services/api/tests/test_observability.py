from __future__ import annotations

import re

from fastapi.testclient import TestClient
from instant_ppt_api.main import create_app


def test_metrics_are_low_cardinality_and_trace_headers_are_w3c_ids() -> None:
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/v1/history", headers={"X-Dev-User-Subject": "metrics-user"})
        assert response.status_code == 200
        assert re.fullmatch(r"[0-9a-f]{32}", response.headers["X-Trace-ID"])
        assert response.headers["X-Trace-ID"] != "0" * 32

        missing = client.get("/v1/jobs/00000000000000000000000000")
        assert missing.status_code == 404
        metrics = client.get("/internal/metrics")
        assert metrics.status_code == 200
        assert metrics.headers["content-type"].startswith("text/plain")
        body = metrics.text
        assert 'instant_ppt_http_requests_total{method="GET",route="/v1/history"' in body
        assert 'route="/v1/jobs/{job_id}"' in body
        assert "metrics-user" not in body
        assert "instant_ppt_authorization_denials_total{status=\"404\"} 1.0" in body
        assert "instant_ppt_sse_active_connections 0.0" in body
        assert "# HELP instant_ppt_generation_jobs" in body
        assert "# HELP instant_ppt_outbox_events" in body
        assert "# HELP instant_ppt_usage_quantity" in body
        assert "# HELP instant_ppt_reconciliation_runs" in body
        assert "# HELP instant_ppt_generation_queue_latency_seconds" in body
        assert "# HELP instant_ppt_first_preview_seconds" in body
        assert "# HELP instant_ppt_source_stage_duration_seconds" in body
        assert "# HELP instant_ppt_provider_calls" in body
        assert "# HELP instant_ppt_provider_tokens" in body
        assert "# HELP instant_ppt_audit_events" in body
        assert "# HELP instant_ppt_oldest_generation_running_seconds" in body
        assert "# HELP instant_ppt_oldest_source_processing_seconds" in body
        assert "# HELP instant_ppt_oldest_outbox_pending_seconds" in body
        assert "# HELP instant_ppt_sse_reconnections_total" in body
        assert "# HELP instant_ppt_sse_resets_total" in body


def test_metrics_endpoint_is_not_self_counted() -> None:
    app = create_app()
    with TestClient(app) as client:
        client.get("/internal/metrics")
        rendered = client.get("/internal/metrics").text
        assert 'route="/internal/metrics"' not in rendered


def test_health_and_database_readiness_are_explicit_and_hidden_from_openapi() -> None:
    app = create_app()
    with TestClient(app) as client:
        health = client.get("/healthz").json()
        assert health["status"] == "ok"
        assert health["runtime"]["runtimeContractVersion"] == "instant-ppt-runtime@v2"
        assert health["runtime"]["workflowContractVersion"] == "instant-ppt-default@v2.0.0"
        readiness = client.get("/readyz").json()
        assert readiness["status"] == "ready"
        assert readiness["runtime"] == health["runtime"]
        paths = client.get("/openapi.json").json()["paths"]
        assert "/healthz" not in paths
        assert "/readyz" not in paths
