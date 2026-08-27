from __future__ import annotations

import json
from io import BytesIO
from urllib import error

import pytest
from instant_ppt_api.planning import (
    DeterministicPlanningGateway,
    PlanningGatewaySettings,
    PlanningUnavailableError,
    RemotePlanningGateway,
    create_planning_gateway,
)


def test_remote_planning_gateway_uses_private_token_and_maps_result() -> None:
    observed: dict[str, object] = {}

    def sender(url: str, body: bytes, headers: dict[str, str], timeout: float):
        observed.update(
            {"url": url, "body": json.loads(body), "headers": headers, "timeout": timeout}
        )
        return {
            "data": {
                "title": "季度复盘",
                "audience": "管理层",
                "goal": "形成决策",
                "targetSlideCount": 8,
                "language": "zh-CN",
                "contentDepth": "conclusion_first",
                "visualPreference": "data_first",
                "notes": "先给结论",
                "sourceRefs": [],
            },
            "provider": "kimi",
            "model": "kimi-k3",
            "inputTokens": 21,
            "outputTokens": 34,
            "repairCount": 1,
        }

    gateway = RemotePlanningGateway(
        PlanningGatewaySettings(
            backend="kimi",
            gateway_url="http://provider-gateway:8090/internal/v1",
            gateway_token="internal-test-token",
            timeout_seconds=12,
        ),
        sender=sender,
    )
    result = gateway.infer_intent(topic="季度复盘", source_refs=[], language="zh-CN")

    assert observed == {
        "url": "http://provider-gateway:8090/internal/v1/planning/intent",
        "body": {"language": "zh-CN", "sourceRefs": [], "topic": "季度复盘"},
        "headers": {
            "Authorization": "Bearer internal-test-token",
            "Content-Type": "application/json",
        },
        "timeout": 12,
    }
    assert result.provider == "kimi"
    assert result.model == "kimi-k3"
    assert result.input_tokens == 21
    assert result.output_tokens == 34
    assert result.repair_count == 1
    assert "internal-test-token" not in repr(gateway._settings)


def test_planning_factory_keeps_fake_default_and_requires_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PLANNING_BACKEND", raising=False)
    assert isinstance(create_planning_gateway(), DeterministicPlanningGateway)

    with pytest.raises(ValueError, match="PROVIDER_GATEWAY_TOKEN"):
        create_planning_gateway(PlanningGatewaySettings(backend="kimi"))
    with pytest.raises(ValueError, match="PROVIDER_GATEWAY_TOKEN"):
        create_planning_gateway(PlanningGatewaySettings(backend="qwen"))

    monkeypatch.setenv("APP_ENVIRONMENT", "production")
    with pytest.raises(ValueError, match="development Provider Gateway token"):
        create_planning_gateway(
            PlanningGatewaySettings(
                backend="kimi",
                gateway_token="local-development-provider-gateway-only",
            )
        )


def test_remote_planning_gateway_preserves_sanitized_upstream_failure() -> None:
    def sender(url: str, body: bytes, headers: dict[str, str], timeout: float):
        del body, headers, timeout
        payload = json.dumps(
            {
                "error": "provider_request_failed",
                "failureKind": "HTTPStatusError",
                "provider": "kimi",
                "retryable": True,
                "upstreamCode": "packy_api_error",
                "upstreamStatus": 403,
            }
        ).encode("utf-8")
        raise error.HTTPError(url, 502, "Bad Gateway", {}, BytesIO(payload))

    gateway = RemotePlanningGateway(
        PlanningGatewaySettings(
            backend="kimi",
            gateway_url="http://provider-gateway:8090/internal/v1",
            gateway_token="internal-test-token",
        ),
        sender=sender,
    )

    with pytest.raises(PlanningUnavailableError) as captured:
        gateway.infer_intent(topic="代理探测", source_refs=[], language="zh-CN")

    assert captured.value.upstream_status == 403
    assert captured.value.upstream_code == "packy_api_error"
    assert captured.value.failure_kind == "HTTPStatusError"
