"""Worker contracts and server-only provider settings."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict


class WorkerContract(BaseModel):
    """Versioned boundary advertised by the sole engine adapter."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = 1
    adapter_name: str = "ppt-master-engine-adapter"
    engine_version: str = "ppt-master@v4.7.0+e8323bfa"
    parser_version: str = "source-parser@1+ppt-master-v4.7.0"


@dataclass(frozen=True, slots=True)
class KimiProviderSettings:
    """Configuration for Kimi's OpenAI-compatible Chat Completions API."""

    api_key: str = field(repr=False)
    base_url: str = "https://api.moonshot.cn/v1"
    model: str = "kimi-k3"
    protocol: str = "openai"
    reasoning_effort: str = "max"
    timeout_seconds: float = 120.0

    @classmethod
    def from_env(cls) -> KimiProviderSettings:
        return cls(
            api_key=os.getenv("MOONSHOT_API_KEY", "").strip(),
            base_url=os.getenv("KIMI_BASE_URL", "https://api.moonshot.cn/v1").strip(),
            model=os.getenv("KIMI_MODEL", "kimi-k3").strip(),
            protocol=os.getenv("KIMI_PROTOCOL", "openai").strip().lower(),
            reasoning_effort=os.getenv("KIMI_REASONING_EFFORT", "max").strip(),
            timeout_seconds=float(os.getenv("KIMI_TIMEOUT_SECONDS", "120")),
        )

    @property
    def available(self) -> bool:
        return bool(self.api_key)


@dataclass(frozen=True, slots=True)
class OpenAIImageSettings:
    """Configuration for the OpenAI Images API used by ppt-master."""

    api_key: str = field(repr=False)
    enabled: bool = False
    backend: str = "openai"
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-image-2"
    output_format: str = "png"
    size: str = "1536x1024"
    quality: str = "auto"
    max_images_per_deck: int = 0
    cost_microunits_per_image: int = 100_000
    timeout_seconds: float = 300.0

    @classmethod
    def from_env(cls) -> OpenAIImageSettings:
        return cls(
            api_key=os.getenv("OPENAI_API_KEY", "").strip(),
            enabled=os.getenv("IMAGE_GENERATION_ENABLED", "false").strip().lower()
            in {"1", "true", "yes", "on"},
            backend=os.getenv("IMAGE_BACKEND", "openai").strip().lower(),
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip(),
            model=os.getenv("OPENAI_MODEL", "gpt-image-2").strip(),
            output_format=os.getenv("OPENAI_OUTPUT_FORMAT", "png").strip().lower(),
            size=os.getenv("OPENAI_IMAGE_SIZE", "1536x1024").strip(),
            quality=os.getenv("OPENAI_IMAGE_QUALITY", "low").strip().lower(),
            max_images_per_deck=int(os.getenv("IMAGE_MAX_PER_DECK", "0")),
            cost_microunits_per_image=int(
                os.getenv("IMAGE_COST_MICROUNITS", "100000")
            ),
            timeout_seconds=float(os.getenv("OPENAI_IMAGE_TIMEOUT_SECONDS", "300")),
        )

    @property
    def available(self) -> bool:
        return self.backend == "openai" and bool(self.api_key)
