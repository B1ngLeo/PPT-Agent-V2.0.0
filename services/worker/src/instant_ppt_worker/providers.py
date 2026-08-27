"""Server-only Provider Gateway for text planning and AI image generation."""

from __future__ import annotations

import base64
import binascii
import json
import logging
import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any, Protocol, TypeVar

import httpx

from instant_ppt_worker.settings import (
    SUPPORTED_QWEN_MODELS,
    KimiProviderSettings,
    OpenAIImageSettings,
    QwenProviderSettings,
)

logger = logging.getLogger(__name__)

_RETRYABLE_PROVIDER_TRANSPORT_ERRORS = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadError,
    httpx.ReadTimeout,
    httpx.RemoteProtocolError,
)

# A gateway can finish an otherwise successful HTTP/SSE exchange with an empty,
# truncated, or malformed provider payload.  Text completions are side-effect free,
# so retry those response-shape failures just like transient transport failures.
_RETRYABLE_PROVIDER_RESPONSE_ERRORS = (
    json.JSONDecodeError,
    KeyError,
    TypeError,
    ValueError,
)

_RETRYABLE_PROVIDER_HTTP_STATUSES = frozenset({403, 408, 409, 425, 429})
_SAFE_PROVIDER_ERROR_CODE = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")


def _retryable_provider_http_status(status_code: int) -> bool:
    return status_code in _RETRYABLE_PROVIDER_HTTP_STATUSES or status_code >= 500


def _safe_upstream_code(response: httpx.Response | None) -> str | None:
    """Extract a bounded machine code without persisting provider response text."""

    if response is None:
        return None
    try:
        payload = response.json()
    except (
        httpx.HTTPError,
        httpx.ResponseNotRead,
        json.JSONDecodeError,
        ValueError,
    ):
        return None
    candidates: list[tuple[Any, bool]] = []
    if isinstance(payload, dict):
        candidates.extend(((payload.get("code"), True), (payload.get("type"), True)))
        error = payload.get("error")
        if isinstance(error, dict):
            candidates.extend(((error.get("code"), True), (error.get("type"), True)))
        else:
            candidates.append((error, False))
    for candidate, explicit_code_field in candidates:
        if (
            isinstance(candidate, str)
            and _SAFE_PROVIDER_ERROR_CODE.fullmatch(candidate)
            and (explicit_code_field or "error" in candidate.lower())
        ):
            return candidate
    return None


def _safe_upstream_detail(response: httpx.Response | None) -> str | None:
    """Return a bounded provider error message for server-side diagnostics."""

    if response is None:
        return None
    try:
        payload = response.json()
    except (httpx.HTTPError, httpx.ResponseNotRead, json.JSONDecodeError, ValueError):
        return None
    candidate: Any = None
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            candidate = error.get("message")
        if candidate is None:
            candidate = payload.get("message")
    if not isinstance(candidate, str):
        return None
    detail = " ".join(candidate.split())[:500]
    # Provider messages should describe parameters, but defensively redact any
    # credential-like bearer token before the value reaches logs.
    detail = re.sub(r"\b(?:sk|Bearer)-[A-Za-z0-9._-]{8,}\b", "[redacted]", detail)
    return detail or None


class ProviderConfigurationError(RuntimeError):
    """Raised when a provider is selected without a usable server-side secret."""


class ProviderRequestError(RuntimeError):
    """A sanitized provider failure safe to propagate to orchestration code."""

    def __init__(
        self,
        provider: str,
        status_code: int | None,
        request_id: str | None,
        failure_kind: str | None = None,
        upstream_code: str | None = None,
        retryable: bool | None = None,
    ) -> None:
        self.provider = provider
        self.status_code = status_code
        self.request_id = request_id
        self.failure_kind = failure_kind
        self.upstream_code = upstream_code
        self.retryable = retryable
        status = str(status_code) if status_code is not None else "transport_error"
        request = f" request_id={request_id}" if request_id else ""
        failure = f" failure_kind={failure_kind}" if failure_kind else ""
        upstream = f" upstream_code={upstream_code}" if upstream_code else ""
        super().__init__(
            f"{provider} request failed: status={status}{request}{failure}{upstream}"
        )


