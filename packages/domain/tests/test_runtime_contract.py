from __future__ import annotations

import pytest
from instant_ppt_domain.runtime_contract import (
    PROCESS_EXPORT_TASK,
    PROCESS_GENERATION_TASK,
    PROCESS_PLANNING_TASK,
    RUNTIME_CONTRACT_VERSION,
    RuntimeContractMismatch,
    RuntimeIdentity,
    assert_runtime_contract,
)


def test_runtime_identity_binds_build_contract_workflow_and_engine(monkeypatch) -> None:
    monkeypatch.setenv("APP_BUILD_REVISION", "0123456789abcdef")
    identity = RuntimeIdentity.from_env()

    assert identity.container_version == "instant-ppt-runtime@0123456789abcdef"
    assert identity.as_dict() == {
        "buildRevision": "0123456789abcdef",
        "runtimeContractVersion": "instant-ppt-runtime@v2",
        "workflowContractVersion": "instant-ppt-default@v2.0.0",
        "engineVersion": "ppt-master@v4.7.0+e8323bfa",
        "containerVersion": "instant-ppt-runtime@0123456789abcdef",
    }


def test_runtime_contract_and_task_names_fail_closed(monkeypatch) -> None:
    monkeypatch.setenv("APP_BUILD_REVISION", "dev-test")
    assert PROCESS_GENERATION_TASK == "instant_ppt.v2.process_generation_job"
    assert PROCESS_PLANNING_TASK == "instant_ppt.v2.process_planning_job"
    assert PROCESS_EXPORT_TASK == "instant_ppt.v2.process_export"
    assert assert_runtime_contract(RUNTIME_CONTRACT_VERSION).build_revision == "dev-test"

    with pytest.raises(RuntimeContractMismatch):
        assert_runtime_contract("instant-ppt-runtime@v1")


def test_installed_code_rejects_environment_contract_override(monkeypatch) -> None:
    monkeypatch.setenv("APP_BUILD_REVISION", "dev-test")
    monkeypatch.setenv("RUNTIME_CONTRACT_VERSION", "instant-ppt-runtime@v1")

    with pytest.raises(RuntimeContractMismatch):
        RuntimeIdentity.from_env()
