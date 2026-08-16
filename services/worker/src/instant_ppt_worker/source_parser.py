"""Clean-decision-gated source conversion through the vendored engine."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from pypdf import PdfReader

from instant_ppt_worker.artifacts import sha256_file
from instant_ppt_worker.errors import (
    SECURITY_DECISION_MISMATCH,
    SECURITY_DECISION_REQUIRED,
    SOURCE_PARSE_FAILED,
    AdapterError,
)
from instant_ppt_worker.models import SecurityDecision
from instant_ppt_worker.paths import ENGINE_SCRIPTS
from instant_ppt_worker.settings import WorkerContract

CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def deterministic_ulid(seed: str) -> str:
    value = int(seed[:30], 16)
    encoded: list[str] = []
    for _ in range(24):
        encoded.append(CROCKFORD[value & 31])
        value >>= 5
    return "01" + "".join(reversed(encoded))


def _language(markdown: str) -> str:
    cjk = sum("\u4e00" <= char <= "\u9fff" for char in markdown)
    latin = sum(char.isascii() and char.isalpha() for char in markdown)
    if cjk and latin > cjk:
        return "mixed"
    return "zh-CN" if cjk else "en-US"


def _parse_pdf_permissively(source: Path, markdown_path: Path) -> dict[str, object]:
    reader = PdfReader(source, strict=False)
    if reader.is_encrypted:
        raise AdapterError(SOURCE_PARSE_FAILED, "encrypted PDF passed the security boundary")
    pages = [page.extract_text() or "" for page in reader.pages]
    markdown_path.write_text(
        "\n\n".join(f"## Page {index + 1}\n\n{text.strip()}" for index, text in enumerate(pages)),
        encoding="utf-8",
    )
    return {
        "schema": "instant-ppt.conversion-profile.v1",
        "backend": "pypdf",
        "backendVersion": "6.16.1",
        "sourceType": "pdf",
        "assets": [],
    }


def parse_source(
    source_key: str,
    source_path: Path,
    decision_path: Path,
    output_dir: Path,
    *,
    source_id: str,
    organization_id: str,
    created_at: str,
) -> dict[str, object]:
    try:
        decision = SecurityDecision.model_validate_json(decision_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AdapterError(
            SECURITY_DECISION_REQUIRED, f"clean decision is unreadable: {exc}"
        ) from exc
    if decision.decision != "clean":
        raise AdapterError(SECURITY_DECISION_REQUIRED, "source does not have a clean decision")
    source_sha = sha256_file(source_path)
    if decision.source_key != source_key or decision.source_sha256 != source_sha:
        raise AdapterError(
            SECURITY_DECISION_MISMATCH, "clean decision is not bound to source bytes"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / "source.md"
    profile_path = output_dir / "conversion-profile.json"
    suffix = source_path.suffix.lower()
    if suffix == ".pdf":
        profile = _parse_pdf_permissively(source_path, markdown_path)
        profile_path.write_text(
            json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    else:
        command = [
            sys.executable,
            str(ENGINE_SCRIPTS / "source_to_md.py"),
            str(source_path),
            "-o",
            str(markdown_path),
            "--json",
        ]
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
        )
        if result.returncode != 0 or not markdown_path.is_file():
            message = (result.stderr or result.stdout or "engine source conversion failed").strip()
            raise AdapterError(SOURCE_PARSE_FAILED, message[-1500:])
        upstream_profile = markdown_path.with_suffix(".conversion_profile.json")
        if upstream_profile.is_file():
            shutil.copyfile(upstream_profile, profile_path)
            upstream_profile.unlink()
        else:
            profile_path.write_text(
                json.dumps(
                    {
                        "schema": "instant-ppt.conversion-profile.v1",
                        "backend": "ppt-master/source_to_md.py",
                        "sourceType": suffix.lstrip("."),
                        "assets": [],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

    markdown = markdown_path.read_text(encoding="utf-8")
    asset_dir = markdown_path.with_name("source_files")
    asset_paths = (
        sorted(path for path in asset_dir.rglob("*") if path.is_file())
        if asset_dir.is_dir()
        else []
    )
    source_package = {
        "schemaVersion": 1,
        "sourceId": source_id,
        "organizationId": organization_id,
        "sourceSha256": source_sha,
        "language": _language(markdown),
        "markdownArtifactId": deterministic_ulid(sha256_file(markdown_path)),
        "assetArtifactIds": [deterministic_ulid(sha256_file(path)) for path in asset_paths],
        "conversionProfileArtifactId": deterministic_ulid(sha256_file(profile_path)),
        "parserVersion": WorkerContract().parser_version,
        "createdAt": created_at,
    }
    package_path = output_dir / "source-package.json"
    package_path.write_text(
        json.dumps(source_package, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "sourcePackage": source_package,
        "paths": [markdown_path, profile_path, package_path, *asset_paths],
    }
