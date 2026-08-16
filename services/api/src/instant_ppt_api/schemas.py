"""HTTP models for the G02 orchestration spike."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class CreateGenerationJobData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent_revision_id: str | None = Field(default=None, alias="intentRevisionId")
    outline_revision_id: str | None = Field(default=None, alias="outlineRevisionId")
    template_version_id: str | None = Field(default=None, alias="templateVersionId")
    slide_count: int = Field(default=3, ge=1, le=30, alias="slideCount")
    source_hashes: list[str] = Field(default_factory=list, alias="sourceHashes")
    failure_modes: dict[int, Literal["none", "once", "always"]] = Field(
        default_factory=dict, alias="failureModes"
    )
    step_delay_ms: int = Field(default=0, ge=0, le=10_000, alias="stepDelayMs")
    crash_once_at_position: int | None = Field(
        default=None, ge=1, le=30, alias="crashOnceAtPosition"
    )


class MutationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = Field(alias="schemaVersion")
    data: dict[str, Any]
    base_revision_id: str | None = Field(default=None, alias="baseRevisionId")


class CreateGenerationJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = Field(alias="schemaVersion")
    data: CreateGenerationJobData
    base_revision_id: str | None = Field(default=None, alias="baseRevisionId")
