"""Conservative typography detection from a scanned book's own OCR geometry.

This module does not read earlier pilots or use book-specific constants. It
looks only at source-matching Apple Vision line boxes in selected pages and
returns a small JSON-serializable style profile to lock after pilot approval.

Uncertain alignment defaults to natural left spacing, never forced justification.
"""
from __future__ import annotations

import statistics

CREAM_RGB = (0.985, 0.977, 0.955)  # very light warm paper
WHITE_RGB = (1.0, 1.0, 1.0)


def palette(background: str) -> tuple[float, float, float]:
    if background == "cream":
        return CREAM_RGB
    if background == "white":
        return WHITE_RGB
    raise ValueError("Background must be cream or white")


def _median(values: list[float], fallback: float) -> float:
    return statistics.median(values) if values else fallback


def observe_page(lines: list[dict], page_width: float, page_height: float) -> dict | None:
    """Read only obvious prose lines, preserving unusual page designs as exceptions."""
    eligible = sorted(
        (line for line in lines
         if len(str(line.get("text", "")).strip()) >= 22
         and .085 <= float(line["y"]) <= .87
         and .055 <= float(line["x"]) <= .92
         and .06 <= float(line["width"]) <= .88),
        key=lambda line: (float(line["y"]), float(line["x"]))
    )
    if len(eligible) < 9:
        return None
    ys = [float(row["y"]) * page_height for row in eligible]
    candidates = sorted(
        b - a for a,b in zip(ys, ys[1:])
        if 6 < b - a < min(42, page_height * .055)
    )
    if len(candidates) < 5:
        return None
    leading = statistics.median(candidates[:max(3, len(candidates) * 3 // 4)])
    groups = [[]]
    for i, line in enumerate(eligible):
        if i and ys[i] - ys[i-1] > leading * 1.53:
            groups.append([])
        groups[-1].append(line)
    prose_groups = [g for g in groups if len(g) >= 3]
    if not prose_groups:
        return None
    nonfinal = [
        float(row["x"]) + float(row["width"])
        for group in prose_groups for row in group[:-1]
    ]
    if len(nonfinal) < 5:
        return None
    right = _median(nonfinal, .88)
    near = sum(abs(edge - right) <= .018 for edge in nonfinal) / len(nonfinal)
    spread = (sorted(nonfinal)[int((len(nonfinal) - 1) * .90)] -
              sorted(nonfinal)[int((len(nonfinal) - 1) * .10)])
    if near >= .78 and spread < .043:
        alignment = "justify"
    elif near <= .58 and spread >= .035:
        alignment = "left"
    else:
        alignment = "uncertain"
    xs = [float(line["x"]) for g in prose_groups for line in g[1:]]
    left = _median(xs, .12)
    # Exclude paragraph-last short lines from the measured body right boundary.
    leading_gaps = [
        ys[i] - ys[i-1] for i in range(1, len(ys))
        if leading * 1.45 < ys[i] - ys[i-1] < leading * 2.8
    ]
    return {
        "alignment": alignment,
        "line_count": sum(len(g) for g in prose_groups),
        "left": round(left, 4),
        "right": round(right, 4),
        "leading_pt": round(leading, 2),
        "paragraph_gap_pt": round(_median(leading_gaps, leading * 1.55), 2),
        "right_edge_near_fraction": round(near, 3),
    }


def infer_style(records: list[tuple[int, object, list[dict]]],
                background: str = "cream") -> dict:
    """Lock one book-level body style; do not pretend to identify decorative pages."""
    palette(background)
    observations = []
    for number, bounds, lines in records:
        observed = observe_page(lines, bounds.width, bounds.height)
        if observed is not None:
            observations.append((number, observed))
    left_votes = sum(x["alignment"] == "left" for _, x in observations)
    justified_votes = sum(x["alignment"] == "justify" for _, x in observations)
    # A multi-page consensus is required for justification, else keep natural
    # word spacing and mark ambiguous layouts for source visual review.
    if justified_votes >= 2 and justified_votes >= max(2, left_votes * 2):
        alignment = "justify"
    elif left_votes >= 2 and left_votes >= justified_votes:
        alignment = "left"
    else:
        alignment = "source_uncertain"  # render naturally left until visually confirmed
    lefts = [x["left"] for _, x in observations]
    rights = [x["right"] for _, x in observations]
    step = [x["leading_pt"] for _, x in observations]
    gaps = [x["paragraph_gap_pt"] for _, x in observations]
    return {
        "alignment": alignment,
        "background": background,
        "margin_left_ratio": round(_median(lefts, .12), 4),
        "margin_right_ratio": round(1 - _median(rights, .88), 4),
        "leading_pt": round(_median(step, 19.0), 2),
        "paragraph_gap_pt": round(_median(gaps, 28.0), 2),
        "pages_observed": len(observations),
        "justified_votes": justified_votes,
        "left_votes": left_votes,
        "source_review_required": alignment == "source_uncertain",
        "note": "Source-derived prose heuristic; manually verify body alignment in actual scan. "
                "Complex pages are not forced to this body style.",
    }


def validate_style(style: dict) -> None:
    if style.get("alignment") not in ("left", "justify", "source_uncertain"):
        raise ValueError("Invalid source alignment in locked style")
    palette(style.get("background"))
    for key in ("margin_left_ratio", "margin_right_ratio"):
        val = style.get(key)
        if not isinstance(val, (int, float)) or not .035 <= val <= .32:
            raise ValueError("Invalid book body margin ratio: " + key)
    if style["margin_left_ratio"] + style["margin_right_ratio"] >= .65:
        raise ValueError("Book margins leave insufficient body width")
    for key in ("leading_pt", "paragraph_gap_pt"):
        if not isinstance(style.get(key), (int, float)) or not 5 <= style[key] <= 80:
            raise ValueError("Invalid book spacing: " + key)


def source_verified_override(detected: dict, override: dict, source_sha: str) -> dict:
    """Allow a visually verified exception without guessing from OCR geometry.

    A nontechnical user never needs to write this file: an agent may record
    what it actually saw on the *current* book's original scanned pages.
    """
    if override.get("source_sha256") != source_sha:
        raise ValueError("Book style override belongs to another source PDF")
    if override.get("source_scan_verified") is not True:
        raise ValueError("Book style override requires source visual verification")
    alignment = override.get("alignment")
    if alignment not in ("left", "justify"):
        raise ValueError("Verified override must explicitly choose left or justify")
    updated=dict(detected)
    updated["alignment"]=alignment
    updated["source_review_required"]=False
    updated["visual_review_override"]=True
    for key in ("margin_left_ratio","margin_right_ratio",
                "leading_pt","paragraph_gap_pt"):
        if key in override:
            updated[key]=override[key]
    validate_style(updated)
    return updated
