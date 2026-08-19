from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from urllib import request

import pytest
from instant_ppt_worker.planning import KimiPlanningService, PlanningCompletion
from instant_ppt_worker.provider_gateway import ProviderGatewayHandler
from instant_ppt_worker.providers import DeterministicFakeProvider


def test_kimi_planning_service_validates_intent_and_preserves_source_refs() -> None:
    response = {
        "title": "季度经营复盘",
        "audience": "管理层",
        "goal": "确定下一季度行动",
        "targetSlideCount": 6,
        "language": "zh-CN",
        "contentDepth": "conclusion_first",
        "visualPreference": "data_first",
        "notes": "先给结论",
        "sourceRefs": ["01ARZ3NDEKTSV4RRFFQ69G5FAV"],
    }
    provider = DeterministicFakeProvider([json.dumps(response, ensure_ascii=False)])
    service = KimiPlanningService(provider)  # type: ignore[arg-type]

    result = service.infer_intent(
        topic="季度经营复盘",
        source_refs=["01ARZ3NDEKTSV4RRFFQ69G5FAV"],
        language="zh-CN",
    )

    assert result.data == response
    assert result.provider == "fake"
    assert result.model == "deterministic-fake-v1"
    assert result.repair_count == 0


def test_kimi_planning_service_rejects_invented_citations() -> None:
    response = {
        "storySummary": "从结论到行动",
        "targetSlideCount": 4,
        "slides": [
            {
                "type": "cover" if index == 0 else ("closing" if index == 3 else "content"),
                "title": f"第 {index + 1} 页",
                "keyPoints": ["论点"],
                "sourceCitations": ["INVENTED"] if index == 1 else [],
            }
            for index in range(4)
        ],
    }
    provider = DeterministicFakeProvider([json.dumps(response, ensure_ascii=False)])
    service = KimiPlanningService(provider)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="invented source citations"):
        service.generate_outline(
            intent={
                "title": "季度经营复盘",
                "targetSlideCount": 4,
                "language": "zh-CN",
                "sourceRefs": [],
            },
            existing=None,
            instruction="",
            action="generate",
            target_slide_id=None,
        )


def test_private_provider_gateway_requires_token_and_serves_planning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeService:
        def infer_intent(self, **_: object) -> PlanningCompletion:
            return PlanningCompletion(
                data={"title": "合成规划"},
                provider="kimi",
                model="kimi-k3",
                input_tokens=4,
                output_tokens=8,
                repair_count=0,
            )

        def close(self) -> None:
            return

    monkeypatch.setenv("PROVIDER_GATEWAY_TOKEN", "private-test-token")
    monkeypatch.setattr(
        "instant_ppt_worker.provider_gateway.KimiPlanningService.from_env",
        lambda: FakeService(),
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), ProviderGatewayHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/internal/v1/planning/intent"
        http_request = request.Request(
            url,
            data=json.dumps(
                {"topic": "合成规划", "sourceRefs": [], "language": "zh-CN"}
            ).encode("utf-8"),
            headers={
                "Authorization": "Bearer private-test-token",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with request.urlopen(http_request, timeout=2) as response:
            body = json.loads(response.read())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert body == {
        "data": {"title": "合成规划"},
        "provider": "kimi",
        "model": "kimi-k3",
        "inputTokens": 4,
        "outputTokens": 8,
        "repairCount": 0,
    }
