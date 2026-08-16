"""Stable adapter error codes and their process exit mapping."""

from dataclasses import dataclass


@dataclass(frozen=True)
class AdapterError(Exception):
    code: str
    message: str
    exit_code: int = 2

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


INVALID_REQUEST = "ENGINE_INVALID_REQUEST"
UNSAFE_SOURCE = "SOURCE_SECURITY_REJECTED"
SECURITY_DECISION_REQUIRED = "SOURCE_CLEAN_DECISION_REQUIRED"
SECURITY_DECISION_MISMATCH = "SOURCE_CLEAN_DECISION_MISMATCH"
SOURCE_PARSE_FAILED = "SOURCE_PARSE_FAILED"
RENDER_FAILED = "ENGINE_RENDER_FAILED"
QA_FAILED = "ENGINE_QA_FAILED"
PACKAGE_FAILED = "ENGINE_PACKAGE_INVALID"
