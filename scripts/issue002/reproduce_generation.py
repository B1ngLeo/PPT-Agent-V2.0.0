from __future__ import annotations

import argparse
import json
from pathlib import Path

from instant_ppt_domain.config import DomainSettings
from instant_ppt_domain.database import create_domain_engine, create_session_factory
from instant_ppt_worker.adapter import run_request
from instant_ppt_worker.approved_sources import resolve_approved_sources
from instant_ppt_worker.default_generation_pipeline import _load_generation, _stable_id
from instant_ppt_worker.default_workflow_request import build_default_workflow_request
from instant_ppt_worker.source_pipeline import WorkerObjectSettings, WorkerObjectStore


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--organization-id", required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    if workspace.exists():
        raise RuntimeError(f"diagnostic workspace already exists: {workspace}")
    workspace.mkdir(parents=True)

    settings = DomainSettings.from_env()
    engine = create_domain_engine(settings.database_url)
    factory = create_session_factory(engine)
    store = WorkerObjectStore(WorkerObjectSettings.from_env())
    try:
        with factory() as session:
            _, snapshot, slides = _load_generation(
                session,
                args.job_id,
                args.organization_id,
            )
            sources = resolve_approved_sources(
                session,
                snapshot,
                object_store=store,
                workspace=workspace / "approved-sources",
            )
        workflow_run_id = _stable_id(f"{args.job_id}:default-agentic-workflow")
        request = build_default_workflow_request(
            snapshot,
            slides,
            workflow_run_id=workflow_run_id,
            sources=sources.model_dump(by_alias=True, mode="json"),
        )
        adapter_request = {
            "schemaVersion": 2,
            "requestId": f"{args.job_id}-diagnostic",
            "operation": "generatePptxDefault",
            "workspaceRoot": str(workspace),
            "outputKey": f"projects/job-{args.job_id[-8:]}",
            "workflow": request.model_dump(by_alias=True, mode="json"),
        }
        response, exit_code = run_request(json.dumps(adapter_request, ensure_ascii=False))
        print(
            json.dumps(
                response.model_dump(by_alias=True, mode="json"),
                ensure_ascii=True,
                indent=2,
            )
        )
        raise SystemExit(exit_code)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
