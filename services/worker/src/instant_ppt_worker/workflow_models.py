"""Versioned Default Agentic workflow contracts for ISSUE-002."""

from __future__ import annotations

from datetime import datetime
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class WorkflowContractModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=lambda value: (
            value.split("_")[0] + "".join(part.title() for part in value.split("_")[1:])
        ),
        populate_by_name=True,
        extra="forbid",
    )


class WorkflowVersions(WorkflowContractModel):
    workflow: str = Field(pattern=r"^instant-ppt-default@v\d+\.\d+\.\d+$")
    engine: Literal["ppt-master@v4.7.0"]
    model: str = Field(min_length=1, max_length=160)
    prompt: str = Field(min_length=1, max_length=160)
    reference: Literal["ppt-master-default@v4.7.0"]
    adapter: Literal["engine-adapter@v2"] = "engine-adapter@v2"


class ApprovalSnapshotRef(WorkflowContractModel):
    snapshot_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    snapshot_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    intent_revision_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    outline_revision_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    approval_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    approved_by: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    approved_at: datetime


class ApprovedIntent(WorkflowContractModel):
    title: str = Field(min_length=1, max_length=300)
    objective: str = Field(min_length=1, max_length=2000)
    audience: str = Field(min_length=1, max_length=500)
    desired_outcome: str = Field(min_length=1, max_length=1000)
    language: str = Field(pattern=r"^[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})+$")
    delivery_context: str = Field(min_length=1, max_length=500)


class ApprovedOutlineSlide(WorkflowContractModel):
    outline_slide_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    slide_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    pnn: str = Field(pattern=r"^P\d{2,3}$")
    order: int = Field(ge=1, le=30)
    role: Literal[
        "cover",
        "section",
        "content",
        "data",
        "comparison",
        "timeline",
        "risk_action",
        "ending",
    ]
    title: str = Field(min_length=1, max_length=300)
    audience_question: str = Field(min_length=1, max_length=1000)


class SourceFragment(WorkflowContractModel):
    fragment_id: str = Field(min_length=1, max_length=160)
    page: int | None = Field(default=None, ge=1)
    kind: Literal["heading", "paragraph", "table", "list", "chart-data"]
    text: str = Field(min_length=1, max_length=16000)
    text_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class ApprovedSourceArtifact(WorkflowContractModel):
    source_artifact_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    source_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    organization_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    object_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    media_type: str = Field(min_length=1, max_length=160)
    private_nonce: str | None = Field(default=None, min_length=12, max_length=128)
    parsed_at: datetime
    fragments: list[SourceFragment] = Field(min_length=1, max_length=256)


class SourceManifest(WorkflowContractModel):
    mode: Literal["approved-artifacts", "no-source-limited"]
    artifacts: list[ApprovedSourceArtifact] = Field(max_length=8)
    manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    continue_limited_draft: bool = False

    @model_validator(mode="after")
    def validate_mode(self) -> SourceManifest:
        if self.mode == "approved-artifacts" and not self.artifacts:
            raise ValueError("approved-artifacts mode requires at least one source artifact")
        if self.mode == "no-source-limited":
            if self.artifacts:
                raise ValueError("no-source-limited mode cannot include source artifacts")
            if not self.continue_limited_draft:
                raise ValueError("no-source-limited mode requires an explicit continue choice")
        return self


class TemplateCandidateDescriptor(WorkflowContractModel):
    candidate_id: str = Field(min_length=1, max_length=160)
    kind: Literal["brand", "style", "layout", "deck"]
    provenance: Literal["library", "explicit"]
    descriptor_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    workspace_root: str = Field(min_length=1, max_length=2048)
    content_accessed: Literal[False] = False
    installed: Literal[False] = False


