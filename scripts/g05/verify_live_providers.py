from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from instant_ppt_worker.providers import (
    KimiProvider,
    OpenAIImageProvider,
    ProviderConfigurationError,
    ProviderRequestError,
)
from instant_ppt_worker.settings import KimiProviderSettings, OpenAIImageSettings

REQUIRED_SECRET_NAMES = ("MOONSHOT_API_KEY", "OPENAI_API_KEY")
LOCAL_ENV_NAMES = REQUIRED_SECRET_NAMES + (
    "KIMI_BASE_URL",
    "KIMI_MODEL",
    "KIMI_PROTOCOL",
    "KIMI_REASONING_EFFORT",
    "KIMI_TIMEOUT_SECONDS",
    "IMAGE_BACKEND",
    "OPENAI_BASE_URL",
    "OPENAI_MODEL",
    "OPENAI_OUTPUT_FORMAT",
    "OPENAI_IMAGE_TIMEOUT_SECONDS",
)


def _load_workspace_env(repository: Path) -> None:
    """Load the ignored local .env without logging names paired with values."""

    path = repository / ".env"
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        if name in LOCAL_ENV_NAMES and name not in os.environ:
            os.environ[name] = value.strip()


def _kimi_smoke() -> dict[str, Any]:
    settings = KimiProviderSettings.from_env()
    provider = KimiProvider(settings)
    try:
        completion = provider.complete(
            [
                {
                    "role": "system",
                    "content": "Return only a JSON object and do not include reasoning.",
                },
                {"role": "user", "content": 'Return exactly {"ok":true}.'},
            ],
            response_format={"type": "json_object"},
            max_completion_tokens=64,
        )
    finally:
        provider.close()
    decoded = json.loads(completion.content)
    if decoded.get("ok") is not True:
        raise ValueError("Kimi smoke response did not contain ok=true")
    return {
        "status": "passed",
        "requestedModel": settings.model,
        "returnedModel": completion.model,
        "promptTokens": completion.prompt_tokens,
        "completionTokens": completion.completion_tokens,
        "structuredJsonVerified": True,
    }


def _openai_image_smoke() -> dict[str, Any]:
    settings = OpenAIImageSettings.from_env()
    provider = OpenAIImageProvider(settings)
    try:
        image = provider.generate(
            "A minimal blue circle centered on a plain white background, no text.",
            size="1024x1024",
            quality="low",
        )
    finally:
        provider.close()
    if image.media_type == "image/png" and not image.content.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("OpenAI image smoke returned invalid PNG bytes")
    return {
        "status": "passed",
        "requestedModel": settings.model,
        "returnedModel": image.model,
        "mediaType": image.media_type,
        "bytes": len(image.content),
        "sha256": hashlib.sha256(image.content).hexdigest(),
        "promptPersisted": False,
    }


def _run_safely(callback: Any) -> dict[str, Any]:
    try:
        return callback()
    except (
        ProviderConfigurationError,
        ProviderRequestError,
        json.JSONDecodeError,
        ValueError,
    ) as error:
        return {"status": "failed", "error": str(error)[:300]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=("all", "kimi", "openai"), default="all")
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[2]
    _load_workspace_env(repository)
    output = repository / "docs/evidence/security/g08-live-provider-smoke.json"
    previous: dict[str, Any] = {}
    if args.provider != "all" and output.is_file():
        try:
            previous = json.loads(output.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            previous = {}
    secret_presence = {name: bool(os.getenv(name, "").strip()) for name in REQUIRED_SECRET_NAMES}
    results = dict(previous.get("results") or {})
    if args.provider in {"all", "kimi"}:
        results["kimi"] = _run_safely(_kimi_smoke)
    if args.provider in {"all", "openai"}:
        results["openaiImage"] = _run_safely(_openai_image_smoke)
    results.setdefault("kimi", {"status": "not_run"})
    results.setdefault("openaiImage", {"status": "not_run"})
    passed = all(result["status"] == "passed" for result in results.values())
    evidence = {
        "schemaVersion": 1,
        "goal": "G08",
        "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "result": "passed" if passed else "failed",
        "executedProvider": args.provider,
        "secretPresence": secret_presence,
        "results": results,
        "security": {
            "secretValuesPersisted": False,
            "authorizationHeadersPersisted": False,
            "providerResponseContentPersisted": False,
            "generatedImagePersisted": False,
        },
    }
    output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Live Provider smoke: {evidence['result']}")
    print(f"Kimi kimi-k3: {results['kimi']['status']}")
    print(f"OpenAI gpt-image-2: {results['openaiImage']['status']}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
