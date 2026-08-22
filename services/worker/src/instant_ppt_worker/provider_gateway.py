"""Private HTTP facade that keeps live Provider secrets outside the public API service."""

from __future__ import annotations

import hmac
import json
import logging
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from instant_ppt_domain.runtime_contract import RuntimeIdentity

from instant_ppt_worker.planning import KimiPlanningService
from instant_ppt_worker.providers import (
    ProviderConfigurationError,
    ProviderRequestError,
)

_MAX_REQUEST_BYTES = 256 * 1024
logger = logging.getLogger(__name__)


def _result(value: Any) -> dict[str, Any]:
    return {
        "data": value.data,
        "provider": value.provider,
        "model": value.model,
        "inputTokens": value.input_tokens,
        "outputTokens": value.output_tokens,
        "repairCount": value.repair_count,
    }


class ProviderGatewayHandler(BaseHTTPRequestHandler):
    server_version = "instant-ppt-provider-gateway/1"
    sys_version = ""

    def _write(self, status: int, body: dict[str, Any]) -> None:
        encoded = json.dumps(
            body, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def _authorized(self) -> bool:
        expected = os.getenv("PROVIDER_GATEWAY_TOKEN", "")
        supplied = self.headers.get("Authorization", "")
        return bool(expected) and hmac.compare_digest(supplied, f"Bearer {expected}")

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/healthz":
            self._write(
                HTTPStatus.OK,
                {"status": "ok", "runtime": RuntimeIdentity.from_env().as_dict()},
            )
            return
        self._write(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if not self._authorized():
            self._write(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            return
        try:
            length = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            length = 0
        if not 0 < length <= _MAX_REQUEST_BYTES:
            self._write(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "request_too_large"})
            return
        try:
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("request must be an object")
            service = KimiPlanningService.from_env()
            try:
                if self.path == "/internal/v1/planning/intent":
                    value = service.infer_intent(
                        topic=str(payload["topic"]),
                        source_refs=[str(item) for item in payload.get("sourceRefs") or []],
                        language=str(payload.get("language") or "zh-CN"),
                    )
                elif self.path == "/internal/v1/planning/outline":
                    value = service.generate_outline(
                        intent=dict(payload["intent"]),
                        existing=(dict(payload["existing"]) if payload.get("existing") else None),
                        instruction=str(payload.get("instruction") or ""),
                        action=str(payload.get("action") or "generate"),
                        target_slide_id=(
                            str(payload["targetSlideId"])
                            if payload.get("targetSlideId")
                            else None
                        ),
                    )
                else:
                    self._write(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                    return
            finally:
                service.close()
            self._write(HTTPStatus.OK, _result(value))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            self._write(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": "invalid_request"})
        except ProviderConfigurationError:
            logger.error(
                "provider_gateway_not_configured path=%s",
                self.path,
            )
            self._write(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "provider_not_configured"})
        except ProviderRequestError as error:
            logger.warning(
                "provider_gateway_request_failed path=%s provider=%s status=%s "
                "request_id=%s failure_kind=%s",
                self.path,
                error.provider,
                error.status_code,
                error.request_id,
                error.failure_kind,
            )
            self._write(HTTPStatus.BAD_GATEWAY, {"error": "provider_request_failed"})

    def log_message(self, format: str, *args: object) -> None:
        # Do not emit prompts, authorization headers, or Provider response bodies.
        return


def main() -> None:
    host = os.getenv("PROVIDER_GATEWAY_HOST", "0.0.0.0")
    port = int(os.getenv("PROVIDER_GATEWAY_PORT", "8090"))
    token = os.getenv("PROVIDER_GATEWAY_TOKEN", "")
    environment = os.getenv("APP_ENVIRONMENT", "local").strip().lower()
    if not token:
        raise RuntimeError("PROVIDER_GATEWAY_TOKEN is required")
    if environment != "local" and token == "local-development-provider-gateway-only":
        raise RuntimeError("the development Provider Gateway token is forbidden outside local")
    server = ThreadingHTTPServer((host, port), ProviderGatewayHandler)
    server.serve_forever(poll_interval=0.5)


if __name__ == "__main__":
    main()
