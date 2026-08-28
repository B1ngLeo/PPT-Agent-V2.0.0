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
    QwenProvider,
    StructuredProviderGateway,
    create_text_provider,
    create_visual_review_text_provider,
)
from instant_ppt_worker.settings import (
    KimiProviderSettings,
    OpenAIImageSettings,
    QwenProviderSettings,
)


def test_provider_settings_use_expected_defaults_without_exposing_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MOONSHOT_API_KEY", "moonshot-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-secret")
    monkeypatch.setenv("QWEN_API_KEY", "qwen-secret")

    kimi = KimiProviderSettings.from_env()
    qwen = QwenProviderSettings.from_env()
    image = OpenAIImageSettings.from_env()

    assert kimi.model == "kimi-k3"
    assert kimi.base_url == "https://api.moonshot.cn/v1"
    assert kimi.protocol == "openai"
    assert kimi.reasoning_effort == "max"
    assert kimi.timeout_seconds == 600
    assert kimi.transport_max_retries == 4
    assert kimi.retry_backoff_seconds == 2
    assert qwen.model == "qwen3.8-flash"
    assert qwen.reasoning_effort == "medium"
    assert qwen.enable_thinking is True
    assert qwen.preserve_thinking is False
    assert qwen.streaming is True
    assert image.backend == "openai"
    assert image.model == "gpt-image-2"
    assert image.enabled is False
    assert image.max_images_per_deck == 0
    assert "moonshot-secret" not in repr(kimi)
    assert "qwen-secret" not in repr(qwen)
    assert "openai-secret" not in repr(image)


@pytest.mark.parametrize("model", ["qwen3.7-plus", "qwen3.8-max", "qwen3.8-flash"])
def test_qwen_provider_accepts_supported_models(model: str) -> None:
    provider = QwenProvider(QwenProviderSettings(api_key="test-qwen-key", model=model))
    provider.close()


@pytest.mark.parametrize("model", ["qwen3.8-max", "qwen3.8-flash"])
def test_qwen38_models_disable_preserved_thinking_by_default(model: str) -> None:
    settings = QwenProviderSettings(api_key="test-qwen-key", model=model)
    assert settings.preserve_thinking is False

    provider = QwenProvider(settings)
    try:
        assert provider.preserve_thinking_history is False
        assert provider._request_defaults["preserve_thinking"] is False
    finally:
        provider.close()


def test_qwen_provider_streams_multimodal_json_and_preserves_reasoning_content() -> None:
    observed: dict[str, object] = {}
    stream = "\n".join(
        [
            'data: {"model":"qwen3.7-plus","choices":[{"delta":{"reasoning_content":"hidden"}}]}',
            'data: {"choices":[{"delta":{"content":"{\\\"ok\\\":"}}]}',
            'data: {"choices":[{"delta":{"content":"true}"},"finish_reason":"stop"}]}',
            'data: {"choices":[],"usage":{"prompt_tokens":19,"completion_tokens":5}}',
            "data: [DONE]",
            "",
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        observed["url"] = str(request.url)
        observed["authorization"] = request.headers["Authorization"]
        observed["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            content=stream.encode("utf-8"),
        )

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Review both images."},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,YQ=="}},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,Yg=="}},
            ],
        }
    ]
    provider = QwenProvider(
        QwenProviderSettings(
            api_key="test-qwen-key",
            base_url="https://gateway.example/v1",
            model="qwen3.7-plus",
            preserve_thinking=True,
            retry_backoff_seconds=0,
        ),
        transport=httpx.MockTransport(handler),
    )
    assert provider.preserve_thinking_history is True
    try:
        completion = provider.complete(
            messages,
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "review", "schema": {"type": "object"}},
            },
            max_completion_tokens=128,
        )
    finally:
        provider.close()

    assert observed["url"] == "https://gateway.example/v1/chat/completions"
    assert observed["authorization"] == "Bearer test-qwen-key"
    assert observed["payload"] == {
        "model": "qwen3.7-plus",
        "messages": messages,
        "enable_thinking": True,
        "preserve_thinking": True,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "review", "schema": {"type": "object"}},
        },
        "max_completion_tokens": 128,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    assert completion.content == '{"ok":true}'
    assert completion.prompt_tokens == 19
    assert completion.completion_tokens == 5
    assert completion.reasoning_content == "hidden"
    assert completion.finish_reason == "stop"


@pytest.mark.parametrize("model", ["qwen3.8-max", "qwen3.8-flash"])
@pytest.mark.parametrize("reasoning_effort", ["none", "minimal", "high", "max"])
def test_qwen_provider_rejects_unsupported_reasoning_effort(
    model: str,
    reasoning_effort: str,
) -> None:
    with pytest.raises(ProviderConfigurationError, match="QWEN_REASONING_EFFORT"):
        QwenProvider(
            QwenProviderSettings(
                api_key="test-qwen-key",
                model=model,
                reasoning_effort=reasoning_effort,
            )
        )


