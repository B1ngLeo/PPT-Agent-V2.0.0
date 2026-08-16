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


class CreateUploadSessionData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str = Field(min_length=1, max_length=255)
    declared_mime_type: str = Field(min_length=1, max_length=160, alias="declaredMimeType")
    expected_sha256: str = Field(pattern=r"^[a-f0-9]{64}$", alias="expectedSha256")
    size_bytes: int = Field(ge=1, le=50 * 1024 * 1024, alias="sizeBytes")


class CreateUploadSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = Field(alias="schemaVersion")
    data: CreateUploadSessionData
    base_revision_id: str | None = Field(default=None, alias="baseRevisionId")


class CreateGenerationJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = Field(alias="schemaVersion")
    data: CreateGenerationJobData
    base_revision_id: str | None = Field(default=None, alias="baseRevisionId")


class CreateDraftData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str = Field(default="", max_length=1000)
    source_id: str | None = Field(default=None, min_length=26, max_length=26, alias="sourceId")
    mode: Literal["native"] = "native"
    template_version_id: str | None = Field(
        default=None, min_length=26, max_length=26, alias="templateVersionId"
    )


class CreateDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = Field(alias="schemaVersion")
    data: CreateDraftData
    base_revision_id: None = Field(default=None, alias="baseRevisionId")


class UpdateDraftData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200)
    topic: str | None = Field(default=None, max_length=1000)
    template_version_id: str | None = Field(
        default=None, min_length=26, max_length=26, alias="templateVersionId"
    )


class UpdateDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = Field(alias="schemaVersion")
    data: UpdateDraftData
    base_revision_id: str | None = Field(default=None, alias="baseRevisionId")


class IntentData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    audience: str = Field(min_length=1, max_length=200)
    goal: str = Field(min_length=1, max_length=200)
    target_slide_count: int = Field(ge=4, le=30, alias="targetSlideCount")
    language: Literal["zh-CN", "en-US"] = "zh-CN"
    content_depth: Literal["conclusion_first", "balanced", "research"] = Field(
        default="balanced", alias="contentDepth"
    )
    visual_preference: Literal["data_first", "photo_illustration", "minimal_visual"] = Field(
        default="data_first", alias="visualPreference"
    )
    notes: str = Field(default="", max_length=4000)
    source_refs: list[str] = Field(default_factory=list, alias="sourceRefs")


class IntentRevisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = Field(alias="schemaVersion")
    data: IntentData
    base_revision_id: str | None = Field(default=None, alias="baseRevisionId")


class OutlineSlideData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outline_slide_id: str = Field(min_length=26, max_length=26, alias="outlineSlideId")
    type: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=300)
    key_points: list[str] = Field(min_length=1, alias="keyPoints")
    source_citations: list[str] = Field(default_factory=list, alias="sourceCitations")


class OutlineData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    story_summary: str = Field(min_length=1, max_length=4000, alias="storySummary")
    target_slide_count: int = Field(ge=4, le=30, alias="targetSlideCount")
    slides: list[OutlineSlideData] = Field(min_length=1, max_length=30)
    operation: Literal[
        "edit", "add", "delete", "move", "undo", "redo", "rewrite_slide", "optimize"
    ] = "edit"


class OutlineRevisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = Field(alias="schemaVersion")
    data: OutlineData
    base_revision_id: str | None = Field(default=None, alias="baseRevisionId")


class GenerateOutlineData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instruction: str = Field(default="", max_length=1000)
    action: Literal["generate", "optimize", "rewrite_slide"] = "generate"
    outline_slide_id: str | None = Field(
        default=None, min_length=26, max_length=26, alias="outlineSlideId"
    )


class GenerateOutlineRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = Field(alias="schemaVersion")
    data: GenerateOutlineData = Field(default_factory=GenerateOutlineData)
    base_revision_id: str | None = Field(default=None, alias="baseRevisionId")


class PresentationOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["update_text", "move", "delete", "accept_missing"]
    slide_id: str | None = Field(default=None, min_length=26, max_length=26, alias="slideId")
    title: str | None = Field(default=None, max_length=300)
    body: list[str] | None = None
    position: int | None = Field(default=None, ge=1, le=30)


class PresentationRevisionData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operations: list[PresentationOperation] = Field(min_length=1, max_length=100)


class PresentationRevisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = Field(alias="schemaVersion")
    data: PresentationRevisionData
    base_revision_id: str = Field(min_length=26, max_length=26, alias="baseRevisionId")


class SlideRegenerationData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instruction: str = Field(default="", max_length=2000)


class SlideRegenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = Field(alias="schemaVersion")
    data: SlideRegenerationData = Field(default_factory=SlideRegenerationData)
    base_revision_id: str = Field(min_length=26, max_length=26, alias="baseRevisionId")


class PresentationExportData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    presentation_revision_id: str | None = Field(
        default=None, min_length=26, max_length=26, alias="presentationRevisionId"
    )
    filename: str | None = Field(default=None, min_length=1, max_length=180)


class PresentationExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = Field(alias="schemaVersion")
    data: PresentationExportData = Field(default_factory=PresentationExportData)
    base_revision_id: str | None = Field(default=None, alias="baseRevisionId")
