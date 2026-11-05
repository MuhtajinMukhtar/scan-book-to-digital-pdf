---
name: scan-book-to-digital-pdf
description: Digitize scanned PDF books into readable, selectable-text PDFs using Apple Vision first and selective lightweight PaddleOCR Mobile for uncertain pages on Mac, with a sample pilot, user approval, exact page mapping, and source-based QA. Use in ChatGPT Work or Codex when a user shares a scanned book and this GitHub repo, including on 8–16 GB Apple Silicon Macs.
---

# Scan Book to Digital PDF

## User experience: PDF + repository link is enough

When the user attaches a scanned book and this repo link, proceed with the workflow; **do not ask whether to use the repo**. Do not burden a nontechnical user with OCR methods or CLI commands. Ask simple questions only when an optional download, a visual choice, or approval really needs their decision. Keep the original PDF untouched. Use a lightweight agent/model for orchestration; handle exceptions with more reasoning only when necessary.

## Core design

- **Primary:** Apple Vision for every processed page, cached in `work/ocr/page_###.json`. This was the successful starting point of the original Mac book experiment.
- **Secondary (selective only):** `PP-OCRv5_mobile_det` + `PP-OCRv5_mobile_rec` via `PaddleOCR`, on *uncertain source pages* only. Not PP-StructureV3, not Tesseract by default. Never infer that PaddleOCR Mobile has the same accuracy as the previous PP-StructureV3 pilot.
- **Light-Mac safety:** process one Mobile page at a time in a monitored child process, with RAM/time limits and small inputs. Skip mobile when no doubt is detected. A model must never be downloaded without permission. If Mobile fails, keep Apple results and flag the page for source review; no automatic expensive retry.
- **Typesetting:** every **non-cover page containing text** must have visible, selectable, genuinely typeset PDF text. An original full-page scan with hidden OCR is **not** a finished page. Source photos, drawings and decorations can remain as separate raster assets, but table cells, quotes and text surrounding illustrations must be digital. Only source-verified **front/back covers** may remain as whole-page scans. The current engine is incomplete on complex layouts; never claim unsupported pages were converted. Read `references/digital-text-policy.md`.

## Pilot: two-stage, genuinely representative

**Critical:** Two body-text samples are a useful *internal smoke test* but **not a complete editorial pilot** for books with pictures, charts, tables, or different typography. A long book must show varied archetypes before approval. User gives **only the PDF and repo link**; agent handles the workflow without questions unless permission is required.

1. **Preflight:** verify authorized macOS, source PDF hash/page count, disk and virtual environment. Apple Vision is the main OCR. No PP-StructureV3; Mobile secondary only for uncertain lines after permission. Read `references/mac-setup.md`.
2. **Internal two-page smoke:** `python scripts/run_book.py pilot --source BOOK.pdf --work-dir ./work`. It selects two text pages and checks the engine at low cost. Status `PILOT_SMOKE_COMPLETE` **must not be presented as a user-approvable final pilot**. If the technical smoke fails, stop and diagnose that fault rather than scaling up.
3. **Representative review pilot (default seven pages):** `python scripts/run_book.py pilot --stage review --source BOOK.pdf --work-dir ./work`. This reuses existing Apple OCR page caches and adds roughly five **different** source pages: a table/form, image/illustration, chapter opener, mixed typography/quote and shorter/profile content *when present*. For very short books it can use fewer pages; for long books choose **6–8 diverse pages**. The sampler uses **low-resolution visual heuristics**, not reliable table recognition: inspect `work/pilot/Source_Review_Candidates.pdf` and `review-selection.json`, visually confirm the actual page types. If a candidate is mislabeled or misses a genuine recurring format, rerun review with confirmed nonconsecutive pages: `--pages 18,40,74,90,124,149,212` (replace numbers with actual source physical pages). Choose **representatives of recurring layouts**, not merely visually odd one-offs. **Never run full-book OCR to discover sample types.**
4. **Verify the real draft:** the file `Book_Pilot_Comparison.pdf` must show the selected content as genuinely *newly typeset, visible text* rather than duplicating the source scan. A screenshot can look perfect because it is still the original scanned page. Inspect the per-page QA: `fallback_sample_pages` and `fallback_source_pages`. **If any sampled page is `searchable_scan_fallback`, the pilot status must remain `PILOT_NEEDS_LAYOUT_WORK` and the agent must not request approval for full-book digital conversion.** First reconstruct its text around photo/illustration assets, table content, chapter art or quotation formatting; reuse Apple Vision caches. Never claim image-only source artwork must turn into vector graphics, but all source textual content must be visibly digital. Source-like margins, paragraph leading, source-verified italics, footer numbers and no cross-page spill remain compulsory. Read `references/typography-and-style-review.md`, `references/pilot-and-style-lock.md` and `scripts/pilot_typeset_gate.py`.
5. **Uncertain OCR:** inspect `work/review/SUMMARY.json`. Apple Vision is primary. If a genuine text segment needs a second opinion, ask permission for optional PP-OCRv5 Mobile; then use `--reuse-apple --enable-mobile` (and `--allow-model-download` only after separate permission). Run Mobile on at most one uncertain page per batch; never all sampled pages by default. If only font/spacing changes, rerender with `--skip-ocr`. For verified italic phrases use source-backed `work/style-annotations.json`; do not hallucinate formatting.
6. **Approval:** a complete source-inspected **review-stage** pilot with diverse source pages and **zero full-page searchable-scan fallbacks** is required for `PILOT_AWAITING_APPROVAL`. The `approve` command rejects smoke-test or `PILOT_NEEDS_LAYOUT_WORK` states. If a layout type is unsupported, accurately say `belum berhasil ditata ulang` and fix the engine, **not** quietly approve the remaining 220 pages. Present the actual verified result and ask one simple question about its appearance. Never self-approve.

