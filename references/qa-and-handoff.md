# Verification, revision, and cross-account handoff

## Required page manifest

Store a machine-readable `manifest.json` with one entry for every physical source page:

```json
{
  "source_sha256": "<actual SHA-256>",
  "source_pages": 197,
  "output_pages": 197,
  "pages": [
    {
      "source_page": 1,
      "printed_folio": null,
      "archetype": "cover",
      "mode": "searchable_scan_fallback",
      "ocr_engine": "Apple Vision",
      "source_ocr_word_coverage": null,
      "fonts": [],
      "images_verified": true,
      "content_verified": true,
      "visual_checked": true,
      "page_boundary_verified": true,
      "reading_order_verified": true,
      "output_page": 1,
      "issues": []
    }
  ]
}
```

Above values are **illustrative only**; never carry the example's 197 pages or engine blindly into another book. For full-book QA, consult **`references/page-fidelity.md`**. A `true` review flag must reflect real verification, never be auto-populated to make the audit pass.

## Technical gates

- **Source integrity:** same original SHA-256 before and after, no original overwrite.
- **Hard one-to-one pagination:** `source page N = output page N`, identical physical page count, dimensions and page order, with no text or figures shifted to another page; do not make exceptions to this contract merely to preserve a typography preference. If a page does not fit, use original searchable-scan fallback on that same page, and report it.
- **Digital coverage:** categorize pages as born-digital vs searchable scanned fallback. Never report total page count as digital-text coverage.
- **Strict per-page text:** run `scripts/page_fidelity_audit.py` with the original scanned PDF, complete source-verified OCR reference reconciled from both engines and the scanned page, and a complete page manifest; `status=FAIL_REVIEW_REQUIRED` is a blocker even if the book has the same total page count. Compare normalized source OCR words against PDF extraction **for each corresponding page**, not only a whole-book total. Original OCR words must be compared independently of generated HTML. Normalization may fold whitespace and verified hyphenation; do not blanket-strip punctuation or whole sections. Treat confidence/real OCR errors separately from lost PDF text. Investigate source token coverage below 95% and stop if important content is missing; thresholds may be adjusted only with documented source evidence, not to suppress errors.
- **Fonts:** check `pdffonts` or page spans for actual embedded serif/sans fonts; honor source italics and headings; whitelisted glyph exceptions are narrow and documented. Use no proprietary font redistribution.
- **Images:** compare source and output visually for photographs, logos and diagrams; verify photo crop and correct orientation.
- **Geometry:** check every page's rectangles/word bounding boxes for out-of-page text, clipping, overlaps and unreasonable spacing.
- **Footer/quotes:** verify printed folio vs PDF physical page mapping, ornamental quotes, centered titles and reflection continuity.
- **Delta:** compare changed page set with previous approved draft; untouched pages should have identical extracted text and preserved images unless global restyling was explicitly authorized.
- **Visual:** source/output contact sheets for all changed, failed, complex, first/last pages; at least one renderer; use a second renderer for tricky pages.

Run `python scripts/page_fidelity_audit.py --source <original.pdf> --output <new.pdf> --source-ocr-dir <work/verified_ocr> --manifest <manifest.json> --json <page-fidelity.json>` first. This must not be treated as an automatic guarantee that OCR detected all text: inspect source scans and document corrections. Then run `python scripts/pdf_audit.py <new.pdf> --baseline <last-approved.pdf> --json <audit.json>`. Optional `--source-ocr-dir <work/ocr>` for independent word coverage; view the generated JSON, do not infer pass from exit code alone.

## Safe resume / exception ledger

When interrupted, preserve the page cache and `progress.json`: last completed page, source SHA, OCR engine/version, renderer/font versions, accepted fixes and unresolved pages. Do not repeat OCR if cached source and checksum still match. Print the *first real error*, determine if it is an actual source OCR error vs over-strict QA, and fix only the affected pages. Resume through one MSO Goal rather than multiplying Goals.

For approval, report in concise Indonesian:
`Source: [N pages, SHA verified] | Digital: [N] | Fallback scans: [N] | Images: [verified/risks] | QA: [pass/pending] | Output: [path/link] | Pending: [specific pages]`.

## Lossless optimization

Try PyMuPDF with garbage collection, stream deflate and object streams. Write a **new file**. Verify identical extracted text, page size, image count and **pixel-identical full-page render** at a stated resolution where feasible; spot-check higher DPI for photos/lines. Quote actual byte sizes and percentage savings; if reducing image JPEG quality, it is **not lossless**.

## Cross-account access through MSO

- Place and validate the shared skill in MSO's discoverable skill catalog (official `claude-skills/<name>` or another configured shared skill root). An account must connect/authenticate to the **same MSO instance** and be authorized to read the catalog; a skill installed only in one account's ChatGPT library is not automatically available to a second account.
- On the second account, call MSO `skills_search("scan-book-to-digital-pdf")` and `skills_read("<exact id from search>")`; if both work, the *shared MSO skill instructions* are reachable. Project documents/source files still require their own file permissions.
- If the other account lacks an MSO connection, import the portable `skill.zip` into that account as an alternate route. Installing ZIP in a different account does **not** itself grant MSO server access.
- Cross-account readiness should be **tested on the second account**; success on the first account alone is evidence of catalog visibility, not proof of the other's permissions.
