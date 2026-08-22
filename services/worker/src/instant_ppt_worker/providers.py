"""Server-only Provider Gateway for text planning and AI image generation."""

from __future__ import annotations

import base64
import binascii
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

import httpx

from instant_ppt_worker.settings import KimiProviderSettings, OpenAIImageSettings

logger = logging.getLogger(__name__)

_RETRYABLE_KIMI_TRANSPORT_ERRORS = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadError,
    httpx.ReadTimeout,
    httpx.RemoteProtocolError,
)


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
    ) -> None:
        self.provider = provider
        self.status_code = status_code
        self.request_id = request_id
        self.failure_kind = failure_kind
        status = str(status_code) if status_code is not None else "transport_error"
        request = f" request_id={request_id}" if request_id else ""
        super().__init__(f"{provider} request failed: status={status}{request}")


@dataclass(frozen=True, slots=True)
class TextCompletion:
    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int


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
        if not 0 <= settings.transport_max_retries <= 2:
            raise ProviderConfigurationError("KIMI_TRANSPORT_MAX_RETRIES must be between 0 and 2")
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
            except _RETRYABLE_KIMI_TRANSPORT_ERRORS as error:
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
        )

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
                converted.append({"role": role, "content": content})
            else:
                raise ValueError("Anthropic-compatible Kimi messages require known roles")
        payload: dict[str, Any] = {
            "model": self._settings.model,
            "messages": converted,
            "max_tokens": max_completion_tokens or 4096,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)
        return self._client.post(_endpoint(self._settings.base_url, "messages"), json=payload)


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
                working_messages.extend(
                    [
                        {"role": "assistant", "content": completion.content},
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
