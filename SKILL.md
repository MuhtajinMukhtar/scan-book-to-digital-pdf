---
name: scan-book-to-digital-pdf
description: Convert photographed or scanned book PDFs into readable digital PDFs with searchable/selectable text. Use when a user asks to digitize, OCR, retypeset, reconstruct, or make an ebook from a scanned book, retaining images and layout, and choosing serif/sans-serif, font size, and paragraph indentation. Works with ChatGPT Work, Codex, or local tools without MSO.
---

# Scan Book to Digital PDF

Follow this workflow for **the uploaded book**, not for a previously processed book. Do not assume every scanned book has the same layout.

## Ask only essential preferences
- **Body font:** serif (Georgia if legally available, else installed open serif such as Liberation Serif) or sans-serif (installed open sans such as DejaVu Sans).
- **Body font size:** auto (estimate from representative source pages) or a user-specified point size.
- **First-line indent:** source / yes / no. Default source; detect real paragraph starts from visual evidence.
- **Language(s):** infer from sample pages, confirm if ambiguous.
- **Output:** new PDF in a separate output folder. Never overwrite the input PDF.
Use source-aware defaults without blocking the user with a questionnaire.

## Execution
1. Inspect source page count, permissions, existing text, image-heavy archetypes, fonts, and SHA-256. Ask only for an uploaded source file if absent. Never publish copyright-protected source scans to GitHub.
2. Run `python scripts/ocr_book.py input.pdf --out-dir work --engine auto --dpi 230` after installing `requirements.txt` in a local virtual environment. Apple Vision requires macOS and the bundled Swift helper; otherwise install Tesseract and requested language packs. The source remains unchanged.
3. Read `work/ocr/page_*.json` and render representative original pages. Correct OCR with reference to actual scans, not only linguistic plausibility. Classify **each** page: body, cover, title, table, diagram, quotation, form, photographic, etc. See `references/page-archetypes.md`.
4. For normal pages, reconstruct paragraph order, headings, inline italics, bullets, footnotes, hyphenation, line breaks, and image placements from scan. Use a page-specific HTML/CSS or vector PDF pipeline. Use font family, point size, paragraph indent and margins selected above; justify body text with last line aligned left. Source style can override body defaults for headings/captions. Never pass raw OCR lines directly as polished prose without review.
5. For pages not safely reconstructed, use original scan **plus selectable OCR text** rather than dropping graphics. Label these `searchable_scan_fallback`, not `born_digital`.
6. Record one mapping per source page in `manifest.json`: source page, output page, page type, OCR engine, digital vs fallback, QA status, errors and reviewed corrections. Preserve one-to-one page mapping by default unless user explicitly requests repagination.
7. Run `python scripts/pdf_audit.py OUTPUT.pdf --source-ocr-dir work/ocr --strict --json QA.json`. Inspect scripts' `--help` for exact options. Check page count, all nonempty pages, selectable text, font embedding/usage, text coverage, retained photos/diagrams and clipping. Visual-review a sample of each archetype and all exceptions at readable zoom.
8. Deliver a new `*_Digital_REVIEW.pdf` plus QA/manifest. Mark final only after editorial acceptance. For optional optimization use `scripts/lossless_optimize.py` and verify parity.

## Hard rules
- Preservation takes precedence over aesthetic reflow. Never fabricate illegible words, skip pages, silently lose figures, or suppress QA failures.
- OCR is recognition, **not** a guarantee of correct text; verify source images.
- Distinguish editable/retypeset pages from scan images with a searchable OCR layer.
- Do not use MSO-specific commands, paths, credentials, private book examples, or proprietary fonts. Use tools available to the current client.
- Running a local Python/Swift/Tesseract pipeline requires a computer-enabled environment; ChatGPT Work/Codex should run it when permitted, otherwise explain what cannot run.
- Read `references/qa-and-handoff.md` before declaring success.