def test_qwen_provider_rejects_completion_truncated_by_total_token_limit() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "qwen3.8-max",
                "choices": [
                    {
                        "finish_reason": "length",
                        "message": {
                            "content": '{"partial":',
                            "reasoning_content": "bounded thinking",
                        },
                    }
                ],
            },
        )

    provider = QwenProvider(
        QwenProviderSettings(
            api_key="test-qwen-key",
            streaming=False,
            transport_max_retries=0,
        ),
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(ProviderRequestError) as captured:
            provider.complete(
                [{"role": "user", "content": "return JSON"}],
                max_completion_tokens=18_000,
            )
    finally:
        provider.close()

    assert captured.value.failure_kind == "completion_length"
    assert captured.value.retryable is False


def test_qwen_provider_retries_empty_stream_response() -> None:
    attempts = 0
    observed_payloads: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        observed_payloads.append(json.loads(request.content))
        if attempts == 1:
            return httpx.Response(
                200,
                headers={"Content-Type": "text/event-stream"},
                content=b"data: [DONE]\n\n",
            )
        return httpx.Response(
            200,
            json={
                "model": "qwen3.8-flash",
                "choices": [{"message": {"content": '{"ok":true}'}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 4},
            },
        )

    provider = QwenProvider(
        QwenProviderSettings(
            api_key="test-qwen-key",
            base_url="https://gateway.example/v1",
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
    assert observed_payloads[0]["model"] == "qwen3.8-flash"
    assert observed_payloads[0]["reasoning_effort"] == "medium"
    assert observed_payloads[0]["enable_thinking"] is True
    assert observed_payloads[0]["preserve_thinking"] is False
    assert observed_payloads[0]["stream"] is True
    assert "stream" not in observed_payloads[1]
    assert "stream_options" not in observed_payloads[1]
    assert completion.content == '{"ok":true}'
    assert completion.prompt_tokens == 3
    assert completion.completion_tokens == 4


def test_qwen_provider_preserves_unread_stream_http_status() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            413,
            stream=httpx.ByteStream(b'{"error":{"type":"request_too_large"}}'),
        )

    provider = QwenProvider(
        QwenProviderSettings(
            api_key="test-qwen-key",
            base_url="https://gateway.example/v1",
            transport_max_retries=0,
            retry_backoff_seconds=0,
        ),
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(ProviderRequestError) as captured:
            provider.complete([{"role": "user", "content": "hello"}])
    finally:
        provider.close()

    assert captured.value.status_code == 413
    assert captured.value.failure_kind == "HTTPStatusError"


def test_text_provider_factory_selects_qwen_and_retains_kimi(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QWEN_API_KEY", "qwen-secret")
    monkeypatch.setenv("MOONSHOT_API_KEY", "kimi-secret")

    qwen = create_text_provider("qwen")
    kimi = create_text_provider("kimi")
    try:
        assert qwen.provider_name == "qwen"
        assert kimi.provider_name == "kimi"
    finally:
        qwen.close()  # type: ignore[attr-defined]
        kimi.close()  # type: ignore[attr-defined]


def test_visual_review_qwen_factory_disables_thinking_for_strict_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QWEN_API_KEY", "qwen-secret")
    monkeypatch.setenv("QWEN_ENABLE_THINKING", "true")
    monkeypatch.setenv("QWEN_PRESERVE_THINKING", "true")
    monkeypatch.setenv("QWEN_REASONING_EFFORT", "medium")

    provider = create_visual_review_text_provider("qwen")
    try:
        assert provider.provider_name == "qwen"
        assert provider.preserve_thinking_history is False  # type: ignore[attr-defined]
        assert provider._reasoning_effort is None  # type: ignore[attr-defined]
        assert provider._request_defaults == {  # type: ignore[attr-defined]
            "enable_thinking": False,
            "preserve_thinking": False,
        }
    finally:
        provider.close()  # type: ignore[attr-defined]


@pytest.mark.parametrize("model", ["qwen3.8-max", "qwen3.8-flash"])
def test_qwen38_nonthinking_mode_requires_reasoning_effort_none(model: str) -> None:
    with pytest.raises(ProviderConfigurationError, match="must be low, medium"):
        QwenProvider(
            QwenProviderSettings(
                api_key="test-qwen-key",
                model=model,
                enable_thinking=False,
                preserve_thinking=False,
                reasoning_effort="medium",
            )
        )


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


def test_kimi_provider_default_recovers_after_four_read_timeouts() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts <= 4:
            raise httpx.ReadTimeout("slow Kimi response", request=request)
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
            retry_backoff_seconds=0,
        ),
        transport=httpx.MockTransport(handler),
    )
    try:
        completion = provider.complete([{"role": "user", "content": "hello"}])
    finally:
        provider.close()

    assert attempts == 5
    assert completion.content == '{"ok":true}'


def test_kimi_provider_retries_temporary_proxy_403() -> None:
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts <= 2:
            return httpx.Response(403, text="temporary proxy rejection")
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
            transport_max_retries=2,
            retry_backoff_seconds=0,
        ),
        transport=httpx.MockTransport(handler),
    )
    try:
        completion = provider.complete([{"role": "user", "content": "hello"}])
    finally:
        provider.close()

    assert attempts == 3
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


def test_kimi_anthropic_proxy_streams_long_responses() -> None:
    observed: dict[str, object] = {}
    stream = "\n".join(
        [
            'event: message_start',
            (
                'data: {"type":"message_start","message":{"model":"kimi-k3",'
                '"usage":{"input_tokens":117,"output_tokens":0}}}'
            ),
            '',
            'event: content_block_start',
            'data:',
            'data: {"type":"content_block_start","content_block":{"type":"text","text":""}}',
            '',
            'event: content_block_delta',
            (
                'data: {"type":"content_block_delta","delta":'
                '{"type":"text_delta","text":"{\\"ok\\":"}}'
            ),
            '',
            'event: content_block_delta',
            'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"true}"}}',
            '',
            'event: message_delta',
            'data: {"type":"message_delta","usage":{"output_tokens":56}}',
            '',
            'event: message_stop',
            'data: {"type":"message_stop"}',
            '',
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        observed["accept"] = request.headers["accept"]
        observed["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=stream.encode("utf-8"),
        )

    provider = KimiProvider(
        KimiProviderSettings(
            api_key="test-proxy-key",
            base_url="https://cf.api.fan/v1",
            protocol="anthropic",
            anthropic_streaming=True,
        ),
        transport=httpx.MockTransport(handler),
    )
    try:
        completion = provider.complete(
            [{"role": "user", "content": "Return ok=true."}],
            max_completion_tokens=64,
        )
    finally:
        provider.close()

    assert observed["accept"] == "text/event-stream"
    assert observed["payload"] == {
        "model": "kimi-k3",
        "messages": [{"role": "user", "content": "Return ok=true."}],
        "max_tokens": 64,
        "stream": True,
    }
    assert completion.content == '{"ok":true}'
    assert completion.model == "kimi-k3"
    assert completion.prompt_tokens == 117
    assert completion.completion_tokens == 56


def test_kimi_anthropic_proxy_converts_openai_image_url_blocks() -> None:
    observed: dict[str, object] = {}
    encoded = base64.b64encode(b"visual-review-jpeg").decode("ascii")

    def handler(request: httpx.Request) -> httpx.Response:
        observed["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "kimi-k3",
                "content": [{"type": "text", "text": '{"passed":true}'}],
                "usage": {"input_tokens": 25, "output_tokens": 6},
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
        provider.complete(
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Review this image."},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{encoded}"
                            },
                        },
                    ],
                }
            ]
        )
    finally:
        provider.close()

    assert observed["payload"] == {
        "model": "kimi-k3",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Review this image."},
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": encoded,
                        },
                    },
                ],
            }
        ],
        "max_tokens": 4096,
    }


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
        KimiProviderSettings(api_key="test-moonshot-key", transport_max_retries=0),
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(ProviderRequestError) as captured:
            provider.complete([{"role": "user", "content": "hello"}])
    finally:
        provider.close()

    assert "status=429" in str(captured.value)
    assert "request_id=req_safe" in str(captured.value)
    assert "failure_kind=HTTPStatusError" in str(captured.value)
    assert secret_body not in str(captured.value)
    assert captured.value.failure_kind == "HTTPStatusError"
    assert attempts == 1


def test_provider_http_error_preserves_only_safe_upstream_code() -> None:
    secret_body = "sensitive diagnostic text"

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={"error": {"type": "packy_api_error", "message": secret_body}},
        )

    provider = KimiProvider(
        KimiProviderSettings(api_key="test-moonshot-key", transport_max_retries=0),
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(ProviderRequestError) as captured:
            provider.complete([{"role": "user", "content": "hello"}])
    finally:
        provider.close()

    assert captured.value.upstream_code == "packy_api_error"
    assert captured.value.retryable is True
    assert "upstream_code=packy_api_error" in str(captured.value)
    assert secret_body not in str(captured.value)


def test_provider_does_not_treat_freeform_error_text_as_a_safe_code() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "customer-secret-identifier"})

    provider = KimiProvider(
        KimiProviderSettings(api_key="test-moonshot-key", transport_max_retries=0),
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(ProviderRequestError) as captured:
            provider.complete([{"role": "user", "content": "hello"}])
    finally:
        provider.close()

    assert captured.value.upstream_code is None
    assert "customer-secret-identifier" not in str(captured.value)
    assert captured.value.retryable is False


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
