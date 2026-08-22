from __future__ import annotations

import base64
import json

import httpx
import pytest
from instant_ppt_domain.models import GenerationSnapshot
from instant_ppt_worker.generation_pipeline import _snapshot_image_settings
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
    assert kimi.protocol == "openai"
    assert kimi.reasoning_effort == "max"
    assert kimi.transport_max_retries == 1
    assert kimi.retry_backoff_seconds == 2
    assert image.backend == "openai"
    assert image.model == "gpt-image-2"
    assert image.enabled is False
    assert image.max_images_per_deck == 0
    assert "moonshot-secret" not in repr(kimi)
    assert "openai-secret" not in repr(image)


def test_generation_uses_image_configuration_frozen_in_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "runtime-secret")
    monkeypatch.setenv("IMAGE_GENERATION_ENABLED", "true")
    monkeypatch.setenv("IMAGE_MAX_PER_DECK", "1")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://runtime.example/v1")
    snapshot = GenerationSnapshot(
        payload={
            "providerConfiguration": {
                "image": {
                    "enabled": True,
                    "backend": "openai",
                    "baseUrl": "https://frozen.example/v1",
                    "model": "gpt-image-2",
                    "outputFormat": "png",
                    "size": "1536x1024",
                    "quality": "low",
                    "maxImagesPerDeck": 1,
                }
            }
        }
    )

    settings = _snapshot_image_settings(snapshot, None)

    assert settings.enabled is True
    assert settings.base_url == "https://frozen.example/v1"
    assert settings.quality == "low"
    assert settings.max_images_per_deck == 1
    assert "runtime-secret" not in repr(settings)


def test_runtime_image_kill_switch_overrides_enabled_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "runtime-secret")
    monkeypatch.setenv("IMAGE_GENERATION_ENABLED", "false")
    monkeypatch.setenv("IMAGE_MAX_PER_DECK", "0")
    snapshot = GenerationSnapshot(
        payload={
            "providerConfiguration": {
                "image": {
                    "enabled": True,
                    "backend": "openai",
                    "model": "gpt-image-2",
                    "maxImagesPerDeck": 1,
                }
            }
        }
    )

    settings = _snapshot_image_settings(snapshot, None)

    assert settings.enabled is False
    assert settings.max_images_per_deck == 0


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


def test_kimi_provider_retries_remote_disconnect_once() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.RemoteProtocolError(
                "server disconnected without sending a response",
                request=request,
            )
        return httpx.Response(
            200,
            json={
                "model": "kimi-k3",
                "choices": [{"message": {"content": '{"ok":true}'}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 4},
            },
        )

    provider = KimiProvider(
        KimiProviderSettings(
            api_key="test-moonshot-key",
            transport_max_retries=1,
            retry_backoff_seconds=0,
        ),
        transport=httpx.MockTransport(handler),
    )
    try:
        completion = provider.complete([{"role": "user", "content": "hello"}])
    finally:
        provider.close()

    assert attempts == 2
    assert completion.content == '{"ok":true}'


def test_openai_image_provider_decodes_gpt_image_2_response() -> None:
    image_bytes = b"\x89PNG\r\n\x1a\nfixture"
    observed: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["url"] = str(request.url)
        observed["payload"] = json.loads(request.content)
        observed["idempotencyKey"] = request.headers.get("Idempotency-Key")
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
        image = provider.generate(
            "蓝色渐变的企业科技背景", idempotency_key="cover-job-v1"
        )
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
    assert observed["idempotencyKey"] == "cover-job-v1"
    assert image.content == image_bytes
    assert image.media_type == "image/png"


def test_kimi_provider_supports_anthropic_compatible_proxy() -> None:
    observed: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["url"] = str(request.url)
        observed["authorization"] = request.headers["Authorization"]
        observed["anthropicVersion"] = request.headers["anthropic-version"]
        observed["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "kimi-k3",
                "content": [{"type": "text", "text": '{"ok":true}'}],
                "usage": {"input_tokens": 117, "output_tokens": 56},
            },
        )

    provider = KimiProvider(
        KimiProviderSettings(
            api_key="test-proxy-key",
            base_url="https://cf.api.fan/v1",
            protocol="anthropic",
        ),
        transport=httpx.MockTransport(handler),
    )
    try:
        completion = provider.complete(
            [
                {"role": "system", "content": "Return only JSON."},
                {"role": "user", "content": "Return ok=true."},
            ],
            response_format={"type": "json_object"},
            max_completion_tokens=64,
        )
    finally:
        provider.close()

    assert observed == {
        "url": "https://cf.api.fan/v1/messages",
        "authorization": "Bearer test-proxy-key",
        "anthropicVersion": "2023-06-01",
        "payload": {
            "model": "kimi-k3",
            "messages": [{"role": "user", "content": "Return ok=true."}],
            "max_tokens": 64,
            "system": "Return only JSON.",
        },
    }
    assert completion.content == '{"ok":true}'
    assert completion.model == "kimi-k3"
    assert completion.prompt_tokens == 117
    assert completion.completion_tokens == 56


def test_missing_keys_are_rejected_without_including_secret_values() -> None:
    with pytest.raises(ProviderConfigurationError, match="MOONSHOT_API_KEY"):
        KimiProvider(KimiProviderSettings(api_key=""))
    with pytest.raises(ProviderConfigurationError, match="OPENAI_API_KEY"):
        OpenAIImageProvider(OpenAIImageSettings(api_key=""))


def test_provider_http_error_is_sanitized() -> None:
    secret_body = "upstream detail that must not escape"
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
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
    assert captured.value.failure_kind == "HTTPStatusError"
    assert attempts == 1


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
