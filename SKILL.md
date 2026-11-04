---
name: scan-book-to-digital-pdf
description: Digitize a scanned book PDF into a readable, searchable, selectable-text PDF with images and source-aware typography. Use for OCR, retypesetting, or restoring printed books from scans, especially with Mac Apple Vision plus PaddleOCR PP-StructureV3 cross-checks. Guide nontechnical users through simple font, size, and paragraph choices while handling OCR, QA, and difficult page layouts yourself.
---

# Scan Book to Digital PDF

## The conversation should be simple

The user may say only: "Tolong jadikan PDF buku ini buku digital yang nyaman dibaca, mengikuti https://github.com/MuhtajinMukhtar/scan-book-to-digital-pdf." They may provide a PDF as an attachment. Do not require them to know words such as OCR, PP-StructureV3, SHA-256, or command line.

- If no PDF is attached, ask for the PDF.
- Default to a faithful layout and source-like font and paragraph starts. If necessary, ask *one friendly question at a time*, phrased in everyday terms: "Mau huruf seperti buku biasa atau bergaya modern?", "Ukuran tulisan seperti aslinya atau lebih besar?", "Awal paragraf menjorok atau rata kiri?". Offer "biarkan seperti aslinya". Do not ask all questions when defaults suffice.
- Report progress as plain language: pages checked, uncertain pages, review PDF. Keep technical logs inside work files, not in the user's chat.
- Do not make the user manually choose the OCR engine. On a compatible Mac, use both engines below.

## Source protection and preferences

Record page count, original SHA-256, file metadata and output destination. Never overwrite the original or an approved prior version. Default to exact source-page mapping unless the user expressly asks for repagination. Respect explicit preferences: body serif (Georgia if installed and licensed, else open serif) or sans-serif; source-estimated or specified font size; first-line indent as source / yes / no. Preserve source headings, italics, photos, diagrams, tables, logos, quotes, forms, footers and reading order. Never redistribute copyrighted scans or font files.

## Mac-first dual-OCR pipeline (mandatory for the full run)

1. Set up an isolated Mac Python environment using `references/mac-setup.md`. Verify a real Apple Vision and PaddleOCR PP-StructureV3 installation before processing. Use no production systems or global package changes.
2. Run `python scripts/mac_hybrid_ocr.py BOOK.pdf --work-dir ./work`. This invokes `scripts/ocr_book.py` with Apple Vision, then PP-StructureV3 on **the same cached page images**, saves raw Paddle JSON and Markdown, and generates per-page comparison reports at `work/fusion/`.
3. Read the **raw** `overall_ocr_res.rec_texts` from Paddle JSON, not just its Markdown rendering. The successful prototype recovered seven lines omitted by Paddle Markdown on a five-page pilot; never assume Markdown is complete. Check `paddle_raw_not_in_markdown`, `paddle_not_in_apple`, `apple_not_in_paddle`, and spelling/wording variant warnings. All are **review candidates**, not automatically approved corrections.
4. Confirm missing text and disputed names against **the original page image** before applying a correction. Compare both engines line-by-line; neither engine is authoritative by itself. Preserve uncertainty in a page-specific issue ledger. Do not invent text based on context alone.
5. Classify every page and compose digitally typeset text from the verified reading order with the chosen size, font, paragraph indentation and justified body. Use original cropped photographs/illustrations. See `references/page-archetypes.md`. For a page that cannot safely be rebuilt, preserve the source image with a selectable OCR layer and mark that page explicitly as a searchable-scan fallback.
6. Write one manifest entry for each original page: source/output page, type, OCR engines, accepted corrections, image checks, digital or searchable-scan status, exceptions and visual-review status.
7. Use `scripts/pdf_audit.py` to verify source-word coverage, page mapping, embedded fonts, no blank/clipped pages and images, and source/output visual comparison. Read `references/qa-and-handoff.md`. Do not suppress failures to report success.
8. Deliver a review PDF and concise outstanding-page summary. Mark final only after the user accepts the editorial result. Run `scripts/lossless_optimize.py` only on a copy and verify rendering/text parity.

## Operational boundaries

- This is **not** a one-click universal retypesetter: the AI agent must perform editorial reconstruction of complex pages. `mac_hybrid_ocr.py` prepares source comparisons; it does not generate the final book by itself.
- If Paddle cannot run on the Mac, **do not silently continue Apple-only** and pretend the output passed dual-OCR; report the installation problem and offer the user a safe next step.
- If the current ChatGPT Work or Codex environment cannot execute Mac software, say so briefly. Obtain a permitted Mac execution environment instead of fabricating OCR outputs.
- Preserve cache/source identity. Never automatically overwrite existing OCR results from another source. Do not publish private files in the repository.
- Use `--compare-only` to re-evaluate existing caches without re-running OCR.
