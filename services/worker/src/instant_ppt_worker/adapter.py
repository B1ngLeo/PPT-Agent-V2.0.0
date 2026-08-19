"""The sole JSON CLI boundary around the vendored ppt-master engine."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter, ValidationError

from instant_ppt_worker.agentic_workflow import run_default_workflow
from instant_ppt_worker.artifacts import artifact_ref
from instant_ppt_worker.errors import INVALID_REQUEST, UNSAFE_SOURCE, AdapterError
from instant_ppt_worker.models import (
    AdapterRequest,
    AdapterResponse,
    ErrorDetail,
    ParseSourceRequest,
    RenderDeckRequest,
    ScanSourceRequest,
)
from instant_ppt_worker.paths import resolve_key
from instant_ppt_worker.renderer import render_deck
from instant_ppt_worker.security import scan_source
from instant_ppt_worker.source_parser import parse_source
from instant_ppt_worker.workflow_models import GeneratePptxDefaultRequest

REQUEST_ADAPTER = TypeAdapter(AdapterRequest)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _workspace(
    request: ScanSourceRequest
    | ParseSourceRequest
    | RenderDeckRequest
    | GeneratePptxDefaultRequest,
) -> Path:
    root = Path(request.workspace_root).resolve()
    if not root.is_dir():
        raise AdapterError(INVALID_REQUEST, "workspaceRoot must be an existing directory")
    return root


def execute(
    request: ScanSourceRequest
    | ParseSourceRequest
    | RenderDeckRequest
    | GeneratePptxDefaultRequest,
) -> AdapterResponse:
    root = _workspace(request)
    artifacts = []
    if isinstance(request, ScanSourceRequest):
        source = resolve_key(root, request.input_key, must_exist=True)
        decision_path = resolve_key(root, request.output_key)
        decision = scan_source(request.input_key, source)
        _write_json(decision_path, decision.model_dump(by_alias=True, mode="json"))
        artifacts.append(artifact_ref(root, decision_path, "securityDecision", "application/json"))
        if decision.decision != "clean":
            raise AdapterError(
                UNSAFE_SOURCE,
                "; ".join(f"{item.code}: {item.message}" for item in decision.findings),
                exit_code=3,
            )
    elif isinstance(request, ParseSourceRequest):
        source = resolve_key(root, request.input_key, must_exist=True)
        decision = resolve_key(root, request.security_decision_key, must_exist=True)
        output = resolve_key(root, request.output_key)
        result = parse_source(
            request.input_key,
            source,
            decision,
            output,
            source_id=request.source_id,
            organization_id=request.organization_id,
            created_at=request.created_at,
        )
        for path in result["paths"]:
            artifacts.append(artifact_ref(root, path, "sourceArtifact"))
    elif isinstance(request, RenderDeckRequest):
        deck_plan = resolve_key(root, request.deck_plan_key, must_exist=True)
        cover_image = (
            resolve_key(root, request.cover_image_key, must_exist=True)
            if request.cover_image_key
            else None
        )
        output = resolve_key(root, request.output_key)
        result = render_deck(
            deck_plan,
            output,
            organization_id=request.organization_id,
            created_at=request.created_at,
            cover_image_path=cover_image,
        )
        for path in result["paths"]:
            artifacts.append(artifact_ref(root, path, "renderArtifact"))
    else:
        project = resolve_key(root, request.output_key)
        result = run_default_workflow(root, project, request.workflow)
        for path in result["paths"]:
            artifacts.append(artifact_ref(root, path, "workflowArtifact"))
    return AdapterResponse(
        request_id=request.request_id,
        operation=request.operation,
        status="succeeded",
        artifacts=artifacts,
    )


def run_request(payload: str) -> tuple[AdapterResponse, int]:
    request: (
        ScanSourceRequest
        | ParseSourceRequest
        | RenderDeckRequest
        | GeneratePptxDefaultRequest
        | None
    ) = None
    try:
        request = REQUEST_ADAPTER.validate_json(payload)
        return execute(request), 0
    except ValidationError as exc:
        response = AdapterResponse(
            request_id="invalid",
            operation="scanSource",
            status="failed",
            error=ErrorDetail(code=INVALID_REQUEST, message=str(exc)),
        )
        return response, 2
    except (AdapterError, OSError, ValueError) as exc:
        error = exc if isinstance(exc, AdapterError) else AdapterError(INVALID_REQUEST, str(exc))
        response = AdapterResponse(
            request_id=request.request_id if request else "invalid",
            operation=request.operation if request else "scanSource",
            status="failed",
            error=ErrorDetail(code=error.code, message=error.message),
        )
        return response, error.exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Versioned JSON boundary for ppt-master")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--request", help="request JSON file")
    source.add_argument("--stdin", action="store_true", help="read request JSON from stdin")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    payload = (
        sys.stdin.read() if arguments.stdin else Path(arguments.request).read_text(encoding="utf-8")
    )
    response, exit_code = run_request(payload)
    print(response.model_dump_json(by_alias=True, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
