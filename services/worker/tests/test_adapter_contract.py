import json
from pathlib import Path

from instant_ppt_worker.adapter import run_request


def test_parse_requires_hash_bound_clean_decision(tmp_path: Path) -> None:
    source = tmp_path / "source.md"
    source.write_text("# Before", encoding="utf-8")
    scan = {
        "schemaVersion": 1,
        "requestId": "scan",
        "operation": "scanSource",
        "workspaceRoot": str(tmp_path),
        "inputKey": "source.md",
        "outputKey": "decision.json",
    }
    _, scan_exit = run_request(json.dumps(scan))
    assert scan_exit == 0
    source.write_text("# Changed after scan", encoding="utf-8")
    parse = {
        "schemaVersion": 1,
        "requestId": "parse",
        "operation": "parseSource",
        "workspaceRoot": str(tmp_path),
        "inputKey": "source.md",
        "securityDecisionKey": "decision.json",
        "outputKey": "parsed",
        "sourceId": "01ARZ3NDEKTSV4RRFFQ69G5FAY",
        "organizationId": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
    }
    response, parse_exit = run_request(json.dumps(parse))
    assert parse_exit == 2
    assert response.error and response.error.code == "SOURCE_CLEAN_DECISION_MISMATCH"
