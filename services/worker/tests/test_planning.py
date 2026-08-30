from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from urllib import error as urlerror
from urllib import request

import pytest
from instant_ppt_worker.planning import PlanningCompletion, PlanningService
from instant_ppt_worker.provider_gateway import ProviderGatewayHandler
from instant_ppt_worker.providers import (
    DeterministicFakeProvider,
    ProviderRequestError,
)


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
    service = PlanningService(provider)

    result = service.infer_intent(
        topic="季度经营复盘",
        source_refs=["01ARZ3NDEKTSV4RRFFQ69G5FAV"],
        language="zh-CN",
    )

    assert result.data == response
    assert result.provider == "fake"
    assert result.model == "deterministic-fake-v1"
    assert result.repair_count == 0
    assert provider.calls[0]["maxCompletionTokens"] == 1600


def test_visual_style_planning_returns_exactly_three_accessible_directions() -> None:
    response = {
        "options": [
            {
                "id": "editorial-green",
                "name": "编辑绿",
                "rationale": "克制可信",
                "recommended": index == 0,
                "colors": {
                    "theme": theme,
                    "background": "#F7F5ED",
                    "text": "#17221D",
                    "secondaryText": "#5C6861",
                },
                "typography": {
                    "headingFont": "Noto Sans CJK SC",
                    "bodyFont": "Microsoft YaHei",
                },
            }
            for index, theme in enumerate(("#1E6B4D", "#2356A8", "#A33A2B"))
        ],
    }
    for index, option in enumerate(response["options"]):
        option["id"] = f"direction-{index + 1}"
        option["name"] = f"方案 {index + 1}"
    provider = DeterministicFakeProvider([json.dumps(response, ensure_ascii=False)])
    service = PlanningService(provider)

    result = service.generate_visual_styles(
        intent={"title": "季度复盘", "audience": "管理层"},
        outline={"storySummary": "从结论到行动", "slides": []},
    )

    assert result.data == response
    assert len(result.data["options"]) == 3
    assert sum(option["recommended"] for option in result.data["options"]) == 1
    assert provider.calls[0]["maxCompletionTokens"] == 8000


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
    serialized = json.dumps(response, ensure_ascii=False)
    provider = DeterministicFakeProvider([serialized, serialized, serialized])
    service = PlanningService(provider)

    with pytest.raises(ProviderRequestError):
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
    assert len(provider.calls) == 3
    assert "invented source citations" in provider.calls[1]["messages"][-1]["content"]
    assert provider.calls[0]["maxCompletionTokens"] == 2600


def test_outline_planning_receives_source_text_and_repairs_unsupported_keypoints() -> None:
    source_ref = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
    unsupported = {
        "storySummary": "从公告事实到应用",
        "targetSlideCount": 4,
        "slides": [
            {
                "type": "cover" if index == 0 else ("closing" if index == 3 else "content"),
                "title": "GPT-5.6 公告" if index in {0, 3} else "混合专家架构",
                "keyPoints": ["采用全新混合专家架构"],
                "sourceCitations": [] if index in {0, 3} else [source_ref],
            }
            for index in range(4)
        ],
    }
    supported = {
        "storySummary": "从程序化工具调用到计算机操作能力",
        "targetSlideCount": 4,
        "slides": [
            {
                "type": "cover",
                "title": "GPT-5.6 公告",
                "keyPoints": ["官方能力更新"],
                "sourceCitations": [],
            },
            {
                "type": "content",
                "title": "程序化工具调用",
                "keyPoints": ["程序化工具调用可协调工具并处理中间结果"],
                "sourceCitations": [source_ref],
            },
            {
                "type": "content",
                "title": "计算机操作能力",
                "keyPoints": ["更强的计算机操作能力可检查并优化渲染结果"],
                "sourceCitations": [source_ref],
            },
            {
                "type": "closing",
                "title": "总结",
                "keyPoints": ["持续关注官方进展"],
                "sourceCitations": [],
            },
        ],
    }
    provider = DeterministicFakeProvider(
        [
            json.dumps(unsupported, ensure_ascii=False),
            json.dumps(supported, ensure_ascii=False),
        ]
    )
    service = PlanningService(provider)
    source_text = (
        "Responses API 中的程序化工具调用可协调工具并处理中间结果。\n"
        "更强的计算机操作能力可以检查并优化渲染结果。"
    )

    result = service.generate_outline(
        intent={
            "title": "GPT-5.6 公告",
            "targetSlideCount": 4,
            "language": "zh-CN",
            "sourceRefs": [source_ref],
        },
        existing=None,
        instruction="",
        action="generate",
        target_slide_id=None,
        source_context={
            "documents": [
                {
                    "sourceRef": source_ref,
                    "sha256": "a" * 64,
                    "text": source_text,
                    "truncated": False,
                }
            ]
        },
    )

    assert result.data == supported
    assert result.repair_count == 1
    first_payload = json.loads(provider.calls[0]["messages"][1]["content"])
    assert first_payload["sourceContext"]["documents"][0]["text"] == source_text


def test_planning_service_delegates_retries_to_durable_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, object] = {}
    provider = DeterministicFakeProvider()
    provider.provider_name = "qwen"

    def create_provider(name: str | None, *, transport_max_retries: int):
        observed.update({"name": name, "transportMaxRetries": transport_max_retries})
        return provider

    monkeypatch.setenv("PLANNING_BACKEND", "qwen")
    monkeypatch.setenv("PLANNING_TRANSPORT_MAX_RETRIES", "0")
    monkeypatch.setattr("instant_ppt_worker.planning.create_text_provider", create_provider)

    service = PlanningService.from_env()

    assert observed == {"name": "qwen", "transportMaxRetries": 0}
    assert service._intent_max_completion_tokens == 18_000
    assert service._outline_max_completion_tokens == 20_000


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
        "instant_ppt_worker.provider_gateway.PlanningService.from_env",
        lambda: FakeService(),
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), ProviderGatewayHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/internal/v1/planning/intent"
        http_request = request.Request(
            url,
            data=json.dumps({"topic": "合成规划", "sourceRefs": [], "language": "zh-CN"}).encode(
                "utf-8"
            ),
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


def test_private_provider_gateway_returns_sanitized_provider_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailedService:
        def infer_intent(self, **_: object) -> PlanningCompletion:
            raise ProviderRequestError(
                "kimi",
                403,
                "safe-request-id",
                "HTTPStatusError",
                "packy_api_error",
                True,
            )

        def close(self) -> None:
            return

    monkeypatch.setenv("PROVIDER_GATEWAY_TOKEN", "private-test-token")
    monkeypatch.setattr(
        "instant_ppt_worker.provider_gateway.PlanningService.from_env",
        lambda: FailedService(),
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), ProviderGatewayHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/internal/v1/planning/intent"
        http_request = request.Request(
            url,
            data=json.dumps({"topic": "代理探测", "sourceRefs": [], "language": "zh-CN"}).encode(
                "utf-8"
            ),
            headers={
                "Authorization": "Bearer private-test-token",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with pytest.raises(urlerror.HTTPError) as captured:
            request.urlopen(http_request, timeout=2)
        body = json.loads(captured.value.read())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert captured.value.code == 502
    assert body == {
        "error": "provider_request_failed",
        "failureKind": "HTTPStatusError",
        "provider": "kimi",
        "retryable": True,
        "upstreamCode": "packy_api_error",
        "upstreamStatus": 403,
    }
