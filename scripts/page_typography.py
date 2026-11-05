"""Source-anchored paragraph layout with explicit, source-verified italic spans.

Apple Vision does not produce reliable font-style tags. Never guess italics
from word meaning; a reviewed per-page style file supplies those spans.
"""
from __future__ import annotations

import re
import statistics

def footer_number(item: dict) -> bool:
    text = str(item.get("text", "")).strip()
    return bool(
        re.fullmatch(r"\d{1,4}|[ivxlcdmIVXLCDM]{1,8}", text)
        and float(item["y"]) >= .875
        and (float(item["x"]) < .27 or float(item["x"]) > .67)
    )

def split_footer(lines: list[dict]) -> tuple[list[dict], list[dict]]:
    return ([line for line in lines if not footer_number(line)],
            [line for line in lines if footer_number(line)])

def _body_leading(y_positions: list[float], font_size: float) -> float:
    """Choose a single page-wide prose leading, ignoring paragraph gaps.

    Source/OCR boxes can jitter vertically by several points. Estimating one
    step *per paragraph* amplified that noise into inconsistent line spacing.
    """
    gaps = sorted(
        b - a for a, b in zip(y_positions, y_positions[1:])
        if font_size * .70 <= b - a <= font_size * 2.9
    )
    if not gaps:
        return font_size * 1.40
    # Lowest 70% excludes larger inter-paragraph and heading separations.
    normal_count = max(1, (len(gaps) * 7 + 9) // 10)
    ordinary = gaps[:normal_count]
    estimate = statistics.median(ordinary)
    return max(font_size * 1.14, min(font_size * 1.85, estimate))


def _dominant_left(xs: list[float], font_size: float) -> tuple[float, int]:
    """Robust body margin based on a majority of line starts, not max spread.

    One OCR outlier must not disable *all* alignment in a paragraph.
    The best cluster is a group of line starts within about half an em.
    """
    tolerance = max(3.5, font_size * .60)
    clusters = [
        [x for x in xs if abs(x - center) <= tolerance]
        for center in xs
    ]
    best = max(clusters, key=lambda group: (
        len(group),
        -(max(group) - min(group)),
        -statistics.median(group),
    ))
    return statistics.median(best), len(best)


def plan_body(body: list[dict], width: float, height: float, font_size: float) -> list[dict]:
    """Retype on the original page with consistent prose leading and margins.

    Preserve source paragraph breaks, true first-line indentation and unusual
    centered/list layouts. Only fix small/isolated OCR x-coordinate errors in a
    paragraph with a clear majority left edge. Never reflow onto the next page.
    """
    if not body:
        return []
    ordered = sorted(body, key=lambda item: (round(float(item["y"]), 4), float(item["x"])))
    ys = [float(line["y"]) * height for line in ordered]
    leading = _body_leading(ys, font_size)
    groups: list[list[dict]] = [[]]
    for index, line in enumerate(ordered):
        if index:
            gap = ys[index] - ys[index - 1]
            if (gap > max(leading * 1.46, font_size * 1.78)
                    or gap < font_size * .66):
                groups.append([])
        groups[-1].append(line)

    positions: list[dict] = []
    for group_index, group in enumerate(groups):
        source_top = [float(item["y"]) * height for item in group]
        xs = [float(item["x"]) * width for item in group]
        text_lengths = [len(str(item.get("text", "")).strip()) for item in group]
        prose = len(group) >= 3 and sum(n >= 22 for n in text_lengths) >= 2
        anchor, support = _dominant_left(xs, font_size)
        # A centred multi-line quote/title often has different left edges
        # precisely because the widths differ. Respect that source geometry.
        centers = [(x + float(item["width"]) * width / 2)
                   for x, item in zip(xs, group)]
        likely_centered = (
            max(xs) - min(xs) > font_size * 1.10
            and max(centers) - min(centers) < font_size * .8
        )
        consensus = (
            prose and not likely_centered
            and support >= max(2, (len(xs) + 1) // 2)
        )

        for j, item in enumerate(group):
            source_x = xs[j]
            draw_x = source_x
            if consensus:
                difference = source_x - anchor
                if j == 0:
                    # The first line may intentionally be indented one or two
                    # ems. Only remove sub-half-em OCR jitter on that line.
                    if abs(difference) <= font_size * .45:
                        draw_x = anchor
                elif abs(difference) <= font_size * 2.25:
                    # A very short, visibly indented final line may be part
                    # of a source quote or signature rather than left prose.
                    is_special_last_line = (
                        j == len(group) - 1
                        and text_lengths[j] < max(text_lengths) * .42
                        and difference > font_size * .85
                    )
                    if not is_special_last_line:
                        draw_x = anchor

            # All ordinary paragraphs share page-wide leading. A one-line
            # paragraph keeps its original source y-position.
            baseline = source_top[0] + font_size * .89 + j * leading
            positions.append({
                **item,
                "draw_x": draw_x,
                "baseline": baseline,
                "paragraph_index": group_index,
                "paragraph_last": j == len(group) - 1,
                "paragraph_line_count": len(group),
                "line_step": round(leading, 3),
                "alignment_corrected": abs(draw_x - source_x) > .5,
            })

    for i, item in enumerate(positions):
        if item["draw_x"] < 4 or item["baseline"] > height - 15:
            raise ValueError("Text line would leave original source page")
        if i and item["baseline"] - positions[i-1]["baseline"] < font_size * .89:
            raise ValueError("Paragraph spacing would overlap neighboring lines")
    return positions


def verified_italics(annotations: dict, source_page: int) -> list[str]:
    entry = annotations.get("pages", {}).get(str(source_page), {})
    spans = entry.get("italic_spans", [])
    phrases = []
    for span in spans:
        if span.get("source_scan_verified") is not True or not span.get("text"):
            raise ValueError("Italic annotation requires exact source-verified text")
        phrases.append(str(span["text"]))
    return phrases

def styled_tokens(text: str, italic_phrases: list[str]) -> list[tuple[str,bool]]:
    spans: list[tuple[int,int]] = []
    for phrase in italic_phrases:
        start = 0
        while True:
            pos = text.find(phrase, start)
            if pos < 0:
                break
            spans.append((pos,pos+len(phrase)))
            start=pos+len(phrase)
    result=[]
    for m in re.finditer(r"\S+|\s+",text):
        chunk=m.group(0)
        is_italic = not chunk.isspace() and any(a <= m.start() and b >= m.end()
                    or a < m.end() and b > m.start() for a,b in spans)
        result.append((chunk,is_italic))
    return result
