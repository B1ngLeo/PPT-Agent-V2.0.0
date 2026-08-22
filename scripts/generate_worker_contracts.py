"""Materialize JSON Schemas for the G01 adapter boundary."""

import json

from instant_ppt_worker.models import AdapterRequest, AdapterResponse, SecurityDecision
from instant_ppt_worker.paths import REPOSITORY_ROOT
from instant_ppt_worker.presentation_agent_runtime import AgentDecision
from instant_ppt_worker.presentation_agent_tools import SlideSceneGraph
from instant_ppt_worker.workflow_models import (
    PageBlueprintArtifact,
    WorkflowRequestV2,
    WorkflowResultV2,
)
from pydantic import TypeAdapter


def main() -> None:
    target = REPOSITORY_ROOT / "services" / "worker" / "contracts"
    target.mkdir(parents=True, exist_ok=True)
    contracts = {
        "engine-adapter.request.schema.json": TypeAdapter(AdapterRequest).json_schema(),
        "engine-adapter.response.schema.json": AdapterResponse.model_json_schema(),
        "security-decision.schema.json": SecurityDecision.model_json_schema(),
        "page-blueprint.v1.schema.json": PageBlueprintArtifact.model_json_schema(),
        "slide-scene-graph.v1.schema.json": SlideSceneGraph.model_json_schema(),
        "agent-decision.v1.schema.json": AgentDecision.model_json_schema(),
        "workflow-request.v2.schema.json": WorkflowRequestV2.model_json_schema(),
        "workflow-result.v2.schema.json": WorkflowResultV2.model_json_schema(),
    }
    for name, schema in contracts.items():
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        contract_version = "v2" if ".v2." in name else "v1"
        schema["$id"] = (
            f"https://contracts.instant-ppt.example/worker/{contract_version}/{name}"
        )
        (target / name).write_text(
            json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
