#!/usr/bin/env python3
"""Deterministic, low-token first-pass book composer from cached OCR.

This engine does not call an LLM or run heavyweight OCR. It consumes the
Apple Vision cache and optional selective PP-OCRv5 Mobile review, renders conservative text-only pages as visible PDF text,
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
from page_typography import (split_footer, plan_body, verified_italics,
                             verified_bolds, styled_runs)
from book_style import infer_style, validate_style, palette, source_verified_override
from book_page_size import (canonical_page_size, normalized_copy,
                            all_pages_uniform, verify_uniform_pdf)


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


def load_cache(work: Path, number: int, source_sha: str, require_hybrid: bool, fusion_subdir: str = "fusion") -> tuple[dict, list[dict]]:
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
    fusion_file = work / fusion_subdir / f"page_{number:03d}.json"
    if require_hybrid and not fusion_file.exists():
        raise ValueError(f"Paddle comparison absent on page {number}")
    issues = []
    if fusion_file.exists():
        fused = json.loads(fusion_file.read_text(encoding="utf-8"))
        if fused.get("page") != number or fused.get("source_sha256") != source_sha:
            raise ValueError(f"Fusion identity/source mismatch on page {number}")
        if fusion_subdir == "fusion_mobile" and (
            fused.get("primary_engine") != "apple-vision" or
            fused.get("secondary_engine") != "paddle-ppocrv5-mobile"
        ):
            raise ValueError(f"Selective OCR evidence must be Apple Vision + Paddle Mobile on page {number}")
        if fusion_subdir == "fusion_safe" and (
            fused.get("primary_engine") != "apple-vision" or
            fused.get("secondary_engine") != "tesseract"
        ):
            raise ValueError(f"Safe OCR evidence is not Apple Vision + Tesseract on page {number}")
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


def italic_font_file(regular: Path) -> Path | None:
    variants = {
        "Arial.ttf": "Arial Italic.ttf",
        "Georgia.ttf": "Georgia Italic.ttf",
        "Times New Roman.ttf": "Times New Roman Italic.ttf",
        "DejaVuSans.ttf": "DejaVuSans-Oblique.ttf",
        "DejaVuSerif.ttf": "DejaVuSerif-Italic.ttf",
    }
    candidates = []
    if regular.name in variants:
        candidates.append(regular.with_name(variants[regular.name]))
    if "-Regular" in regular.name:
        candidates.append(regular.with_name(regular.name.replace("-Regular", "-Italic")))
    candidates.append(regular.with_name(regular.stem + "-Italic" + regular.suffix))
    # Never silently treat the upright font as its own italic variant.
    return next((candidate for candidate in candidates
                 if candidate != regular and candidate.is_file()), None)


def styled_font_file(regular: Path, kind: str) -> Path | None:
    """Look for a *real* matching local bold or bold-italic file."""
    if kind not in ("bold", "bold_italic"):
        raise ValueError("Invalid styled font variant")
    names = {
        "Arial.ttf": ("Arial Bold.ttf", "Arial Bold Italic.ttf"),
        "Georgia.ttf": ("Georgia Bold.ttf", "Georgia Bold Italic.ttf"),
        "Times New Roman.ttf": ("Times New Roman Bold.ttf", "Times New Roman Bold Italic.ttf"),
        "DejaVuSans.ttf": ("DejaVuSans-Bold.ttf", "DejaVuSans-BoldOblique.ttf"),
        "DejaVuSerif.ttf": ("DejaVuSerif-Bold.ttf", "DejaVuSerif-BoldItalic.ttf"),
    }
    n = 0 if kind == "bold" else 1
    candidates = [regular.with_name(names[regular.name][n])] if regular.name in names else []
    for old, new in (("-Regular", "-Bold" if n == 0 else "-BoldItalic"),
                     ("Regular", "Bold" if n == 0 else "BoldItalic")):
        if old in regular.name:
            candidates.append(regular.with_name(regular.name.replace(old, new)))
    candidates.append(regular.with_name(
        regular.stem + ("-Bold" if n == 0 else "-BoldItalic") + regular.suffix))
    return next((candidate for candidate in candidates
                 if candidate != regular and candidate.is_file()), None)


def paint_line(page: fitz.Page, text: str, x: float, baseline: float, width_limit: float,
               base_font: fitz.Font, font_size: float, italic_phrases: list[str],
               italic_font: fitz.Font | None, justify_to: float | None = None,
               bold_phrases: list[str] | None = None,
               bold_font: fitz.Font | None = None,
               bold_italic_font: fitz.Font | None = None) -> bool:
    # Normalize accidental multiple OCR spaces. Do not alter punctuation or
    # attempt cross-line rewriting in the fixed-source-page book workflow.
    text = re.sub(r"\s+", " ", text.strip())
    tokens = styled_runs(text, italic_phrases, bold_phrases or [])
    def variant(italic: bool, bold: bool) -> tuple[fitz.Font | None, str]:
        if bold and italic:
            return bold_italic_font, "BookBoldItalic"
        if bold:
            return bold_font, "BookBold"
        if italic:
            return italic_font, "BookItalic"
        return base_font, "BookBody"
    lengths=[]
    for token,ital,bold in tokens:
        selected,_name=variant(ital,bold)
        if selected is None:
            raise ValueError("Source-verified bold/italic font is unavailable")
        lengths.append(selected.text_length(token,fontsize=font_size))
    natural=sum(lengths)
    if natural>width_limit+1.5:
        return False
    gaps=[i for i,(token,_,_) in enumerate(tokens) if token.isspace()]
    extra=0.0
    if justify_to is not None and gaps:
        proposed=(justify_to-x-natural)/len(gaps)
        # If reaching the right margin requires extreme spacing, *do not*
        # force it. Source-aligned ragged-right text never enters this branch.
        if 0 <= proposed <= font_size*.28 and natural >= (justify_to-x)*.83:
            extra=proposed
    cursor=x
    for (token,ital,bold),advance in zip(tokens,lengths):
        if token.isspace():
            cursor+=advance+extra
            continue
        _font,name=variant(ital,bold)
        page.insert_text((cursor,baseline),token,fontname=name,
                         fontsize=font_size,color=(.17,.19,.18),overlay=True)
        cursor+=advance
    return True


def digital_footer(page: fitz.Page, src: fitz.Page, items: list[dict],
                   base_font: fitz.Font, size: float) -> bool:
    """Preserve original footer graphic; replace only verified OCR page-number ink.

    The local background paint is conservative and needs visual QA on textured
    scanned paper. If sampling is unsafe, keep the original scanned footer.
    """
    if len(items) != 1:
        return False
    line = items[0]
    width,height = src.rect.width,src.rect.height
    x,y = float(line["x"])*width,float(line["y"])*height
    w,h = float(line["width"])*width,float(line["height"])*height
    if not (6 <= h <= 22 and 3 <= w <= 43 and y >= height*.875):
        return False
    sample_rect = fitz.Rect(max(0,x-7),max(0,y-1),min(width,x+w+8),min(height,y+h+2))
    pix = src.get_pixmap(matrix=fitz.Matrix(1,1),clip=sample_rect,colorspace=fitz.csRGB,alpha=False)
    if pix.width < 5 or pix.height < 5:
        return False
    im = Image.frombytes("RGB",(pix.width,pix.height),pix.samples)
    # Background from side strips away from the glyph (not the dark text).
    colors = [im.getpixel((k,j)) for j in range(pix.height)
              for k in list(range(min(3,pix.width)))+list(range(max(0,pix.width-3),pix.width))]
    if not colors:
        return False
    bg = tuple(int(statistics.median(p[c] for p in colors)) for c in range(3))
    if any(max(p[c] for p in colors)-min(p[c] for p in colors) > 90 for c in range(3)):
        return False
    box = fitz.Rect(max(0,x-1),max(0,y-1),min(width,x+w+1),min(height,y+h+1))
    foot_size = max(7,min(13,h*.87))
    if base_font.text_length(line["text"],fontsize=foot_size) > w + 6:
        return False
    page.draw_rect(box,color=None,fill=tuple(c/255 for c in bg),overlay=True)
    page.insert_text((x,y+foot_size*.93),line["text"],fontname="BookBody",
                     fontsize=foot_size,color=(.45,.45,.45),overlay=True)
    return True


def typeset_page(out: fitz.Document, original: fitz.Document, idx: int, lines: list[dict],
                 fontfile: Path, font: fitz.Font, size: float, keep_footer: bool,
                 italic_phrases: list[str] | None = None,
                 bold_phrases: list[str] | None = None,
                 book_style: dict | None = None) -> tuple[bool, str]:
    src = original[idx]
    page = out.new_page(width=src.rect.width,height=src.rect.height)
    style = book_style or {
        "alignment": "source_uncertain", "background": "cream",
        "margin_left_ratio": .12, "margin_right_ratio": .12,
        "leading_pt": size*1.4, "paragraph_gap_pt": size*1.8,
        "pages_observed": 0
    }
    validate_style(style)
    page.draw_rect(page.rect,color=None,fill=palette(style["background"]),overlay=False)
    page.insert_font(fontname="BookBody",fontfile=str(fontfile))
    italic_phrases = italic_phrases or []
    bold_phrases = bold_phrases or []
    for phrase in italic_phrases + bold_phrases:
        if not any(phrase in entry["text"] for entry in lines):
            return False, "source-verified emphasized phrase not present in OCR on this page"
    italic_file = italic_font_file(fontfile)
    if italic_phrases and italic_file is None:
        return False, "matching italic font unavailable; source styles need review"
    italic_font = fitz.Font(fontfile=str(italic_file)) if italic_file else None
    if italic_font is not None and italic_phrases:
        page.insert_font(fontname="BookItalic",fontfile=str(italic_file))
    bold_file = styled_font_file(fontfile, "bold")
    both_file = styled_font_file(fontfile, "bold_italic")
    if bold_phrases and bold_file is None:
        return False, "matching bold font unavailable; source styles need review"
    if bold_phrases and italic_phrases and both_file is None and any(
        bold in italic or italic in bold
        for bold in bold_phrases for italic in italic_phrases
    ):
        return False, "matching bold italic font unavailable; source styles need review"
    bold_font = fitz.Font(fontfile=str(bold_file)) if bold_file else None
    both_font = fitz.Font(fontfile=str(both_file)) if both_file else None
    if bold_phrases and bold_file:
        page.insert_font(fontname="BookBold",fontfile=str(bold_file))
    if both_file and bold_phrases and italic_phrases:
        page.insert_font(fontname="BookBoldItalic",fontfile=str(both_file))
    body,footer = split_footer(lines)
    if len(body) < 7:
        return False, "insufficient body OCR for true digital typesetting"
    try:
        measured = style.get("pages_observed", 0) >= 2
        positions=plan_body(
            body,src.rect.width,src.rect.height,size,
            body_margin=(style["margin_left_ratio"]*src.rect.width if measured else None),
            preferred_leading=(style["leading_pt"] if measured else None),
            preferred_paragraph_gap=(style["paragraph_gap_pt"] if measured else None)
        )
    except ValueError as exc:
        return False,str(exc)
    if keep_footer and src.rect.height>100:
        strip = fitz.Rect(0,src.rect.height-36,src.rect.width,src.rect.height)
        page.show_pdf_page(strip,original,idx,clip=strip,overlay=True,keep_proportion=False)
    # Estimate the right body text edge from source long lines. Do not change
    # mirrored left/right margins or force justification on short closing lines.
    sorted_edges = sorted([float(line["x"]+line["width"])*src.rect.width for line in body
                           if len(line["text"])>=25])
    right_edge = (
        src.rect.width*(1-style["margin_right_ratio"])
        if style.get("alignment") == "justify" and style.get("pages_observed",0) >= 2
        else (sorted_edges[max(0,int(len(sorted_edges)*.75)-1)]
              if sorted_edges else src.rect.width*.90)
    )
    for record in positions:
        text = record["text"]
        x,baseline = record["draw_x"],record["baseline"]
        maxwidth=src.rect.width-max(24,src.rect.width*.055)-x
        # Only a source-verified justified book gets extended word gaps.
        # A ragged-right or uncertain book uses natural word spacing.
        target = (right_edge if style["alignment"] == "justify"
                  and not record["paragraph_last"]
                  and record["paragraph_line_count"]>1 and len(text.split())>=5
                  else None)
        try:
            ok=paint_line(page,text,x,baseline,maxwidth,font,size,
                          italic_phrases,italic_font,justify_to=target,
                          bold_phrases=bold_phrases,bold_font=bold_font,
                          bold_italic_font=both_font)
        except ValueError as exc:
            return False,str(exc)
        if not ok:
            return False,"source line would overflow at approved font size"
    footer_warning = ""
    if keep_footer and footer:
        # Preserve decorations; report whenever the original page number
        # could not be safely replaced with visible, selectable PDF text.
        if not digital_footer(page,src,footer,font,size):
            footer_warning = "footer_number_still_raster_review_needed"
    elif footer:
        return False,"source footer digit not preserved"
    generated = word_counts(page.get_text("text"))
    expected = word_counts(" ".join(line["text"] for line in body))
    # Footer may remain visually intact as source strip but not extracted; do
    # not falsely claim it is digital unless visible OCR was inserted above.
    if expected-generated:
        return False,"source OCR words lost in typeset output"
    visible=sum(len(x.get("chars",[])) for x in page.get_texttrace()
                if x.get("type")!=3)
    if visible<65:
        return False,"insufficient visible vector text"
    return True,footer_warning


def fallback_page(out: fitz.Document, original: fitz.Document, idx: int, lines: list[dict]) -> None:
    src = original[idx]
    page = out.new_page(width=src.rect.width, height=src.rect.height)
    page.show_pdf_page(page.rect, original, idx, overlay=False)
    add_hidden_ocr(page, lines, src.rect)


def build(source: Path, work: Path, dest: Path, mode: str, page_list: list[int],
          family: str, fontfile: Path, font_size: float | None,
          keep_footer: bool = True, strict_hybrid: bool = True,
          approval: Path | None = None, fusion_subdir: str = "fusion",
          style_annotations: Path | None = None,
          verified_cover_pages: set[int] | None = None,
          book_style: dict | None = None,
          background_override: str | None = None,
          style_override: Path | None = None) -> dict:
    source_sha = sha256(source)
    verified_cover_pages = set(verified_cover_pages or ())
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
    annotations = {}
    if style_annotations and style_annotations.is_file():
        annotations = json.loads(style_annotations.read_text(encoding="utf-8"))
        if annotations.get("source_sha256") != source_sha:
            raise ValueError("Style annotations do not match the source PDF hash")
    doc = fitz.open(source)
    canonical_size = canonical_page_size(doc, verified_cover_pages)
    if verified_cover_pages - {1, len(doc)}:
        raise ValueError("Only first or last physical page may be an exempt cover")
    if mode == "full" and page_list != list(range(1, len(doc)+1)):
        raise ValueError("Cannot publish incomplete full-book page mapping")
    font = fitz.Font(fontfile=str(fontfile))
    data = []
    for num in page_list:
        if num in verified_cover_pages:
            data.append((num, [], []))
            continue  # A verified cover is preserved without wasting OCR cycles.
        cache, issues = load_cache(work, num, source_sha, require_hybrid=strict_hybrid, fusion_subdir=fusion_subdir)
        lines = usable_lines(cache)
        data.append((num, lines, issues))
    suggested = recommended_size([(doc[n-1].rect, lines) for n, lines, _ in data], font)
    size = suggested if font_size is None else font_size
    if not 7 <= size <= 24:
        raise ValueError("Unsupported body font size outside 7-24 pt")
    source_style = (dict(book_style) if book_style is not None else
                    infer_style([(number,doc[number-1].rect,lines)
                                 for number,lines,_issues in data
                                 if number not in verified_cover_pages]))
    validate_style(source_style)
    if book_style is None and style_override and style_override.is_file():
        override = json.loads(style_override.read_text(encoding="utf-8"))
        source_style = source_verified_override(source_style, override, source_sha)
    if background_override is not None:
        palette(background_override)
        source_style["background"] = background_override
    # Produce deterministic pages; page-level rollback leaves the source intact.
    temp = dest.with_suffix(".partial.pdf")
    output = fitz.open()
    rows = []
    for number, lines, issues in data:
        src = doc[number - 1]
        if number in verified_cover_pages:
            fallback_page(output, doc, number - 1, [])
            rows.append({
                "source_page": number,
                "output_page": len(output),
                "mode": "verified_cover_raster_exempt",
                "ocr_issues": 0, "ocr_review_required": False,
                "ocr_secondary_status": None,
                "detected_nontext_ink_score": 0.0,
                "reasons": ["source_scan_verified_cover_exception"],
                "warnings": [],
                "source_verified_italic_spans": 0,
                "source_verified_bold_spans": 0,
            })
            continue
        mode_name = "searchable_scan_fallback"
        reasons = []
        warnings = []
        if len(lines) < 7:
            reasons.append("not enough recognized body lines")
        # The safe Tesseract second opinion is often more noisy than Apple Vision.
        # It is a QA warning, not a reason to discard every otherwise safe
        # visible pilot page. Keep the result explicitly unverified.
        if issues and fusion_subdir not in ("fusion_safe", "fusion_mobile"):
            reasons.append("Apple/Paddle disagreement awaiting source review")
        ink_score = unrecognized_ink(src, lines)
        if ink_score > 1:
            reasons.append("graphic, decoration, or unrecognized text risk")
        if not reasons:
            ok, reason = typeset_page(
                output, doc, number - 1, lines, fontfile, font, size, keep_footer,
                italic_phrases=verified_italics(annotations, number),
                bold_phrases=verified_bolds(annotations, number),
                book_style=source_style
            )
            if ok:
                mode_name = "born_digital_unverified"
                if reason:
                    warnings.append(reason)
            else:
                reasons.append(reason)
                output.delete_page(len(output) - 1)
        if reasons:
            fallback_page(output, doc, number - 1, lines)
        review_file = work / "review" / f"page_{number:03d}.json"
        review_status = None
        review_reasons = []
        if review_file.is_file():
            review_data = json.loads(review_file.read_text(encoding="utf-8"))
            if review_data.get("source_sha256") != source_sha or review_data.get("page") != number:
                raise ValueError(f"Review cache does not match source page {number}")
            review_status = review_data.get("secondary_status")
            review_reasons = review_data.get("assessment", {}).get("reasons", [])
        rows.append({"source_page": number, "output_page": len(output),
                     "mode": mode_name, "ocr_issues": len(issues),
                     "ocr_review_required": bool(issues or review_reasons), "ocr_secondary_status": review_status,
                     "detected_nontext_ink_score": round(ink_score, 3),
                     "reasons": reasons, "warnings": warnings,
                     "source_verified_italic_spans": len(verified_italics(annotations, number)),
                     "source_verified_bold_spans": len(verified_bolds(annotations, number))})
    # Source scans can have uneven PDF page canvases. Paper is a book-level
    # property, not a separate choice for every scan. Avoid changing the
    # typesetting engine's source-relative coordinates: fit its completed
    # per-page PDF as a *vector* into one common paper size instead.
    if not all_pages_uniform(output, canonical_size):
        fitted, page_size_evidence = normalized_copy(
            output, canonical_size, palette(source_style["background"]),
            verified_cover_pages=verified_cover_pages
        )
        output.close()
        output = fitted
    else:
        page_size_evidence = [
            {
                "source_page": i + 1,
                "before_width_pt": round(output[i].rect.width, 2),
                "before_height_pt": round(output[i].rect.height, 2),
                "after_width_pt": canonical_size["width_pt"],
                "after_height_pt": canonical_size["height_pt"],
                "scale": 1.0, "offset_x_pt": 0.0, "offset_y_pt": 0.0,
                "aspect_ratio_preserved": True,
                "full_page_content_preserved": True,
                "visual_review_recommended": False,
            } for i in range(len(output))
        ]
    verify_uniform_pdf(output, canonical_size)
    for row, evidence in zip(rows, page_size_evidence):
        row["paper_normalization"] = evidence
    dest.parent.mkdir(parents=True, exist_ok=True)
    output.save(temp, garbage=3, deflate=True)
    output.close()
    reread = fitz.open(temp)
    if len(reread) != len(page_list):
        raise RuntimeError("Output page count incorrect, preserving partial for inspection")
    verify_uniform_pdf(reread, canonical_size)
    reread.close()
    if sha256(source) != source_sha:
        raise RuntimeError("Source modified during build")
    temp.replace(dest)
    counts = Counter(row["mode"] for row in rows)
    report = {"status": "REVIEW_REQUIRED", "note": "Not an editorial fidelity certification.",
              "source_sha256": source_sha,
              "ocr_backend": ("apple-vision-primary+paddle-mobile-selective" if fusion_subdir == "fusion_mobile"
                              else "apple-vision+tesseract" if fusion_subdir == "fusion_safe"
                              else "legacy-paddle"),
              "source_page_count": len(doc),
              "output_page_count": len(page_list), "mapping": page_list,
              "canonical_page_size": canonical_size,
              "page_size_normalization_required": any(
                  abs(e["scale"]-1.0) > .001 or
                  e["offset_x_pt"] > .05 or e["offset_y_pt"] > .05
                  for e in page_size_evidence
              ),
              "page_size_visual_review_pages": [
                  page_list[i] for i,e in enumerate(page_size_evidence)
                  if e["visual_review_recommended"]
              ],
              "font_family": family, "font_file_name": fontfile.name,
              "body_font_size_pt": size, "digital_pages": counts["born_digital_unverified"],
              "fallback_pages": counts["searchable_scan_fallback"],
              "per_page": rows,
              "verified_cover_pages": sorted(verified_cover_pages),
              "typography_layout_version": 5,
              "book_style": source_style,
              "style_annotations_sha256": sha256(style_annotations) if style_annotations and style_annotations.exists() else None}
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
