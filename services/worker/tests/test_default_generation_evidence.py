import json
import zipfile
from pathlib import Path

from instant_ppt_worker.default_generation_pipeline import (
    _build_failed_agent_evidence_bundle,
    _failure_project_candidate,
)


def test_failed_agent_evidence_bundle_survives_project_cleanup_boundary(
    tmp_path: Path,
) -> None:
    project = tmp_path / "projects" / "job-12345678_ppt169_20260827"
    (project / "agent" / "turns").mkdir(parents=True)
    (project / "agent" / "tool-calls").mkdir(parents=True)
    (project / "agent" / "rejected-design-spec").mkdir(parents=True)
    (project / "validation").mkdir(parents=True)
    (project / "agent" / "turns" / "turn.json").write_text(
        json.dumps(
            {
                "provider": "qwen",
                "finishReason": "stop",
                "usage": {"inputTokens": 10, "outputTokens": 20},
            }
        ),
        encoding="utf-8",
    )
    (project / "agent" / "tool-calls" / "call.json").write_text(
        json.dumps(
            {
                "status": "policy-denied",
                "observation": {"code": "DESIGN_SPEC_SCHEMA_INVALID"},
            }
        ),
        encoding="utf-8",
    )
    (project / "agent" / "rejected-design-spec" / "draft.md").write_text(
        "## V. 布局原则\n",
        encoding="utf-8",
    )
    (project / "agent" / "failure-metadata.json").write_text(
        json.dumps({"endpointHost": "dashscope.aliyuncs.com"}),
        encoding="utf-8",
    )
    (project / "validation" / "workflow-events.jsonl").write_text(
        '{"stage":"strategist","action":"failed"}\n',
        encoding="utf-8",
    )
    bundle = tmp_path / "failed-agent-evidence.zip"

    count = _build_failed_agent_evidence_bundle(project, bundle)

    assert count == 5
    with zipfile.ZipFile(bundle) as archive:
        names = set(archive.namelist())
        assert "agent/turns/turn.json" in names
        assert "agent/tool-calls/call.json" in names
        assert "agent/rejected-design-spec/draft.md" in names
        assert "agent/failure-metadata.json" in names
        assert "validation/workflow-events.jsonl" in names
        assert "DESIGN_SPEC_SCHEMA_INVALID" in archive.read(
            "agent/tool-calls/call.json"
        ).decode("utf-8")


def test_failure_project_candidate_resolves_timestamped_project(tmp_path: Path) -> None:
    output_key = "projects/job-12345678"
    expected = tmp_path / "projects" / "job-12345678_ppt169_20260827"
    expected.mkdir(parents=True)

    assert _failure_project_candidate(tmp_path, output_key) == expected
