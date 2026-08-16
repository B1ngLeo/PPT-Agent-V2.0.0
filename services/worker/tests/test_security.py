import json
from pathlib import Path

from instant_ppt_worker.adapter import run_request


def _payload(root: Path, source: str, decision: str = "decision.json") -> str:
    return json.dumps(
        {
            "schemaVersion": 1,
            "requestId": "scan-test",
            "operation": "scanSource",
            "workspaceRoot": str(root),
            "inputKey": source,
            "outputKey": decision,
        }
    )


def test_clean_markdown_is_accepted(tmp_path: Path) -> None:
    (tmp_path / "clean.md").write_text("# Safe\n\nLocal content", encoding="utf-8")
    response, exit_code = run_request(_payload(tmp_path, "clean.md"))
    assert exit_code == 0
    assert response.status == "succeeded"
    decision = json.loads((tmp_path / "decision.json").read_text(encoding="utf-8"))
    assert decision["decision"] == "clean"


def test_eicar_and_external_html_are_rejected(tmp_path: Path) -> None:
    (tmp_path / "eicar.txt").write_text(
        "INSTANT-PPT-EICAR-TEST-SIGNATURE",
        encoding="utf-8",
    )
    response, exit_code = run_request(_payload(tmp_path, "eicar.txt", "eicar.json"))
    assert exit_code == 3
    assert response.error and response.error.code == "SOURCE_SECURITY_REJECTED"

    (tmp_path / "external.html").write_text(
        '<html><img src="https://example.invalid/track.png"></html>',
        encoding="utf-8",
    )
    response, exit_code = run_request(_payload(tmp_path, "external.html", "external.json"))
    assert exit_code == 3
    assert response.error and "EXTERNAL_REFERENCE" in response.error.message


def test_object_key_traversal_is_rejected(tmp_path: Path) -> None:
    response, exit_code = run_request(_payload(tmp_path, "../outside.md"))
    assert exit_code == 2
    assert response.error and response.error.code == "ENGINE_INVALID_REQUEST"
