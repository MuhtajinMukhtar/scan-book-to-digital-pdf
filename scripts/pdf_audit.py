#!/usr/bin/env python3
"""Read-only, independent QA for a source-faithful digital book PDF.

Requirements: PyMuPDF (fitz). Works on Linux and macOS.
Usage: python pdf_audit.py book.pdf --baseline approved.pdf --json report.json
Optional: --source-ocr-dir work/ocr --strict --min-coverage 0.95
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
import re
import sys
from pathlib import Path

try:
    import fitz
except ImportError:
    raise SystemExit("PyMuPDF missing: install into an authorized isolated environment.")

def sha256(path: Path) -> str:
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()

def words_counter(text: str) -> collections.Counter[str]:
    # Unicode-aware word tokens; no lossy transliteration or stripping punctuation
    # from the actual output file (only for normalized coverage comparison).
    return collections.Counter(re.findall(r"[^\W_]+(?:['’-][^\W_]+)*", text.casefold(), re.UNICODE))

def ocr_words(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    lines = data.get("lines", [])
    accepted = []
    for z in lines:
        raw = z.get("text", "").strip()
        # Exclude only obvious folios/trademark running heads; do not drop
        # ambiguous '66' or Roman numerals without source verification.
        y = z.get("y")
        if y is not None and (float(y) < 0.10 or float(y) > 0.92):
            if re.fullmatch(r"(\d{1,4}|[ivxlcdm]{1,8})", raw, flags=re.I):
                continue
        if raw:
            accepted.append(raw)
    return words_counter(" ".join(accepted))

def compare_coverage(source: collections.Counter, generated: collections.Counter) -> float:
    count = sum(source.values())
    if count == 0:
        return 1.0
    return sum(min(v, generated.get(token, 0)) for token, v in source.items()) / count

def page_visible_text(page) -> bool:
    # Hidden OCR layers generally use text rendering mode 3. If the old PDF
    # omits this metadata, this is merely a heuristic; record as such.
    try:
        return any(
            x.get("type") != 3 and x.get("chars")
            for x in page.get_texttrace()
        )
    except Exception:
        return bool(page.get_text("text").strip())

def audit(pdf: Path, baseline: Path | None, ocr_dir: Path | None, threshold: float):
    d = fitz.open(pdf)
    old = fitz.open(baseline) if baseline else None
    result = {
        "input_pdf": str(pdf),
        "input_sha256": sha256(pdf),
        "pages": len(d),
        "baseline_sha256": sha256(baseline) if baseline else None,
        "baseline_pages": len(old) if old else None,
        "output_vs_baseline_changed_text_pages": [],
        "output_vs_baseline_changed_image_count_pages": [],
        "output_vs_baseline_changed_size_pages": [],
        "blank_pages": [],
        "out_of_bounds": [],
        "low_ocr_coverage": [],
        "fonts_used": {},
        "digital_text_pages_heuristic": [],
        "searchable_scan_pages_heuristic": [],
        "page_data": [],
    }
    all_fonts = collections.Counter()
    for i, page in enumerate(d, start=1):
        text = page.get_text("text")
        word_data = page.get_text("words")
        images = len(page.get_images(full=True))
        visible = page_visible_text(page)
        if not text.strip() and images == 0:
            result["blank_pages"].append(i)
        if text.strip():
            (result["digital_text_pages_heuristic"] if visible else
             result["searchable_scan_pages_heuristic"]).append(i)
        for word in word_data:
            x0, y0, x1, y1 = word[:4]
            if x0 < -1 or y0 < -1 or x1 > page.rect.width + 1 or y1 > page.rect.height + 1:
                result["out_of_bounds"].append({"page": i, "word": word[4][:60]})
        for f in page.get_fonts(full=True):
            all_fonts[f[3].split("+")[-1]] += 1
        info = {
            "page": i,
            "size_pt": [round(page.rect.width, 2), round(page.rect.height, 2)],
            "text_chars": len(text),
            "images": images,
            "text_appears_visible": visible,
        }
        if old and i <= len(old):
            ref = old[i-1]
            if text != ref.get_text("text"):
                result["output_vs_baseline_changed_text_pages"].append(i)
            if images != len(ref.get_images(full=True)):
                result["output_vs_baseline_changed_image_count_pages"].append(i)
            if page.rect != ref.rect:
                result["output_vs_baseline_changed_size_pages"].append(i)
        if ocr_dir:
            j = ocr_dir / f"page_{i:03d}.json"
            if j.exists():
                source = ocr_words(j)
                coverage = compare_coverage(source, words_counter(text))
                info["source_ocr_word_coverage"] = round(coverage, 5)
                if coverage < threshold:
                    result["low_ocr_coverage"].append({"page": i, "coverage": round(coverage, 5)})
            else:
                info["source_ocr_word_coverage"] = None
        result["page_data"].append(info)
    result["fonts_used"] = dict(all_fonts.most_common())
    result["pass_structural_qa"] = (
        len(result["blank_pages"]) == 0
        and len(result["out_of_bounds"]) == 0
        and (old is None or len(old) == len(d))
    )
    result["pass_ocr_threshold"] = not result["low_ocr_coverage"]
    return result

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("pdf", type=Path)
    p.add_argument("--baseline", type=Path)
    p.add_argument("--source-ocr-dir", type=Path)
    p.add_argument("--json", type=Path, dest="json_path")
    p.add_argument("--min-coverage", type=float, default=0.95)
    p.add_argument("--strict", action="store_true")
    args = p.parse_args()
    if not args.pdf.is_file():
        p.error("Input PDF not found")
    if args.baseline and not args.baseline.is_file():
        p.error("Baseline PDF not found")
    if not 0 <= args.min_coverage <= 1:
        p.error("min-coverage must be between 0 and 1")
    result = audit(args.pdf, args.baseline, args.source_ocr_dir, args.min_coverage)
    summary = {
        "pages": result["pages"],
        "blank": result["blank_pages"],
        "out_of_bounds": len(result["out_of_bounds"]),
        "changed_text_pages": result["output_vs_baseline_changed_text_pages"],
        "changed_image_count_pages": result["output_vs_baseline_changed_image_count_pages"],
        "low_source_ocr_coverage": result["low_ocr_coverage"][:12],
        "structural_pass": result["pass_structural_qa"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.json_path:
        args.json_path.parent.mkdir(parents=True, exist_ok=True)
        args.json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.strict and (not result["pass_structural_qa"] or not result["pass_ocr_threshold"]):
        return 2
    return 0

if __name__ == "__main__":
    sys.exit(main())
