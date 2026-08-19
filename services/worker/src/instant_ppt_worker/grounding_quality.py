"""Deterministic claim-to-source evidence maps and semantic release checks."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from instant_ppt_worker.models import DeckPlan

_FACT_PREFIX = re.compile(r"^(?:结论|证据|事实|数据)[：:]\s*")
_NUMBER = re.compile(r"(?<![A-Za-z0-9])[-+]?(?:\d+(?:\.\d+)?|\.\d+)%?")
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9._-]*|[\u3400-\u9fff]")


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _normalize(value: str) -> str:
    return "".join(value.casefold().split()).strip("。！？.!?")


def _claim_core(value: str) -> str:
    return _normalize(_FACT_PREFIX.sub("", value.strip()))


def _numbers(value: str) -> list[str]:
    return [match.group(0).rstrip("%") for match in _NUMBER.finditer(value)]


def _semantic_terms(value: str) -> set[str]:
    return {token.casefold() for token in _WORD.findall(value) if token.strip()}


def _citation(fragment: dict[str, Any]) -> dict[str, Any]:
    return {
        "sourceArtifactId": fragment["sourceArtifactId"],
        "fragmentId": fragment["fragmentId"],
        "textSha256": fragment["textSha256"],
        "page": fragment.get("page"),
    }


def _supporting_fragments(text: str, fragments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    core = _claim_core(text)
    exact = [item for item in fragments if core and core in _normalize(str(item["text"]))]
    if exact:
        return exact
    claim_numbers = set(_numbers(text))
    claim_terms = _semantic_terms(text)
    candidates: list[dict[str, Any]] = []
    for fragment in fragments:
        source = str(fragment["text"])
        if claim_numbers and not claim_numbers.issubset(set(_numbers(source))):
            continue
        source_terms = _semantic_terms(source)
        if claim_terms and len(claim_terms & source_terms) / len(claim_terms) >= 0.7:
            candidates.append(fragment)
    return candidates


def build_evidence_map(
    deck: DeckPlan,
    roster: list[dict[str, Any]],
    fragments: list[dict[str, Any]],
    *,
    source_manifest_sha256: str,
) -> dict[str, Any]:
    """Bind every factual visible claim and chart datum to immutable fragments."""

    slides: list[dict[str, Any]] = []
    cited_core: set[tuple[str, str]] = set()
    for slide, planned in zip(deck.slides, roster, strict=True):
        claims: list[dict[str, Any]] = []
        visible = [("title", slide.title), *(
            (f"body[{index}]", value) for index, value in enumerate(slide.body)
        )]
        for field, text in visible:
            if not fragments:
                claim_type = "limited-general"
                supporting: list[dict[str, Any]] = []
            elif field == "title" and planned["role"] == "cover":
                claim_type = "framing"
                supporting = []
            elif field == "title" and planned.get("chart"):
                claim_type = "derived-comparison"
                supporting = [
                    item
                    for item in fragments
                    if any(
                        label.casefold() in str(item["text"]).casefold()
                        and f"{value:g}" in str(item["text"])
                        for label, value in planned["chart"]["values"]
                    )
                ]
            elif text.startswith("行动："):
                claim_type = "audience-action"
                supporting = []
            elif "直接来自已批准来源" in text:
                claim_type = "source-disclosure"
                supporting = []
            else:
                claim_type = "factual"
                supporting = _supporting_fragments(text, fragments)
            citations = [_citation(item) for item in supporting]
            cited_core.update(
                (str(item["sourceArtifactId"]), str(item["fragmentId"]))
                for item in supporting
            )
            claim: dict[str, Any] = {
                "field": field,
                "text": text,
                "claimType": claim_type,
                "citations": citations,
                "claimSha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            }
            if claim_type == "derived-comparison":
                values = list(planned["chart"]["values"])
                ranked = sorted(values, key=lambda item: item[1], reverse=True)
                claim["derivation"] = {
                    "formula": "(leader-runnerUp)/runnerUp*100",
                    "operands": [
                        {"label": label, "value": value} for label, value in values
                    ],
                    "result": (
                        (ranked[0][1] - ranked[1][1]) / ranked[1][1] * 100
                        if len(ranked) >= 2 and ranked[1][1]
                        else 0
                    ),
                }
            claims.append(claim)
        chart = None
        if planned.get("chart"):
            chart = {
                "objectKey": planned["chart"]["objectKey"],
                "values": [
                    {"label": label, "value": value}
                    for label, value in planned["chart"]["values"]
                ],
                "unit": planned["chart"]["unit"],
                "comparisonBaseline": 0,
                "citations": [
                    _citation(item)
                    for item in fragments
                    if any(
                        label.casefold() in str(item["text"]).casefold()
                        and f"{value:g}" in str(item["text"])
                        for label, value in planned["chart"]["values"]
                    )
                ],
            }
            cited_core.update(
                (str(item["sourceArtifactId"]), str(item["fragmentId"]))
                for item in fragments
                if any(
                    label.casefold() in str(item["text"]).casefold()
                    and f"{value:g}" in str(item["text"])
                    for label, value in planned["chart"]["values"]
                )
            )
        slides.append(
            {
                "slideId": slide.slide_id,
                "outlineSlideId": slide.outline_slide_id,
                "pnn": planned["pnn"],
                "role": planned["role"],
                "claims": claims,
                "chart": chart,
            }
        )
    core_fragments = [
        {
            "sourceArtifactId": item["sourceArtifactId"],
            "fragmentId": item["fragmentId"],
            "textSha256": item["textSha256"],
            "required": (
                str(item["sourceArtifactId"]), str(item["fragmentId"])
            )
            in cited_core,
        }
        for item in fragments
    ]
    value = {
        "schema": "instant-ppt.evidence-map.v1",
        "sourceManifestSha256": source_manifest_sha256,
        "mode": "closed-corpus" if fragments else "limited-general-draft",
        "slides": slides,
        "sourceCoreFragments": core_fragments,
    }
    value["evidenceMapSha256"] = _canonical_hash(value)
    return value


def evaluate_evidence_map(
    evidence_map: dict[str, Any],
    fragments: list[dict[str, Any]],
    *,
    source_manifest_sha256: str,
) -> dict[str, Any]:
    """Reject allowed-but-unsupported citations, stale hashes, and invalid charts."""

    findings: list[dict[str, Any]] = []
    expected_map_hash = str(evidence_map.get("evidenceMapSha256") or "")
    unhashed = {key: value for key, value in evidence_map.items() if key != "evidenceMapSha256"}
    if expected_map_hash != _canonical_hash(unhashed):
        findings.append(
            {
                "code": "EVIDENCE_MAP_HASH_STALE",
                "severity": "blocking",
                "slideId": "deck",
                "field": "evidenceMapSha256",
                "message": "evidence map hash does not bind its current payload",
                "excerpt": expected_map_hash[:16],
            }
        )
    if evidence_map.get("sourceManifestSha256") != source_manifest_sha256:
        findings.append(
            {
                "code": "EVIDENCE_SOURCE_MANIFEST_STALE",
                "severity": "blocking",
                "slideId": "deck",
                "field": "sourceManifestSha256",
                "message": "evidence map is bound to another source manifest",
                "excerpt": str(evidence_map.get("sourceManifestSha256", ""))[:16],
            }
        )
    lookup = {
        (str(item["sourceArtifactId"]), str(item["fragmentId"])): item
        for item in fragments
    }
    cited: set[tuple[str, str]] = set()
    for slide in evidence_map.get("slides", []):
        slide_id = str(slide.get("slideId") or "unknown")
        for claim in slide.get("claims", []):
            claim_type = str(claim.get("claimType") or "")
            text = str(claim.get("text") or "")
            citations = list(claim.get("citations") or [])
            resolved: list[dict[str, Any]] = []
            for citation in citations:
                key = (
                    str(citation.get("sourceArtifactId") or ""),
                    str(citation.get("fragmentId") or ""),
                )
                fragment = lookup.get(key)
                if fragment is None or citation.get("textSha256") != fragment["textSha256"]:
                    findings.append(
                        {
                            "code": "CITATION_NOT_IN_APPROVED_SNAPSHOT",
                            "severity": "blocking",
                            "slideId": slide_id,
                            "field": str(claim.get("field") or "claim"),
                            "message": "citation is missing or hash-stale",
                            "excerpt": text[:180],
                        }
                    )
                    continue
                cited.add(key)
                resolved.append(fragment)
            if claim_type == "factual":
                supported = bool(resolved) and bool(_supporting_fragments(text, resolved))
                if not supported:
                    findings.append(
                        {
                            "code": "CITATION_SEMANTICALLY_UNSUPPORTED",
                            "severity": "blocking",
                            "slideId": slide_id,
                            "field": str(claim.get("field") or "claim"),
                            "message": "allowed citation does not support the visible claim",
                            "excerpt": text[:180],
                        }
                    )
            elif claim_type == "derived-comparison":
                derivation = dict(claim.get("derivation") or {})
                operands = list(derivation.get("operands") or [])
                source_text = "\n".join(str(item["text"]) for item in resolved)
                operands_supported = bool(operands) and all(
                    str(item.get("label", "")).casefold() in source_text.casefold()
                    and f"{float(item.get('value', 0)):g}" in source_text
                    for item in operands
                )
                claim_numbers = {round(float(value), 0) for value in _numbers(text)}
                derived = round(float(derivation.get("result", -1)), 0)
                if not operands_supported or derived not in claim_numbers:
                    findings.append(
                        {
                            "code": "DERIVED_CLAIM_NOT_REPRODUCIBLE",
                            "severity": "blocking",
                            "slideId": slide_id,
                            "field": str(claim.get("field") or "title"),
                            "message": (
                                "derived comparison cannot be reproduced from cited operands"
                            ),
                            "excerpt": text[:180],
                        }
                    )
        chart = slide.get("chart")
        if chart:
            source_text = "\n".join(
                str(lookup[key]["text"])
                for key in (
                    (
                        str(item.get("sourceArtifactId") or ""),
                        str(item.get("fragmentId") or ""),
                    )
                    for item in chart.get("citations", [])
                )
                if key in lookup
            )
            chart_supported = (
                chart.get("comparisonBaseline") == 0
                and bool(str(chart.get("unit") or ""))
                and str(chart.get("unit") or "").casefold() in source_text.casefold()
                and all(
                    str(item.get("label") or "").casefold() in source_text.casefold()
                    and f"{float(item.get('value', 0)):g}" in source_text
                    for item in chart.get("values", [])
                )
            )
            if not chart_supported:
                findings.append(
                    {
                        "code": "CHART_SOURCE_DATA_MISMATCH",
                        "severity": "blocking",
                        "slideId": slide_id,
                        "field": "chart",
                        "message": "chart labels, values, unit, or zero baseline lack support",
                        "excerpt": str(chart.get("objectKey") or "")[:180],
                    }
                )
    required_core = {
        (str(item["sourceArtifactId"]), str(item["fragmentId"]))
        for item in evidence_map.get("sourceCoreFragments", [])
        if item.get("required")
    }
    if not required_core.issubset(cited):
        findings.append(
            {
                "code": "SOURCE_CORE_COVERAGE_MISSING",
                "severity": "blocking",
                "slideId": "deck",
                "field": "sourceCoreFragments",
                "message": "one or more agreed core source fragments are not used",
                "excerpt": ",".join(
                    fragment for _, fragment in sorted(required_core - cited)
                )[:180],
            }
        )
    evidence_slides = list(evidence_map.get("slides", []))
    endings = [slide for slide in evidence_slides if slide.get("role") == "ending"]
    if len(evidence_slides) >= 3 and not endings:
        findings.append(
            {
                "code": "ENDING_SLIDE_MISSING",
                "severity": "blocking",
                "slideId": "deck",
                "field": "roster",
                "message": "multi-page narrative has no ending role",
                "excerpt": ",".join(str(slide.get("role") or "") for slide in evidence_slides),
            }
        )
    if endings:
        ending_text = " ".join(
            str(claim.get("text") or "") for claim in endings[-1].get("claims", [])
        )
        if "结论：" not in ending_text or "行动：" not in ending_text:
            findings.append(
                {
                    "code": "ENDING_CLOSURE_INCOMPLETE",
                    "severity": "blocking",
                    "slideId": str(endings[-1].get("slideId") or "deck"),
                    "field": "ending",
                    "message": "ending must close with both conclusion and action",
                    "excerpt": ending_text[:180],
                }
            )
    if len(evidence_slides) >= 5:
        longest_repeated_role = 1
        current_run = 1
        for previous, current in zip(evidence_slides, evidence_slides[1:], strict=False):
            if current.get("role") == previous.get("role") == "content":
                current_run += 1
                longest_repeated_role = max(longest_repeated_role, current_run)
            else:
                current_run = 1
        if longest_repeated_role >= 3:
            findings.append(
                {
                    "code": "VISUAL_ROLE_PATTERN_REPETITION",
                    "severity": "blocking",
                    "slideId": "deck",
                    "field": "roster",
                    "message": "three or more consecutive pages collapse to one content role",
                    "excerpt": f"longest-content-run={longest_repeated_role}",
                }
            )
    report = {
        "schema": "instant-ppt.grounding-quality.v1",
        "sourceManifestSha256": source_manifest_sha256,
        "evidenceMapSha256": expected_map_hash,
        "passed": not findings,
        "findings": findings,
        "requiredCoreCount": len(required_core),
        "coveredCoreCount": len(required_core & cited),
        "roleCount": len({str(slide.get("role") or "") for slide in evidence_slides}),
    }
    report["reportSha256"] = _canonical_hash(report)
    return report
