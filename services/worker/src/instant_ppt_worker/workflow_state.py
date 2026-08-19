"""Default workflow gate order and stale-receipt rules."""

from __future__ import annotations

from collections.abc import Mapping

WORKFLOW_STAGES = (
    "attribution_guard",
    "source_import",
    "template_candidates",
    "stage1",
    "template_handoff",
    "stage2",
    "design_spec_gate1",
    "refine_spec",
    "spec_lock_gate2",
    "design_parameters",
    "live_preview",
    "executor_p01",
    "first_page_gate",
    "executor_remaining",
    "final_svg_gate",
    "chart_gate",
    "final_svg_content_gate",
    "notes",
    "animations",
    "visual_review",
    "step7_finalize",
    "step7_export",
    "postflight",
    "pptx_content_gate",
    "narration",
    "publish",
)

WORKFLOW_TRANSITIONS: dict[str, frozenset[str]] = {
    "created": frozenset({"running", "cancelled"}),
    "running": frozenset(
        {
            "awaiting_stage1_confirmation",
            "template_handoff_ready",
            "awaiting_stage2_confirmation",
            "final_confirmed",
            "awaiting_refine_spec_approval",
            "needs_manual",
            "failed",
            "partially_succeeded",
            "succeeded",
            "cancel_requested",
        }
    ),
    "awaiting_stage1_confirmation": frozenset({"running", "cancel_requested", "failed"}),
    "template_handoff_ready": frozenset({"running", "cancel_requested", "failed"}),
    "awaiting_stage2_confirmation": frozenset({"running", "cancel_requested", "failed"}),
    "final_confirmed": frozenset(
        {"running", "awaiting_refine_spec_approval", "cancel_requested", "failed"}
    ),
    "awaiting_refine_spec_approval": frozenset(
        {"running", "cancel_requested", "failed"}
    ),
    "cancel_requested": frozenset({"cancelled"}),
    "needs_manual": frozenset({"running", "cancel_requested", "failed"}),
    "partially_succeeded": frozenset(),
    "succeeded": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
}


class WorkflowTransitionError(ValueError):
    pass


def validate_workflow_transition(current: str, target: str) -> None:
    if current == target:
        return
    if current not in WORKFLOW_TRANSITIONS or target not in WORKFLOW_TRANSITIONS[current]:
        raise WorkflowTransitionError(f"illegal workflow transition: {current} -> {target}")


def validate_receipt(
    receipts: Mapping[str, Mapping[str, str]],
    kind: str,
    *,
    subject_sha256: str | None = None,
    allow_reported_failure: bool = False,
) -> None:
    receipt = receipts.get(kind)
    if receipt is None:
        raise WorkflowTransitionError(f"missing required receipt: {kind}")
    status = receipt.get("status")
    accepted = {"passed", "passed-with-warnings"}
    if allow_reported_failure:
        accepted.add("failed")
    if status not in accepted:
        raise WorkflowTransitionError(f"receipt is not closed: {kind}={status}")
    if subject_sha256 is not None and receipt.get("subjectSha256") != subject_sha256:
        raise WorkflowTransitionError(f"stale receipt: {kind}")


