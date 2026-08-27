"""Runtime identity and versioned task names shared by API, outbox, and workers."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

RUNTIME_CONTRACT_VERSION = "instant-ppt-runtime@v2"
DEFAULT_WORKFLOW_VERSION = "instant-ppt-default@v2.0.0"
ENGINE_VERSION = "ppt-master@v4.7.0+e8323bfa"

PROCESS_GENERATION_TASK = "instant_ppt.v2.process_generation_job"
PROCESS_PLANNING_TASK = "instant_ppt.v2.process_planning_job"
PROCESS_EXPORT_TASK = "instant_ppt.v2.process_export"
PROCESS_SLIDE_REGENERATION_TASK = "instant_ppt.v2.process_slide_regeneration"

_REVISION = re.compile(r"^(?:[0-9a-f]{7,64}|dev-[a-z0-9][a-z0-9._-]{0,63})$")


class RuntimeContractMismatch(RuntimeError):
    """Raised before business work when a task targets another runtime contract."""


@dataclass(frozen=True, slots=True)
class RuntimeIdentity:
    build_revision: str
    runtime_contract_version: str = RUNTIME_CONTRACT_VERSION
    workflow_contract_version: str = DEFAULT_WORKFLOW_VERSION
    engine_version: str = ENGINE_VERSION

    @classmethod
    def from_env(cls) -> RuntimeIdentity:
        revision = os.getenv("APP_BUILD_REVISION", "dev-uncommitted").strip().lower()
        if not _REVISION.fullmatch(revision):
            raise ValueError(
                "APP_BUILD_REVISION must be a Git SHA or a dev-* local revision label"
            )
        configured_contract = os.getenv(
            "RUNTIME_CONTRACT_VERSION", RUNTIME_CONTRACT_VERSION
        ).strip()
        if configured_contract != RUNTIME_CONTRACT_VERSION:
            raise RuntimeContractMismatch(
                "configured runtime contract does not match the installed code"
            )
        return cls(build_revision=revision)

    @property
    def container_version(self) -> str:
        return f"instant-ppt-runtime@{self.build_revision}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "buildRevision": self.build_revision,
            "runtimeContractVersion": self.runtime_contract_version,
            "workflowContractVersion": self.workflow_contract_version,
            "engineVersion": self.engine_version,
            "containerVersion": self.container_version,
        }


def assert_runtime_contract(supplied: str) -> RuntimeIdentity:
    identity = RuntimeIdentity.from_env()
    if supplied != identity.runtime_contract_version:
        raise RuntimeContractMismatch(
            "task runtime contract does not match the executing worker"
        )
    return identity