@dataclass(frozen=True, slots=True)
class TextCompletion:
    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    reasoning_content: str | None = None
    finish_reason: str | None = None


class TextProvider(Protocol):
    """Provider-neutral text completion boundary used by planning workflows."""

    provider_name: str

    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        response_format: dict[str, Any] | None = None,
        max_completion_tokens: int | None = None,
    ) -> TextCompletion: ...


@dataclass(frozen=True, slots=True)
class GeneratedImage:
    content: bytes
    media_type: str
    model: str


class ImageProvider(Protocol):
    provider_name: str

    def generate(
        self,
        prompt: str,
        *,
        size: str | None = None,
        quality: str | None = None,
        idempotency_key: str | None = None,
    ) -> GeneratedImage: ...


def _endpoint(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


class OpenAICompatibleTextProvider:
    """Reusable OpenAI Chat Completions adapter for provider-neutral workflows."""

    provider_name = "openai-compatible"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        reasoning_effort: str | None,
        timeout_seconds: float,
        transport_max_retries: int,
        retry_backoff_seconds: float,
        streaming: bool,
        request_defaults: dict[str, Any] | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise ProviderConfigurationError(
                f"{self.provider_name.upper()} API key is not configured"
            )
        if not base_url.startswith(("http://", "https://")):
            raise ProviderConfigurationError(
                f"{self.provider_name} base URL must be HTTP(S)"
            )
        if not model:
            raise ProviderConfigurationError(f"{self.provider_name} model is required")
        if not 0 <= transport_max_retries <= 5:
            raise ProviderConfigurationError(
                f"{self.provider_name} transport retries must be between 0 and 5"
            )
        if not 0 <= retry_backoff_seconds <= 30:
            raise ProviderConfigurationError(
                f"{self.provider_name} retry backoff must be between 0 and 30 seconds"
            )
        self._base_url = base_url
        self._model = model
        self._reasoning_effort = reasoning_effort
        self._transport_max_retries = transport_max_retries
        self._retry_backoff_seconds = retry_backoff_seconds
        self._streaming = streaming
        self._request_defaults = dict(request_defaults or {})
        self._client = httpx.Client(
            timeout=timeout_seconds,
            transport=transport,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

    def close(self) -> None:
        self._client.close()

    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        response_format: dict[str, Any] | None = None,
        max_completion_tokens: int | None = None,
    ) -> TextCompletion:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            **self._request_defaults,
        }
        if self._reasoning_effort:
            payload["reasoning_effort"] = self._reasoning_effort
        normalized_format = self._response_format(response_format)
        if normalized_format is not None:
            payload["response_format"] = normalized_format
        if max_completion_tokens is not None:
            payload["max_completion_tokens"] = max_completion_tokens
        use_streaming = self._streaming

        for attempt in range(self._transport_max_retries + 1):
            attempt_payload = dict(payload)
            if use_streaming:
                attempt_payload["stream"] = True
                attempt_payload["stream_options"] = {"include_usage": True}
            try:
                if use_streaming:
                    return self._complete_stream(attempt_payload)
                response = self._client.post(
                    _endpoint(self._base_url, "chat/completions"), json=attempt_payload
                )
                response.raise_for_status()
                return self._decode_completion(response.json())
            except _RETRYABLE_PROVIDER_TRANSPORT_ERRORS as error:
                if attempt < self._transport_max_retries:
                    use_streaming = self._fallback_from_streaming(
                        use_streaming, type(error).__name__
                    )
                    self._retry_delay(attempt, type(error).__name__)
                    continue
                raise self._request_error(error) from error
            except httpx.HTTPStatusError as error:
                logger.warning(
                    "%s_http_error status=%s upstream_code=%s detail=%s",
                    self.provider_name,
                    error.response.status_code,
                    _safe_upstream_code(error.response),
                    _safe_upstream_detail(error.response),
                )
                if (
                    _retryable_provider_http_status(error.response.status_code)
                    and attempt < self._transport_max_retries
                ):
                    self._retry_delay(attempt, str(error.response.status_code))
                    continue
                raise self._request_error(error) from error
            except _RETRYABLE_PROVIDER_RESPONSE_ERRORS as error:
                if attempt < self._transport_max_retries:
                    use_streaming = self._fallback_from_streaming(
                        use_streaming, type(error).__name__
                    )
                    self._retry_delay(attempt, type(error).__name__)
                    continue
                raise self._request_error(error) from error
            except httpx.HTTPError as error:
                raise self._request_error(error) from error
        raise AssertionError("unreachable provider retry state")

    def _fallback_from_streaming(
        self, use_streaming: bool, failure_kind: str
    ) -> bool:
        if use_streaming:
            logger.warning(
                "%s_streaming_fallback failure_kind=%s next_transport=non_streaming",
                self.provider_name,
                failure_kind,
            )
            return False
        return use_streaming

    def _response_format(
        self, response_format: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        return response_format

    def _retry_delay(self, attempt: int, failure_kind: str) -> None:
        delay = self._retry_backoff_seconds * (2**attempt)
        logger.warning(
            "%s_transport_retry attempt=%s max_retries=%s failure_kind=%s "
            "backoff_seconds=%s",
            self.provider_name,
            attempt + 1,
            self._transport_max_retries,
            failure_kind,
            delay,
        )
        if delay:
            time.sleep(delay)

    def _decode_completion(self, body: dict[str, Any]) -> TextCompletion:
        choice = body["choices"][0]
        finish_reason = choice.get("finish_reason")
        if finish_reason == "length":
            raise ProviderRequestError(
                self.provider_name,
                None,
                None,
                "completion_length",
                retryable=False,
            )
        message = choice["message"]
        content = message.get("content") or ""
        if not isinstance(content, str) or not content:
            raise ValueError("OpenAI-compatible response returned no text content")
        usage = body.get("usage") or {}
        return TextCompletion(
            content=content,
            model=str(body.get("model") or self._model),
            prompt_tokens=int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0),
            completion_tokens=int(
                usage.get("completion_tokens") or usage.get("output_tokens") or 0
            ),
            reasoning_content=(
                message.get("reasoning_content")
                if isinstance(message.get("reasoning_content"), str)
                else None
            ),
            finish_reason=str(finish_reason) if finish_reason is not None else None,
        )

    def _complete_stream(self, payload: dict[str, Any]) -> TextCompletion:
        content: list[str] = []
        reasoning_content: list[str] = []
        model = self._model
        finish_reason: str | None = None
        prompt_tokens = 0
        completion_tokens = 0
        request_url = _endpoint(self._base_url, "chat/completions")
        with self._client.stream(
            "POST",
            request_url,
            json=payload,
            headers={"Accept": "text/event-stream"},
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                raw = line.removeprefix("data:").strip()
                if not raw or raw == "[DONE]":
                    continue
                event = json.loads(raw)
                if not isinstance(event, dict):
                    raise ValueError("OpenAI-compatible stream event must be an object")
                if event.get("error"):
                    raise httpx.RemoteProtocolError(
                        "OpenAI-compatible stream emitted an error event",
                        request=response.request,
                    )
                model = str(event.get("model") or model)
                choices = event.get("choices") or []
                if choices and isinstance(choices[0], dict):
                    event_finish_reason = choices[0].get("finish_reason")
                    if event_finish_reason is not None:
                        finish_reason = str(event_finish_reason)
                    delta = choices[0].get("delta") or {}
                    if isinstance(delta, dict):
                        text = delta.get("content")
                        if isinstance(text, str):
                            content.append(text)
                        thinking = delta.get("reasoning_content")
                        if isinstance(thinking, str):
                            reasoning_content.append(thinking)
                usage = event.get("usage") or {}
                if isinstance(usage, dict):
                    prompt_tokens = int(
                        usage.get("prompt_tokens")
                        or usage.get("input_tokens")
                        or prompt_tokens
                    )
                    completion_tokens = int(
                        usage.get("completion_tokens")
                        or usage.get("output_tokens")
                        or completion_tokens
                    )
        if finish_reason == "length":
            raise ProviderRequestError(
                self.provider_name,
                None,
                None,
                "completion_length",
                retryable=False,
            )
        text = "".join(content)
        if not text:
            raise ValueError("OpenAI-compatible stream returned no text content")
        return TextCompletion(
            content=text,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            reasoning_content="".join(reasoning_content) or None,
            finish_reason=finish_reason,
        )

    def _request_error(self, error: Exception) -> ProviderRequestError:
        response = getattr(error, "response", None)
        status_code = response.status_code if response is not None else None
        request_id = (
            response.headers.get("msh-request-id")
            or response.headers.get("x-request-id")
            or response.headers.get("request-id")
            if response is not None
            else None
        )
        return ProviderRequestError(
            self.provider_name,
            status_code,
            request_id,
            type(error).__name__,
            _safe_upstream_code(response),
            (
                _retryable_provider_http_status(status_code)
                if status_code is not None
                else isinstance(
                    error,
                    (
                        *_RETRYABLE_PROVIDER_TRANSPORT_ERRORS,
                        *_RETRYABLE_PROVIDER_RESPONSE_ERRORS,
                    ),
                )
            ),
        )


class QwenProvider(OpenAICompatibleTextProvider):
    """Supported Qwen text models over an OpenAI-compatible gateway."""

    provider_name = "qwen"

    def __init__(
        self,
        settings: QwenProviderSettings,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not settings.available:
            raise ProviderConfigurationError("QWEN_API_KEY is not configured")
        if settings.model not in SUPPORTED_QWEN_MODELS:
            supported = ", ".join(sorted(SUPPORTED_QWEN_MODELS))
            raise ProviderConfigurationError(f"QWEN_MODEL must be one of: {supported}")
        reasoning_effort: str | None = None
        if settings.model == "qwen3.8-max":
            allowed_reasoning_efforts = (
                {"low", "medium", "xhigh"} if settings.enable_thinking else {"none"}
            )
            if settings.reasoning_effort not in allowed_reasoning_efforts:
                raise ProviderConfigurationError(
                    "QWEN_REASONING_EFFORT must be low, medium, or xhigh when thinking "
                    "is enabled, and none when thinking is disabled"
                )
            reasoning_effort = settings.reasoning_effort
        if not settings.enable_thinking and settings.preserve_thinking:
            raise ProviderConfigurationError(
                "QWEN_PRESERVE_THINKING must be false when thinking is disabled"
            )
        # Supported Qwen reasoning models require historical assistant
        # reasoning_content to be replayed while preserved thinking is enabled.
        # The Agent runtime reads this capability before applying context compaction.
        self.preserve_thinking_history = settings.preserve_thinking
        super().__init__(
            api_key=settings.api_key,
            base_url=settings.base_url,
            model=settings.model,
            # qwen3.7-plus controls thinking with enable_thinking. DashScope only
            # documents reasoning_effort for qwen3.8-max and rejects it on 3.7.
            reasoning_effort=reasoning_effort,
            timeout_seconds=settings.timeout_seconds,
            transport_max_retries=settings.transport_max_retries,
            retry_backoff_seconds=settings.retry_backoff_seconds,
            streaming=settings.streaming,
            request_defaults={
                "enable_thinking": settings.enable_thinking,
                "preserve_thinking": settings.preserve_thinking,
            },
            transport=transport,
        )


class KimiProvider:
    """Kimi K3 adapter that keeps provider-specific fields out of domain contracts."""

    provider_name = "kimi"

    def __init__(
        self,
        settings: KimiProviderSettings,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not settings.available:
            raise ProviderConfigurationError("MOONSHOT_API_KEY is not configured")
        if settings.model != "kimi-k3":
            raise ProviderConfigurationError("KIMI_MODEL must be kimi-k3")
        if settings.protocol not in {"openai", "anthropic"}:
            raise ProviderConfigurationError("KIMI_PROTOCOL must be openai or anthropic")
        if settings.reasoning_effort not in {"low", "high", "max"}:
            raise ProviderConfigurationError("KIMI_REASONING_EFFORT must be low, high, or max")
        if not 0 <= settings.transport_max_retries <= 5:
            raise ProviderConfigurationError("KIMI_TRANSPORT_MAX_RETRIES must be between 0 and 5")
        if not 0 <= settings.retry_backoff_seconds <= 30:
            raise ProviderConfigurationError(
                "KIMI_RETRY_BACKOFF_SECONDS must be between 0 and 30"
            )
        self._settings = settings
        headers = {
            "Authorization": f"Bearer {settings.api_key}",
            "Content-Type": "application/json",
        }
        if settings.protocol == "anthropic":
            headers["anthropic-version"] = "2023-06-01"
        self._client = httpx.Client(
            timeout=settings.timeout_seconds,
            transport=transport,
            headers=headers,
        )

    def close(self) -> None:
        self._client.close()

    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        response_format: dict[str, Any] | None = None,
        max_completion_tokens: int | None = None,
    ) -> TextCompletion:
        for attempt in range(self._settings.transport_max_retries + 1):
            try:
                if self._settings.protocol == "anthropic":
                    response = self._complete_anthropic(messages, max_completion_tokens)
                else:
                    response = self._complete_openai(
                        messages, response_format, max_completion_tokens
                    )
                response.raise_for_status()
                body = response.json()
                if self._settings.protocol == "anthropic":
                    content = "".join(
                        str(block.get("text") or "")
                        for block in body["content"]
                        if isinstance(block, dict) and block.get("type") == "text"
                    )
                    usage = body.get("usage") or {}
                    prompt_tokens = int(usage.get("input_tokens") or 0)
                    completion_tokens = int(usage.get("output_tokens") or 0)
                else:
                    message = body["choices"][0]["message"]
                    content = message.get("content") or ""
                    usage = body.get("usage") or {}
                    prompt_tokens = int(usage.get("prompt_tokens") or 0)
                    completion_tokens = int(usage.get("completion_tokens") or 0)
                return TextCompletion(
                    content=content,
                    model=body.get("model") or self._settings.model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                )
            except _RETRYABLE_PROVIDER_TRANSPORT_ERRORS as error:
                if attempt < self._settings.transport_max_retries:
                    delay = self._settings.retry_backoff_seconds * (2**attempt)
                    logger.warning(
                        "kimi_transport_retry attempt=%s max_retries=%s "
                        "failure_kind=%s backoff_seconds=%s",
                        attempt + 1,
                        self._settings.transport_max_retries,
                        type(error).__name__,
                        delay,
                    )
                    if delay:
                        time.sleep(delay)
                    continue
                raise self._request_error(error) from error
            except httpx.HTTPStatusError as error:
                if (
                    _retryable_provider_http_status(error.response.status_code)
                    and attempt < self._settings.transport_max_retries
                ):
                    delay = self._settings.retry_backoff_seconds * (2**attempt)
                    logger.warning(
                        "kimi_http_retry attempt=%s max_retries=%s status=%s "
                        "backoff_seconds=%s",
                        attempt + 1,
                        self._settings.transport_max_retries,
                        error.response.status_code,
                        delay,
                    )
                    if delay:
                        time.sleep(delay)
                    continue
                raise self._request_error(error) from error
            except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
                raise self._request_error(error) from error
        raise AssertionError("unreachable Kimi retry state")

    @staticmethod
    def _request_error(error: Exception) -> ProviderRequestError:
        response = getattr(error, "response", None)
        status_code = response.status_code if response is not None else None
        request_id = (
            response.headers.get("msh-request-id")
            or response.headers.get("x-request-id")
            or response.headers.get("request-id")
            if response is not None
            else None
        )
        return ProviderRequestError(
            "kimi",
            status_code,
            request_id,
            type(error).__name__,
            KimiProvider._safe_upstream_code(response),
            (
                _retryable_provider_http_status(status_code)
                if status_code is not None
                else isinstance(error, _RETRYABLE_PROVIDER_TRANSPORT_ERRORS)
            ),
        )

    @staticmethod
    def _safe_upstream_code(response: httpx.Response | None) -> str | None:
        return _safe_upstream_code(response)

    def _complete_openai(
        self,
        messages: list[dict[str, Any]],
        response_format: dict[str, Any] | None,
        max_completion_tokens: int | None,
    ) -> httpx.Response:
        payload: dict[str, Any] = {
            "model": self._settings.model,
            "messages": messages,
            "reasoning_effort": self._settings.reasoning_effort,
        }
        if response_format is not None:
            payload["response_format"] = response_format
        if max_completion_tokens is not None:
            payload["max_completion_tokens"] = max_completion_tokens
        return self._client.post(
            _endpoint(self._settings.base_url, "chat/completions"), json=payload
        )

    def _complete_anthropic(
        self,
        messages: list[dict[str, Any]],
        max_completion_tokens: int | None,
    ) -> httpx.Response:
        system_parts: list[str] = []
        converted: list[dict[str, Any]] = []
        for message in messages:
            role = message.get("role")
            content = message.get("content") or ""
            if role == "system":
                system_parts.append(str(content))
            elif role in {"user", "assistant"}:
                converted.append(
                    {"role": role, "content": self._anthropic_content(content)}
                )
            else:
                raise ValueError("Anthropic-compatible Kimi messages require known roles")
        payload: dict[str, Any] = {
            "model": self._settings.model,
            "messages": converted,
            "max_tokens": max_completion_tokens or 4096,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)
        if self._settings.anthropic_streaming:
            payload["stream"] = True
            return self._complete_anthropic_stream(payload)
        return self._client.post(_endpoint(self._settings.base_url, "messages"), json=payload)

    def _complete_anthropic_stream(self, payload: dict[str, Any]) -> httpx.Response:
        """Consume Anthropic SSE so long generations keep the proxy connection active."""

        content: list[str] = []
        model = self._settings.model
        prompt_tokens = 0
        completion_tokens = 0
        event_name: str | None = None
        request_url = _endpoint(self._settings.base_url, "messages")
        with self._client.stream(
            "POST",
            request_url,
            json=payload,
            headers={"Accept": "text/event-stream"},
        ) as response:
            response.raise_for_status()
            request = response.request
            response_headers = response.headers
            for line in response.iter_lines():
                if not line:
                    event_name = None
                    continue
                if line.startswith("event:"):
                    event_name = line.removeprefix("event:").strip()
                    continue
                if not line.startswith("data:"):
                    continue
                raw = line.removeprefix("data:").strip()
                if not raw:
                    continue
                if raw == "[DONE]":
                    continue
                event = json.loads(raw)
                if not isinstance(event, dict):
                    raise ValueError("Anthropic-compatible stream event must be an object")
                event_type = str(event.get("type") or event_name or "")
                if event_type == "error":
                    raise httpx.RemoteProtocolError(
                        "Anthropic-compatible stream emitted an error event",
                        request=request,
                    )
                if event_type == "message_start":
                    message = event.get("message") or {}
                    if isinstance(message, dict):
                        model = str(message.get("model") or model)
                        usage = message.get("usage") or {}
                        if isinstance(usage, dict):
                            prompt_tokens = int(usage.get("input_tokens") or 0)
                            completion_tokens = int(usage.get("output_tokens") or 0)
                    continue
                if event_type == "content_block_start":
                    block = event.get("content_block") or {}
                    if isinstance(block, dict) and block.get("type") == "text":
                        content.append(str(block.get("text") or ""))
                    continue
                if event_type == "content_block_delta":
                    delta = event.get("delta") or {}
                    if isinstance(delta, dict) and delta.get("type") == "text_delta":
                        content.append(str(delta.get("text") or ""))
                    continue
                if event_type == "message_delta":
                    usage = event.get("usage") or {}
                    if isinstance(usage, dict):
                        completion_tokens = int(
                            usage.get("output_tokens") or completion_tokens
                        )

        text = "".join(content)
        if not text:
            raise ValueError("Anthropic-compatible stream returned no text content")
        return httpx.Response(
            200,
            request=request,
            headers=response_headers,
            json={
                "model": model,
                "content": [{"type": "text", "text": text}],
                "usage": {
                    "input_tokens": prompt_tokens,
                    "output_tokens": completion_tokens,
                },
            },
        )

    @staticmethod
    def _anthropic_content(content: Any) -> str | list[dict[str, Any]]:
        if isinstance(content, str):
            return content
        if not isinstance(content, list):
            raise ValueError("Anthropic-compatible Kimi content must be text or blocks")
        converted: list[dict[str, Any]] = []
        for block in content:
            if not isinstance(block, dict):
                raise ValueError("Anthropic-compatible Kimi blocks must be objects")
            block_type = block.get("type")
            if block_type == "text":
                converted.append({"type": "text", "text": str(block.get("text") or "")})
                continue
            if block_type != "image_url":
                raise ValueError("Anthropic-compatible Kimi block type is unsupported")
            image_url = block.get("image_url")
            url = image_url.get("url") if isinstance(image_url, dict) else image_url
            if not isinstance(url, str) or not url.startswith("data:image/"):
                raise ValueError("Anthropic-compatible Kimi images must be data URLs")
            header, separator, encoded = url.partition(",")
            media_type = header.removeprefix("data:").removesuffix(";base64")
            if (
                separator != ","
                or not header.endswith(";base64")
                or media_type not in {"image/jpeg", "image/png", "image/webp"}
            ):
                raise ValueError("Anthropic-compatible Kimi image data URL is invalid")
            try:
                base64.b64decode(encoded, validate=True)
            except (binascii.Error, ValueError) as error:
                raise ValueError(
                    "Anthropic-compatible Kimi image base64 is invalid"
                ) from error
            converted.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": encoded,
                    },
                }
            )
        return converted


