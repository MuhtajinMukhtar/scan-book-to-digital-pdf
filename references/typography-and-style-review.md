# Source-faithful pilot typography: margins, paragraph rhythm, italics and footer

For the AI agent. The user should only see the PDF pilot and approve or request revisions.

## What the engine can do now

- Keep all text on the **same physical source page** with source page dimensions unchanged.
- Group consecutive OCR lines into paragraphs and regularize baseline spacing within a paragraph instead of repeating OCR y-coordinate jitter.
- Stabilize continuation lines' left edge while preserving intentional **mirrored gutters** on facing pages.
- Modestly justify sufficiently long nonfinal paragraph lines; keep final lines left-aligned. Never silently shrink or overflow text.
- Attempt an unambiguous **printed page number** as visible/selectable text. Preserve footer ornament from the source and flag `footer_number_still_raster_review_needed` when replacing the number is unsafe.
- Render **source-verified italic spans**. Apple Vision alone does not reliably identify italic styles; never infer italics from keywords or language.

## Source-verified italic spans

Only after comparing the actual source scan with the pilot, create `work/style-annotations.json`, if necessary:

~~~json
{
  "source_sha256": "<actual SHA-256 of original scanned PDF>",
  "pages": {
    "124": {
      "italic_spans": [
        {"text": "image", "source_scan_verified": true},
        {"text": "advertising", "source_scan_verified": true},
        {"text": "hati yang terjaga", "source_scan_verified": true}
      ]
    }
  }
}
~~~

Page 124 here is an *example* from the discussion. **Never copy these phrases into a different book without inspecting its actual source.** The exact phrase must appear in the OCR of that physical page. The agent should identify formatting from the source sample, add entries only when supported, and seek review if ambiguous.

Rerender without OCR:

~~~sh
python scripts/run_book.py pilot --source BOOK.pdf --work-dir ./work --skip-ocr --pages 90,124
~~~

The pilot profile locks the annotation file SHA. Changing annotations after approval blocks full-book processing until a revised pilot is approved. If a matching local italic font isn't available, report the exception instead of silently stripping emphasis.

## Images, tables, and footer examples

The deterministic engine **still cannot fully reconstruct complex tables and illustration pages**. It can preserve a page as a searchable original scan while retaining its page identity; this is a disclosed exception, not a fully digital page. If the source includes tables or illustrations, show representative pages of each category in the pilot before seeking all-book approval.

For page numbers, review odd/even positioning, the original paper color and footer ornament. If the QA report flags a footer still raster, report it. Do not claim the whole footer is digital merely because the body is selectable.

## Editorial acceptance

Inspect actual PDF output and source side-by-side:
- Uniform leading within the same paragraph; correct gap between paragraphs
- Source-like mirrored margins, no text shift to a neighboring page
- Printed italic and other emphasis present when source supports it
- Numeric footer text reconstructed or flagged; graphics and tables preserved/rebuilt transparently
- Identical physical page count, order, dimensions and same-page text

A code test is not a substitute for reviewing the actual book scan.
