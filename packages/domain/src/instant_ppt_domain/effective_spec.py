"""Immutable Effective Design Spec compilation for ISSUE-002 revision lifecycles."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from instant_ppt_domain.ids import new_ulid
from instant_ppt_domain.models import (
    DesignSpecEditPatch,
    EffectiveDesignSpecRevision,
)
from instant_ppt_domain.service import canonical_sha256


class EffectiveSpecConflict(ValueError):
    """The base hash or an object precondition no longer matches."""


class EffectiveSpecValidationError(ValueError):
    """An edit cannot be represented without violating the frozen roster contract."""


@dataclass(frozen=True, slots=True)
class CompiledPatch:
    sequence: int
    slide_id: str
    object_key: str
    old_value_sha256: str
    new_value: Any
    new_value_sha256: str
    touches_lock_owned_field: bool
    patch_sha256: str


@dataclass(frozen=True, slots=True)
class EffectiveSpecCompilation:
    payload: dict[str, Any]
    effective_spec_sha256: str
    spec_lock_sha256: str
    patches: tuple[CompiledPatch, ...]
    lock_changed: bool


def _valid_sha(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _validate_roster(roster: list[dict[str, Any]]) -> None:
    if not roster:
        raise EffectiveSpecValidationError("effective roster cannot be empty")
    expected = [f"P{index:02d}" for index in range(1, len(roster) + 1)]
    actual = [str(slide.get("pnn") or "") for slide in roster]
    if actual != expected:
        raise EffectiveSpecValidationError("effective roster must have contiguous exact PNN keys")
    slide_ids = [str(slide.get("slideId") or "") for slide in roster]
    outline_ids = [str(slide.get("outlineSlideId") or "") for slide in roster]
    if any(not value for value in [*slide_ids, *outline_ids]):
        raise EffectiveSpecValidationError("effective roster identities are required")
    if len(set(slide_ids)) != len(slide_ids) or len(set(outline_ids)) != len(outline_ids):
        raise EffectiveSpecValidationError("effective roster identities must be unique")
    for slide in roster:
        if not str(slide.get("role") or ""):
            raise EffectiveSpecValidationError("every effective slide requires a page role")
        if not str(slide.get("title") or "").strip():
            raise EffectiveSpecValidationError("every effective slide requires a title")
        body = slide.get("body")
        if not isinstance(body, list) or not all(isinstance(value, str) for value in body):
            raise EffectiveSpecValidationError("every effective slide body must be a string array")


def _patch(
    *,
    sequence: int,
    base_effective_spec_sha256: str,
    slide_id: str,
    object_key: str,
    old_value: Any,
    new_value: Any,
    actor_id: str,
    touches_lock_owned_field: bool,
) -> CompiledPatch:
    old_hash = canonical_sha256(old_value)
    new_hash = canonical_sha256(new_value)
    payload = {
        "schemaVersion": 1,
        "sequence": sequence,
        "baseEffectiveSpecSha256": base_effective_spec_sha256,
        "slideId": slide_id,
        "objectKey": object_key,
        "oldValueSha256": old_hash,
        "newValueSha256": new_hash,
        "actorId": actor_id,
        "touchesLockOwnedField": touches_lock_owned_field,
    }
    return CompiledPatch(
        sequence=sequence,
        slide_id=slide_id,
        object_key=object_key,
        old_value_sha256=old_hash,
        new_value=copy.deepcopy(new_value),
        new_value_sha256=new_hash,
        touches_lock_owned_field=touches_lock_owned_field,
        patch_sha256=canonical_sha256(payload),
    )


def initial_effective_payload(
    *,
    effective_spec_revision_id: str,
    workflow_run_id: str,
    presentation_revision_id: str,
    design_spec_sha256: str,
    spec_lock_sha256: str,
    source_manifest_sha256: str,
    roster: list[dict[str, Any]],
    canonical_artifacts: dict[str, str],
) -> dict[str, Any]:
    if not all(
        _valid_sha(value)
        for value in (design_spec_sha256, spec_lock_sha256, source_manifest_sha256)
    ):
        raise EffectiveSpecValidationError(
            "initial effective spec hashes must be lowercase SHA-256"
        )
    values = copy.deepcopy(roster)
    _validate_roster(values)
    return {
        "schemaVersion": 1,
        "effectiveSpecRevisionId": effective_spec_revision_id,
        "workflowRunId": workflow_run_id,
        "presentationRevisionId": presentation_revision_id,
        "basedOnEffectiveSpecSha256": None,
        "baseDesignSpecSha256": design_spec_sha256,
        "specLockSha256": spec_lock_sha256,
        "specLockDisposition": "gate2-passed",
        "sourceManifestSha256": source_manifest_sha256,
        "patchSha256s": [],
        "roster": values,
        "canonicalArtifacts": dict(canonical_artifacts),
        "wholeDeckFinalGate": "passed",
        "publicationReady": True,
    }


def compile_operations(
    *,
    effective_spec_revision_id: str,
    base_payload: dict[str, Any],
    base_effective_spec_sha256: str,
    operations: list[dict[str, Any]],
    actor_id: str,
) -> EffectiveSpecCompilation:
    if canonical_sha256(base_payload) != base_effective_spec_sha256:
        raise EffectiveSpecConflict("base Effective Design Spec hash does not match its payload")
    if not operations:
        raise EffectiveSpecValidationError("at least one effective spec operation is required")
    roster = copy.deepcopy(base_payload.get("roster"))
    if not isinstance(roster, list):
        raise EffectiveSpecValidationError("base Effective Design Spec has no roster")
    _validate_roster(roster)
    patches: list[CompiledPatch] = []
    lock_changed = False

    def append_patch(
        slide: dict[str, Any],
        field: str,
        value: Any,
        *,
        touches_lock: bool = False,
    ) -> None:
        patch = _patch(
            sequence=len(patches) + 1,
            base_effective_spec_sha256=base_effective_spec_sha256,
            slide_id=str(slide["slideId"]),
            object_key=f"§IX/{slide['pnn']}/{field}",
            old_value=slide.get(field),
            new_value=value,
            actor_id=actor_id,
            touches_lock_owned_field=touches_lock,
        )
        expected = next(
            (
                operation.get("oldValueSha256")
                for operation in operations
                if operation.get("slideId") == slide["slideId"] and operation.get("field") == field
            ),
            None,
        )
        if expected is not None and expected != patch.old_value_sha256:
            raise EffectiveSpecConflict(f"stale precondition for {patch.object_key}")
        patches.append(patch)
        slide[field] = copy.deepcopy(value)
        slide["artifactId"] = None
        slide["artifactStatus"] = "stale"

    for operation in operations:
        kind = str(operation.get("type") or "")
        slide_id = str(operation.get("slideId") or "")
        index = next(
            (position for position, slide in enumerate(roster) if slide["slideId"] == slide_id),
            -1,
        )
        if kind in {"update_text", "regenerate"}:
            if index < 0:
                raise EffectiveSpecValidationError(f"{kind} slideId does not exist")
            slide = roster[index]
            if kind == "regenerate" and (index == 0 or slide.get("role") == "cover"):
                raise EffectiveSpecValidationError("single-slide regeneration cannot target cover")
            title_key = "resultTitle" if kind == "regenerate" else "title"
            body_key = "resultBody" if kind == "regenerate" else "body"
            if title_key not in operation and body_key not in operation:
                raise EffectiveSpecValidationError(f"{kind} requires a title or body result")
            if title_key in operation:
                title = str(operation[title_key]).strip()
                if not 1 <= len(title) <= 300:
                    raise EffectiveSpecValidationError("slide title must contain 1 to 300 chars")
                append_patch(slide, "title", title)
            if body_key in operation:
                body = operation[body_key]
                if not isinstance(body, list) or not all(isinstance(value, str) for value in body):
                    raise EffectiveSpecValidationError("slide body must be a string array")
                append_patch(slide, "body", [value[:2000] for value in body])
            if kind == "regenerate":
                instruction_hash = operation.get("instructionSha256")
                if not _valid_sha(instruction_hash):
                    raise EffectiveSpecValidationError(
                        "regeneration requires only an instruction SHA-256 audit value"
                    )
                slide["regenerationInstructionSha256"] = instruction_hash
        elif kind in {"move", "delete"}:
            if index < 0:
                raise EffectiveSpecValidationError(f"{kind} slideId does not exist")
            approval_hash = operation.get("rosterApprovalReceiptSha256")
            if not _valid_sha(approval_hash):
                raise EffectiveSpecValidationError(
                    "roster changes require an explicit approval or bounded delegation receipt"
                )
            old_roster = [
                {key: slide[key] for key in ("slideId", "outlineSlideId", "pnn", "role")}
                for slide in roster
            ]
            if kind == "move":
                position = operation.get("position")
                if not isinstance(position, int) or not 1 <= position <= len(roster):
                    raise EffectiveSpecValidationError("move position is outside the roster")
                roster.insert(position - 1, roster.pop(index))
            else:
                if len(roster) == 1:
                    raise EffectiveSpecValidationError("effective roster cannot become empty")
                roster.pop(index)
            for position, slide in enumerate(roster, start=1):
                slide["pnn"] = f"P{position:02d}"
                slide["artifactId"] = None
                slide["artifactStatus"] = "stale"
            patch = _patch(
                sequence=len(patches) + 1,
                base_effective_spec_sha256=base_effective_spec_sha256,
                slide_id=slide_id,
                object_key="§IX/roster",
                old_value=old_roster,
                new_value=[
                    {key: slide[key] for key in ("slideId", "outlineSlideId", "pnn", "role")}
                    for slide in roster
                ],
                actor_id=actor_id,
                touches_lock_owned_field=True,
            )
            patches.append(patch)
            lock_changed = True
        elif kind == "accept_missing":
            continue
        else:
            raise EffectiveSpecValidationError(f"unsupported effective spec operation: {kind}")

    if not patches:
        raise EffectiveSpecValidationError("operation set produced no Effective Design Spec patch")
    _validate_roster(roster)
    base_lock_hash = str(base_payload.get("specLockSha256") or "")
    if not _valid_sha(base_lock_hash):
        raise EffectiveSpecValidationError("base spec_lock hash is invalid")
    spec_lock_sha256 = (
        canonical_sha256(
            {
                "schemaVersion": 1,
                "derivedFromSpecLockSha256": base_lock_hash,
                "rosterRouting": [
                    {key: slide[key] for key in ("slideId", "outlineSlideId", "pnn", "role")}
                    for slide in roster
                ],
            }
        )
        if lock_changed
        else base_lock_hash
    )
    spec_lock_gate2_receipt_sha256 = (
        canonical_sha256(
            {
                "schemaVersion": 1,
                "kind": "spec-lock-gate2",
                "subjectSha256": spec_lock_sha256,
                "readBackRoster": [
                    {key: slide[key] for key in ("slideId", "outlineSlideId", "pnn", "role")}
                    for slide in roster
                ],
            }
        )
        if lock_changed
        else None
    )
    payload = {
        **copy.deepcopy(base_payload),
        "effectiveSpecRevisionId": effective_spec_revision_id,
        "presentationRevisionId": None,
        "basedOnEffectiveSpecSha256": base_effective_spec_sha256,
        "specLockSha256": spec_lock_sha256,
        "specLockDisposition": (
            "derived-gate2-passed" if lock_changed else "reused-with-applicability-receipt"
        ),
        "specLockGate2ReceiptSha256": spec_lock_gate2_receipt_sha256,
        "patchSha256s": [patch.patch_sha256 for patch in patches],
        "roster": roster,
        "canonicalArtifacts": {},
        "wholeDeckFinalGate": "stale",
        "publicationReady": False,
    }
    return EffectiveSpecCompilation(
        payload=payload,
        effective_spec_sha256=canonical_sha256(payload),
        spec_lock_sha256=spec_lock_sha256,
        patches=tuple(patches),
        lock_changed=lock_changed,
    )


def effective_for_presentation_revision(
    session: Session, presentation_revision_id: str
) -> EffectiveDesignSpecRevision | None:
    return session.scalar(
        select(EffectiveDesignSpecRevision).where(
            EffectiveDesignSpecRevision.presentation_revision_id == presentation_revision_id
        )
    )


def persist_initial_effective_revision(
    session: Session,
    *,
    organization_id: str,
    workflow_run_id: str,
    presentation_revision_id: str,
    design_spec_sha256: str,
    spec_lock_sha256: str,
    source_manifest_sha256: str,
    roster: list[dict[str, Any]],
    canonical_artifacts: dict[str, str],
    effective_spec_revision_id: str | None = None,
) -> EffectiveDesignSpecRevision:
    effective_id = effective_spec_revision_id or new_ulid()
    payload = initial_effective_payload(
        effective_spec_revision_id=effective_id,
        workflow_run_id=workflow_run_id,
        presentation_revision_id=presentation_revision_id,
        design_spec_sha256=design_spec_sha256,
        spec_lock_sha256=spec_lock_sha256,
        source_manifest_sha256=source_manifest_sha256,
        roster=roster,
        canonical_artifacts=canonical_artifacts,
    )
    row = EffectiveDesignSpecRevision(
        id=effective_id,
        organization_id=organization_id,
        workflow_run_id=workflow_run_id,
        presentation_revision_id=presentation_revision_id,
        based_on_id=None,
        revision_number=1,
        base_design_spec_sha256=design_spec_sha256,
        effective_spec_sha256=canonical_sha256(payload),
        spec_lock_sha256=spec_lock_sha256,
        roster=payload["roster"],
        payload=payload,
    )
    session.add(row)
    session.flush()
    return row


def persist_compilation(
    session: Session,
    *,
    base: EffectiveDesignSpecRevision,
    presentation_revision_id: str,
    operations: list[dict[str, Any]],
    actor_id: str,
    effective_spec_revision_id: str | None = None,
    whole_deck_final_qa_sha256: str | None = None,
) -> EffectiveDesignSpecRevision:
    effective_id = effective_spec_revision_id or new_ulid()
    compilation = compile_operations(
        effective_spec_revision_id=effective_id,
        base_payload=base.payload,
        base_effective_spec_sha256=base.effective_spec_sha256,
        operations=operations,
        actor_id=actor_id,
    )
    payload = {**compilation.payload, "presentationRevisionId": presentation_revision_id}
    if whole_deck_final_qa_sha256 is not None:
        if not _valid_sha(whole_deck_final_qa_sha256):
            raise EffectiveSpecValidationError("whole-deck final QA hash is invalid")
        payload.update(
            {
                "wholeDeckFinalGate": "passed",
                "wholeDeckFinalQaSha256": whole_deck_final_qa_sha256,
                "publicationReady": True,
            }
        )
    effective_hash = canonical_sha256(payload)
    row = EffectiveDesignSpecRevision(
        id=effective_id,
        organization_id=base.organization_id,
        workflow_run_id=base.workflow_run_id,
        presentation_revision_id=presentation_revision_id,
        based_on_id=base.id,
        revision_number=base.revision_number + 1,
        base_design_spec_sha256=base.base_design_spec_sha256,
        effective_spec_sha256=effective_hash,
        spec_lock_sha256=compilation.spec_lock_sha256,
        roster=payload["roster"],
        payload=payload,
    )
    session.add(row)
    session.flush()
    for patch in compilation.patches:
        session.add(
            DesignSpecEditPatch(
                id=new_ulid(),
                organization_id=base.organization_id,
                workflow_run_id=base.workflow_run_id,
                base_effective_spec_revision_id=base.id,
                effective_spec_revision_id=row.id,
                sequence=patch.sequence,
                slide_id=patch.slide_id,
                object_key=patch.object_key,
                old_value_sha256=patch.old_value_sha256,
                new_value=patch.new_value,
                new_value_sha256=patch.new_value_sha256,
                touches_lock_owned_field=patch.touches_lock_owned_field,
                actor_id=actor_id,
                patch_sha256=patch.patch_sha256,
            )
        )
    return row
