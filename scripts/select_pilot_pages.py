#!/usr/bin/env python3
"""Cheap image-statistics selection of two text-heavy pilot pages.

No OCR, no language model, no network. Inspect only ~24 small PDF thumbnails,
not every full-resolution page. The selection is a heuristic and always
receives a subsequent human review of the original scans.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import fitz


def score_page(page: fitz.Page) -> dict:
    pix = page.get_pixmap(matrix=fitz.Matrix(.55, .55),
                          colorspace=fitz.csGRAY, alpha=False)
    w, h = pix.width, pix.height
    samples = memoryview(pix.samples)
    x0, x1 = int(w*.12), int(w*.88)
    y0, y1 = int(h*.08), int(h*.87)
    text_rows = []
    heavy = 0
    dark_pixels = 0
    for y in range(y0, y1):
        offset = y*w
        dark = sum(1 for x in range(x0, x1) if samples[offset+x] < 148)
        frac = dark / max(1, x1-x0)
        dark_pixels += dark
        if .045 <= frac <= .42:
            text_rows.append(y)
        if frac > .55:
            heavy += 1
    groups = 0
    last = -100
    for y in text_rows:
        if y - last > 2:
            groups += 1
        last = y
    ink_ratio = dark_pixels / max(1, (x1-x0)*(y1-y0))
    # Favor 15..55 horizontal text bands, not huge dark figures or blank pages.
    score = min(groups, 45) - max(0, groups-45)*.3 - 1.0*heavy - max(0, ink_ratio-.12)*100
    if groups < 12:
        score -= 22
    return {"text_row_groups": groups, "dense_rows": heavy,
            "ink_ratio": round(ink_ratio, 4), "score": round(score, 2)}


def candidate_numbers(count: int) -> list[int]:
    fractions = (.07, .10, .17, .22, .35, .41, .48, .57, .68, .81)
    choices = set()
    for f in fractions:
        mid = min(count, max(1, round(count*f)))
        for delta in (-1, 0, 1):
            value = mid+delta
            if 1 <= value <= count:
                choices.add(value)
    return sorted(choices)


def choose(source: Path, count: int = 2) -> dict:
    with fitz.open(source) as doc:
        candidates = []
        for number in candidate_numbers(len(doc)):
            try:
                metrics = score_page(doc[number-1])
                candidates.append({"source_page": number, **metrics})
            except (ValueError, RuntimeError):
                continue
        if not candidates:
            raise ValueError("Unable to survey scanned pages")
        # Different parts of book, with representative text-heavy content.
        split = max(1, len(doc)//2)
        early = sorted((v for v in candidates if v["source_page"] <= split),
                       key=lambda row: (-row["score"], row["source_page"]))
        late = sorted((v for v in candidates if v["source_page"] > split),
                      key=lambda row: (-row["score"], row["source_page"]))
        chosen = []
        for group in (early, late):
            if group and len(chosen) < count:
                chosen.append(group[0]["source_page"])
        if len(chosen) < count:
            for row in sorted(candidates, key=lambda row: -row["score"]):
                if row["source_page"] not in chosen:
                    chosen.append(row["source_page"])
                if len(chosen) >= count:
                    break
        if len(chosen) < count:
            raise ValueError("Fewer than two unique pages in source")
        return {"pages": sorted(chosen),
                "method": "low-resolution thumbnail text-density heuristic",
                "candidate_pages_surveyed": len(candidates),
                "selected_metrics": [x for x in candidates if x["source_page"] in chosen]}


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("source", type=Path)
    p.add_argument("--count", type=int, default=2)
    a=p.parse_args()
    if not a.source.is_file():
        p.error("Source PDF not found")
    if a.count != 2:
        p.error("Initial low-cost pilot must contain exactly 2 pages")
    print(json.dumps(choose(a.source, a.count), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