class TemplatePolicy(WorkflowContractModel):
    mode: Literal["free_design", "templates"]
    candidates: list[TemplateCandidateDescriptor] = Field(max_length=32)
    active_template_version: str | None = Field(default=None, pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")

    @model_validator(mode="after")
    def validate_template_state(self) -> TemplatePolicy:
        if self.mode == "free_design" and self.active_template_version is not None:
            raise ValueError("free_design requires activeTemplateVersion=null")
        return self


class ProvidedImageAsset(WorkflowContractModel):
    asset_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    filename: str = Field(min_length=1, max_length=180, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    workspace_key: str = Field(min_length=1, max_length=512)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    media_type: Literal["image/png", "image/jpeg", "image/webp"]
    purpose: str = Field(min_length=1, max_length=500)
    slide_ids: list[str] = Field(min_length=1, max_length=32)
    required: bool = True
    crop_policy: Literal["adaptive", "no-crop"] = "adaptive"
    layout_pattern: str = Field(default="#P1-02", min_length=1, max_length=160)
    license: str = Field(default="user-provided", min_length=1, max_length=160)

    @model_validator(mode="after")
    def validate_media_suffix(self) -> ProvidedImageAsset:
        allowed = {
            "image/png": {".png"},
            "image/jpeg": {".jpg", ".jpeg"},
            "image/webp": {".webp"},
        }[self.media_type]
        if PurePosixPath(self.filename).suffix.lower() not in allowed:
            raise ValueError("provided image filename suffix must match mediaType")
        return self

    @field_validator("workspace_key")
    @classmethod
    def validate_workspace_key(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or value != path.as_posix():
            raise ValueError("provided image workspaceKey must be a safe relative POSIX path")
        return value

    @field_validator("slide_ids")
    @classmethod
    def validate_slide_ids(cls, value: list[str]) -> list[str]:
        alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
        if len(value) != len(set(value)) or any(
            len(item) != 26 or any(character not in alphabet for character in item)
            for item in value
        ):
            raise ValueError("provided image slideIds must be unique ULIDs")
        return value


class OfficeNativeImageFallback(WorkflowContractModel):
    slide_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    construction: Literal["native-shapes", "native-diagram", "native-chart"]
    trigger_codes: list[str] = Field(min_length=1, max_length=16)
    decision_receipt_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class ImagePolicy(WorkflowContractModel):
    scope: Literal["none", "cover_only", "selective"]
    usage: list[Literal["ai", "web", "provided", "placeholder", "none"]] = Field(
        min_length=1, max_length=4
    )
    notes: dict[str, str] = Field(default_factory=dict)
    ai_path: Literal["auto", "api", "host-native", "manual"] | None = None
    ai_path_chain: list[Literal["api", "host-native", "manual"]] = Field(
        default_factory=list, max_length=3
    )
    provided_assets: list[ProvidedImageAsset] = Field(default_factory=list, max_length=32)
    office_native_fallbacks: list[OfficeNativeImageFallback] = Field(
        default_factory=list, max_length=32
    )

    @model_validator(mode="after")
    def validate_usage(self) -> ImagePolicy:
        if len(self.usage) != len(set(self.usage)):
            raise ValueError("imageUsage values must be unique")
        if "none" in self.usage and self.usage != ["none"]:
            raise ValueError("imageUsage none is exclusive")
        if self.scope == "none" and self.usage != ["none"]:
            raise ValueError("imageScope none maps only to imageUsage=['none']")
        if self.scope != "none" and self.usage == ["none"]:
            raise ValueError("cover_only/selective require at least one real image source")
        if self.scope == "none" and (
            self.notes
            or self.ai_path is not None
            or self.ai_path_chain
            or self.provided_assets
            or self.office_native_fallbacks
        ):
            raise ValueError("imageScope none cannot carry image planning state")
        if self.scope != "none" and not self.notes:
            raise ValueError("non-none imageScope requires role-specific imageNotes")
        if ("provided" in self.usage) != bool(self.provided_assets):
            raise ValueError("provided imageUsage must match providedAssets")
        if "ai" in self.usage:
            if self.ai_path is None or not self.ai_path_chain:
                raise ValueError("AI image usage requires a confirmed path and declared chain")
            if len(self.ai_path_chain) != len(set(self.ai_path_chain)):
                raise ValueError("AI image path chain must not repeat strategies")
            if self.ai_path == "auto":
                if self.ai_path_chain[-1] != "manual":
                    raise ValueError("automatic AI image path chain must end in manual")
            elif self.ai_path == "manual":
                if self.ai_path_chain != ["manual"]:
                    raise ValueError("manual AI image path cannot declare automated strategies")
            elif self.ai_path_chain not in ([self.ai_path], [self.ai_path, "manual"]):
                raise ValueError("explicit AI image paths cannot switch automated providers")
        elif self.ai_path is not None or self.ai_path_chain:
            raise ValueError("AI image path applies only when imageUsage includes ai")
        fallback_slide_ids = [value.slide_id for value in self.office_native_fallbacks]
        if len(fallback_slide_ids) != len(set(fallback_slide_ids)):
            raise ValueError("office-native fallback decisions must be unique per slide")
        if self.office_native_fallbacks and "ai" not in self.usage:
            raise ValueError("office-native image fallback applies only to AI acquisition")
        return self


class ProductionPolicy(WorkflowContractModel):
    proactive_speaker_notes: bool
    proactive_custom_animations: bool
    proactive_narration_audio: bool
    effective_speaker_notes: Literal["enabled", "disabled"]
    effective_custom_animations: Literal["enabled", "disabled"]
    effective_narration_audio: Literal["enabled", "disabled"]
    visual_review: bool
    refine_spec: bool

    @model_validator(mode="after")
    def validate_dependencies(self) -> ProductionPolicy:
        if (
            self.effective_narration_audio == "enabled"
            and self.effective_speaker_notes != "enabled"
        ):
            raise ValueError("narration audio requires speaker notes")
        return self


class ResearchPolicy(WorkflowContractModel):
    mode: Literal["closed_corpus", "approved_web_research"]
    allowed_domains: list[str] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def validate_domains(self) -> ResearchPolicy:
        if self.mode == "closed_corpus" and self.allowed_domains:
            raise ValueError("closed_corpus cannot allow research domains")
        if self.mode == "approved_web_research" and not self.allowed_domains:
            raise ValueError("approved_web_research requires an explicit domain allowlist")
        return self


class AgentRuntimePolicy(WorkflowContractModel):
    allowed_tools: list[
        Literal[
            "read-source",
            "write-project",
            "run-vendored-script",
            "start-live-preview",
            "provider-text",
            "provider-image",
            "approved-web",
        ]
    ] = Field(min_length=1)
    allow_subagent_research: bool = False
    allow_subagent_review: bool = False
    allow_subagent_svg_authoring: Literal[False] = False
    max_turns: int = Field(ge=1, le=200)
    max_tokens: int = Field(ge=1, le=2_000_000)
    max_cost_microunits: int = Field(ge=0)
    soft_timeout_seconds: int = Field(ge=30, le=43_200)
    hard_timeout_seconds: int = Field(ge=60, le=86_400)
    preview_idle_timeout_seconds: int = Field(ge=0, le=86_400)
    max_stage_attempts: int = Field(ge=1, le=5)

    @model_validator(mode="after")
    def validate_timeouts(self) -> AgentRuntimePolicy:
        if self.hard_timeout_seconds <= self.soft_timeout_seconds:
            raise ValueError("hard timeout must exceed soft timeout")
        return self


class ConfirmationPolicy(WorkflowContractModel):
    mode: Literal["explicit_user", "delegated"]
    delegation_scope: list[str] = Field(default_factory=list, max_length=32)
    policy_version: str = Field(min_length=1, max_length=80)
    receipt_ttl_seconds: int = Field(ge=60, le=604_800)

    @model_validator(mode="after")
    def validate_delegation(self) -> ConfirmationPolicy:
        if self.mode == "delegated" and not self.delegation_scope:
            raise ValueError("delegated confirmation requires a bounded scope")
        if self.mode == "explicit_user" and self.delegation_scope:
            raise ValueError("explicit_user mode cannot carry delegation scope")
        return self


class ResumeCheckpointRef(WorkflowContractModel):
    checkpoint_set_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    checkpoint_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    fencing_token: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")


class WorkflowRequestV2(WorkflowContractModel):
    schema_version: Literal[2]
    workflow_run_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    organization_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    route: Literal["generate_pptx"]
    profile: Literal["default-agentic", "quick-engineering"]
    versions: WorkflowVersions
    approval: ApprovalSnapshotRef
    intent: ApprovedIntent
    outline: list[ApprovedOutlineSlide] = Field(min_length=1, max_length=30)
    sources: SourceManifest
    template: TemplatePolicy
    image: ImagePolicy
    research: ResearchPolicy
    production: ProductionPolicy
    runtime: AgentRuntimePolicy
    confirmation: ConfirmationPolicy
    requested_stage: Literal[
        "attribution_guard",
        "source_import",
        "stage1",
        "template_handoff",
        "stage2",
        "design_spec_gate1",
        "refine_spec",
        "spec_lock_gate2",
        "executor_p01",
        "executor_remaining",
        "final_svg_gate",
        "chart_gate",
        "notes",
        "animations",
        "visual_review",
        "step7_finalize",
        "step7_export",
        "postflight",
        "narration",
        "publish",
    ] = "attribution_guard"
    resume: ResumeCheckpointRef | None = None

    @model_validator(mode="after")
    def validate_profile(self) -> WorkflowRequestV2:
        if self.profile == "default-agentic":
            if self.versions.reference != "ppt-master-default@v4.7.0":
                raise ValueError("default-agentic requires the Default reference authority")
            if "run-vendored-script" not in self.runtime.allowed_tools:
                raise ValueError("default-agentic requires the vendored-script capability")
        if self.production.visual_review and not self.runtime.allow_subagent_review:
            raise ValueError("visual review requires the bounded review-agent capability")
        outline_slide_ids = {slide.slide_id for slide in self.outline}
        image_note_ids = {
            self.outline[0].slide_id if key == "cover" else key
            for key in self.image.notes
        }
        if not image_note_ids.issubset(outline_slide_ids):
            raise ValueError("imageNotes must reference the exact approved slide roster")
        if self.image.scope == "cover_only" and image_note_ids != {
            self.outline[0].slide_id
        }:
            raise ValueError("cover_only image scope must bind only P01")
        planned_slide_ids = {
            slide_id
            for asset in self.image.provided_assets
            for slide_id in asset.slide_ids
        }
        fallback_slide_ids = {
            fallback.slide_id for fallback in self.image.office_native_fallbacks
        }
        if not planned_slide_ids.issubset(image_note_ids):
            raise ValueError("provided image targets must be confirmed in imageNotes")
        if not fallback_slide_ids.issubset(image_note_ids):
            raise ValueError("office-native fallback targets must be confirmed in imageNotes")
        if any(
            value in {"api", "host-native"} for value in self.image.ai_path_chain
        ) and "provider-image" not in self.runtime.allowed_tools:
            raise ValueError("automated image acquisition requires provider-image capability")
        orders = [slide.order for slide in self.outline]
        if orders != list(range(1, len(self.outline) + 1)):
            raise ValueError("outline order must be contiguous and authoritative")
        if [slide.pnn for slide in self.outline] != [
            f"P{index:02d}" for index in range(1, len(self.outline) + 1)
        ]:
            raise ValueError("outline PNN values must match the exact ordered roster")
        if len({slide.slide_id for slide in self.outline}) != len(self.outline):
            raise ValueError("outline slideId values must be unique")
        if len({slide.outline_slide_id for slide in self.outline}) != len(self.outline):
            raise ValueError("outlineSlideId values must be unique")
        return self


class GeneratePptxDefaultRequest(WorkflowContractModel):
    schema_version: Literal[2]
    request_id: str = Field(min_length=1, max_length=128)
    operation: Literal["generatePptxDefault"]
    workspace_root: str = Field(min_length=1)
    output_key: str = Field(min_length=1)
    workflow: WorkflowRequestV2

    @model_validator(mode="after")
    def validate_default_profile(self) -> GeneratePptxDefaultRequest:
        if self.workflow.profile != "default-agentic":
            raise ValueError("generatePptxDefault only accepts profile=default-agentic")
        return self


class WorkflowReceipt(WorkflowContractModel):
    receipt_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    kind: Literal[
        "attribution",
        "stage1-confirmation",
        "template-handoff",
        "stage2-confirmation",
        "image-resources",
        "design-spec-gate1",
        "refine-spec-approval",
        "spec-lock-gate2",
        "design-parameter-confirmation",
        "live-preview",
        "first-page-gate",
        "final-svg-gate",
        "chart-gate",
        "content-gate",
        "final-svg-content-gate",
        "speaker-notes",
        "custom-animations",
        "step7-finalize",
        "step7-export",
        "pptx-content-gate",
        "postflight",
        "narration-audio",
        "publication",
    ]
    status: Literal["passed", "passed-with-warnings", "failed", "pending", "stale"]
    subject_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    payload_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    actor_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    delegated: bool
    delegation_scope: list[str] = Field(max_length=32)
    policy_version: str = Field(min_length=1, max_length=80)
    expires_at: datetime
    created_at: datetime


class WorkflowArtifactRef(WorkflowContractModel):
    kind: str = Field(min_length=1, max_length=80)
    key: str = Field(min_length=1, max_length=2048)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    size_bytes: int = Field(ge=0)
    mime_type: str = Field(min_length=1, max_length=160)
    stage: str = Field(min_length=1, max_length=80)


class WorkflowUsage(WorkflowContractModel):
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    image_count: int = Field(ge=0)
    render_seconds: int = Field(ge=0)
    cost_microunits: int = Field(ge=0)


class WorkflowError(WorkflowContractModel):
    code: str = Field(min_length=1, max_length=80)
    message: str = Field(min_length=1, max_length=2000)
    owner: Literal["strategist", "executor", "runtime", "provider", "user"]
    recovery_stage: str | None = Field(default=None, max_length=80)
    retryable: bool


class WorkflowResultV2(WorkflowContractModel):
    schema_version: Literal[2] = 2
    workflow_run_id: str = Field(pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    request_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    route: Literal["generate_pptx"] = "generate_pptx"
    profile: Literal["default-agentic", "quick-engineering"]
    status: Literal[
        "awaiting_stage1_confirmation",
        "template_handoff_ready",
        "awaiting_stage2_confirmation",
        "final_confirmed",
        "awaiting_refine_spec_approval",
        "running",
        "needs_manual",
        "failed",
        "partially_succeeded",
        "succeeded",
        "cancelled",
    ]
    stage: str = Field(min_length=1, max_length=80)
    checkpoint_set_id: str | None = Field(default=None, pattern=r"^[0-9A-HJKMNP-TV-Z]{26}$")
    receipts: list[WorkflowReceipt]
    artifacts: list[WorkflowArtifactRef]
    errors: list[WorkflowError]
    usage: WorkflowUsage
    canonical_bundle_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
