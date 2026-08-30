import pytest
from instant_ppt_api.schemas import CreateGenerationJobRequest
from pydantic import ValidationError


def _request(image_policy: dict[str, object]) -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "data": {
            "continueLimitedDraft": True,
            "authorizeStrategistDesignLock": True,
            "imagePolicy": image_policy,
        },
    }


def test_generation_api_accepts_explicit_selective_ai_policy() -> None:
    parsed = CreateGenerationJobRequest.model_validate(
        _request(
            {
                "scope": "selective",
                "usage": ["ai"],
                "notes": {"01ARZ3NDEKTSV4RRFFQ69G5FAA": "non-evidentiary section art"},
                "aiPath": "auto",
                "aiPathChain": ["api", "manual"],
            }
        )
    )

    assert parsed.data.image_policy.scope == "selective"
    assert parsed.data.image_policy.ai_path_chain == ["api", "manual"]
    assert parsed.data.authorize_strategist_design_lock is True
    assert parsed.data.visual_review_level == "off"


@pytest.mark.parametrize("level", ["off", "standard"])
def test_generation_api_accepts_explicit_visual_review_level(level: str) -> None:
    payload = _request({"scope": "none", "usage": ["none"], "notes": {}})
    payload["data"]["visualReviewLevel"] = level  # type: ignore[index]

    parsed = CreateGenerationJobRequest.model_validate(payload)

    assert parsed.data.visual_review_level == level


def test_generation_api_rejects_removed_final_visual_review_level() -> None:
    payload = _request({"scope": "none", "usage": ["none"], "notes": {}})
    payload["data"]["visualReviewLevel"] = "final"  # type: ignore[index]

    with pytest.raises(ValidationError):
        CreateGenerationJobRequest.model_validate(payload)


def test_generation_api_requires_complete_visual_style_reference_pair() -> None:
    payload = _request({"scope": "none", "usage": ["none"], "notes": {}})
    payload["data"]["visualStylePlanningJobId"] = "01ARZ3NDEKTSV4RRFFQ69G5FAV"  # type: ignore[index]

    with pytest.raises(ValidationError):
        CreateGenerationJobRequest.model_validate(payload)

    payload["data"]["visualStyleOptionId"] = "editorial-green"  # type: ignore[index]
    parsed = CreateGenerationJobRequest.model_validate(payload)
    assert parsed.data.visual_style_option_id == "editorial-green"


@pytest.mark.parametrize(
    "policy",
    [
        {"scope": "none", "usage": ["ai"], "notes": {}},
        {
            "scope": "cover_only",
            "usage": ["ai"],
            "notes": {"not-cover": "invalid"},
            "aiPath": "api",
            "aiPathChain": ["api", "manual"],
        },
        {
            "scope": "cover_only",
            "usage": ["ai"],
            "notes": {"cover": "hero"},
            "aiPath": "api",
            "aiPathChain": ["api", "host-native", "manual"],
        },
    ],
)
def test_generation_api_rejects_implicit_or_switching_image_policy(
    policy: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        CreateGenerationJobRequest.model_validate(_request(policy))
