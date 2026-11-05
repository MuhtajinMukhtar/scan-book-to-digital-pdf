#!/usr/bin/env python3
"""Reject 'pilot' PDFs that only reuse scanned-page images with searchable OCR.

Pilot output pages must be in the same order as the source indices given by
--source-pages, e.g. --source-pages 7,19,43,87,101. This is a technical guard,
not a substitute for visual/content/source fidelity review.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import fitz


def assess_pilot(
    source_pdf: Path,
    pilot_pdf: Path,
    source_pages: list[int],
    min_typeset: int = 2,
    min_visible_chars: int = 70,
    max_image_coverage: float = 0.82,
) -> dict:
    issues: list[dict] = []
    rows = []
    source = fitz.open(source_pdf)
    pilot = fitz.open(pilot_pdf)
    try:
        if not source_pages or len(source_pages) != len(set(source_pages)):
            issues.append({"type": "missing_or_duplicate_source_page_mapping"})
        if len(pilot) != len(source_pages):
            issues.append({"type": "pilot_count_mapping_mismatch",
                           "pilot_pages": len(pilot), "mapped_pages": len(source_pages)})
        for pilot_i, source_i in enumerate(source_pages, start=1):
            if not 1 <= source_i <= len(source):
                issues.append({"type": "source_page_out_of_range", "source_page": source_i})
                continue
            if pilot_i > len(pilot):
                continue
            orig = source[source_i - 1]
            page = pilot[pilot_i - 1]
            if abs(orig.rect.width - page.rect.width) > .5 or abs(orig.rect.height - page.rect.height) > .5:
                issues.append({"type": "page_geometry_changed", "source_page": source_i})
            visible = 0
            for trace in page.get_texttrace():
                if trace.get("type", 0) != 3 and float(trace.get("opacity", 1.0)) > .5:
                    visible += len(trace.get("chars", []))
            page_area = max(.01, page.rect.width * page.rect.height)
            image_boxes = [x.get("bbox") for x in page.get_image_info() if x.get("bbox")]
            image_coverage_sum = 0.0
            largest_image_ratio = 0.0
            for coords in image_boxes:
                bbox = fitz.Rect(coords) & page.rect
                if bbox.is_empty:
                    continue
                ratio = bbox.get_area() / page_area
                largest_image_ratio = max(largest_image_ratio, ratio)
                image_coverage_sum += ratio
            # A full-page scan may be tiled; sum clipped at one. This errs on
            # the side of requesting visual inspection, rather than auto-pass.
            image_coverage_sum = min(1.0, image_coverage_sum)
            real_typeset = (
                visible >= min_visible_chars
                and largest_image_ratio < max_image_coverage
                and image_coverage_sum < max_image_coverage
            )
            if largest_image_ratio >= max_image_coverage or image_coverage_sum >= max_image_coverage:
                issues.append({"type": "scan_image_dominates_page", "source_page": source_i,
                               "largest_image_ratio": round(largest_image_ratio, 3),
                               "image_coverage_sum": round(image_coverage_sum, 3)})
            if not real_typeset:
                issues.append({"type": "not_verified_as_visible_typeset_page",
                               "source_page": source_i, "visible_text_chars": visible})
            rows.append({
                "source_page": source_i, "pilot_page": pilot_i,
                "visible_vector_text_chars": visible,
                "largest_image_ratio": round(largest_image_ratio, 3),
                "image_coverage_sum": round(image_coverage_sum, 3),
                "real_typeset_candidate": real_typeset,
                "fonts": sorted({x[3] for x in page.get_fonts(full=True)}),
            })
        typeset = sum(bool(p.get("real_typeset_candidate")) for p in rows)
        if typeset < min_typeset:
            issues.append({"type": "insufficient_real_typeset_samples",
                           "required": min_typeset, "observed": typeset})
        return {
            "status": "PASS_NEEDS_EDITORIAL_REVIEW" if not issues else "FAIL_NOT_DIGITALLY_TYPESET_PILOT",
            "source_pages": len(source), "pilot_pages": len(pilot),
            "real_typeset_sample_pages": typeset,
            "page_data": rows, "issues": issues,
            "limitations": "Detects image-dominant/hidden-OCR samples and checks page mapping. "
                           "Not proof of correct OCR, page text equality, style, font authenticity "
                           "or visual source fidelity. Humans must compare both PDFs.",
        }
    finally:
        source.close()
        pilot.close()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--pilot", type=Path, required=True)
    p.add_argument("--source-pages", required=True, help="1-based original PDF pages in pilot output order: 7,19,42")
    p.add_argument("--json", type=Path, required=True)
    p.add_argument("--min-typeset", type=int, default=2)
    p.add_argument("--min-visible-chars", type=int, default=70)
    args = p.parse_args()
    if args.min_typeset < 1 or args.min_visible_chars < 1:
        p.error("Minimum sample and visible text counts must be positive")
    for file in (args.source, args.pilot):
        if not file.is_file():
            p.error(f"Missing input file: {file}")
    try:
        src = [int(x.strip()) for x in args.source_pages.split(",")]
        result = assess_pilot(args.source, args.pilot, src, args.min_typeset, args.min_visible_chars)
    except (ValueError, fitz.FileDataError) as exc:
        p.error(str(exc))
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "real_typeset_samples": result["real_typeset_sample_pages"],
                      "total_pilot_pages": result["pilot_pages"], "report": str(args.json)}, ensure_ascii=False))
    return 0 if result["status"] == "PASS_NEEDS_EDITORIAL_REVIEW" else 2


if __name__ == "__main__":
    sys.exit(main())