def validate_stage_entry(
    next_stage: str,
    receipts: Mapping[str, Mapping[str, str]],
    *,
    request_sha256: str,
    design_spec_sha256: str | None = None,
    spec_lock_sha256: str | None = None,
    final_svg_sha256: str | None = None,
    pptx_sha256: str | None = None,
    refine_spec: bool = False,
    has_data_charts: bool = False,
    speaker_notes_enabled: bool = False,
    custom_animations_enabled: bool = False,
    narration_enabled: bool = False,
) -> None:
    """Reject cross-gate bundling and stale downstream entry."""

    if next_stage not in WORKFLOW_STAGES:
        raise WorkflowTransitionError(f"unknown workflow stage: {next_stage}")
    if WORKFLOW_STAGES.index(next_stage) > WORKFLOW_STAGES.index("source_import"):
        validate_receipt(receipts, "attribution", subject_sha256=request_sha256)
    if WORKFLOW_STAGES.index(next_stage) >= WORKFLOW_STAGES.index("template_handoff"):
        validate_receipt(receipts, "stage1-confirmation", subject_sha256=request_sha256)
    if WORKFLOW_STAGES.index(next_stage) >= WORKFLOW_STAGES.index("stage2"):
        validate_receipt(receipts, "template-handoff", subject_sha256=request_sha256)
    if WORKFLOW_STAGES.index(next_stage) >= WORKFLOW_STAGES.index("design_spec_gate1"):
        validate_receipt(receipts, "stage2-confirmation", subject_sha256=request_sha256)
    if WORKFLOW_STAGES.index(next_stage) > WORKFLOW_STAGES.index("design_spec_gate1"):
        if design_spec_sha256 is None:
            raise WorkflowTransitionError("design spec is required")
        validate_receipt(
            receipts,
            "design-spec-gate1",
            subject_sha256=design_spec_sha256,
        )
    if refine_spec and WORKFLOW_STAGES.index(next_stage) >= WORKFLOW_STAGES.index(
        "spec_lock_gate2"
    ):
        validate_receipt(
            receipts,
            "refine-spec-approval",
            subject_sha256=design_spec_sha256,
        )
    if WORKFLOW_STAGES.index(next_stage) > WORKFLOW_STAGES.index("spec_lock_gate2"):
        if spec_lock_sha256 is None:
            raise WorkflowTransitionError("spec lock is required")
        validate_receipt(receipts, "spec-lock-gate2", subject_sha256=spec_lock_sha256)
    if WORKFLOW_STAGES.index(next_stage) >= WORKFLOW_STAGES.index("executor_p01"):
        validate_receipt(receipts, "design-parameter-confirmation", subject_sha256=spec_lock_sha256)
        validate_receipt(
            receipts,
            "live-preview",
            subject_sha256=spec_lock_sha256,
            allow_reported_failure=True,
        )
    if WORKFLOW_STAGES.index(next_stage) >= WORKFLOW_STAGES.index("executor_remaining"):
        validate_receipt(receipts, "first-page-gate")
    if WORKFLOW_STAGES.index(next_stage) > WORKFLOW_STAGES.index("final_svg_gate"):
        if final_svg_sha256 is None:
            raise WorkflowTransitionError("final SVG roster hash is required")
        validate_receipt(receipts, "final-svg-gate", subject_sha256=final_svg_sha256)
    if has_data_charts and WORKFLOW_STAGES.index(next_stage) >= WORKFLOW_STAGES.index(
        "step7_finalize"
    ):
        validate_receipt(receipts, "chart-gate", subject_sha256=final_svg_sha256)
    if WORKFLOW_STAGES.index(next_stage) >= WORKFLOW_STAGES.index("step7_finalize"):
        validate_receipt(receipts, "final-svg-content-gate", subject_sha256=final_svg_sha256)
    if WORKFLOW_STAGES.index(next_stage) > WORKFLOW_STAGES.index("step7_finalize"):
        validate_receipt(receipts, "step7-finalize", subject_sha256=final_svg_sha256)
    if WORKFLOW_STAGES.index(next_stage) > WORKFLOW_STAGES.index("step7_export"):
        if pptx_sha256 is None:
            raise WorkflowTransitionError("PPTX hash is required")
        validate_receipt(receipts, "step7-export", subject_sha256=pptx_sha256)
    if next_stage == "publish":
        if speaker_notes_enabled:
            validate_receipt(receipts, "speaker-notes", subject_sha256=final_svg_sha256)
        if custom_animations_enabled:
            validate_receipt(receipts, "custom-animations", subject_sha256=final_svg_sha256)
        if narration_enabled:
            validate_receipt(receipts, "narration-audio", subject_sha256=pptx_sha256)
        validate_receipt(receipts, "postflight", subject_sha256=pptx_sha256)
        validate_receipt(receipts, "pptx-content-gate", subject_sha256=pptx_sha256)
