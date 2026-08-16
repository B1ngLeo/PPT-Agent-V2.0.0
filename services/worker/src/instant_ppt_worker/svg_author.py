"""Deterministic DeckPlan to canonical, editable SVG authoring."""

from __future__ import annotations

import html
import unicodedata
from pathlib import Path

from instant_ppt_worker.models import DeckPlan, SlidePlan

COLORS = ("#2563EB", "#0F766E", "#9333EA", "#C2410C")


def _text(value: str) -> str:
    return html.escape(value, quote=False)


def _display_units(value: str) -> int:
    return sum(
        2 if unicodedata.east_asian_width(character) in {"W", "F"} else 1
        for character in value
    )


def _fit(value: str, limit: int) -> str:
    if _display_units(value) <= limit:
        return value
    fitted: list[str] = []
    used = 0
    ellipsis_units = _display_units("…")
    for character in value:
        width = 2 if unicodedata.east_asian_width(character) in {"W", "F"} else 1
        if used + width + ellipsis_units > limit:
            break
        fitted.append(character)
        used += width
    return "".join(fitted) + "…"


def _font_size_for_line(
    value: str, *, preferred: int, available_width: int, minimum: int = 12
) -> int:
    display_units = max(_display_units(value), 1)
    fitted = (available_width * 2) // display_units
    return max(minimum, min(preferred, fitted))


def _element(tag: str, element_id: str, attributes: dict[str, object], content: str = "") -> str:
    rendered = " ".join(f'{name}="{value}"' for name, value in attributes.items())
    if content:
        return f'  <{tag} id="{element_id}" {rendered}>{content}</{tag}>'
    return f'  <{tag} id="{element_id}" {rendered}/>'


def author_slide(slide: SlidePlan, deck_title: str, index: int, path: Path) -> None:
    accent = COLORS[index % len(COLORS)]
    title_preferred = 42 if _display_units(slide.title) <= 50 else 24
    title_size = _font_size_for_line(
        slide.title,
        preferred=title_preferred,
        available_width=940,
    )
    body = slide.body[:6]
    page_role = (
        slide.role if slide.role in {"cover", "toc", "section", "content", "ending"} else "content"
    )
    lines = [
        (
            '<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" '
            f'viewBox="0 0 1280 720" data-pptx-page-role="{page_role}">'
        ),
        "  <defs>",
        f'    <linearGradient id="background-gradient-{index}" x1="0" y1="0" x2="1" y2="1">',
        '      <stop offset="0" stop-color="#F8FAFC"/>',
        '      <stop offset="1" stop-color="#E2E8F0"/>',
        "    </linearGradient>",
        "  </defs>",
        _element(
            "rect",
            f"background-{index}",
            {
                "x": 0,
                "y": 0,
                "width": 1280,
                "height": 720,
                "fill": f"url(#background-gradient-{index})",
                "data-pptx-role": "background",
            },
        ),
        _element(
            "rect",
            f"accent-{index}",
            {
                "x": 72,
                "y": 68,
                "width": 12,
                "height": 88,
                "rx": 6,
                "fill": accent,
                "data-pptx-role": "decoration",
            },
        ),
        f'  <g id="content-{index}" data-pptx-bounds="112 68 1056 532">',
        _element(
            "text",
            f"title-{index}",
            {
                "x": 112,
                "y": 122,
                "font-family": "Arial, Microsoft YaHei, sans-serif",
                "font-size": title_size,
                "font-weight": 700,
                "fill": "#0F172A",
            },
            _text(slide.title),
        ),
        _element(
            "text",
            f"deck-label-{index}",
            {
                "x": 112,
                "y": 158,
                "font-family": "Arial, Microsoft YaHei, sans-serif",
                "font-size": 18,
                "fill": "#64748B",
            },
            _text(_fit(deck_title, 104)),
        ),
    ]
    if slide.role == "cover":
        lines.extend(
            [
                _element(
                    "rect",
                    f"cover-panel-{index}",
                    {
                        "x": 112,
                        "y": 236,
                        "width": 1056,
                        "height": 280,
                        "rx": 28,
                        "fill": "#FFFFFF",
                        "stroke": "#CBD5E1",
                    },
                ),
                _element(
                    "text",
                    f"cover-message-{index}",
                    {
                        "x": 160,
                        "y": 344,
                        "font-family": "Arial, Microsoft YaHei, sans-serif",
                        "font-size": _font_size_for_line(
                            body[0],
                            preferred=32,
                            available_width=920,
                        ),
                        "fill": accent,
                    },
                    _text(body[0]),
                ),
                _element(
                    "text",
                    f"cover-subtitle-{index}",
                    {
                        "x": 160,
                        "y": 410,
                        "font-family": "Arial, Microsoft YaHei, sans-serif",
                        "font-size": 23,
                        "fill": "#334155",
                    },
                    "Editable native presentation baseline",
                ),
            ]
        )
    else:
        panel_width = 500 if len(body) > 3 else 1056
        lines.append(
            _element(
                "rect",
                f"content-panel-{index}",
                {
                    "x": 112,
                    "y": 210,
                    "width": panel_width,
                    "height": 390,
                    "rx": 24,
                    "fill": "#FFFFFF",
                    "stroke": "#CBD5E1",
                },
            )
        )
        for body_index, item in enumerate(body):
            column = body_index // 3
            row = body_index % 3
            x = 152 + column * 528
            y = 286 + row * 92
            lines.append(
                _element(
                    "circle",
                    f"bullet-{index}-{body_index}",
                    {"cx": x, "cy": y - 8, "r": 7, "fill": accent},
                )
            )
            lines.append(
                _element(
                    "text",
                    f"body-{index}-{body_index}",
                    {
                        "x": x + 26,
                        "y": y,
                        "font-family": "Arial, Microsoft YaHei, sans-serif",
                        "font-size": _font_size_for_line(
                            item,
                            preferred=22,
                            available_width=850 if panel_width == 1056 else 390,
                        ),
                        "fill": "#1E293B",
                    },
                    _text(item),
                )
            )
    lines.extend(
        [
            "  </g>",
            _element(
                "text",
                f"page-{index}",
                {
                    "x": 1168,
                    "y": 668,
                    "text-anchor": "end",
                    "font-family": "Arial, sans-serif",
                    "font-size": 16,
                    "fill": "#64748B",
                    "data-pptx-role": "decoration",
                },
                f"{index + 1:02d}",
            ),
            "</svg>",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def author_deck(deck: DeckPlan, project_dir: Path) -> list[Path]:
    svg_dir = project_dir / "svg_output"
    svg_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for index, slide in enumerate(sorted(deck.slides, key=lambda item: item.order)):
        path = svg_dir / f"slide_{index + 1:02d}.svg"
        author_slide(slide, deck.title, index, path)
        paths.append(path)
    return paths
