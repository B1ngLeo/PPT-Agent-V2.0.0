from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

FORBIDDEN_SECRET_NAMES = ("MOONSHOT_API_KEY", "OPENAI_API_KEY")
CLIENT_ROOTS = (Path("apps/web/src"), Path("services/api/src"))
PRODUCT_ROOTS = CLIENT_ROOTS + (Path("packages/domain/src"),)


def source_files(root: Path) -> list[Path]:
    return [
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix in {".py", ".ts", ".tsx", ".js", ".mjs"}
    ]


def main() -> int:
    repository = Path(__file__).resolve().parents[2]
    secret_hits: list[str] = []
    reasoning_hits: list[str] = []

    for relative_root in CLIENT_ROOTS:
        for path in source_files(repository / relative_root):
            content = path.read_text(encoding="utf-8")
            if any(name in content for name in FORBIDDEN_SECRET_NAMES):
                secret_hits.append(path.relative_to(repository).as_posix())

    for relative_root in PRODUCT_ROOTS:
        for path in source_files(repository / relative_root):
            if "reasoning_content" in path.read_text(encoding="utf-8"):
                reasoning_hits.append(path.relative_to(repository).as_posix())

    generation_pipeline = (
        repository / "services/worker/src/instant_ppt_worker/generation_pipeline.py"
    ).read_text(encoding="utf-8")
    worker_settings = (
        repository / "services/worker/src/instant_ppt_worker/settings.py"
    ).read_text(encoding="utf-8")
    worker_providers = (
        repository / "services/worker/src/instant_ppt_worker/providers.py"
    ).read_text(encoding="utf-8")
    image_path_integrated = all(
        marker in generation_pipeline
        for marker in ("OpenAIImageProvider", "generation_ai_cover_image", "imageGeneration")
    )
    image_call_cap = (
        1 if "settings.max_images_per_deck not in {0, 1}" in worker_providers else -1
    )
    current_image_default = 0 if "max_images_per_deck: int = 0" in worker_settings else -1

    bundle_hits: list[str] = []
    bundle_root = repository / "apps/web/.next/static"
    if bundle_root.exists():
        for path in source_files(bundle_root):
            content = path.read_text(encoding="utf-8", errors="ignore")
            if any(name in content for name in FORBIDDEN_SECRET_NAMES):
                bundle_hits.append(path.relative_to(repository).as_posix())

    results = {
        "workerOnlySecretNames": not secret_hits,
        "browserBundleSecretNamesAbsent": not bundle_hits,
        "reasoningContentAbsentFromProductContracts": not reasoning_hits,
        "imageProviderProductPathIntegrated": image_path_integrated,
        "maxImageProviderCallsPerDeck": image_call_cap,
        "currentDefaultImageProviderCallsPerDeck": current_image_default,
        "moonshotSmoke": (
            "eligible_secret_present"
            if os.getenv("MOONSHOT_API_KEY", "").strip()
            else "not_run_no_secret"
        ),
        "openAiImageSmoke": (
            "eligible_secret_present"
            if os.getenv("OPENAI_API_KEY", "").strip()
            else "not_run_no_secret"
        ),
    }
    evidence = {
        "schemaVersion": 1,
        "goal": "G05",
        "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "result": "passed" if all(
            (
                results["workerOnlySecretNames"],
                results["browserBundleSecretNamesAbsent"],
                results["reasoningContentAbsentFromProductContracts"],
                results["imageProviderProductPathIntegrated"],
                results["maxImageProviderCallsPerDeck"] == 1,
                results["currentDefaultImageProviderCallsPerDeck"] == 0,
            )
        ) else "failed",
        "results": results,
        "findings": {
            "clientSecretNameHits": secret_hits,
            "bundleSecretNameHits": bundle_hits,
            "productReasoningContentHits": reasoning_hits,
        },
        "notes": [
            "Secret presence is recorded only as a boolean-derived status; "
            "values are never read into evidence.",
            "A real kimi-k3 smoke is conditional on MOONSHOT_API_KEY and provider availability.",
            "The image adapter supports an explicit maximum of one cover image per deck; "
            "the current product default keeps IMAGE_GENERATION_ENABLED=false and the "
            "per-deck quota at zero.",
        ],
    }
    output = repository / "docs/evidence/security/g05-provider-results.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"G05 provider security: {evidence['result']}")
    print(f"MOONSHOT smoke: {results['moonshotSmoke']}")
    print(f"OpenAI image smoke: {results['openAiImageSmoke']}")
    return 0 if evidence["result"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