def create_text_provider(
    provider_name: str | None = None,
    *,
    transport_max_retries: int | None = None,
) -> TextProvider:
    """Build the selected live text provider with Qwen as the safe default."""

    selected = (provider_name or os.getenv("TEXT_PROVIDER", "")).strip().lower()
    if not selected:
        planning_backend = os.getenv("PLANNING_BACKEND", "").strip().lower()
        selected = planning_backend if planning_backend in {"kimi", "qwen"} else "qwen"
    if selected == "kimi":
        settings = KimiProviderSettings.from_env()
        if transport_max_retries is not None:
            settings = replace(settings, transport_max_retries=transport_max_retries)
        return KimiProvider(settings)
    if selected == "qwen":
        settings = QwenProviderSettings.from_env()
        if transport_max_retries is not None:
            settings = replace(settings, transport_max_retries=transport_max_retries)
        return QwenProvider(settings)
    raise ProviderConfigurationError("TEXT_PROVIDER must be kimi or qwen")


def create_visual_review_text_provider(
    provider_name: str | None = None,
    *,
    transport_max_retries: int | None = None,
) -> TextProvider:
    """Build the multimodal reviewer with deterministic structured output defaults."""

    selected = (provider_name or os.getenv("TEXT_PROVIDER", "")).strip().lower()
    if not selected:
        planning_backend = os.getenv("PLANNING_BACKEND", "").strip().lower()
        selected = planning_backend if planning_backend in {"kimi", "qwen"} else "qwen"
    if selected != "qwen":
        return create_text_provider(
            selected,
            transport_max_retries=transport_max_retries,
        )
    settings = replace(
        QwenProviderSettings.from_env(),
        reasoning_effort=None,
        enable_thinking=False,
        preserve_thinking=False,
    )
    if transport_max_retries is not None:
        settings = replace(settings, transport_max_retries=transport_max_retries)
    return QwenProvider(settings)


