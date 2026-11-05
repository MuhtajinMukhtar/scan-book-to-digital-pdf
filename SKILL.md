---
name: scan-book-to-digital-pdf
description: Convert a scanned book PDF into a readable, selectable-text digital PDF with a short user-approved pilot. Use in ChatGPT Work/Codex when the user supplies only a PDF plus the repo URL; use low-resource local OCR, deterministic PDF rendering and strict per-page QA. Avoid heavy PP-StructureV3 on Macs with memory or segmentation-fault issues.
---

# Scan Book to Digital PDF

## Simple user experience

When a nontechnical person provides a scanned PDF and this repository URL, **proceed using this Skill**. Don't ask whether they want to use the repo. The aim is a visible, selectable digital text book, **not** an unchanged bitmap scan with hidden OCR. Never overwrite the original.

Default to source-like fonts, margins, type hierarchy and paragraph indentation where supported. If needed, ask one simple question such as "Mau huruf seperti buku aslinya, atau dibuat lebih besar?" Do not ask the user to choose Python, OCR engines, model downloads, or page numbers.

**Model-light:** use a lighter/fast model to run the deterministic scripts and summarize QA. Escalate only difficult source-specific exceptions. Never send whole-book OCR results into model context.

## Safe two-page pilot

**Default OCR: Apple Vision + Tesseract on an authorized Mac. Never start PaddlePaddle or PP-StructureV3 automatically.**

1. Check source PDF count/hash, actual macOS execution, free disk, and whether `tesseract` has **both `ind` and `eng` languages**. Read `references/mac-setup.md`. If missing, stop **before** costly jobs and request permission for minimal local installation. Do not run Apple Vision on Ubuntu/Linux.
2. Use the deterministic driver: `python scripts/run_book.py pilot --source BOOK.pdf --work-dir ./work`. It chooses two likely text pages from low-resolution thumbnails and runs Apple Vision + Tesseract only for those pages. It caches recognized lines and makes an actual digital pilot PDF plus a side-by-side comparison.
3. **Cache reuse:** preserve previous `work/ocr/page_###.json` Apple Vision results. Tesseract results and independent comparisons are written in `work/tesseract/` and `work/fusion_safe/`. These results are **not equivalent to Apple Vision + PaddleOCR PP-StructureV3**. Differences require source-image checking. Do not overwrite legacy Paddle caches.
4. For font/spacing changes, reuse OCR via `--skip-ocr` and the same selected pages. The current automatic renderer is conservative: ordinary text can become visible vector text, while complex photos, tables, chapter ornaments and uncertain pages can remain **clearly labeled searchable-scan fallbacks**. It does **not** yet faithfully reproduce every bold/italic run, paragraph indent or decorative design of the previous manually curated pilot.
5. Confirm at least **two genuinely typeset text pages** with visible/selectable glyphs, no hidden-scan pretence. Check font, left/right margins, first/last source words and QA warnings. Run `scripts/pilot_typeset_gate.py`; see `references/pilot-and-style-lock.md`. If it fails, report `PILOT_INCOMPLETE` and do not solicit full-book approval.
6. Present the review PDF and comparison in simple language. Expand the pilot to more varied examples only if needed and the first lightweight step works, ideally reusing OCR results.

## Full-book gate

**Stop at `PILOT_AWAITING_APPROVAL`.** After the user has actually accepted the **specific** digital pilot version (never self-approve), run:

```sh
python scripts/run_book.py approve --source BOOK.pdf --work-dir ./work --confirm APPROVE_PILOT
python scripts/run_book.py full --source BOOK.pdf --work-dir ./work
```

Physical source page N must equal output page N: same page count, dimensions, order and page-specific content; no silent overflow to N+1. If text does not fit within approved typography, keep that **same original page** as a searchable-scan fallback and flag it. Do not clip, omit or silently shrink text. Run the strict `scripts/page_fidelity_audit.py` on a complete, source-verified OCR reference and read `references/page-fidelity.md` plus `references/qa-and-handoff.md`. A full output remains **REVIEW** until real source comparisons and exception review pass.

## Safety and truthful reporting

- **PP-StructureV3 is opt-in advanced legacy code** (disabled in the safe driver). It is a multi-model parser and produced high RAM usage and a native convolution segmentation fault in real Mac testing. `scripts/mac_hybrid_ocr.py` now requires explicit `--ack-heavy-ppstructure`. Never repeat such a crash on the same environment or redirect it to lower-memory Ubuntu.
- Tesseract uses different algorithms; quality is **not guaranteed equivalent** to successful prior PaddleOCR results. Review uncertainty against actual scans; don't invent missing text.
- If the safe second OCR isn't available, stop before doing a heavy run and ask permission for a small install. Never claim a second OCR ran if it did not; never silently substitute cloud OCR.
- Stop when Mac is hot/sluggish, resources constrained, or Work/Codex quota heavily consumed; preserve checkpoints and cached results. No parallel heavy OCR workers. Do not alter production or publish copyrighted scans/fonts.
- Prefer short status reports. Run `python -m unittest discover -s tests -v` for script QA. Synthetic CI passing **does not prove Mac M1 runtime stability, full visual fidelity or low usage**.

## Supporting instructions

- `references/mac-setup.md` — safe Mac setup.
- `references/resource-budget.md` — staged resource limits and caches.
- `references/pilot-and-style-lock.md` — style profile, pilot and human approval.
- `references/page-fidelity.md` — physical page fidelity and QA.
- `references/qa-and-handoff.md` — final acceptance.
