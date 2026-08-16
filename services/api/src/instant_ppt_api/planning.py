"""Provider-neutral deterministic planning gateway used by the G05 product flow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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
            slides = [
                {
                    "type": (
                        "cover" if index == 0 else ("closing" if index == count - 1 else "content")
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
