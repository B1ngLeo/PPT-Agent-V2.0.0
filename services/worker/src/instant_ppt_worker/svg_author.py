"""Deterministic DeckPlan to canonical, editable SVG authoring."""

from __future__ import annotations

import html
import json
import math
import unicodedata
from pathlib import Path

from instant_ppt_worker.models import DeckPlan, SlidePlan

COLORS = ("#2563EB", "#0F766E", "#9333EA", "#C2410C")


def _text(value: str) -> str:
    return html.escape(value, quote=False)


def _display_units(value: str) -> int:
    return sum(
        2 if unicodedata.east_asian_width(character) in {"W", "F"} else 1 for character in value
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


def _image_href(image_path: Path, svg_path: Path) -> str:
    if image_path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise ValueError("cover image must be PNG, JPEG, or WebP")
    expected_images_dir = (svg_path.parent.parent / "images").resolve()
    resolved = image_path.resolve(strict=True)
    if resolved.parent != expected_images_dir:
        raise ValueError("image must be a direct project-local images/ asset")
    return f"../images/{resolved.name}"


def author_slide(
    slide: SlidePlan,
    deck_title: str,
    index: int,
    path: Path,
    *,
    cover_image_path: Path | None = None,
    image_path: Path | None = None,
    image_crop_policy: str = "adaptive",
    image_placeholder: str | None = None,
) -> None:
    accent = COLORS[index % len(COLORS)]
    # Keep the authored SVG on the title anchor declared by the Default
    # workflow's Design Spec/spec lock.  A non-anchor size may be tolerated as
    # a sparse exception, but becomes a blocking typography drift on decks
    # with three or more slides.
    title_preferred = 38 if _display_units(slide.title) <= 50 else 24
    title_size = _font_size_for_line(
        slide.title,
        preferred=title_preferred,
        available_width=940,
    )
    body = slide.body[:6]
    page_role = (
        slide.role if slide.role in {"cover", "toc", "section", "content", "ending"} else "content"
    )
    selected_image = image_path or (cover_image_path if slide.role == "cover" else None)
    image_href = _image_href(selected_image, path) if selected_image is not None else None
    has_image_slot = bool(image_href or image_placeholder)
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
                        "width": 520 if has_image_slot else 1056,
                        "height": 280,
                        "rx": 28,
                        "fill": "#FFFFFF",
                        "stroke": "#CBD5E1",
                    },
                ),
                *(
                    [
                        _element(
                            "image",
                            f"cover-image-{index}",
                            {
                                "x": 672,
                                "y": 236,
                                "width": 496,
                                "height": 280,
                                "href": image_href,
                                "preserveAspectRatio": (
                                    "xMidYMid meet"
                                    if image_crop_policy == "no-crop"
                                    else "xMidYMid slice"
                                ),
                            },
                        )
                    ]
                    if image_href
                    else []
                ),
                *(
                    [
                        _element(
                            "rect",
                            f"cover-image-placeholder-{index}",
                            {
                                "x": 672,
                                "y": 236,
                                "width": 496,
                                "height": 280,
                                "rx": 20,
                                "fill": "#FFFFFF",
                                "stroke": accent,
                                "stroke-width": 3,
                                "stroke-dasharray": "12,8",
                            },
                        ),
                        _element(
                            "text",
                            f"cover-image-placeholder-label-{index}",
                            {
                                "x": 920,
                                "y": 384,
                                "text-anchor": "middle",
                                "font-family": "Arial, Microsoft YaHei, sans-serif",
                                "font-size": 18,
                                "fill": "#64748B",
                            },
                            _text(_fit(image_placeholder, 40)),
                        ),
                    ]
                    if image_placeholder and not image_href
                    else []
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
                            available_width=440 if has_image_slot else 920,
                        ),
                        "fill": accent,
                    },
                    _text(body[0]),
                ),
            ]
        )
    elif image_href or image_placeholder:
        lines.extend(
            [
                _element(
                    "rect",
                    f"image-copy-panel-{index}",
                    {
                        "x": 112,
                        "y": 210,
                        "width": 500,
                        "height": 390,
                        "rx": 24,
                        "fill": "#FFFFFF",
                        "stroke": "#CBD5E1",
                    },
                ),
                *(
                    [
                        _element(
                            "image",
                            f"placed-image-{index}",
                            {
                                "x": 644,
                                "y": 210,
                                "width": 524,
                                "height": 390,
                                "href": image_href,
                                "preserveAspectRatio": (
                                    "xMidYMid meet"
                                    if image_crop_policy == "no-crop"
                                    else "xMidYMid slice"
                                ),
                            },
                        )
                    ]
                    if image_href
                    else [
                        _element(
                            "rect",
                            f"image-placeholder-{index}",
                            {
                                "x": 644,
                                "y": 210,
                                "width": 524,
                                "height": 390,
                                "rx": 24,
                                "fill": "#FFFFFF",
                                "stroke": accent,
                                "stroke-width": 3,
                                "stroke-dasharray": "12,8",
                            },
                        ),
                        _element(
                            "text",
                            f"image-placeholder-label-{index}",
                            {
                                "x": 906,
                                "y": 402,
                                "text-anchor": "middle",
                                "font-family": "Arial, Microsoft YaHei, sans-serif",
                                "font-size": 18,
                                "fill": "#64748B",
                            },
                            _text(_fit(image_placeholder or "图片资源待处理", 44)),
                        ),
                    ]
                ),
            ]
        )
        for body_index, item in enumerate(body[:4]):
            y = 286 + body_index * 72
            lines.extend(
                [
                    _element(
                        "circle",
                        f"image-bullet-{index}-{body_index}",
                        {"cx": 152, "cy": y - 8, "r": 7, "fill": accent},
                    ),
                    _element(
                        "text",
                        f"image-body-{index}-{body_index}",
                        {
                            "x": 178,
                            "y": y,
                            "font-family": "Arial, Microsoft YaHei, sans-serif",
                            "font-size": _font_size_for_line(
                                item,
                                preferred=20,
                                available_width=390,
                            ),
                            "fill": "#1E293B",
                        },
                        _text(item),
                    ),
                ]
            )
    elif slide.role == "comparison":
        panel_gap = 32
        panel_width = (1056 - panel_gap) // 2
        for body_index, item in enumerate(body[:4]):
            column = body_index % 2
            row = body_index // 2
            x = 112 + column * (panel_width + panel_gap)
            y = 216 + row * 184
            lines.extend(
                [
                    _element(
                        "rect",
                        f"comparison-panel-{index}-{body_index}",
                        {
                            "x": x,
                            "y": y,
                            "width": panel_width,
                            "height": 152,
                            "rx": 22,
                            "fill": "#FFFFFF",
                            "stroke": accent,
                        },
                    ),
                    _element(
                        "text",
                        f"comparison-label-{index}-{body_index}",
                        {
                            "x": x + 28,
                            "y": y + 44,
                            "font-family": "Arial, Microsoft YaHei, sans-serif",
                            "font-size": 16,
                            "font-weight": 700,
                            "fill": accent,
                        },
                        f"{body_index + 1:02d}",
                    ),
                    _element(
                        "text",
                        f"comparison-body-{index}-{body_index}",
                        {
                            "x": x + 28,
                            "y": y + 92,
                            "font-family": "Arial, Microsoft YaHei, sans-serif",
                            "font-size": _font_size_for_line(
                                item,
                                preferred=20,
                                available_width=panel_width - 56,
                            ),
                            "fill": "#1E293B",
                        },
                        _text(item),
                    ),
                ]
            )
    elif slide.role == "timeline":
        count = max(len(body), 1)
        # Timeline labels are centered on their nodes. Keep the endpoint nodes
        # inside a wider safe area so useful CJK labels remain on-canvas.
        start_x = 376
        end_x = 904
        gap = (end_x - start_x) / max(count - 1, 1)
        lines.append(
            _element(
                "line",
                f"timeline-line-{index}",
                {
                    "x1": start_x,
                    "y1": 344,
                    "x2": end_x,
                    "y2": 344,
                    "stroke": "#CBD5E1",
                    "stroke-width": 8,
                },
            )
        )
        for body_index, item in enumerate(body):
            x = (
                (start_x + end_x) / 2
                if count == 1
                else start_x + body_index * gap
            )
            lines.extend(
                [
                    _element(
                        "circle",
                        f"timeline-node-{index}-{body_index}",
                        {"cx": x, "cy": 344, "r": 18, "fill": accent},
                    ),
                    _element(
                        "text",
                        f"timeline-step-{index}-{body_index}",
                        {
                            "x": x,
                            "y": 300,
                            "text-anchor": "middle",
                            "font-family": "Arial, sans-serif",
                            "font-size": 16,
                            "font-weight": 700,
                            "fill": accent,
                        },
                        f"{body_index + 1:02d}",
                    ),
                    _element(
                        "text",
                        f"timeline-body-{index}-{body_index}",
                        {
                            "x": x,
                            "y": 410,
                            "text-anchor": "middle",
                            "font-family": "Arial, Microsoft YaHei, sans-serif",
                            "font-size": _font_size_for_line(
                                item,
                                preferred=18,
                                available_width=max(150, int(gap) - 24),
                            ),
                            "fill": "#1E293B",
                        },
                        _text(item),
                    ),
                ]
            )
    elif slide.role == "risk_action":
        for body_index, item in enumerate(body[:4]):
            y = 226 + body_index * 92
            lines.extend(
                [
                    _element(
                        "rect",
                        f"risk-tag-{index}-{body_index}",
                        {
                            "x": 112,
                            "y": y,
                            "width": 164,
                            "height": 64,
                            "rx": 16,
                            "fill": accent,
                        },
                    ),
                    _element(
                        "text",
                        f"risk-label-{index}-{body_index}",
                        {
                            "x": 194,
                            "y": y + 40,
                            "text-anchor": "middle",
                            "font-family": "Arial, Microsoft YaHei, sans-serif",
                            "font-size": 17,
                            "font-weight": 700,
                            "fill": "#FFFFFF",
                        },
                        "风险" if body_index % 2 == 0 else "行动",
                    ),
                    _element(
                        "rect",
                        f"risk-body-panel-{index}-{body_index}",
                        {
                            "x": 300,
                            "y": y,
                            "width": 868,
                            "height": 64,
                            "rx": 16,
                            "fill": "#FFFFFF",
                            "stroke": "#CBD5E1",
                        },
                    ),
                    _element(
                        "text",
                        f"risk-body-{index}-{body_index}",
                        {
                            "x": 328,
                            "y": y + 40,
                            "font-family": "Arial, Microsoft YaHei, sans-serif",
                            "font-size": _font_size_for_line(
                                item,
                                preferred=20,
                                available_width=812,
                            ),
                            "fill": "#1E293B",
                        },
                        _text(item),
                    ),
                ]
            )
    elif slide.role == "ending":
        for body_index, item in enumerate(body[:2]):
            y = 236 + body_index * 172
            lines.extend(
                [
                    _element(
                        "rect",
                        f"ending-band-{index}-{body_index}",
                        {
                            "x": 112,
                            "y": y,
                            "width": 1056 if body_index == 0 else 880,
                            "height": 132,
                            "rx": 26,
                            "fill": "#FFFFFF" if body_index == 0 else accent,
                            "stroke": accent,
                        },
                    ),
                    _element(
                        "text",
                        f"ending-body-{index}-{body_index}",
                        {
                            "x": 152,
                            "y": y + 78,
                            "font-family": "Arial, Microsoft YaHei, sans-serif",
                            "font-size": _font_size_for_line(
                                item,
                                preferred=24 if body_index == 0 else 22,
                                available_width=800,
                            ),
                            "font-weight": 700 if body_index == 0 else 600,
                            "fill": "#0F172A" if body_index == 0 else "#FFFFFF",
                        },
                        _text(item),
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


def author_chart_slide(
    slide: SlidePlan,
    path: Path,
    *,
    chart: list[tuple[str, float]],
    unit: str,
) -> None:
    """Author an editable native-chart marker with a faithful SVG fallback."""

    if len(chart) < 2:
        raise ValueError("native comparison chart requires at least two values")
    x_min, y_min, x_max, y_max = 180.0, 230.0, 1120.0, 560.0
    axis_max = max(1.0, math.ceil(max(value for _, value in chart) / 100.0) * 100.0)
    gap = (x_max - x_min) / len(chart)
    bar_width = min(160.0, gap * 0.55)
    metadata = {
        "x": 120,
        "y": 180,
        "width": 1040,
        "height": 420,
        "plot_area": {
            "x": x_min,
            "y": y_min,
            "width": x_max - x_min,
            "height": y_max - y_min,
        },
        "name": "throughput-comparison",
        "type": "column",
        "categories": [label for label, _ in chart],
        "series": [
            {
                "name": unit,
                "values": [value for _, value in chart],
                "point_colors": [
                    "#2563EB" if index == 0 else "#0F766E" for index in range(len(chart))
                ],
            }
        ],
        "data_labels": {"show_value": True, "position": "outside_end", "font_size": 16},
        "show_legend": False,
        "axes": {
            "category": {"kind": "text", "position": "bottom", "visible": True},
            "value": {
                "kind": "value",
                "position": "left",
                "visible": True,
                "minimum": 0,
                "maximum": axis_max,
                "major_unit": axis_max / 5,
                "major_gridlines": True,
            },
        },
        "style": {
            "font_family": "Microsoft YaHei",
            "title_font_size": 24,
            "axis_font_size": 14,
            "colors": ["#2563EB"],
            "chart_area_fill": "#FFFFFF",
            "plot_area_fill": "#FFFFFF",
            "text_color": "#1E293B",
            "axis_color": "#64748B",
            "grid_color": "#CBD5E1",
        },
        "source": {
            "text": "Source: approved immutable fragments",
            "x": 140,
            "y": 604,
            "width": 900,
            "height": 28,
            "font_size": 12,
            "color": "#64748B",
        },
    }
    lines = [
        (
            '<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" '
            'viewBox="0 0 1280 720" data-pptx-page-role="content">'
        ),
        (
            '  <rect id="background" x="0" y="0" width="1280" height="720" '
            'fill="#F8FAFC" data-pptx-role="background"/>'
        ),
        '  <g id="page-content" data-pptx-bounds="72 56 1136 600">',
        (
            '    <text id="title" x="80" y="98" '
            'font-family="Microsoft YaHei, Arial, sans-serif" font-size="38" '
            f'font-weight="700" fill="#0F172A">{_text(slide.title)}</text>'
        ),
        (
            '    <text id="takeaway" x="80" y="148" '
            'font-family="Microsoft YaHei, Arial, sans-serif" font-size="19" '
            f'fill="#334155">{_text(slide.body[-1])}</text>'
        ),
        '    <g id="throughput-comparison" data-pptx-replace-with="chart">',
        '      <metadata type="application/json">',
        html.escape(json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))),
        "      </metadata>",
        (
            '      <rect id="chart-panel" x="120" y="180" width="1040" '
            'height="420" rx="12" fill="#FFFFFF" stroke="#CBD5E1"/>'
        ),
        '      <g id="throughput-comparison-chartArea">',
    ]
    for tick in range(6):
        value = axis_max * tick / 5
        y = y_max - (y_max - y_min) * tick / 5
        lines.extend(
            [
                (
                    f'        <line id="grid-{tick}" x1="{x_min:g}" y1="{y:g}" '
                    f'x2="{x_max:g}" y2="{y:g}" stroke="#E2E8F0" stroke-width="1"/>'
                ),
                (
                    f'        <text id="tick-{tick}" x="{x_min - 18:g}" y="{y + 5:g}" '
                    'text-anchor="end" font-family="Arial, sans-serif" font-size="14" '
                    f'fill="#64748B">{value:g}</text>'
                ),
            ]
        )
    lines.append(
        "        <!-- chart-plot-area: object=throughput-comparison | "
        f"{x_min:g},{y_min:g},{x_max:g},{y_max:g} -->"
    )
    for index, (label, value) in enumerate(chart):
        center = x_min + gap * (index + 0.5)
        height = (value / axis_max) * (y_max - y_min)
        y = y_max - height
        color = "#2563EB" if index == 0 else "#0F766E"
        lines.extend(
            [
                (
                    f'        <rect id="bar-{index}" x="{center - bar_width / 2:g}" '
                    f'y="{y:g}" width="{bar_width:g}" height="{height:g}" rx="6" '
                    f'fill="{color}"/>'
                ),
                (
                    f'        <text id="value-{index}" x="{center:g}" y="{y - 12:g}" '
                    'text-anchor="middle" font-family="Arial, sans-serif" font-size="18" '
                    f'font-weight="700" fill="#0F172A">{value:g} {_text(unit)}</text>'
                ),
                (
                    f'        <text id="label-{index}" x="{center:g}" y="590" '
                    'text-anchor="middle" font-family="Arial, sans-serif" font-size="16" '
                    f'fill="#334155">{_text(label)}</text>'
                ),
            ]
        )
    lines.extend(
        [
            "      </g>",
            "    </g>",
            "  </g>",
            (
                '  <text id="page-number" x="1190" y="676" text-anchor="end" '
                'font-family="Arial, sans-serif" font-size="15" fill="#64748B" '
                f'data-pptx-role="decoration">{slide.order + 1:02d}</text>'
            ),
            "</svg>",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def author_deck(
    deck: DeckPlan, project_dir: Path, *, cover_image_path: Path | None = None
) -> list[Path]:
    svg_dir = project_dir / "svg_output"
    svg_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for index, slide in enumerate(sorted(deck.slides, key=lambda item: item.order)):
        path = svg_dir / f"slide_{index + 1:02d}.svg"
        author_slide(slide, deck.title, index, path, cover_image_path=cover_image_path)
        paths.append(path)
    return paths
