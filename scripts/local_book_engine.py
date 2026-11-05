#!/usr/bin/env python3
"""Deterministic, low-token first-pass book composer from cached OCR.

This engine does not call an LLM or run heavyweight OCR. It consumes the
Apple-Vision cache and PaddleOCR fusion report already produced by
mac_hybrid_ocr.py, renders conservative text-only pages as visible PDF text,
and preserves complicated pages as searchable scans with explicit QA flags.

No output is accepted as editorially verified without source-page review.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import statistics
import sys

import fitz
from PIL import Image, ImageDraw


def sha256(path: Path) -> str:
    with path.open("rb") as fh:
        return hashlib.file_digest(fh, "sha256").hexdigest()


def word_counts(text: str) -> Counter[str]:
    return Counter(re.findall(r"[^\W_]+(?:['’-][^\W_]+)*", text.casefold()))


def font_path(family: str, explicit: str | None = None) -> Path:
    if explicit:
        result = Path(explicit).expanduser()
        if not result.is_file():
            raise ValueError(f"Font file unavailable: {result}")
        return result
    serif = [
        "/System/Library/Fonts/Supplemental/Georgia.ttf",
        "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSerif-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    ]
    sans = [
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Verdana.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in serif if family == "serif" else sans:
        if Path(path).is_file():
            return Path(path)
    raise ValueError("No usable local font; provide --font-file. Do not download licensed fonts.")


def parse_pages(spec: str, count: int, mode: str) -> list[int]:
    if spec == "auto":
        if mode == "full":
            return list(range(1, count + 1))
        # Two-page low-cost pilot: deliberately does not trigger a whole-book OCR.
        picks = [max(3, round(count * .08)), max(4, round(count * .40))]
        if picks[0] == picks[1]:
            picks[1] = min(count, picks[0] + 1)
        return sorted({min(count, n) for n in picks})
    pages = [int(token.strip()) for token in spec.split(",") if token.strip()]
    if not pages or len(set(pages)) != len(pages) or min(pages) < 1 or max(pages) > count:
        raise ValueError("Invalid or repeated source page mapping")
    if mode == "full" and pages != list(range(1, count + 1)):
        raise ValueError("Full mode requires all source pages in exact physical order")
    return pages


def load_cache(work: Path, number: int, source_sha: str, require_hybrid: bool) -> tuple[dict, list[dict]]:
    file = work / "ocr" / f"page_{number:03d}.json"
    if not file.is_file():
        raise ValueError(f"Missing cached Apple Vision OCR for source page {number}")
    data = json.loads(file.read_text(encoding="utf-8"))
    if data.get("page") != number or data.get("source_sha256") != source_sha:
        raise ValueError(f"OCR identity/source hash mismatch on page {number}")
    if data.get("engine") not in ("apple-vision", "tesseract"):
        raise ValueError(f"Unsupported OCR engine on page {number}: {data.get('engine')}")
    if require_hybrid and data["engine"] != "apple-vision":
        raise ValueError(f"Apple Vision missing on page {number}: no false hybrid claims")
    fusion_file = work / "fusion" / f"page_{number:03d}.json"
    if require_hybrid and not fusion_file.exists():
        raise ValueError(f"Paddle comparison absent on page {number}")
    issues = []
    if fusion_file.exists():
        fused = json.loads(fusion_file.read_text(encoding="utf-8"))
        if fused.get("page") != number or fused.get("source_sha256") != source_sha:
            raise ValueError(f"Fusion identity/source mismatch on page {number}")
        issues = fused.get("issues", [])
    return data, issues


def usable_lines(cache: dict) -> list[dict]:
    result = []
    for item in cache.get("lines", []):
        try:
            text = str(item.get("text", "")).strip()
            x, y, w, h = (float(item[k]) for k in ("x", "y", "width", "height"))
            if not text:
                continue
            if not (0 <= x <= 1 and 0 <= y <= 1 and 0 < w <= 1 and 0 < h <= 1):
                raise ValueError("bad box")
            if x + w > 1.05 or y + h > 1.05:
                raise ValueError("box beyond page")
            result.append({"text": text, "x": x, "y": y, "width": w, "height": h})
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Invalid OCR line rectangle; review source before generating output") from exc
    return sorted(result, key=lambda it: (round(it["y"], 3), it["x"]))


def recommended_size(records: list[tuple[fitz.Rect, list[dict]]], font: fitz.Font) -> float:
    # Estimate one common body size for all selected pages; never auto-resize each line.
    hvalues: list[float] = []
    widths: list[float] = []
    for bounds, lines in records:
        for ln in lines:
            if ln["y"] < .045 or ln["y"] > .95:
                continue
            hvalues.append(bounds.height * ln["height"])
            if len(ln["text"]) >= 22:
                length = font.text_length(ln["text"], fontsize=1)
                available = max(1, min(bounds.width - 28 - ln["x"] * bounds.width,
                                       ln["width"] * bounds.width + 26))
                if length:
                    widths.append(available / length)
    if not hvalues:
        return 13.5
    height_estimate = statistics.median(hvalues) * 1.10
    width_estimate = sorted(widths)[max(0, int(len(widths) * .15) - 1)] if widths else 15.0
    return round(max(9, min(17, height_estimate, width_estimate)), 1)


def unrecognized_ink(source_page: fitz.Page, lines: list[dict]) -> float:
    """Conservative low-res heuristic: suspicious non-OCR dark pixels => fallback.

    Does NOT try to infer that an image is safe to discard.
    """
    pix = source_page.get_pixmap(matrix=fitz.Matrix(.5, .5), colorspace=fitz.csGRAY, alpha=False)
    im = Image.frombytes("L", (pix.width, pix.height), pix.samples)
    draw = ImageDraw.Draw(im)
    for item in lines:
        # Cover recognized text with a few pixels of tolerance.
        box = [int(item["x"] * pix.width) - 3, int(item["y"] * pix.height) - 3,
               int((item["x"] + item["width"]) * pix.width) + 3,
               int((item["y"] + item["height"]) * pix.height) + 3]
        draw.rectangle(box, fill=255)
    center = im.crop((int(pix.width * .07), int(pix.height * .055),
                      int(pix.width * .93), int(pix.height * .925)))
    pixels = center.histogram()
    area = max(1, center.width * center.height)
    dark = sum(pixels[:135]) / area
    midtone = sum(pixels[:185]) / area
    return max(dark / .008, midtone / .035)


def add_hidden_ocr(page: fitz.Page, lines: list[dict], bounds: fitz.Rect) -> None:
    for item in lines:
        x = max(2, bounds.width * item["x"])
        y = max(7, bounds.height * (item["y"] + item["height"]))
        try:
            page.insert_text((x, y), item["text"], fontsize=9, fontname="helv",
                             render_mode=3, overlay=True)
        except Exception:
            # Record text failure via extraction check. The original remains visible.
            pass


def typeset_page(out: fitz.Document, original: fitz.Document, idx: int, lines: list[dict],
                 fontfile: Path, font: fitz.Font, size: float, keep_footer: bool) -> tuple[bool, str]:
    src = original[idx]
    page = out.new_page(width=src.rect.width, height=src.rect.height)
    font_name = "BookBody"
    page.insert_font(fontname=font_name, fontfile=str(fontfile))
    previous_y = -100.0
    for line in lines:
        text = line["text"]
        x = src.rect.width * line["x"]
        top = src.rect.height * line["y"]
        bottom = src.rect.height * (line["y"] + line["height"])
        baseline = top + size * .89
        if (x < 4 or baseline > src.rect.height - 16 or top < -1
                or baseline - previous_y < size * .88):
            return False, "line bounds or overlap"
        actual = font.text_length(text, fontsize=size)
        maxwidth = src.rect.width - max(24, src.rect.width * .055) - x
        if actual > maxwidth + 1.5:
            return False, "line would overflow at locked font size"
        # This is a first-pass, source-anchored typesetting. It intentionally does
        # not hallucinate italics/paragraph boundaries from OCR geometry alone.
        page.insert_text((x, baseline), text, fontname=font_name, fontsize=size,
                         color=(.17, .19, .18), overlay=True)
        previous_y = baseline
    if keep_footer and src.rect.height > 100:
        clip = fitz.Rect(0, src.rect.height - 36, src.rect.width, src.rect.height)
        page.show_pdf_page(clip, original, idx, clip=clip, overlay=False,
                           keep_proportion=False)
    generated = word_counts(page.get_text("text"))
    expected = word_counts(" ".join(ln["text"] for ln in lines))
    if expected - generated:
        return False, "OCR text lost in generated text layer"
    visible = sum(len(x.get("chars", [])) for x in page.get_texttrace() if x.get("type") != 3)
    if visible < 65:
        return False, "insufficient visible vector text"
    return True, ""


def fallback_page(out: fitz.Document, original: fitz.Document, idx: int, lines: list[dict]) -> None:
    src = original[idx]
    page = out.new_page(width=src.rect.width, height=src.rect.height)
    page.show_pdf_page(page.rect, original, idx, overlay=False)
    add_hidden_ocr(page, lines, src.rect)


def build(source: Path, work: Path, dest: Path, mode: str, page_list: list[int],
          family: str, fontfile: Path, font_size: float | None,
          keep_footer: bool = True, strict_hybrid: bool = True,
          approval: Path | None = None) -> dict:
    source_sha = sha256(source)
    if source.resolve() == dest.resolve():
        raise ValueError("Output must never overwrite the source")
    report_path = dest.with_suffix(".qa.json")
    if mode == "full":
        if not approval or not approval.is_file():
            raise ValueError("Full book blocked: explicit pilot approval record missing")
        evidence = json.loads(approval.read_text(encoding="utf-8"))
        if evidence.get("source_sha256") != source_sha or evidence.get("decision") != "PILOT_APPROVED":
            raise ValueError("Approval is missing, invalid, or for another scanned book")
        style_file = work / "pilot" / "style-profile.json"
        if not style_file.is_file() or evidence.get("style_profile_sha256") != sha256(style_file):
            raise ValueError("Approval does not match frozen pilot typography profile")
        style = json.loads(style_file.read_text(encoding="utf-8"))
        if style.get("body_font_size_pt") != font_size or style.get("font_file_sha256") != sha256(fontfile):
            raise ValueError("Body font or font size changed after pilot approval")
    doc = fitz.open(source)
    if mode == "full" and page_list != list(range(1, len(doc)+1)):
        raise ValueError("Cannot publish incomplete full-book page mapping")
    font = fitz.Font(fontfile=str(fontfile))
    data = []
    for num in page_list:
        cache, issues = load_cache(work, num, source_sha, require_hybrid=strict_hybrid)
        lines = usable_lines(cache)
        data.append((num, lines, issues))
    suggested = recommended_size([(doc[n-1].rect, lines) for n, lines, _ in data], font)
    size = suggested if font_size is None else font_size
    if not 7 <= size <= 24:
        raise ValueError("Unsupported body font size outside 7-24 pt")
    # Produce deterministic pages; page-level rollback leaves the source intact.
    temp = dest.with_suffix(".partial.pdf")
    output = fitz.open()
    rows = []
    for number, lines, issues in data:
        src = doc[number - 1]
        mode_name = "searchable_scan_fallback"
        reasons = []
        if len(lines) < 7:
            reasons.append("not enough recognized body lines")
        if issues:
            reasons.append("Apple/Paddle disagreement awaiting source review")
        ink_score = unrecognized_ink(src, lines)
        if ink_score > 1:
            reasons.append("graphic, decoration, or unrecognized text risk")
        if not reasons:
            ok, reason = typeset_page(output, doc, number - 1, lines, fontfile, font, size, keep_footer)
            if ok:
                mode_name = "born_digital_unverified"
            else:
                reasons.append(reason)
                output.delete_page(len(output) - 1)
        if reasons:
            fallback_page(output, doc, number - 1, lines)
        rows.append({"source_page": number, "output_page": len(output),
                     "mode": mode_name, "ocr_issues": len(issues),
                     "detected_nontext_ink_score": round(ink_score, 3),
                     "reasons": reasons})
    dest.parent.mkdir(parents=True, exist_ok=True)
    output.save(temp, garbage=3, deflate=True)
    output.close()
    reread = fitz.open(temp)
    if len(reread) != len(page_list):
        raise RuntimeError("Output page count incorrect, preserving partial for inspection")
    for k, page_num in enumerate(page_list):
        if abs(reread[k].rect.width-doc[page_num-1].rect.width) > .5 or abs(reread[k].rect.height-doc[page_num-1].rect.height) > .5:
            raise RuntimeError("Output page dimensions changed, preserving partial")
    reread.close()
    if sha256(source) != source_sha:
        raise RuntimeError("Source modified during build")
    temp.replace(dest)
    counts = Counter(row["mode"] for row in rows)
    report = {"status": "REVIEW_REQUIRED", "note": "Not an editorial fidelity certification.",
              "source_sha256": source_sha, "source_page_count": len(doc),
              "output_page_count": len(page_list), "mapping": page_list,
              "font_family": family, "font_file_name": fontfile.name,
              "body_font_size_pt": size, "digital_pages": counts["born_digital_unverified"],
              "fallback_pages": counts["searchable_scan_fallback"],
              "per_page": rows}
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    doc.close()
    return report


def comparison(source: Path, output: Path, page_numbers: list[int], dest: Path) -> None:
    before = fitz.open(source)
    after = fitz.open(output)
    target = fitz.open()
    for i, source_number in enumerate(page_numbers):
        original = before[source_number-1]
        result = after[i]
        w, h = original.rect.width, original.rect.height
        frame = target.new_page(width=2*w+24, height=h+32)
        a = fitz.Rect(0, 32, w, h+32)
        b = fitz.Rect(w+24, 32, 2*w+24, h+32)
        frame.show_pdf_page(a, before, source_number-1)
        frame.show_pdf_page(b, after, i)
        frame.insert_text((8, 20), f"SOURCE PAGE {source_number}", fontsize=10)
        frame.insert_text((w+32, 20), f"DIGITAL DRAFT {i+1}", fontsize=10)
    target.save(dest, garbage=3, deflate=True)
    target.close()
    after.close()
    before.close()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--work-dir", type=Path, required=True)
    p.add_argument("--mode", choices=["pilot", "full"], default="pilot")
    p.add_argument("--pages", default="auto", help="Pilot source pages: 18,19,74; 'auto' chooses two. Full mode requires all.")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--font-family", choices=["serif", "sans"], default="sans")
    p.add_argument("--font-file", default=None)
    p.add_argument("--font-size", type=float, help="Lock single body size across all pages, e.g. 14")
    p.add_argument("--approval", type=Path, help="User-approved pilot record required before full mode")
    p.add_argument("--allow-single-ocr", action="store_true", help="Testing only; never label as hybrid")
    p.add_argument("--no-footer-strip", action="store_true")
    a = p.parse_args()
    if not a.source.is_file():
        p.error("Source PDF missing")
    try:
        with fitz.open(a.source) as scanned:
            pages = parse_pages(a.pages, len(scanned), a.mode)
        path = font_path(a.font_family, a.font_file)
        report = build(a.source, a.work_dir, a.output, a.mode, pages, a.font_family,
                       path, a.font_size, keep_footer=not a.no_footer_strip,
                       strict_hybrid=not a.allow_single_ocr, approval=a.approval)
        if a.mode == "pilot":
            comparison(a.source, a.output, pages,
                       a.output.with_name(a.output.stem + "_Comparison.pdf"))
        print(json.dumps({k: v for k, v in report.items() if k != "per_page"},
                         ensure_ascii=False, indent=2))
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
