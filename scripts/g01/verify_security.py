"""Prove every G01 threat fixture is rejected before parse."""

from __future__ import annotations

import json
from pathlib import Path

from instant_ppt_worker.errors import SECURITY_DECISION_REQUIRED, AdapterError
from instant_ppt_worker.paths import REPOSITORY_ROOT
from instant_ppt_worker.security import scan_source
from instant_ppt_worker.source_parser import parse_source

ROOT = REPOSITORY_ROOT / "tests" / "security-fixtures"
EVIDENCE = REPOSITORY_ROOT / "docs" / "evidence" / "g01-security-results.json"
FIXTURE_ID = "01ARZ3NDEKTSV4RRFFQ69G5FAY"
ORGANIZATION_ID = "01ARZ3NDEKTSV4RRFFQ69G5FAV"


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    fixtures = manifest["fixtures"]
    if len(fixtures) < 13:
        raise SystemExit("security: threat matrix is incomplete")
    results: list[dict[str, object]] = []
    decisions = ROOT / "generated" / "decisions"
    parse_root = ROOT / "generated" / "parse"
    for fixture in fixtures:
        source_key = fixture["sourceKey"]
        expected = fixture["expectedCode"]
        decision = scan_source(source_key, ROOT / source_key)
        codes = [finding.code for finding in decision.findings]
        if decision.decision != "rejected" or expected not in codes:
            raise AssertionError(f"{source_key}: expected {expected}, got {codes}")
        decision_path = decisions / f"{Path(source_key).stem}.json"
        _write(decision_path, decision.model_dump(by_alias=True, mode="json"))
        output_dir = parse_root / Path(source_key).stem
        try:
            parse_source(
                source_key,
                ROOT / source_key,
                decision_path,
                output_dir,
                source_id=FIXTURE_ID,
                organization_id=ORGANIZATION_ID,
                created_at="2026-08-16T00:00:00Z",
            )
        except AdapterError as exc:
            if exc.code != SECURITY_DECISION_REQUIRED:
                raise
        else:
            raise AssertionError(f"{source_key}: rejected source reached parse")
        if output_dir.exists():
            raise AssertionError(f"{source_key}: parse artifact directory was created")
        results.append(
            {
                "sourceKey": source_key,
                "expectedCode": expected,
                "findingCodes": codes,
                "decision": "rejected",
                "parseReached": False,
            }
        )
    _write(
        EVIDENCE,
        {
            "schemaVersion": 1,
            "fixtureCount": len(results),
            "rejectedCount": len(results),
            "parseReachedCount": 0,
            "results": results,
        },
    )
    print(f"security: {len(results)}/{len(results)} threats rejected before parse")


if __name__ == "__main__":
    main()
