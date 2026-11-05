# Fixed-page fidelity: hard acceptance gate

## Non-negotiable invariants

For a requested **same-pages** digital reconstruction, the source is authoritative:

1. An N-page source **must** produce exactly N output pages.
2. Source physical page **i** must map to output physical page **i**. Never shift sentences, paragraphs, quotations, notes, charts, photos or footers into a neighboring page.
3. Every output page must have the same physical page dimensions as its corresponding source page. Verify order, first/last passage and reading sequence, not merely page numbers.
4. Do not crop, hide, truncate, silently shrink, or omit text to satisfy a fixed page size. If the approved body font/size cannot fit, recover spacing/layout only within source-supported tolerances. Otherwise preserve **that exact page** as an original searchable-scan fallback with its own selectable OCR layer, flag it in the manifest and review. Do not use the next page as overflow space.
5. Each page must retain its source photos, logos, tables, diagrams and illustrations, and its digitally typeset text must be real visible/selectable text. Scan fallbacks must be clearly counted separately.
6. Source original SHA-256 must remain unchanged.

**Pilots:** Apply the same one-to-one content rule to each selected sample, even though the pilot PDF contains only those selected pages. The full-book audit below applies only after approval and processing of the *entire* N-page book.

## Audit sources and limits

- The `--source` file is the **actual original scanned PDF**, not a previous digital output.
- The `--source-ocr-dir` must have a **page_i.json for each source physical page**, with correct `page`, `source_sha256`, and `lines[].text`. Use `work/verified_ocr`: assemble a **source-verified text reference** using Apple Vision as the primary OCR, optional PP-OCRv5 Mobile on doubtful pages, **and the actual scan**. Mobile is not required for high-confidence pages, and differences are review candidates rather than automatically accepted text. The program is intentionally not a substitute for this reconciliation. Retain `work/ocr` unmodified as raw Apple OCR. All verified lines must remain assigned to the physical page where they appear, including material that was missing from either engine. Do not forge verification flags.
- The full PDF may be typeset but its page count, geometry, and text still have to match the original *per page*. Extraction from a PDF can miss visually present or clipped text, so it is not a substitute for reading source and output page images.
- The comparison is intentionally **fail-closed**: missing caches, mismatching hashes, omitted/duplicated page manifests, unexplained extra or missing words, missing review flags, and likely cross-page movement force `FAIL_REVIEW_REQUIRED`. A full-book 95% coverage percentage **cannot** certify all individual pages.
- Exact token comparisons can flag legitimate OCR corrections, ligatures and differences in punctuation; inspect those against the scan, then document exact token-by-token source-verified exceptions instead of lowering thresholds. Never accept an exception based solely on AI guesses.
- Text token accounting alone cannot prove image fidelity or correct paragraph order. Set `visual_checked`, `images_verified`, `content_verified`, `reading_order_verified`, and `page_boundary_verified` only after real evidence-based page review.

## Required page manifest

Generate `manifest.json` with source counts and SHA-256, and exactly one entry for every page i:

```json
{
  "source_sha256": "<source file's actual SHA-256>",
  "source_pages": 2,
  "output_pages": 2,
  "pages": [
    {
      "source_page": 1,
      "output_page": 1,
      "mode": "born_digital",
      "content_verified": true,
      "images_verified": true,
      "visual_checked": true,
      "page_boundary_verified": true,
      "reading_order_verified": true
    },
    {
      "source_page": 2,
      "output_page": 2,
      "mode": "searchable_scan_fallback",
      "content_verified": true,
      "images_verified": true,
      "visual_checked": true,
      "page_boundary_verified": true,
      "reading_order_verified": true
    }
  ]
}
```

The example is **schema only**: all flags start false/unverified in a new book and may turn true only after actually inspecting source and output. Image-only pages with verified no words may use `source_page_has_no_text_verified: true`. If the raw OCR contains a mistake, use a page-specific `reviewed_ocr_errors` item that includes `token`, `count`, `reason`, `reviewer`, `source_excerpt`, and `source_scan_verified: true`; to account for genuine extra output words use equivalent `reviewed_output_additions`. These are explicitly *reviewed OCR disagreements*, **never permission to remove real source content**. Explain each exception in the final report.

## Command: full-book QA

```sh
python scripts/page_fidelity_audit.py \
  --source original-scan.pdf \
  --output Digital_REVIEW.pdf \
  --source-ocr-dir work/verified_ocr \
  --manifest manifest.json \
  --json page-fidelity.json
```

- Exit code **0** and `status: PASS` means all *specified* data/verification gates were satisfied, not mathematical proof that OCR recognized every character.
- Exit code **2** and `status: FAIL_REVIEW_REQUIRED` means fix or source-review the identified page, rerun the audit, and preserve any earlier accepted PDF versions.
- Report `possible_cross_page_spill` by origin and destination page even if total page count is correct.
- Run `scripts/pdf_audit.py` as a separate structural/font audit; independently view source and result in a visual contact sheet **for every exception and enough samples of all page types**, and check every page content/visual flags as recorded.
- Do not promise perfect page fidelity until a real book has been reviewed. The safe claim is that the workflow is designed to **reject** unverified changes and will present unresolved pages for correction.

## Easy summary to the user

**Original N pages → Result N pages | Page mapping: verified/failed | Missing/moved content: none found or page numbers | Fallback scans: N | Editorial QA: pending/approved.**

Never collapse `QA_PENDING` into `PASS` just because the PDF opens or its page count matches.
