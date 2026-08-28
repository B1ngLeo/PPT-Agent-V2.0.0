"""Thin report adapter for the vendored PPT-Master SVG quality gate.

This module intentionally knows only the upstream report envelope and source
fingerprint.  SVG element, attribute, text, and CSS semantics remain owned by
the unmodified vendored checker and converter.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

QUALITY_REPORT_SCHEMA = "ppt-master.svg-quality-report.v1"


def svg_source_fingerprint(svg_paths: list[Path]) -> dict[str, object]:
    """Mirror the vendored report/export fingerprint for the exact SVG bytes."""

    files: list[dict[str, object]] = []
    aggregate = hashlib.sha256()
    for path in sorted(svg_paths, key=lambda value: value.name):
        file_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        files.append({"file": path.name, "sha256": file_sha256})
        aggregate.update(path.name.encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(file_sha256.encode("ascii"))
        aggregate.update(b"\n")
    return {
        "algorithm": "sha256",
        "digest": aggregate.hexdigest(),
        "file_count": len(files),
        "files": files,
    }


def final_report_diagnostics(
    report: dict[str, Any],
    svg_paths: list[Path],
) -> list[dict[str, str]]:
    """Return stable orchestration diagnostics without reinterpreting SVG rules."""

    diagnostics: list[dict[str, str]] = []
    if report.get("schema") != QUALITY_REPORT_SCHEMA:
        diagnostics.append(
            {
                "code": "SVG_QUALITY_REPORT_SCHEMA_INVALID",
                "message": "final SVG quality report schema is missing or unsupported",
            }
        )
    if report.get("stage") != "final":
        diagnostics.append(
            {
                "code": "SVG_QUALITY_REPORT_NOT_FINAL",
                "message": "SVG export requires a final-stage quality report",
            }
        )
    expected_fingerprint = svg_source_fingerprint(svg_paths)
    actual_fingerprint = report.get("source_fingerprint")
    if not isinstance(actual_fingerprint, dict):
        diagnostics.append(
            {
                "code": "SVG_QUALITY_REPORT_FINGERPRINT_MISSING",
                "message": "final SVG quality report has no verifiable source fingerprint",
            }
        )
    elif actual_fingerprint != expected_fingerprint:
        diagnostics.append(
            {
                "code": "SVG_QUALITY_REPORT_STALE",
                "message": "final SVG quality report does not match the current SVG roster",
            }
        )

    categories = report.get("categories")
    blocking = categories.get("blocking") if isinstance(categories, dict) else None
    blocking_count = blocking.get("count") if isinstance(blocking, dict) else None
    if not isinstance(blocking_count, int) or isinstance(blocking_count, bool):
        diagnostics.append(
            {
                "code": "SVG_QUALITY_REPORT_BLOCKING_COUNT_INVALID",
                "message": "final SVG quality report has no verifiable blocking count",
            }
        )
    elif blocking_count > 0:
        diagnostics.append(
            {
                "code": "SVG_QUALITY_BLOCKING",
                "message": f"final SVG quality report contains {blocking_count} blocking issue(s)",
            }
        )

    summary = report.get("summary")
    error_count = summary.get("errors") if isinstance(summary, dict) else None
    if not isinstance(error_count, int) or isinstance(error_count, bool):
        diagnostics.append(
            {
                "code": "SVG_QUALITY_REPORT_ERROR_COUNT_INVALID",
                "message": "final SVG quality report has no verifiable error count",
            }
        )
    elif error_count > 0:
        diagnostics.append(
            {
                "code": "SVG_QUALITY_ERRORS_PRESENT",
                "message": f"final SVG quality report contains errors in {error_count} file(s)",
            }
        )
    if report.get("_commandError"):
        diagnostics.append(
            {
                "code": "SVG_QUALITY_CHECKER_COMMAND_FAILED",
                "message": str(report["_commandError"])[:1000],
            }
        )
    return diagnostics


def final_report_passed(report: dict[str, Any], svg_paths: list[Path]) -> bool:
    return not final_report_diagnostics(report, svg_paths)


def advisory_count(report: dict[str, Any]) -> int:
    """Count upstream warnings for receipt status without promoting them to errors."""

    categories = report.get("categories")
    introduced = categories.get("introduced") if isinstance(categories, dict) else None
    introduced_count = introduced.get("count") if isinstance(introduced, dict) else 0
    source_import = categories.get("source-import") if isinstance(categories, dict) else None
    source_import_count = source_import.get("count") if isinstance(source_import, dict) else 0
    return sum(
        value
        for value in (introduced_count, source_import_count)
        if isinstance(value, int) and not isinstance(value, bool) and value > 0
    )


def receipt_status(report: dict[str, Any], svg_paths: list[Path]) -> str:
    if not final_report_passed(report, svg_paths):
        return "blocking"
    return "passed-with-warnings" if advisory_count(report) else "passed"
