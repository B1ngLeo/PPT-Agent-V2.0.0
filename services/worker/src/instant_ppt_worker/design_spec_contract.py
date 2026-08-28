"""PPT Master design-spec authoring contract and worker-side validation.

The vendored PPT Master reference and its versioned Markdown schema are the
authoritative sources.  This module projects them into the Main Presentation
Agent tool surface and adds only application-owned Outline invariants.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from functools import lru_cache
from typing import Any

from instant_ppt_worker.paths import VENDOR_ROOT

DESIGN_SPEC_REFERENCE_PATH = VENDOR_ROOT / "templates" / "design_spec_reference.md"
DESIGN_SPEC_SCHEMA_PATH = VENDOR_ROOT / "templates" / "schemas" / "design_spec.schema.json"

_SECTION_HEADING = re.compile(r"(?m)^##[ \t]+(?P<heading>[^\r\n]+?)[ \t]*$")
_SUBHEADING = re.compile(r"(?m)^###[ \t]+(?P<heading>[^\r\n]+?)[ \t]*$")
PPT_MASTER_AUTHORITY_POLICY = "presentation-authoring@v3-ppt-master-authority"

_LEGACY_SLIDE_HEADING = re.compile(
    r"(?m)^####[ \t]+Slide[ \t]+(?P<number>\d+)[ \t]*/[ \t]*"
    r"(?P<pnn>P\d{2,3})[ \t]+-[ \t]+(?P<title>[^\r\n]+?)[ \t]*$"
)
_UPSTREAM_SLIDE_HEADING = re.compile(
    r"(?m)^####[ \t]+Slide[ \t]+(?P<number>\d+)[ \t]+-[ \t]+"
    r"(?P<title>[^\r\n]+?)[ \t]*$"
)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@lru_cache(maxsize=1)
def _reference_text() -> str:
    return DESIGN_SPEC_REFERENCE_PATH.read_text(encoding="utf-8-sig")


@lru_cache(maxsize=1)
def _schema() -> dict[str, Any]:
    value = json.loads(DESIGN_SPEC_SCHEMA_PATH.read_text(encoding="utf-8-sig"))
    contract = value.get("x-markdown")
    if not isinstance(contract, dict) or contract.get("version") != 1:
        raise RuntimeError("vendored design-spec schema has no supported x-markdown contract")
    return value


@lru_cache(maxsize=1)
def _canonical_headings() -> tuple[str, ...]:
    """Read canonical I-X authoring headings from the reference template."""

    found: list[str] = []
    for match in _SECTION_HEADING.finditer(_reference_text()):
        heading = match.group("heading").strip()
        if re.fullmatch(r"[IVX]+\.[ \t]+.+", heading) and heading not in found:
            found.append(heading)
    expected = [
        definition
        for definition in _schema()["x-markdown"].get("sections", [])
        if isinstance(definition, dict)
    ]
    if len(found) != len(expected):
        raise RuntimeError("design-spec reference headings drifted from its machine schema")
    return tuple(found)


@lru_cache(maxsize=1)
def _authoring_reference_projection() -> str:
    """Project the complete authoring skeleton without explanatory prose."""

    blocks = re.findall(r"```markdown\s*\n(.*?)```", _reference_text(), flags=re.DOTALL)
    if len(blocks) < 5:
        raise RuntimeError("design-spec reference no longer exposes its canonical Markdown blocks")
    rules = [
        "Runtime authoring rules:",
        (
            "- Replace every angle-bracket notation with final values; never emit ellipses "
            "or placeholders."
        ),
        (
            "- Keep headings, subsection headings, table fields, and slide fields in English; "
            "values may use the deck language."
        ),
        (
            "- Omit VII only when no Chart/Table catalog reference is selected; always keep "
            "VIII, even with an empty table."
        ),
        (
            "- When there are no image resources, leave VIII with only its header and "
            "separator rows; never add a dash, none, N/A, or other placeholder data row."
        ),
        (
            "- Every real VIII row uses Crop Policy adaptive or no-crop and Acquire Via "
            "ai, web, user, placeholder, or slice."
        ),
        "- Add III / AI Image Strategy when any VIII row uses Acquire Via: ai.",
        (
            "- Write one ordered Slide block for every approved page using its exact "
            "canonical heading."
        ),
        "- Every Slide requires Audience move, Layout, Title, Core message, and complete Content.",
        "- When notes are disabled, X contains only '- **Generation**: disabled'.",
    ]
    return "\n\n".join([*rules, *(block.strip() for block in blocks)])


def design_spec_contract_payload(
    outline: Iterable[Any], *, upstream_authority: bool = False
) -> dict[str, Any]:
    """Return the complete, supervisor-owned contract the Strategist must read."""

    schema = _schema()
    reference = _reference_text()
    roster = []
    for page in outline:
        roster.append(
            {
                "order": int(page.order),
                "pnn": str(page.pnn),
                "title": str(page.title),
                "canonicalHeading": (
                    f"#### Slide {page.order:02d} - {page.title}"
                    if upstream_authority
                    else f"#### Slide {page.order:02d} / {page.pnn} - {page.title}"
                ),
            }
        )
    return {
        "schema": "instant-ppt.design-spec-contract.v1",
        "sourceSchemaId": schema.get("$id"),
        "sourceSchemaSha256": _sha256_text(
            DESIGN_SPEC_SCHEMA_PATH.read_text(encoding="utf-8-sig")
        ),
        "referenceSha256": _sha256_text(reference),
        "languageRule": (
            "Keep every Markdown section heading, subsection heading, table field, and "
            "slide-block field in the reference's original English. Content values may use "
            "the presentation language."
        ),
        "canonicalSectionHeadings": list(_canonical_headings()),
        "approvedRoster": roster,
        "markdownSchema": schema["x-markdown"],
        "authoringReference": (
            reference if upstream_authority else _authoring_reference_projection()
        ),
        "pageHeadingAuthority": (
            "PPT Master native `Slide NN - <page name>`; PNN and slideId remain outside "
            "design_spec.md and page titles may be refined without changing page count/order"
            if upstream_authority
            else "legacy exact order/PNN/approved-title heading"
        ),
    }


def _parse_sections(text: str) -> list[dict[str, Any]]:
    matches = list(_SECTION_HEADING.finditer(text))
    sections: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        body_start = match.end()
        body_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections.append(
            {
                "heading": match.group("heading").strip(),
                "offset": match.start(),
                "body": text[body_start:body_end].strip(),
            }
        )
    return sections


def _error(code: str, location: str, message: str) -> dict[str, str]:
    return {"code": code, "location": location, "message": message}


def _field_present(body: str, field: str) -> bool:
    return (
        re.search(
            rf"(?mi)^[ \t]*-[ \t]+(?:\*\*)?{re.escape(field)}(?:\*\*)?[ \t]*:[ \t]*\S",
            body,
        )
        is not None
    )


def _image_resource_rows(body: str) -> list[list[str]]:
    """Return §VIII data rows after its canonical 12-column table header."""

    expected_header = [
        "Filename",
        "Dimensions",
        "Ratio",
        "Purpose",
        "Type",
        "Layout pattern",
        "Crop Policy",
        "Acquire Via",
        "Status",
        "Reference",
        "text_policy",
        "page_role",
    ]
    lines = [line.strip() for line in body.splitlines()]
    for index, line in enumerate(lines):
        if not line.startswith("|") or not line.endswith("|"):
            continue
        cells = [cell.strip() for cell in line[1:-1].split("|")]
        if cells != expected_header:
            continue
        rows: list[list[str]] = []
        for candidate in lines[index + 2 :]:
            if not candidate and not rows:
                continue
            if not candidate.startswith("|") or not candidate.endswith("|"):
                break
            rows.append([cell.strip() for cell in candidate[1:-1].split("|")])
        return rows
    return []


def validate_design_spec(
    text: str, outline: Iterable[Any], *, upstream_authority: bool = False
) -> list[dict[str, str]]:
    """Validate PPT Master grammar plus this application's approved roster."""

    errors: list[dict[str, str]] = []
    schema = _schema()
    contract = schema["x-markdown"]
    first_non_empty = next((line.strip() for line in text.splitlines() if line.strip()), "")
    expected_marker = f"<!-- ppt-master-schema: {contract['marker']} -->"
    if first_non_empty != expected_marker:
        errors.append(
            _error(
                "marker_missing_or_invalid",
                "header",
                f"first non-empty line must be exactly {expected_marker}",
            )
        )

    for pattern in contract.get("unresolved_patterns", []):
        if isinstance(pattern, str) and re.search(pattern, text):
            errors.append(
                _error(
                    "unresolved_placeholder",
                    "document",
                    f"content contains an unresolved placeholder matching {pattern}",
                )
            )

    sections = _parse_sections(text)
    matched: dict[str, dict[str, Any] | None] = {}
    definitions = [
        value for value in contract.get("sections", []) if isinstance(value, dict)
    ]
    for definition in definitions:
        section_id = str(definition.get("id") or "")
        pattern = str(definition.get("pattern") or "")
        candidates = [
            section
            for section in sections
            if pattern and re.fullmatch(pattern, str(section["heading"]))
        ]
        if len(candidates) > 1:
            errors.append(
                _error(
                    "duplicate_section",
                    section_id,
                    f"section {section_id} appears more than once",
                )
            )
        section = candidates[0] if candidates else None
        matched[section_id] = section
        if definition.get("required") is True and section is None:
            errors.append(
                _error(
                    "missing_section",
                    section_id,
                    f"missing required section matching {pattern}",
                )
            )
        elif section is not None and int(definition.get("min_body_chars") or 0) > len(
            str(section["body"])
        ):
            errors.append(
                _error("empty_section", section_id, f"section {section_id} has no content")
            )

    ordered = [
        (str(section_id), matched.get(str(section_id)))
        for section_id in contract.get("section_order", [])
        if matched.get(str(section_id)) is not None
    ]
    offsets = [int(section["offset"]) for _, section in ordered if section is not None]
    if offsets != sorted(offsets):
        errors.append(
            _error(
                "section_order_invalid",
                "document",
                "sections must follow the canonical I-X order",
            )
        )

    image_section = matched.get("image_resource_list")
    visual_section = matched.get("visual_theme")
    image_rows = (
        _image_resource_rows(str(image_section["body"]))
        if image_section is not None
        else []
    )
    placeholder_values = {"", "-", "—", "–", "none", "n/a", "na", "not applicable"}
    for row_index, row in enumerate(image_rows, start=1):
        location = f"image_resource_list.row_{row_index}"
        if len(row) != 12:
            errors.append(
                _error(
                    "image_resource_row_invalid",
                    location,
                    "each Image Resource List row must contain exactly 12 columns",
                )
            )
            continue
        normalized = [cell.strip().lower() for cell in row]
        if all(value in placeholder_values for value in normalized):
            errors.append(
                _error(
                    "image_resource_placeholder_row",
                    location,
                    "leave the Image Resource List empty instead of adding a placeholder row",
                )
            )
            continue
        if normalized[0] in placeholder_values:
            errors.append(
                _error(
                    "image_resource_filename_invalid",
                    location,
                    "Filename must identify a real planned image resource",
                )
            )
        if normalized[5] in placeholder_values:
            errors.append(
                _error(
                    "image_resource_layout_pattern_missing",
                    location,
                    "Layout pattern must be non-empty for every image resource",
                )
            )
        if normalized[6] not in {"adaptive", "no-crop"}:
            errors.append(
                _error(
                    "image_resource_crop_policy_invalid",
                    location,
                    "Crop Policy must be adaptive or no-crop",
                )
            )
        if normalized[7] not in {"ai", "web", "user", "placeholder", "slice"}:
            errors.append(
                _error(
                    "image_resource_acquire_via_invalid",
                    location,
                    "Acquire Via must be ai, web, user, placeholder, or slice",
                )
            )
    if image_section is not None and re.search(
        r"(?im)^\|[^\n]*\|\s*ai\s*\|", str(image_section["body"])
    ):
        visual_body = str(visual_section["body"]) if visual_section else ""
        if re.search(r"(?m)^###[ \t]+AI Image Strategy[ \t]*$", visual_body) is None:
            errors.append(
                _error(
                    "conditional_subheading_missing",
                    "visual_theme",
                    "AI Image Strategy is required when an image row uses Acquire Via: ai",
                )
            )

    required_subheadings = {
        "visual_theme": ("Theme Style", "Color Scheme"),
        "typography_system": ("Font Plan", "Font Size Hierarchy"),
        "layout_principles": ("Page Structure", "Spacing Specification"),
    }
    for section_id, headings in required_subheadings.items():
        section = matched.get(section_id)
        if section is None:
            continue
        present = {
            match.group("heading").strip()
            for match in _SUBHEADING.finditer(section["body"])
        }
        for heading in headings:
            if heading not in present:
                errors.append(
                    _error(
                        "missing_subheading",
                        section_id,
                        f"missing required subsection: {heading}",
                    )
                )

    approved = list(outline)
    project_section = matched.get("project_information")
    project_body = str(project_section.get("body", "")) if project_section else ""
    count_match = re.search(r"(?mi)^\|[ \t]*Page Count[ \t]*\|[ \t]*(\d+)[ \t]*\|", project_body)
    if count_match is None:
        errors.append(
            _error(
                "page_count_missing",
                "project_information",
                "Project Information must contain a Page Count table row",
            )
        )
    elif int(count_match.group(1)) != len(approved):
        errors.append(
            _error(
                "page_count_mismatch",
                "project_information",
                f"Page Count must be {len(approved)} to match the approved Outline",
            )
        )

    content_outline_section = matched.get("content_outline")
    outline_body = (
        str(content_outline_section.get("body", "")) if content_outline_section else ""
    )
    slide_pattern = _UPSTREAM_SLIDE_HEADING if upstream_authority else _LEGACY_SLIDE_HEADING
    slide_matches = list(slide_pattern.finditer(outline_body))
    expected_roster: list[tuple[Any, ...]]
    actual_roster: list[tuple[Any, ...]]
    if upstream_authority:
        expected_roster = [(int(page.order),) for page in approved]
        actual_roster = [(int(match.group("number")),) for match in slide_matches]
    else:
        expected_roster = [
            (int(page.order), str(page.pnn), str(page.title)) for page in approved
        ]
        actual_roster = [
            (int(match.group("number")), match.group("pnn"), match.group("title").strip())
            for match in slide_matches
        ]
    if actual_roster != expected_roster:
        errors.append(
            _error(
                "approved_roster_mismatch",
                "content_outline",
                (
                    "slide headings must use the upstream Slide NN - <page name> format "
                    "and preserve the approved page count/order"
                    if upstream_authority
                    else "slide headings must match every approved order/PNN/title exactly"
                ),
            )
        )
    for index, page in enumerate(approved):
        match = slide_matches[index] if index < len(slide_matches) else None
        if match is None or (
            not upstream_authority and match.group("pnn") != str(page.pnn)
        ):
            continue
        body_start = match.end()
        body_end = (
            slide_matches[index + 1].start()
            if index + 1 < len(slide_matches)
            else len(outline_body)
        )
        body = outline_body[body_start:body_end]
        for field in ("Audience move", "Layout", "Title", "Core message", "Content"):
            if not _field_present(body, field):
                errors.append(
                    _error(
                        "slide_field_missing",
                        str(page.pnn),
                        f"{page.pnn} requires a non-empty {field} field",
                    )
                )
    return errors


def rejected_design_spec_sha256(text: str) -> str:
    return _sha256_text(text)
