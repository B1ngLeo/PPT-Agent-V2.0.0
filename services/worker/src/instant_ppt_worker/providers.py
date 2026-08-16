"""Server-only Provider Gateway for text planning and AI image generation."""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

import httpx

from instant_ppt_worker.settings import KimiProviderSettings, OpenAIImageSettings


class ProviderConfigurationError(RuntimeError):
    """Raised when a provider is selected without a usable server-side secret."""


class ProviderRequestError(RuntimeError):
    """A sanitized provider failure safe to propagate to orchestration code."""

    def __init__(self, provider: str, status_code: int | None, request_id: str | None) -> None:
        self.provider = provider
        self.status_code = status_code
        self.request_id = request_id
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
        if settings.reasoning_effort not in {"low", "high", "max"}:
            raise ProviderConfigurationError("KIMI_REASONING_EFFORT must be low, high, or max")
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

    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        response_format: dict[str, Any] | None = None,
        max_completion_tokens: int | None = None,
    ) -> TextCompletion:
        payload: dict[str, Any] = {
            "model": self._settings.model,
            "messages": messages,
            "reasoning_effort": self._settings.reasoning_effort,
        }
        if response_format is not None:
            payload["response_format"] = response_format
        if max_completion_tokens is not None:
            payload["max_completion_tokens"] = max_completion_tokens
        try:
            response = self._client.post(
                _endpoint(self._settings.base_url, "chat/completions"), json=payload
            )
            response.raise_for_status()
            body = response.json()
            message = body["choices"][0]["message"]
            usage = body.get("usage") or {}
            return TextCompletion(
                content=message.get("content") or "",
                model=body.get("model") or self._settings.model,
                prompt_tokens=int(usage.get("prompt_tokens") or 0),
                completion_tokens=int(usage.get("completion_tokens") or 0),
            )
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            response = getattr(error, "response", None)
            status_code = response.status_code if response is not None else None
            request_id = (
                response.headers.get("msh-request-id") or response.headers.get("x-request-id")
                if response is not None
                else None
            )
            raise ProviderRequestError("kimi", status_code, request_id) from error


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
    ) -> StructuredCompletion:
        working_messages = [dict(message) for message in messages]
        last_error = "invalid structured output"
        for repair_count in range(self.max_repairs + 1):
            completion = self.provider.complete(
                working_messages,
                response_format={"type": "json_object"},
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
        size: str = "1536x1024",
        quality: str = "auto",
    ) -> GeneratedImage:
        try:
            response = self._client.post(
                _endpoint(self._settings.base_url, "images/generations"),
                json={
                    "model": self._settings.model,
                    "prompt": prompt,
                    "size": size,
                    "quality": quality,
                    "output_format": self._settings.output_format,
                },
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
