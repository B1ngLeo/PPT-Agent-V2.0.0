from instant_ppt_domain.provider_policy import (
    DEFAULT_QWEN_BASE_URL,
    is_official_qwen_base_url,
    resolve_qwen_base_url,
)


def test_qwen_provider_policy_accepts_official_compatible_endpoints() -> None:
    assert is_official_qwen_base_url(DEFAULT_QWEN_BASE_URL)
    assert is_official_qwen_base_url(
        "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
    )
    assert is_official_qwen_base_url(
        "https://workspace.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1"
    )


def test_qwen_provider_policy_rejects_proxy_and_malformed_endpoints() -> None:
    assert not is_official_qwen_base_url("https://cf.api.fan/v1")
    assert not is_official_qwen_base_url("http://dashscope.aliyuncs.com/compatible-mode/v1")
    assert not is_official_qwen_base_url("https://dashscope.aliyuncs.com/api/v1")
    assert not is_official_qwen_base_url(
        "https://dashscope.aliyuncs.com/compatible-mode/v1?proxy=1"
    )


def test_qwen_provider_policy_falls_back_to_official_default() -> None:
    assert resolve_qwen_base_url("https://cf.api.fan/v1") == DEFAULT_QWEN_BASE_URL
    assert resolve_qwen_base_url("") == DEFAULT_QWEN_BASE_URL
