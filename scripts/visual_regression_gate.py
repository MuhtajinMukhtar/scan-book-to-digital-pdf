#!/usr/bin/env python3
"""Compare a newly generated *comparison PDF* to a previously preferred pilot.

This is a visual-regression smoke gate, not a book retypesetter. It measures
the digital panel (right half) only: text font size, text vertical footprint,
text quantity, and separate image asset coverage. It requires independently
verified source hash and page mapping. It does NOT assess OCR accuracy, table
text, paragraph structure, image pixel fidelity or user/editorial acceptance.

No PDFs or book text are committed to this public repository: a golden
baseline JSON contains only measured geometry and font statistics.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import fitz


def sha256(path: Path) -> str:
    with path.open("rb") as fp:
        return hashlib.file_digest(fp, "sha256").hexdigest()


def weighted_median(pairs: list[tuple[float, int]]) -> float:
    if not pairs:
        return 0.0
    total = sum(weight for _, weight in pairs)
    cumulative = 0
    for value, weight in sorted(pairs):
        cumulative += weight
        if cumulative * 2 >= total:
            return round(value, 2)
    return round(pairs[-1][0], 2)


def comparison_metrics(page: fitz.Page) -> dict:
    mid = page.rect.width / 2
    selected = []
    for block in page.get_text("dict")["blocks"]:
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                box = span["bbox"]
                content = span["text"].strip()
                if (box[0] > mid + 10 and box[1] > 39
                        and box[3] < page.rect.height - 45
                        and len(content) >= 3
                        and span["size"] >= 7):
                    selected.append(span)
    weights = [(round(item["size"], 2), len(item["text"].strip()))
               for item in selected]
    char_count = sum(len(item["text"].strip()) for item in selected)
    y0 = min((item["bbox"][1] for item in selected), default=0)
    y1 = max((item["bbox"][3] for item in selected), default=0)
    right = fitz.Rect(mid + 5, 30, page.rect.width, page.rect.height - 10)
    raster_coverage = 0.0
    for item in page.get_image_info():
        if not item.get("bbox"):
            continue
        clipped = fitz.Rect(item["bbox"]) & right
        if not clipped.is_empty:
            raster_coverage += clipped.get_area() / max(1.0, page.rect.get_area()/2)
    return {
        "median_font_pt": weighted_median(weights),
        "text_vertical_footprint": round((y1 - y0) / max(1, page.rect.height), 4),
        "extractable_char_count": char_count,
        "raster_area_fraction": round(min(1.0, raster_coverage), 4)
    }


def extract(pdf: Path, source_pages: list[int]) -> dict[str, dict]:
    with fitz.open(pdf) as doc:
        if len(doc) != len(source_pages):
            raise ValueError(f"Comparison has {len(doc)} pages but {len(source_pages)} source mappings")
        if len(set(source_pages)) != len(source_pages) or min(source_pages, default=0) < 1:
            raise ValueError("Source page numbers must be unique and positive")
        return {
            str(number): comparison_metrics(page)
            for page, number in zip(doc, source_pages)
        }


def verify(candidate: Path, baseline: dict, source: Path,
           source_pages: list[int] | None = None) -> dict:
    expected_sha = baseline.get("source_sha256")
    if not expected_sha or sha256(source) != expected_sha:
        raise ValueError("Original PDF checksum differs from golden visual reference")
    if baseline.get("schema_version") != 1 or baseline.get("format") != "side_by_side_comparison":
        raise ValueError("Unsupported golden baseline schema or PDF format")
    order = source_pages or baseline["source_page_order"]
    observed = extract(candidate, order)
    required = baseline["page_metrics"]
    issues = []
    evaluated = []
    for source_page in order:
        key = str(source_page)
        if key not in required:
            issues.append({"source_page": source_page, "issue": "no_golden_sample_for_this_page"})
            continue
        ref = required[key]
        now = observed[key]
        checked = [("font", "median_font_pt", .90),
                   ("vertical_text_extent", "text_vertical_footprint", .79),
                   ("extractable_text", "extractable_char_count", .95)]
        for label, metric, ratio in checked:
            previous = float(ref.get(metric, 0))
            actual = float(now.get(metric, 0))
            if previous > 0 and actual < previous * ratio:
                issues.append({
                    "source_page": source_page, "issue": f"{label}_regressed",
                    "previous": previous, "observed": actual,
                    "ratio": round(actual / previous, 3)
                })
        if ref.get("raster_area_fraction", 0) >= .075:
            previous = ref["raster_area_fraction"]
            actual = now["raster_area_fraction"]
            if actual < previous * .65:
                issues.append({
                    "source_page": source_page,
                    "issue": "illustration_or_graphic_area_lost",
                    "previous": previous, "observed": actual,
                    "ratio": round(actual / previous, 3)
                })
        evaluated.append(source_page)
    if len(evaluated) < len(required):
        missing = sorted(set(map(int, required)) - set(evaluated))
        issues.append({"issue": "golden_samples_missing_from_candidate",
                       "missing_source_pages": missing})
    return {
        "status": "PILOT_VISUAL_REGRESSION" if issues else "PASS_VISUAL_THRESHOLDS_ONLY",
        "original_source_sha256": expected_sha,
        "baseline_artifact_sha256": baseline.get("reference_comparison_sha256"),
        "candidate_sha256": sha256(candidate),
        "sampled_pages": evaluated,
        "issues": issues,
        "metrics": observed,
        "caveat": (
            "This gate only catches measurable font reduction, vertical compression, "
            "large asset loss and text-count changes. Passing does not prove the "
            "two pilots look alike; inspect every page side-by-side before approval."
        )
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--candidate-comparison", type=Path, required=True)
    p.add_argument("--baseline", type=Path, required=True)
    p.add_argument("--source-pages", help="Physical source pages in candidate order, comma-separated")
    p.add_argument("--json", type=Path, required=True)
    args = p.parse_args()
    if any(not path.is_file() for path in [args.source, args.candidate_comparison, args.baseline]):
        p.error("Source, candidate comparison and baseline JSON must all exist")
    try:
        golden = json.loads(args.baseline.read_text(encoding="utf-8"))
        order = ([int(x) for x in args.source_pages.split(",")]
                 if args.source_pages else None)
        report = verify(args.candidate_comparison, golden, args.source, order)
    except (ValueError, KeyError, TypeError, fitz.FileDataError) as exc:
        p.error(str(exc))
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                         encoding="utf-8")
    print(json.dumps({"status": report["status"], "issues": len(report["issues"]),
                      "report": str(args.json)}))
    return 2 if report["issues"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