## Only after explicit approval

After the user genuinely accepts the **diverse review-stage** digital pilot (not the internal smoke test), run:

```sh
python scripts/run_book.py approve --source BOOK.pdf --work-dir ./work --confirm APPROVE_PILOT
python scripts/run_book.py full --source BOOK.pdf --work-dir ./work
```

Process the remaining pages with Apple Vision first, reusing caches. Run optional selective Mobile later or with `--enable-mobile` only when it was authorized and resource feasibility is known. The full-book output is always a **REVIEW** until source comparisons and unresolved pages are resolved; it is never automatically FINAL.

**Hard page contract:** Source physical page N must remain output page N: same total count, dimensions and reading order. No missing or overflowed content may move into N+1. Preserve any nonfitting page temporarily as an incomplete searchable-scan draft rather than losing it, but **never classify the book as finished** while any non-cover page is still fallback. After `run_book.py full`, the new mandatory `digital_text_policy_gate.py` returns `INCOMPLETE_DIGITAL_PAGES` with source page numbers and a nonzero exit code if the rule is violated. Only actual source-verified first/last covers are exempt; the AI verifies source artwork and records its hash in local `work/cover-evidence.json` **before pilot approval**. Without that evidence no cover is exempt. Passing the digital gate still requires separate editorial/source fidelity QA. Consult `references/page-fidelity.md` and `references/qa-and-handoff.md`; audit every page with `scripts/page_fidelity_audit.py` using a source-verified OCR reference.

## Stop conditions and honesty

- Never call `scripts/mac_hybrid_ocr.py` or PP-StructureV3 automatically. Its old multi-model implementation led to large RAM usage and a segmentation fault in testing on Mac. The heavy legacy path remains explicit opt-in only, and should not be retried on the same failed environment.
- An 8 GB Mac is a *target*, not a certified hardware guarantee. If Mobile hits its RSS/time cap, skip it, preserve the Apple cache and report the specific failure. Do not reroute to the user's smaller Ubuntu server or run a parallel batch.
- Model downloads, software installation and full-book processing require their respective permissions/approval. Don't change Mac system Python or power settings, and don't publish copyrighted scans or fonts to the public repo.
- GitHub synthetic tests cover logic and safety gates; **a real Mac M2/8 GB pilot and quality benchmark remain necessary** before promising resource or fidelity results.

## References

- `references/mac-setup.md` — lightweight installation and compatibility
- `references/resource-budget.md` — bounded work, cache and stop rules
- `references/pilot-and-style-lock.md` — visual pilot and typography
- `references/page-fidelity.md` — source-to-output page proof
- `references/qa-and-handoff.md` — editorial acceptance
- `references/digital-text-policy.md` — mandatory fully digital non-cover pages, cover exceptions and completion gate
- `references/typography-and-style-review.md` — pilot paragraph rhythm, verified italics, footer and image/table review
