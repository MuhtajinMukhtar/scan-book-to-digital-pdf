# Scan Book to Digital PDF

Turn scanned books into **readable PDFs with selectable, searchable text**, using ChatGPT Work, Codex, or an AI coding agent. Inspired by an editorial digitization workflow, this repository contains a reusable **Skill** and practical OCR/QA utilities. **No MSO required.**

> **Status:** OCR, per-page caches, QA and optimization tools are included. Re-typesetting of arbitrary layouts is an **agent-guided editorial stage**, not a one-click universal converter. Complex pages must be checked against their scans.

## For nontechnical users (ChatGPT Work)

1. Give ChatGPT Work your scanned PDF and this repository URL: https://github.com/MuhtajinMukhtar/scan-book-to-digital-pdf
2. Ask it to read `SKILL.md`, follow the instructions, and execute only in an authorized workspace.
3. Choose **serif (Georgia or a free alternative)** or **sans-serif**, **font size auto or a number**, and **first-line indentation source/yes/no**.
4. Ask for `*_Digital_REVIEW.pdf` and `QA.json`. Check the flagged pages before accepting.

Suggested prompt:

> Please use https://github.com/MuhtajinMukhtar/scan-book-to-digital-pdf and follow SKILL.md to digitize this uploaded scanned book. Body font: serif Georgia if available; otherwise a similar open font. Font size: estimate from source. Preserve source paragraph indentation. Keep all figures, photographs, tables, and page mapping. Give me a review PDF and page-by-page QA; tell me exactly which pages remain searchable scans instead of digitally typeset pages. Never modify the original.

## For Codex / terminal users

```bash
git clone https://github.com/MuhtajinMukhtar/scan-book-to-digital-pdf.git
cd scan-book-to-digital-pdf
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/ocr_book.py /path/to/book.pdf --out-dir ./work --engine auto --dpi 230
python scripts/pdf_audit.py /path/to/output.pdf --source-ocr-dir ./work/ocr --json ./QA.json
```

On macOS, `--engine auto` can use Apple Vision via bundled `vision_ocr.swift` if Xcode command line tools are available. On Linux install Tesseract and the language packs needed by the book. OCR output is cached per page so processing can be resumed.

## What it can and cannot promise

- **Can:** OCR pages, cache recognition, preserve source data, audit digital output, compare source OCR with generated text, and optionally optimize without intended visual loss.
- **Needs editorial work:** correctly rebuilding paragraphs, indentation, special typography, charts, multi-column text, chapter openers, forms, and source-consistent page layout.
- **Fallback:** retain scan artwork and add OCR text when complete reconstruction is unsafe; record fallback pages visibly in QA.

Never upload copyrighted books, private documents, or licensed font files to a public repository. This project does not include scans, OCR results from a real book, or fonts.

## Files

- `SKILL.md` — agent workflow and user preferences
- `scripts/ocr_book.py` and `scripts/vision_ocr.swift` — per-page OCR
- `scripts/pdf_audit.py` — independent output audit
- `scripts/lossless_optimize.py` — copy-only optimization with QA
- `references/` — layout patterns and acceptance criteria

## License

MIT. See `LICENSE`.