class DeterministicFakeProvider:
    """Repeatable provider for contracts, schema repair, and offline E2E tests."""

    provider_name = "fake"

    def __init__(self, responses: list[str] | None = None) -> None:
        self._responses = list(responses or ['{"ok":true}'])
        self.calls: list[dict[str, Any]] = []

    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        response_format: dict[str, Any] | None = None,
        max_completion_tokens: int | None = None,
    ) -> TextCompletion:
        index = min(len(self.calls), len(self._responses) - 1)
        content = self._responses[index]
        self.calls.append(
            {
                "messages": messages,
                "responseFormat": response_format,
                "maxCompletionTokens": max_completion_tokens,
            }
        )
        return TextCompletion(
            content=content,
            model="deterministic-fake-v1",
            prompt_tokens=sum(len(str(message.get("content", ""))) for message in messages),
            completion_tokens=len(content),
        )


StructuredValue = TypeVar("StructuredValue")


@dataclass(frozen=True, slots=True)
class StructuredCompletion:
    value: Any
    completion: TextCompletion
    repair_count: int


class StructuredProviderGateway:
    """Parse, validate, and finitely repair structured provider output."""

    def __init__(self, provider: TextProvider, *, max_repairs: int = 2) -> None:
        if not 0 <= max_repairs <= 2:
            raise ValueError("max_repairs must be between 0 and 2")
        self.provider = provider
        self.max_repairs = max_repairs

    def generate(
        self,
        messages: list[dict[str, Any]],
        *,
        validate: Callable[[dict[str, Any]], StructuredValue],
        max_completion_tokens: int | None = None,
    ) -> StructuredCompletion:
        working_messages = [dict(message) for message in messages]
        last_error = "invalid structured output"
        for repair_count in range(self.max_repairs + 1):
            completion = self.provider.complete(
                working_messages,
                response_format={"type": "json_object"},
                max_completion_tokens=max_completion_tokens,
            )
            try:
                decoded = json.loads(completion.content)
                if not isinstance(decoded, dict):
                    raise ValueError("root must be an object")
                value = validate(decoded)
                return StructuredCompletion(value, completion, repair_count)
            except (json.JSONDecodeError, ValueError, TypeError, KeyError) as error:
                last_error = str(error)[:240]
                if repair_count >= self.max_repairs:
                    break
                assistant_message: dict[str, Any] = {
                    "role": "assistant",
                    "content": completion.content,
                }
                if completion.reasoning_content:
                    assistant_message["reasoning_content"] = completion.reasoning_content
                working_messages.extend(
                    [
                        assistant_message,
                        {
                            "role": "user",
                            "content": (
                                "Return only a corrected JSON object that satisfies the requested "
                                f"schema. Validation error: {last_error}"
                            ),
                        },
                    ]
                )
        raise ProviderRequestError("structured-output", None, None)


