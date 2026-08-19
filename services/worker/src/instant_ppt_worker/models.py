"""Versioned JSON models for the adapter boundary."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from instant_ppt_worker.workflow_models import GeneratePptxDefaultRequest


class ContractModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=lambda value: (
            value.split("_")[0] + "".join(part.title() for part in value.split("_")[1:])
        ),
        populate_by_name=True,
        extra="forbid",
    )


class ScanSourceRequest(ContractModel):
    schema_version: Literal[1]
    request_id: str = Field(min_length=1, max_length=128)
    operation: Literal["scanSource"]
    workspace_root: str = Field(min_length=1)
    input_key: str = Field(min_length=1)
    output_key: str = Field(min_length=1)


class ParseSourceRequest(ContractModel):
    schema_version: Literal[1]
    request_id: str = Field(min_length=1, max_length=128)
    operation: Literal["parseSource"]
    workspace_root: str = Field(min_length=1)
    input_key: str = Field(min_length=1)
    security_decision_key: str = Field(min_length=1)
    output_key: str = Field(min_length=1)
    source_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    organization_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    created_at: str = "2026-08-16T00:00:00Z"


class RenderDeckRequest(ContractModel):
    schema_version: Literal[1]
    request_id: str = Field(min_length=1, max_length=128)
    operation: Literal["renderDeck"]
    workspace_root: str = Field(min_length=1)
    deck_plan_key: str = Field(min_length=1)
    cover_image_key: str | None = None
    output_key: str = Field(min_length=1)
    organization_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    created_at: str = "2026-08-16T00:00:00Z"


AdapterRequest = Annotated[
    ScanSourceRequest | ParseSourceRequest | RenderDeckRequest | GeneratePptxDefaultRequest,
    Field(discriminator="operation"),
]


class ArtifactRef(ContractModel):
    kind: str
    key: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    size_bytes: int = Field(ge=0)
    mime_type: str


class ErrorDetail(ContractModel):
    code: str
    message: str


class AdapterResponse(ContractModel):
    schema_version: Literal[1] = 1
    request_id: str
    operation: Literal["scanSource", "parseSource", "renderDeck", "generatePptxDefault"]
    status: Literal["succeeded", "failed"]
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    error: ErrorDetail | None = None


class SecurityFinding(ContractModel):
    code: str
    message: str


class SecurityDecision(ContractModel):
    schema_version: Literal[1] = 1
    decision: Literal["clean", "rejected"]
    source_key: str
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    detected_type: str
    scanner: str = "intake-harness@1"
    findings: list[SecurityFinding] = Field(default_factory=list)
    checked_at: str = "2026-08-16T00:00:00Z"


class TemplateBinding(ContractModel):
    schema_version: Literal[1]
    template_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    template_version_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    compatibility_version: str = Field(min_length=1)
    role_bindings: dict[str, str]


class SlidePlan(ContractModel):
    schema_version: Literal[1]
    slide_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    outline_slide_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    order: int = Field(ge=0)
    role: str = Field(min_length=1)
    title: str = Field(min_length=1)
    body: list[str] = Field(min_length=1)
    editable: bool


class DeckPlan(ContractModel):
    schema_version: Literal[1]
    snapshot_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    title: str = Field(min_length=1)
    mode_id: Literal["native"]
    template_binding: TemplateBinding
    slides: list[SlidePlan] = Field(min_length=1, max_length=30)
