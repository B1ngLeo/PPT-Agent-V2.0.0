from instant_ppt_domain.generation import _authoring_policy, _provider_configuration


def test_generation_snapshot_freezes_text_provider_transport(monkeypatch) -> None:
    monkeypatch.setenv("TEXT_PROVIDER", "kimi")
    monkeypatch.setenv("PLANNING_BACKEND", "kimi")
    monkeypatch.setenv("KIMI_BASE_URL", "https://gateway.example/v1")
    monkeypatch.setenv("KIMI_MODEL", "kimi-k3")
    monkeypatch.setenv("KIMI_PROTOCOL", "anthropic")
    monkeypatch.setenv("KIMI_REASONING_EFFORT", "high")
    monkeypatch.setenv("KIMI_TIMEOUT_SECONDS", "321")
    monkeypatch.setenv("KIMI_TRANSPORT_MAX_RETRIES", "2")
    monkeypatch.setenv("KIMI_RETRY_BACKOFF_SECONDS", "3.5")

    planning = _provider_configuration()["planning"]

    assert planning == {
        "backend": "kimi",
        "provider": "kimi",
        "baseUrl": "https://gateway.example/v1",
        "model": "kimi-k3",
        "protocol": "anthropic",
        "reasoningEffort": "high",
        "timeoutSeconds": 321.0,
        "transportMaxRetries": 2,
        "retryBackoffSeconds": 3.5,
        "streaming": False,
        "inputCostMicrounitsPer1K": 0,
        "outputCostMicrounitsPer1K": 0,
    }


def test_generation_snapshot_freezes_qwen_transport(monkeypatch) -> None:
    monkeypatch.setenv("PLANNING_BACKEND", "qwen")
    monkeypatch.setenv("TEXT_PROVIDER", "qwen")
    monkeypatch.setenv("QWEN_BASE_URL", "https://cf.api.fan/v1")
    monkeypatch.setenv("QWEN_MODEL", "qwen3.7-plus")
    monkeypatch.setenv("QWEN_REASONING_EFFORT", "medium")
    monkeypatch.setenv("QWEN_ENABLE_THINKING", "true")
    monkeypatch.setenv("QWEN_PRESERVE_THINKING", "true")
    monkeypatch.setenv("QWEN_TIMEOUT_SECONDS", "600")
    monkeypatch.setenv("QWEN_TRANSPORT_MAX_RETRIES", "4")
    monkeypatch.setenv("QWEN_RETRY_BACKOFF_SECONDS", "2")
    monkeypatch.setenv("QWEN_STREAMING", "true")

    planning = _provider_configuration()["planning"]

    assert planning == {
        "backend": "qwen",
        "provider": "qwen",
        "baseUrl": "https://cf.api.fan/v1",
        "model": "qwen3.7-plus",
        "protocol": "openai",
        "reasoningEffort": "medium",
        "enableThinking": True,
        "preserveThinking": True,
        "timeoutSeconds": 600.0,
        "transportMaxRetries": 4,
        "retryBackoffSeconds": 2.0,
        "streaming": True,
        "inputCostMicrounitsPer1K": 0,
        "outputCostMicrounitsPer1K": 0,
    }


def test_generation_snapshot_defaults_to_qwen37_plus(monkeypatch) -> None:
    monkeypatch.setenv("PLANNING_BACKEND", "qwen")
    monkeypatch.setenv("TEXT_PROVIDER", "qwen")
    monkeypatch.delenv("QWEN_MODEL", raising=False)

    planning = _provider_configuration()["planning"]

    assert planning["provider"] == "qwen"
    assert planning["model"] == "qwen3.7-plus"


def test_agent_authoring_visual_review_is_required_by_default(monkeypatch) -> None:
    monkeypatch.delenv("PRESENTATION_VISUAL_REVIEW_REQUIRED", raising=False)
    monkeypatch.setenv("PRESENTATION_AUTHORING_MODE", "agent-authoring")

    policy = _authoring_policy()

    assert policy["mode"] == "agent-authoring"
    assert policy["visualReview"] == {
        "required": True,
        "policyVersion": "visual-review-adaptive@v2",
        "maxRounds": 5,
    }


def test_operator_can_disable_visual_review_without_disabling_agent_authoring(
    monkeypatch,
) -> None:
    monkeypatch.setenv("PRESENTATION_AUTHORING_MODE", "agent-authoring")
    monkeypatch.setenv("PRESENTATION_VISUAL_REVIEW_REQUIRED", "false")

    policy = _authoring_policy()

    assert policy["mode"] == "agent-authoring"
    assert policy["fallbackReason"] is None
    assert policy["visualReview"] == {
        "required": False,
        "policyVersion": "visual-review-operator-disabled@v2",
        "maxRounds": 0,
    }
