"""Worker settings that are safe to import before business orchestration exists."""

from pydantic import BaseModel, ConfigDict


class WorkerContract(BaseModel):
    """Versioned boundary advertised by the sole engine adapter."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = 1
    adapter_name: str = "ppt-master-engine-adapter"
    engine_version: str = "ppt-master@v4.7.0+e8323bfa"
    parser_version: str = "source-parser@1+ppt-master-v4.7.0"
