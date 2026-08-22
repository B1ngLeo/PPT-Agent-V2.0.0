"""Provider-neutral planning gateways used by the G05 product flow."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any
from urllib import error, request


@dataclass(frozen=True, slots=True)
class PlanningResult:
    data: dict[str, Any]
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    repair_count: int = 0


class PlanningSchemaError(RuntimeError):
    pass


class PlanningUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PlanningGatewaySettings:
    backend: str = "fake"
    gateway_url: str = "http://provider-gateway:8090/internal/v1"
    gateway_token: str = field(default="", repr=False)
    timeout_seconds: float = 300.0

    @classmethod
    def from_env(cls) -> PlanningGatewaySettings:
        return cls(
            backend=os.getenv("PLANNING_BACKEND", "fake").strip().lower(),
            gateway_url=os.getenv(
                "PROVIDER_GATEWAY_URL", "http://provider-gateway:8090/internal/v1"
            ).strip(),
            gateway_token=os.getenv("PROVIDER_GATEWAY_TOKEN", "").strip(),
            timeout_seconds=float(os.getenv("PROVIDER_GATEWAY_TIMEOUT_SECONDS", "300")),
        )


class DeterministicPlanningGateway:
    """Offline provider with stable content for contracts and browser E2E."""

    provider = "fake"
    model = "deterministic-fake-v1"

    @staticmethod
    def _tokens(value: Any) -> int:
        return max(1, len(str(value)) // 2)

    def infer_intent(
        self, *, topic: str, source_refs: list[str], language: str = "zh-CN"
    ) -> PlanningResult:
        title = (topic.strip().splitlines()[0] if topic.strip() else "文档演示")[:200]
        data = {
            "title": title,
            "audience": "管理层" if language == "zh-CN" else "Leadership team",
            "goal": "策略决策" if language == "zh-CN" else "Strategic decision",
            "targetSlideCount": 8,
            "language": language,
            "contentDepth": "conclusion_first",
            "visualPreference": "data_first",
            "notes": (
                "先给结论，再解释证据与行动。" if language == "zh-CN" else "Lead with conclusions."
            ),
            "sourceRefs": source_refs,
        }
        return PlanningResult(
            data=data,
            provider=self.provider,
            model=self.model,
            input_tokens=self._tokens({"topic": topic, "sourceRefs": source_refs}),
            output_tokens=self._tokens(data),
        )

    def generate_outline(
        self,
        *,
        intent: dict[str, Any],
        existing: dict[str, Any] | None,
        instruction: str,
        action: str,
        target_slide_id: str | None,
    ) -> PlanningResult:
        count = int(intent["targetSlideCount"])
        language = intent["language"]
        if existing:
            slides = [dict(slide) for slide in existing["slides"]]
            story = str(existing["storySummary"])
            if action == "rewrite_slide" and target_slide_id:
                matched = False
                for slide in slides:
                    if slide["outlineSlideId"] == target_slide_id:
                        suffix = instruction.strip()[:80] or (
                            "强化结论与证据" if language == "zh-CN" else "Sharpen the evidence"
                        )
                        slide["keyPoints"] = [suffix, *slide["keyPoints"][:2]]
                        matched = True
                if not matched:
                    raise PlanningSchemaError("target outline slide does not exist")
            else:
                suffix = instruction.strip()[:120] or (
                    "强化结论、证据与行动的衔接"
                    if language == "zh-CN"
                    else "Strengthen conclusion, evidence, and action"
                )
                story = f"{story.rstrip('。.')}；{suffix}。"
                slides[0] = {
                    **slides[0],
                    "keyPoints": [suffix, *slides[0]["keyPoints"][:2]],
                }
        else:
            zh_titles = [
                "封面与核心命题",
                "一页结论",
                "现状与关键数据",
                "问题拆解",
                "原因与洞察",
                "策略选择",
                "行动路线图",
                "收束与下一步",
            ]
            en_titles = [
                "Cover and thesis",
                "Executive conclusion",
                "Current state and evidence",
                "Problem framing",
                "Root causes",
                "Strategic choices",
                "Action roadmap",
                "Next steps",
            ]
            titles = zh_titles if language == "zh-CN" else en_titles
            content_roles = (
                ("content", "data", "comparison", "content", "risk_action", "timeline")
                if intent.get("sourceRefs")
                else ("content", "comparison", "timeline", "risk_action")
            )
            slides = [
                {
                    "type": (
                        "cover"
                        if index == 0
                        else (
                            "closing"
                            if index == count - 1
                            else content_roles[(index - 1) % len(content_roles)]
                        )
                    ),
                    "title": titles[index % len(titles)],
                    "keyPoints": [
                        (
                            f"围绕“{intent['title']}”给出第 {index + 1} 个清晰论点"
                            if language == "zh-CN"
                            else f"Make argument {index + 1} for {intent['title']}"
                        )
                    ],
                    "sourceCitations": list(intent.get("sourceRefs") or []),
                }
                for index in range(count)
            ]
            story = (
                "从核心结论出发，以证据解释原因，并落到可执行行动。"
                if language == "zh-CN"
                else "Move from conclusion through evidence to executable action."
            )
        data = {"storySummary": story, "targetSlideCount": count, "slides": slides}
        return PlanningResult(
            data=data,
            provider=self.provider,
            model=self.model,
            input_tokens=self._tokens(
                {"intent": intent, "instruction": instruction, "action": action}
            ),
            output_tokens=self._tokens(data),
        )


def _post_json(url: str, payload: bytes, headers: dict[str, str], timeout: float) -> dict[str, Any]:
    http_request = request.Request(url, data=payload, headers=headers, method="POST")
    with request.urlopen(http_request, timeout=timeout) as response:
        body = response.read(512 * 1024 + 1)
    if len(body) > 512 * 1024:
        raise PlanningSchemaError("provider gateway response exceeds the size limit")
    decoded = json.loads(body)
    if not isinstance(decoded, dict):
        raise PlanningSchemaError("provider gateway response must be an object")
    return decoded


class RemotePlanningGateway:
    """Synchronous API facade over the internal, secret-holding Provider service."""

    def __init__(
        self,
        settings: PlanningGatewaySettings,
        *,
        sender: Any = _post_json,
    ) -> None:
        if settings.backend != "kimi":
            raise ValueError("RemotePlanningGateway requires PLANNING_BACKEND=kimi")
        if not settings.gateway_url.startswith(("http://", "https://")):
            raise ValueError("PROVIDER_GATEWAY_URL must be an HTTP(S) URL")
        if not settings.gateway_token:
            raise ValueError("PROVIDER_GATEWAY_TOKEN is required for live planning")
        if (
            os.getenv("APP_ENVIRONMENT", "local").strip().lower() != "local"
            and settings.gateway_token == "local-development-provider-gateway-only"
        ):
            raise ValueError("the development Provider Gateway token is forbidden outside local")
        self._settings = settings
        self._sender = sender

    def _call(self, path: str, payload: dict[str, Any]) -> PlanningResult:
        url = f"{self._settings.gateway_url.rstrip('/')}/{path.lstrip('/')}"
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self._settings.gateway_token}",
            "Content-Type": "application/json",
        }
        try:
            body = self._sender(url, encoded, headers, self._settings.timeout_seconds)
            data = body["data"]
            if not isinstance(data, dict):
                raise TypeError("data is not an object")
            return PlanningResult(
                data=data,
                provider=str(body["provider"]),
                model=str(body["model"]),
                input_tokens=max(0, int(body.get("inputTokens") or 0)),
                output_tokens=max(0, int(body.get("outputTokens") or 0)),
                repair_count=int(body.get("repairCount") or 0),
            )
        except error.HTTPError as exc:
            if exc.code in {502, 503, 504}:
                raise PlanningUnavailableError("live planning provider is unavailable") from exc
            raise PlanningSchemaError("provider gateway rejected the planning request") from exc
        except (error.URLError, TimeoutError) as exc:
            raise PlanningUnavailableError("provider gateway is unavailable") from exc
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise PlanningSchemaError("provider gateway returned an invalid response") from exc

    def infer_intent(
        self, *, topic: str, source_refs: list[str], language: str = "zh-CN"
    ) -> PlanningResult:
        return self._call(
            "planning/intent",
            {"topic": topic, "sourceRefs": source_refs, "language": language},
        )

    def generate_outline(
        self,
        *,
        intent: dict[str, Any],
        existing: dict[str, Any] | None,
        instruction: str,
        action: str,
        target_slide_id: str | None,
    ) -> PlanningResult:
        return self._call(
            "planning/outline",
            {
                "intent": intent,
                "existing": existing,
                "instruction": instruction,
                "action": action,
                "targetSlideId": target_slide_id,
            },
        )


def create_planning_gateway(
    settings: PlanningGatewaySettings | None = None,
) -> DeterministicPlanningGateway | RemotePlanningGateway:
    resolved = settings or PlanningGatewaySettings.from_env()
    if resolved.backend == "fake":
        return DeterministicPlanningGateway()
    if resolved.backend == "kimi":
        return RemotePlanningGateway(resolved)
    raise ValueError("PLANNING_BACKEND must be fake or kimi")
