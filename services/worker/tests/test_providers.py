from __future__ import annotations

import base64
import json

import httpx
import pytest
from instant_ppt_worker.providers import (
    DeterministicFakeProvider,
    KimiProvider,
    OpenAIImageProvider,
    ProviderConfigurationError,
    ProviderRequestError,
    StructuredProviderGateway,
)
from instant_ppt_worker.settings import KimiProviderSettings, OpenAIImageSettings


def test_provider_settings_use_expected_defaults_without_exposing_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MOONSHOT_API_KEY", "moonshot-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-secret")

    kimi = KimiProviderSettings.from_env()
    image = OpenAIImageSettings.from_env()

    assert kimi.model == "kimi-k3"
    assert kimi.base_url == "https://api.moonshot.cn/v1"
    assert kimi.reasoning_effort == "max"
    assert image.backend == "openai"
    assert image.model == "gpt-image-2"
    assert "moonshot-secret" not in repr(kimi)
    assert "openai-secret" not in repr(image)


def test_kimi_provider_sends_supported_k3_request() -> None:
    observed: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["url"] = str(request.url)
        observed["authorization"] = request.headers["Authorization"]
        observed["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "kimi-k3",
                "choices": [
                    {
                        "message": {
                            "content": '{"title":"季度复盘"}',
                            "reasoning_content": "internal reasoning",
                        }
                    }
                ],
                "usage": {"prompt_tokens": 11, "completion_tokens": 7},
            },
        )

    provider = KimiProvider(
        KimiProviderSettings(api_key="test-moonshot-key"),
        transport=httpx.MockTransport(handler),
    )
    assert provider.provider_name == "kimi"
    try:
        completion = provider.complete(
            [{"role": "user", "content": "生成大纲"}],
            response_format={"type": "json_object"},
        )
    finally:
        provider.close()

    assert observed["url"] == "https://api.moonshot.cn/v1/chat/completions"
    assert observed["authorization"] == "Bearer test-moonshot-key"
    assert observed["payload"] == {
        "model": "kimi-k3",
        "messages": [{"role": "user", "content": "生成大纲"}],
        "reasoning_effort": "max",
        "response_format": {"type": "json_object"},
    }
    assert completion.content == '{"title":"季度复盘"}'
    assert completion.prompt_tokens == 11
    assert completion.completion_tokens == 7


def test_openai_image_provider_decodes_gpt_image_2_response() -> None:
    image_bytes = b"\x89PNG\r\n\x1a\nfixture"
    observed: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["url"] = str(request.url)
        observed["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"data": [{"b64_json": base64.b64encode(image_bytes).decode("ascii")}]},
        )

    provider = OpenAIImageProvider(
        OpenAIImageSettings(api_key="test-openai-key"),
        transport=httpx.MockTransport(handler),
    )
    assert provider.provider_name == "openai-image"
    try:
        image = provider.generate("蓝色渐变的企业科技背景")
    finally:
        provider.close()

    assert observed["url"] == "https://api.openai.com/v1/images/generations"
    assert observed["payload"] == {
        "model": "gpt-image-2",
        "prompt": "蓝色渐变的企业科技背景",
        "size": "1536x1024",
        "quality": "auto",
        "output_format": "png",
    }
    assert image.content == image_bytes
    assert image.media_type == "image/png"


def test_missing_keys_are_rejected_without_including_secret_values() -> None:
    with pytest.raises(ProviderConfigurationError, match="MOONSHOT_API_KEY"):
        KimiProvider(KimiProviderSettings(api_key=""))
    with pytest.raises(ProviderConfigurationError, match="OPENAI_API_KEY"):
        OpenAIImageProvider(OpenAIImageSettings(api_key=""))


def test_provider_http_error_is_sanitized() -> None:
    secret_body = "upstream detail that must not escape"

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            headers={"x-request-id": "req_safe"},
            text=secret_body,
        )

    provider = KimiProvider(
        KimiProviderSettings(api_key="test-moonshot-key"),
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(ProviderRequestError) as captured:
            provider.complete([{"role": "user", "content": "hello"}])
    finally:
        provider.close()

    assert "status=429" in str(captured.value)
    assert "request_id=req_safe" in str(captured.value)
    assert secret_body not in str(captured.value)


def test_structured_gateway_repairs_once_and_is_repeatable() -> None:
    provider = DeterministicFakeProvider(["not-json", '{"title":"季度复盘","slideCount":8}'])
    gateway = StructuredProviderGateway(provider)

    result = gateway.generate(
        [{"role": "user", "content": "生成季度复盘大纲"}],
        validate=lambda value: (
            value
            if isinstance(value.get("slideCount"), int)
            else (_ for _ in ()).throw(ValueError("slideCount is required"))
        ),
    )

    assert result.value == {"title": "季度复盘", "slideCount": 8}
    assert result.repair_count == 1
    assert len(provider.calls) == 2
    assert provider.calls[1]["responseFormat"] == {"type": "json_object"}


def test_structured_gateway_stops_after_two_repairs() -> None:
    provider = DeterministicFakeProvider(["bad", "still bad", "also bad", '{"ok":true}'])
    gateway = StructuredProviderGateway(provider, max_repairs=2)

    with pytest.raises(ProviderRequestError, match="structured-output"):
        gateway.generate([{"role": "user", "content": "hello"}], validate=lambda value: value)

    assert len(provider.calls) == 3
