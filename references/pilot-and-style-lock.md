# Representative pilot and typography lock (mandatory)

**Outcome:** The user sees a real, readable PDF example from their own scan before a potentially lengthy full-book run. The user approves the *actual appearance*, not a list of technical settings. Use simple Indonesian for user communication.

## 1. Inspect, sample, and estimate (without full-book OCR)

Inspect all pages using PDF page count, modest thumbnails and a non-destructive scan-quality survey. Select about **5–8 source pages** drawn from different sections, not just the first five adjacent pages. Include, when present:

- Two or more body pages (prefer one early and one late, with different paragraph density)
- A chapter opener or multi-line heading
- A quotation, italics, bullets, notes, or a special typographic page
- A page with a genuine photo or illustration
- A table, form, diagram or columns if the book contains them

Do not immediately process all candidate pages. **First implement a two-page internal technical/typographic smoke test** (one body and one representative unusual page), compare scan vs actual visible text and verify the two OCR engines and typeset guard. Reuse those results when extending to the rest of the 5–8-page pilot. Use fewer pages for short books. Expand up to 10 only when necessary to show distinct formats and the cost/device budget allows; stop for operator review if local resources or model quota are strained. If a page type has no representative sample, record this as a later exception instead of pretending the sample covers it.

**Resource gate:** Read `references/resource-budget.md` before any expensive job. Do not run PP-StructureV3 in the safe pipeline or upload all full-resolution pages into the model context. Before user approval, do not OCR/compose/export the whole book. Reading a low-resolution thumbnail or page metadata from all pages *to choose samples* is allowed.

## 2. Run dual OCR only for chosen samples

Prefer `python scripts/run_book.py pilot --source BOOK.pdf --work-dir work --pages N,M` for two representative pages (or omit `--pages` to auto-select). It calls `scripts/mac_safe_ocr.py` with Apple Vision + Tesseract once for the selection and caches both results. For additional pages, use a small separate run with the same source/work directory; never run the heavy PP-StructureV3 method automatically.

Compare Apple Vision and Tesseract output in `work/fusion_safe/`, plus the actual scan image. Tesseract's quality is not guaranteed to match the prior PaddleOCR method. Review all restored lines, proper names, unusually shaped glyphs, and discrepancies against the original scan. Keep uncertain content visible in a review log.

## 3. Build one coherent typography system

Infer style from original scans and explicit user preference. Use **intentional text roles**, not a fresh choice on each page:

| Role | Lock before approval |
|---|---|
| Body paragraphs | Font family, weight, font size (pt), color, leading, justified with last line left |
| First-line paragraphs | Indent width and when to apply it; no indent where the source denotes a special paragraph |
| Chapter titles | Font family, weight, size, alignment, before/after spacing |
| Headings/subheadings | Hierarchical size and weight, line wrapping and spacing |
| Quotes/italics | Italic family/style, indentation, quote ornament, background where present |
| Captions/footnotes | Font family, size, alignment and distance from image/text |
| Running headers/footers | Font family, size, folio placement and margins |
| Page geometry | Source page size, margins, columns, image box positioning, paragraph gap and optional hyphenation |

Use visual evidence to **approximate** scanned fonts; exact face identity may be unknowable from raster pixels. Respect the user's font/size/indent choices and keep body style identical across normal pages. Do **not** flatten the typographic hierarchy: headings may intentionally use a different size or family than body text, but the same heading role must be consistent across pages. Verify font availability and embedded font names after rendering; unexpected glyph substitutions are flagged and fixed, never treated as a new default.

Store the source image references and a machine-readable **`work/pilot/style-profile.json`** with font names, sizes, paragraph/leading rules, layout geometry, page samples, source hash, and revision number. Do not include proprietary font files in public or shared deliverables.

## 4. Guarantee fixed pages in the pilot

Render every pilot sample within an individual frame having the exact source page dimensions. A selected source page must not split into two outputs or borrow space from its neighbor. If its text cannot fit at the approved font size/line spacing, change only source-evidenced layout spacing within the requested style, or present a **searchable-scan fallback of that same page** and ask the user what to prioritize. Do **not** shrink text silently, crop, omit, or move any lines to the following page. Compare the start and end of each sampled source page with the corresponding pilot page and inspect the last paragraph/line visually.

## 5. Prove the pilot is actually reconstructed

