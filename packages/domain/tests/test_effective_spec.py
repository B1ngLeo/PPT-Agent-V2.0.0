import hashlib

import pytest
from instant_ppt_domain.effective_spec import (
    EffectiveSpecConflict,
    EffectiveSpecValidationError,
    compile_operations,
    initial_effective_payload,
)
from instant_ppt_domain.service import canonical_sha256

HASH = "a" * 64
RUN = "01ARZ3NDEKTSV4RRFFQ69G5FAA"
REVISION = "01ARZ3NDEKTSV4RRFFQ69G5FAB"
EFFECTIVE = "01ARZ3NDEKTSV4RRFFQ69G5FAC"
NEXT_EFFECTIVE = "01ARZ3NDEKTSV4RRFFQ69G5FAD"
ACTOR = "01ARZ3NDEKTSV4RRFFQ69G5FAE"


def _base() -> dict[str, object]:
    return initial_effective_payload(
        effective_spec_revision_id=EFFECTIVE,
        workflow_run_id=RUN,
        presentation_revision_id=REVISION,
        design_spec_sha256=HASH,
        spec_lock_sha256="b" * 64,
        source_manifest_sha256="c" * 64,
        roster=[
            {
                "slideId": "01ARZ3NDEKTSV4RRFFQ69G5FAF",
                "outlineSlideId": "01ARZ3NDEKTSV4RRFFQ69G5FAG",
                "pnn": "P01",
                "role": "cover",
                "title": "原封面",
                "body": ["原摘要"],
                "artifactId": "01ARZ3NDEKTSV4RRFFQ69G5FAH",
            },
            {
                "slideId": "01ARZ3NDEKTSV4RRFFQ69G5FAJ",
                "outlineSlideId": "01ARZ3NDEKTSV4RRFFQ69G5FAK",
                "pnn": "P02",
                "role": "data",
                "title": "原数据结论",
                "body": ["原数据正文"],
                "artifactId": "01ARZ3NDEKTSV4RRFFQ69G5FAM",
            },
        ],
        canonical_artifacts={
            "pptxArtifactId": "01ARZ3NDEKTSV4RRFFQ69G5FAN",
            "bundleArtifactId": "01ARZ3NDEKTSV4RRFFQ69G5FAP",
        },
    )


def test_text_edit_compiles_hash_bound_patch_and_stales_old_artifact() -> None:
    base = _base()
    base_hash = canonical_sha256(base)

    result = compile_operations(
        effective_spec_revision_id=NEXT_EFFECTIVE,
        base_payload=base,
        base_effective_spec_sha256=base_hash,
        operations=[
            {
                "type": "update_text",
                "slideId": "01ARZ3NDEKTSV4RRFFQ69G5FAJ",
                "title": "编辑后的结论",
                "body": ["编辑后的正文"],
            }
        ],
        actor_id=ACTOR,
    )

    edited = result.payload["roster"][1]
    assert edited["title"] == "编辑后的结论"
    assert edited["body"] == ["编辑后的正文"]
    assert edited["artifactId"] is None
    assert edited["artifactStatus"] == "stale"
    assert [patch.object_key for patch in result.patches] == ["§IX/P02/title", "§IX/P02/body"]
    assert result.patches[0].old_value_sha256 == canonical_sha256("原数据结论")
    assert result.spec_lock_sha256 == base["specLockSha256"]
    assert result.payload["wholeDeckFinalGate"] == "stale"
    assert result.payload["canonicalArtifacts"] == {}


def test_stale_base_and_cover_regeneration_are_rejected() -> None:
    base = _base()
    with pytest.raises(EffectiveSpecConflict):
        compile_operations(
            effective_spec_revision_id=NEXT_EFFECTIVE,
            base_payload=base,
            base_effective_spec_sha256="f" * 64,
            operations=[
                {
                    "type": "update_text",
                    "slideId": "01ARZ3NDEKTSV4RRFFQ69G5FAF",
                    "title": "冲突",
                }
            ],
            actor_id=ACTOR,
        )

    with pytest.raises(EffectiveSpecValidationError, match="cannot target cover"):
        compile_operations(
            effective_spec_revision_id=NEXT_EFFECTIVE,
            base_payload=base,
            base_effective_spec_sha256=canonical_sha256(base),
            operations=[
                {
                    "type": "regenerate",
                    "slideId": "01ARZ3NDEKTSV4RRFFQ69G5FAF",
                    "resultTitle": "封面",
                    "instructionSha256": hashlib.sha256(b"private").hexdigest(),
                }
            ],
            actor_id=ACTOR,
        )


def test_regeneration_keeps_role_and_never_persists_instruction_text() -> None:
    base = _base()
    instruction = "请把数据结论改成工程 prompt 不可见"
    result = compile_operations(
        effective_spec_revision_id=NEXT_EFFECTIVE,
        base_payload=base,
        base_effective_spec_sha256=canonical_sha256(base),
        operations=[
            {
                "type": "regenerate",
                "slideId": "01ARZ3NDEKTSV4RRFFQ69G5FAJ",
                "resultTitle": "重新生成的数据结论",
                "resultBody": ["重新生成的数据正文"],
                "instructionSha256": hashlib.sha256(instruction.encode()).hexdigest(),
            }
        ],
        actor_id=ACTOR,
    )

    assert result.payload["roster"][1]["role"] == "data"
    assert instruction not in str(result.payload)
    assert result.payload["roster"][1]["regenerationInstructionSha256"]


def test_roster_change_requires_receipt_and_derives_new_lock() -> None:
    base = _base()
    operation = {
        "type": "move",
        "slideId": "01ARZ3NDEKTSV4RRFFQ69G5FAJ",
        "position": 1,
    }
    with pytest.raises(EffectiveSpecValidationError, match="approval"):
        compile_operations(
            effective_spec_revision_id=NEXT_EFFECTIVE,
            base_payload=base,
            base_effective_spec_sha256=canonical_sha256(base),
            operations=[operation],
            actor_id=ACTOR,
        )

    operation["rosterApprovalReceiptSha256"] = "d" * 64
    result = compile_operations(
        effective_spec_revision_id=NEXT_EFFECTIVE,
        base_payload=base,
        base_effective_spec_sha256=canonical_sha256(base),
        operations=[operation],
        actor_id=ACTOR,
    )
    assert [slide["pnn"] for slide in result.payload["roster"]] == ["P01", "P02"]
    assert result.payload["roster"][0]["slideId"] == operation["slideId"]
    assert result.lock_changed is True
    assert result.spec_lock_sha256 != base["specLockSha256"]
    assert result.payload["specLockDisposition"] == "derived-gate2-passed"
    assert len(result.payload["specLockGate2ReceiptSha256"]) == 64
