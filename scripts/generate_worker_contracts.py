"""Materialize JSON Schemas for the G01 adapter boundary."""

import json

from instant_ppt_worker.models import AdapterRequest, AdapterResponse, SecurityDecision
from instant_ppt_worker.paths import REPOSITORY_ROOT
from pydantic import TypeAdapter


def main() -> None:
    target = REPOSITORY_ROOT / "services" / "worker" / "contracts"
    target.mkdir(parents=True, exist_ok=True)
    contracts = {
        "engine-adapter.request.schema.json": TypeAdapter(AdapterRequest).json_schema(),
        "engine-adapter.response.schema.json": AdapterResponse.model_json_schema(),
        "security-decision.schema.json": SecurityDecision.model_json_schema(),
    }
    for name, schema in contracts.items():
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        schema["$id"] = f"https://contracts.instant-ppt.example/worker/v1/{name}"
        (target / name).write_text(
            json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
