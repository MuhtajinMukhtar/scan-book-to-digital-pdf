"""One physical paper size for every generated book page, including covers.

Source scans may have slightly different PDF MediaBoxes because of scanning,
cropping or export. Determine a representative *book* size from the source
body pages, then fit each complete composed page inside that paper (uniform
scale, centered). No page is cropped, stretched, merged or moved to another.
The selected size belongs to this source PDF, not a hard-coded A4/Letter size.
"""
from __future__ import annotations

from collections import Counter
import statistics

import fitz


SIZE_TOLERANCE_PT = .02


def canonical_page_size(doc: fitz.Document,
                        verified_cover_pages: set[int] | None = None) -> dict:
    """Return a source-derived physical size (points), excluding covers if possible."""
    if len(doc) == 0:
        raise ValueError("Cannot choose paper size for an empty PDF")
    covers = set(verified_cover_pages or ())
    body = [(i + 1, page.rect.width, page.rect.height)
            for i, page in enumerate(doc) if i + 1 not in covers]
    if not body:
        body = [(i + 1, page.rect.width, page.rect.height)
                for i, page in enumerate(doc)]
    for _, width, height in body:
        if not (36 <= width <= 14400 and 36 <= height <= 14400):
            raise ValueError("Source page has invalid physical size")
    # Median is robust to outlying scan canvas sizes or oversized covers.
    # Rounding only once avoids artificial 0.01 pt differences among pages.
    width = round(statistics.median(item[1] for item in body), 2)
    height = round(statistics.median(item[2] for item in body), 2)
    return {
        "width_pt": width, "height_pt": height,
        "unit": "pt", "method": "source_body_median",
        "sampled_body_pages": len(body),
        "covers_excluded_from_estimate": sorted(covers),
    }


def matches_page_size(page: fitz.Page, size: dict,
                      tolerance: float = SIZE_TOLERANCE_PT) -> bool:
    return (abs(page.rect.width - size["width_pt"]) <= tolerance
            and abs(page.rect.height - size["height_pt"]) <= tolerance
            and abs(page.mediabox.width - size["width_pt"]) <= tolerance
            and abs(page.mediabox.height - size["height_pt"]) <= tolerance
            and abs(page.cropbox.width - size["width_pt"]) <= tolerance
            and abs(page.cropbox.height - size["height_pt"]) <= tolerance)


def all_pages_uniform(doc: fitz.Document, size: dict) -> bool:
    return all(matches_page_size(page, size) for page in doc)


def normalized_copy(doc: fitz.Document, size: dict,
                    background: tuple[float, float, float] = (1, 1, 1),
                    verified_cover_pages: set[int] | None = None
                    ) -> tuple[fitz.Document, list[dict]]:
    """Create uniform paper preserving visible PDF vectors, text and artwork.

    Caller owns and must close the returned document. The input document stays
    open and unchanged. Every page is fitted proportionally, never stretched.
    Return per-page scale/offset evidence for visual and extraction QA.
    """
    width, height = size["width_pt"], size["height_pt"]
    if not (36 <= width <= 14400 and 36 <= height <= 14400):
        raise ValueError("Invalid canonical paper dimensions")
    covers = set(verified_cover_pages or ())
    output = fitz.open()
    evidence: list[dict] = []
    try:
        for i, source_page in enumerate(doc):
            src_width, src_height = source_page.rect.width, source_page.rect.height
            if src_width <= 0 or src_height <= 0:
                raise ValueError(f"Invalid page {i + 1} dimensions")
            scale = min(width / src_width, height / src_height)
            fitted_w, fitted_h = scale * src_width, scale * src_height
            left, top = (width - fitted_w) / 2, (height - fitted_h) / 2
            box = fitz.Rect(left, top, left + fitted_w, top + fitted_h)
            new = output.new_page(width=width, height=height)
            if i + 1 not in covers:
                new.draw_rect(new.rect, color=None, fill=background, overlay=False)
            new.show_pdf_page(box, doc, i, keep_proportion=False, overlay=True)
            source_words = Counter(token[4] for token in source_page.get_text("words"))
            fitted_words = Counter(token[4] for token in new.get_text("words"))
            if source_words != fitted_words:
                raise ValueError(
                    f"Page {i + 1} text changed during paper-size normalization"
                )
            if any(word[0] < -.5 or word[1] < -.5 or
                   word[2] > width + .5 or word[3] > height + .5
                   for word in new.get_text("words")):
                raise ValueError(
                    f"Page {i + 1} digital text would leave unified paper"
                )
            evidence.append({
                "source_page": i + 1,
                "before_width_pt": round(src_width, 2),
                "before_height_pt": round(src_height, 2),
                "after_width_pt": width, "after_height_pt": height,
                "scale": round(scale, 6),
                "offset_x_pt": round(left, 3),
                "offset_y_pt": round(top, 3),
                "aspect_ratio_preserved": True,
                "full_page_content_preserved": True,
                "visual_review_recommended": (
                    abs(scale - 1.0) > .06 or
                    max(left / width, top / height) > .04
                ),
            })
    except Exception:
        output.close()
        raise
    if not all_pages_uniform(output, size):
        output.close()
        raise RuntimeError("Paper size normalization produced mixed page sizes")
    return output, evidence


def verify_uniform_pdf(doc: fitz.Document, size: dict) -> None:
    if not all_pages_uniform(doc, size):
        raise RuntimeError("Book output has nonuniform MediaBox/CropBox dimensions")
