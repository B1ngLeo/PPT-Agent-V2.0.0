"""Stable RFC 7807 responses."""

from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse


def problem_response(
    *,
    status: int,
    code: str,
    title: str,
    detail: str,
    instance: str,
    retryable: bool = False,
    request_id: str = "g02-request",
    field_errors: list[dict[str, str]] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "schemaVersion": 1,
        "type": f"https://errors.instant-ppt.example/{code}",
        "title": title,
        "status": status,
        "detail": detail,
        "instance": instance,
        "code": code,
        "retryable": retryable,
        "requestId": request_id,
        "fieldErrors": field_errors or [],
    }
    return JSONResponse(body, status_code=status, media_type="application/problem+json")
