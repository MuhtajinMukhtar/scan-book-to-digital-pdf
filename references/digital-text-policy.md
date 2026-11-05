# Mandatory digital-text policy

**All source pages containing text must be reconstructed as visibly typeset, searchable, selectable PDF text. Only verified covers may remain whole-page scans.** A source scan with a hidden OCR layer does not count.

## Text must be real PDF text on non-cover pages

- Normal prose, titles, headings, footnotes, page numbers and emphasized/italic words
- Table/form column headers and cell contents, with source-relative positions preserved
- All written material around source photographs and drawings
- Quotation text on decorative callout backgrounds

Photos, illustrations, border ornaments and table rules may remain *separate image or vector assets*. The **whole original scanned page** must not be retained as the final image of a non-cover page.

A genuinely text-free blank or artwork-only page has no text to digitize: flag it for source inspection instead of inventing words or quietly treating it as a cover. Under the initial strict gate it remains unresolved until properly reviewed.

## Only a source-verified cover may be exempt

Visually inspect the original first page and, if present, last page. If they really are book covers, the AI agent may create local `work/cover-evidence.json`:

~~~json
{
  "source_sha256": "<actual SHA-256 of the uploaded PDF>",
  "pages": [
    {
      "source_page": 1,
      "kind": "front_cover",
      "source_scan_verified": true,
      "source_description": "Observed original cover with title and artwork"
    }
  ]
}
~~~

Use real source hash and visual description; never invent a verified cover from an arbitrary chapter page. Only physical first or last PDF pages qualify. The cover file and SHA are locked into the approved pilot style profile. Verified cover imagery may be preserved without running OCR.

## Mandatory full-book completion gate

`scripts/run_book.py full` automatically invokes `scripts/digital_text_policy_gate.py`. It checks source-to-output physical page mapping and dimensions, the per-page compositor QA modes, visible vector PDF text, effective image coverage and validated cover evidence.

The gate rejects any non-cover page that is an unchanged searchable scan, a nearly-full-page raster with a small digital overlay, or has no visible selectable PDF text. It accounts for actual clipping of footer images so that preserving a narrow decorative footer does **not** count as a retained scanned whole page.

- `READY_FOR_EDITORIAL_FIDELITY_REVIEW`: all non-cover pages pass necessary structural text-digitalization checks. This does **not** establish character-by-character accuracy.
- `INCOMPLETE_DIGITAL_PAGES`: return nonzero code and list all failed source pages. Keep the PDF only as an incomplete review draft. **Never call it FINAL, complete, or fully digitized.**
- Source accuracy, captions, images, table reading order, italics, page boundaries and typography still require visual source comparison and `scripts/page_fidelity_audit.py` before FINAL designation.

The engine cannot yet reconstruct every complex page automatically. **This policy prevents false completion; it does not claim that missing table/photo-layout technology has already been implemented.** The pilot must therefore reconstruct representative table, image and decorative pages, not simply show identical scans on both sides.

## Agent-only check

~~~sh
python scripts/digital_text_policy_gate.py \
  --source BOOK.pdf --output work/output/Book_Full_REVIEW.pdf \
  --qa work/output/Book_Full_REVIEW.qa.json \
  --cover-evidence work/cover-evidence.json \
  --json work/output/Book_Full_REVIEW.digital-policy.json
~~~

Omit `--cover-evidence` when there are no visually verified covers. Ordinary users do not need to run commands or handle configuration.
