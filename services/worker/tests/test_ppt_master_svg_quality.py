import json
from pathlib import Path

from instant_ppt_worker.ppt_master_svg_quality import (
    final_report_diagnostics,
    final_report_passed,
    receipt_status,
    svg_source_fingerprint,
)


def _report(svg_paths: list[Path]) -> dict[str, object]:
    return {
        "schema": "ppt-master.svg-quality-report.v1",
        "stage": "final",
        "source_fingerprint": svg_source_fingerprint(svg_paths),
        "summary": {"errors": 0, "warnings": 0},
        "categories": {
            "blocking": {"count": 0, "issues": []},
            "introduced": {"count": 0, "issues": []},
            "source-import": {"count": 0, "summary": {}},
        },
    }


def test_final_report_requires_final_stage_current_hash_and_zero_errors(tmp_path: Path) -> None:
    svg = tmp_path / "slide_01.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>', encoding="utf-8")
    svg_paths = [svg]
    report = _report(svg_paths)

    assert final_report_passed(report, svg_paths) is True
    assert final_report_diagnostics(report, svg_paths) == []

    non_final = json.loads(json.dumps(report))
    non_final["stage"] = "first-page"
    assert {item["code"] for item in final_report_diagnostics(non_final, svg_paths)} == {
        "SVG_QUALITY_REPORT_NOT_FINAL"
    }

    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg"><g/></svg>', encoding="utf-8")
    assert {item["code"] for item in final_report_diagnostics(report, svg_paths)} == {
        "SVG_QUALITY_REPORT_STALE"
    }


def test_svg_warnings_are_advisory_but_errors_are_blocking(tmp_path: Path) -> None:
    svg = tmp_path / "slide_01.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>', encoding="utf-8")
    svg_paths = [svg]
    warning_report = _report(svg_paths)
    warning_report["summary"] = {"errors": 0, "warnings": 1}
    warning_report["categories"]["introduced"] = {  # type: ignore[index]
        "count": 1,
        "issues": [{"file": "slide_01.svg", "message": "advisory spacing"}],
    }

    assert final_report_passed(warning_report, svg_paths) is True
    assert receipt_status(warning_report, svg_paths) == "passed-with-warnings"

    blocking_report = json.loads(json.dumps(warning_report))
    blocking_report["summary"]["errors"] = 1
    blocking_report["categories"]["blocking"] = {
        "count": 1,
        "issues": [{"file": "slide_01.svg", "message": "text overflow"}],
    }

    assert final_report_passed(blocking_report, svg_paths) is False
    assert receipt_status(blocking_report, svg_paths) == "blocking"