class OpenAIImageProvider:
    """OpenAI gpt-image-2 adapter returning verified decoded image bytes."""

    provider_name = "openai-image"
    _MEDIA_TYPES = {"png": "image/png", "jpeg": "image/jpeg", "webp": "image/webp"}

    def __init__(
        self,
        settings: OpenAIImageSettings,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not settings.available:
            raise ProviderConfigurationError("IMAGE_BACKEND=openai and OPENAI_API_KEY are required")
        if settings.model != "gpt-image-2":
            raise ProviderConfigurationError("OPENAI_MODEL must be gpt-image-2")
        if settings.output_format not in self._MEDIA_TYPES:
            raise ProviderConfigurationError("OPENAI_OUTPUT_FORMAT must be png, jpeg, or webp")
        if settings.size not in {"1024x1024", "1536x1024", "1024x1536"}:
            raise ProviderConfigurationError("OPENAI_IMAGE_SIZE is not supported by gpt-image-2")
        if settings.quality not in {"low", "medium", "high", "auto"}:
            raise ProviderConfigurationError("OPENAI_IMAGE_QUALITY is invalid")
        if settings.max_images_per_deck not in {0, 1}:
            raise ProviderConfigurationError("IMAGE_MAX_PER_DECK must be 0 or 1")
        if settings.cost_microunits_per_image < 0:
            raise ProviderConfigurationError("IMAGE_COST_MICROUNITS must be nonnegative")
        self._settings = settings
        self._client = httpx.Client(
            timeout=settings.timeout_seconds,
            transport=transport,
            headers={
                "Authorization": f"Bearer {settings.api_key}",
                "Content-Type": "application/json",
            },
        )

    def close(self) -> None:
        self._client.close()

    def generate(
        self,
        prompt: str,
        *,
        size: str | None = None,
        quality: str | None = None,
        idempotency_key: str | None = None,
    ) -> GeneratedImage:
        try:
            headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
            response = self._client.post(
                _endpoint(self._settings.base_url, "images/generations"),
                json={
                    "model": self._settings.model,
                    "prompt": prompt,
                    "size": size or self._settings.size,
                    "quality": quality or self._settings.quality,
                    "output_format": self._settings.output_format,
                },
                headers=headers,
            )
            response.raise_for_status()
            encoded = response.json()["data"][0]["b64_json"]
            content = base64.b64decode(encoded, validate=True)
            if not content:
                raise ValueError("empty image")
            return GeneratedImage(
                content=content,
                media_type=self._MEDIA_TYPES[self._settings.output_format],
                model=self._settings.model,
            )
        except (httpx.HTTPError, KeyError, TypeError, ValueError, binascii.Error) as error:
            response = getattr(error, "response", None)
            status_code = response.status_code if response is not None else None
            request_id = response.headers.get("x-request-id") if response is not None else None
            raise ProviderRequestError("openai-image", status_code, request_id) from error