**Do not present the same raster scan as the 'after' result.** A scan with invisible OCR words may be searchable and selectable, but it does *not* demonstrate the requested digital typography and does *not* satisfy the pilot. Distinguish three stages:
- `OCR_PREVIEW`: the original scanned pages plus a text-recognition layer. Useful internally, **not approvable** as visual pilot.
- `TYPESET_PILOT`: verified OCR rendered as visible/vector PDF text, with real font family, actual point size, paragraph spacing, indents, images retained as cropped objects, and fixed page borders.
- `PILOT_APPROVED`: user explicitly approves the **TYPESET_PILOT** version after viewing a side-by-side comparison. A prior "ya/lanjut" replying to an OCR preview cannot authorize all pages.

Run `python scripts/pilot_typeset_gate.py --source BOOK.pdf --pilot BOOK_Pilot_v1_REVIEW.pdf --source-pages 7,19,43,88,104 --json work/pilot/pilot-typeset-check.json`, replacing source indices with the real selected pages in pilot page order. **At least two representative body/content sample pages must genuinely contain visible rendered text**, not a dominant scan bitmap. Compare the PDF font names and sizes to the style profile. Exception/cover artwork can use scan fallback if marked honestly, but such pages do not count toward the minimum real typeset examples. This guard is intentionally conservative; an image-heavy page may be flagged for inspection.

Require `PASS_NEEDS_EDITORIAL_REVIEW` plus independent visual/text QA. If not passed, keep `PILOT_INCOMPLETE_SCAN_PREVIEW`, **do not ask for style approval or start full book**, and redo those pages as visible typeset samples.

## 6. Generate a real visual pilot

Generate **`<Book>_Pilot_v1_REVIEW.pdf`** (only selected source pages, each tagged with its original physical page number) and **`<Book>_Pilot_Comparison.pdf`** with source scan/result side by side or an equivalent clearly labeled comparison. Render and inspect: text accuracy and completeness, alignment, spacing, page density, title hierarchy, paragraph indents, image preservation, font consistency, and no overflow.

Check *digital text* is selectable (not merely an image with invisible OCR layer) on sample pages that can safely be typeset. If a sample is intentionally a searchable scan fallback, identify it explicitly. Save issue log and sample-page QA. Do **not** label a pilot "approved" until an explicit user decision.

Keep explanations short: **"Ini contoh beberapa halaman dari bagian berbeda. Apakah huruf, ukurannya, dan tata letaknya sudah cocok? Jika cocok, saya lanjutkan semuanya."**

## 7. Approval and revisions

Status starts **`PILOT_AWAITING_APPROVAL`**. The user may answer **only after the digital typeset gate passes and visually different source-vs-result examples have been presented**:
- **"Cocok, lanjutkan."** = explicit approval of the current pilot version/style profile (assuming no unresolved blocking QA).
- **"Huruf agak kecil", "jarak terlalu rapat", etc.** = revise pilot, increase version, compare, and request approval again.
- **No answer / unrelated conversation** = stay blocked, never launch full-book conversion automatically.

Record the approval with the exact pilot version, source SHA, style-profile SHA or revision, timestamp if available, and user decision. Do not infer approval from a tool run or the original request.

Only after approval: set status **`PILOT_APPROVED`**, use the frozen profile for all ordinary pages, reuse OCR caches, and process the remaining pages. Newly encountered layouts can get additional style-role rules without silently changing the agreed body family/size/spacing. If an unavoidable change substantially alters the accepted style, show a focused sample and request approval for that exception.

## 8. Full-book consistency QA

Before final delivery, audit:
- Page-by-page same **body family, size and leading**, apart from documented intentional exceptions.
- Same style per equivalent heading/caption/quote role. Preserve real bold/italic hierarchy.
- Embedded actual fonts, text bounds, punctuation, image/text integrity, and page count.
- No page has silently reverted to generic/default HTML font or scan-only mode.
- Source page mapping and untouched original hash remain verified.

The whole-book PDF is a **REVIEW** until final editorial acceptance. A pilot approval authorizes the full conversion; it **does not** waive final content or layout QA.

**Full-book hard gate:** every output page N must match source page N in page-specific content, not just overall word totals. Run `scripts/page_fidelity_audit.py` with complete OCR and manifest; see `references/page-fidelity.md`. A sample approval authorizes full processing but does not permit overflow or skipped pages.
