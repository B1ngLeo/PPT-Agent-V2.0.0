from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from instant_ppt_worker.models import DeckPlan
from instant_ppt_worker.planning import KimiPlanningService
from instant_ppt_worker.providers import OpenAIImageProvider
from instant_ppt_worker.renderer import render_deck
from instant_ppt_worker.settings import OpenAIImageSettings

LOCAL_ENV_NAMES = (
    "MOONSHOT_API_KEY",
    "OPENAI_API_KEY",
    "KIMI_BASE_URL",
    "KIMI_MODEL",
    "KIMI_PROTOCOL",
    "KIMI_REASONING_EFFORT",
    "KIMI_TIMEOUT_SECONDS",
    "IMAGE_BACKEND",
    "OPENAI_BASE_URL",
    "OPENAI_MODEL",
    "OPENAI_OUTPUT_FORMAT",
    "OPENAI_IMAGE_SIZE",
    "OPENAI_IMAGE_QUALITY",
    "OPENAI_IMAGE_TIMEOUT_SECONDS",
)


def _load_workspace_env(repository: Path) -> None:
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


def _deck(title: str, body: str) -> DeckPlan:
    return DeckPlan.model_validate(
        {
            "schemaVersion": 1,
            "snapshotId": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
            "title": title,
            "modeId": "native",
            "templateBinding": {
                "schemaVersion": 1,
                "templateId": "01ARZ3NDEKTSV4RRFFQ69G5FAA",
                "templateVersionId": "01ARZ3NDEKTSV4RRFFQ69G5FAB",
                "compatibilityVersion": "ppt-master@v4.7.0",
                "roleBindings": {"cover": "layout-cover"},
            },
            "slides": [
                {
                    "schemaVersion": 1,
                    "slideId": "01ARZ3NDEKTSV4RRFFQ69G5FAC",
                    "outlineSlideId": "01ARZ3NDEKTSV4RRFFQ69G5FAD",
                    "order": 0,
                    "role": "cover",
                    "title": title,
                    "body": [body],
                    "editable": True,
                }
            ],
        }
    )


def _run() -> dict[str, Any]:
    planning = KimiPlanningService.from_env()
    try:
        intent = planning.infer_intent(
            topic="合成数据：企业 AI 产品季度规划",
            source_refs=[],
            language="zh-CN",
        )
        outline = planning.generate_outline(
            intent=intent.data,
            existing=None,
            instruction="生成四页、结论先行、不要虚构数据",
            action="generate",
            target_slide_id=None,
        )
    finally:
        planning.close()

    image_settings = OpenAIImageSettings.from_env()
    image_provider = OpenAIImageProvider(image_settings)
    try:
        image = image_provider.generate(
            "A polished 3:2 landscape abstract editorial illustration for enterprise AI "
            "strategy, cobalt and teal, generous negative space, no text, no logo, no watermark.",
            size="1536x1024",
            quality="low",
            idempotency_key="g08-live-product-cover-v1",
        )
    finally:
        image_provider.close()

    suffix = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}[
        image.media_type
    ]
    with tempfile.TemporaryDirectory(prefix="instant-ppt-live-provider-product-") as temporary:
        root = Path(temporary)
        cover = root / f"cover{suffix}"
        cover.write_bytes(image.content)
        deck = _deck(
            str(intent.data["title"]),
            str(outline.data["slides"][0]["keyPoints"][0]),
        )
        plan = root / "deck-plan.json"
        plan.write_text(deck.model_dump_json(by_alias=True), encoding="utf-8")
        output = root / "output"
        render_deck(
            plan,
            output,
            organization_id="01ARZ3NDEKTSV4RRFFQ69G5FAE",
            created_at="2026-08-16T00:00:00Z",
            cover_image_path=cover,
        )
        package = json.loads(
            (output / "validation/pptx-package-qa.json").read_text(encoding="utf-8")
        )
        pptx_sha = hashlib.sha256((output / "deck.pptx").read_bytes()).hexdigest()

    return {
        "kimiIntent": {
            "status": "passed",
            "provider": intent.provider,
            "model": intent.model,
            "promptTokens": intent.input_tokens,
            "completionTokens": intent.output_tokens,
            "repairCount": intent.repair_count,
            "schemaValidated": True,
        },
        "kimiOutline": {
            "status": "passed",
            "provider": outline.provider,
            "model": outline.model,
            "promptTokens": outline.input_tokens,
            "completionTokens": outline.output_tokens,
            "repairCount": outline.repair_count,
            "slideCount": len(outline.data["slides"]),
            "schemaValidated": True,
        },
        "gptImageCover": {
            "status": "passed",
            "provider": "openai-image",
            "model": image.model,
            "mediaType": image.media_type,
            "bytes": len(image.content),
            "sha256": hashlib.sha256(image.content).hexdigest(),
            "imageCallCount": 1,
        },
        "pptxEmbedding": {
            "status": "passed" if package["passed"] else "failed",
            "pptxSha256": pptx_sha,
            "mediaPartCount": len(package["mediaParts"]),
            "allMediaReferenced": package["mediaParts"] == package["mediaReferences"],
            "unreferencedMediaPartCount": len(package["unreferencedMediaParts"]),
            "editableTextMatched": (
                package["matchedEditableTextCount"] == package["expectedEditableTextCount"]
            ),
            "fullSlidePictureCount": package["fullSlidePictureCount"],
        },
    }


def main() -> int:
    repository = Path(__file__).resolve().parents[2]
    _load_workspace_env(repository)
    output = repository / "docs/evidence/security/g08-live-product-provider-integration.json"
    try:
        results = _run()
        passed = all(result["status"] == "passed" for result in results.values())
        error = None
    except Exception as caught:  # sanitized evidence; no Provider bodies or prompts
        results = {}
        passed = False
        error = type(caught).__name__
    evidence = {
        "schemaVersion": 1,
        "goal": "G08",
        "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "result": "passed" if passed else "failed",
        "results": results,
        "errorType": error,
        "security": {
            "secretValuesPersisted": False,
            "authorizationHeadersPersisted": False,
            "providerResponseContentPersisted": False,
            "promptContentPersisted": False,
            "generatedArtifactsPersisted": False,
            "syntheticInputOnly": True,
        },
    }
    output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Live product Provider integration: {evidence['result']}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
