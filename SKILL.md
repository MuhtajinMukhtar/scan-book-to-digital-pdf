---
name: scan-book-to-digital-pdf
description: Digitize scanned PDF books into readable, selectable-text PDFs using Apple Vision first and selective lightweight PaddleOCR Mobile for uncertain pages on Mac, with a sample pilot, user approval, exact page mapping, and source-based QA. Use in ChatGPT Work or Codex when a user shares a scanned book and this GitHub repo, including on 8–16 GB Apple Silicon Macs.
---

# Scan Book to Digital PDF

## User experience: PDF + repository link is enough

### Fresh-start checkpoint priority (mandatory)

When a user provides **only a PDF and repository URL in a new Work/Codex chat**, first read the **current** `main` `SKILL.md` and verify the source PDF identity. **Do not let stale reports or previous experiments dictate the workflow.** In a blind run, do not inspect prior Work sessions, historic checkpoints, or source-specific style references. Reuse raw cached OCR only if the source SHA matches; otherwise perform a fresh, limited Apple Vision smoke test on the Mac.

**No unnecessary fork in front of a nontechnical user.** If an authorized Mac with Apple Vision is available, proceed there; **never suggest Ubuntu for Apple Vision**, and never propose repeating PP-StructureV3. Ask the user about installation or downloads only when needed and explicitly permitted. Verify actual current resource failures before stopping; do not extrapolate prior crashed experiments to the new lightweight workflow. Preserve user files and old caches.

Never assume another chat's PDFs are present. A GitHub code rollback does not revert PDFs already generated elsewhere.

When the user attaches a scanned book and this repo link, proceed with the workflow; **do not ask whether to use the repo**. Do not burden a nontechnical user with OCR methods or CLI commands. Ask simple questions only when an optional download, a visual choice, or approval really needs their decision. Keep the original PDF untouched. Use a lightweight agent/model for orchestration; handle exceptions with more reasoning only when necessary.

## Core design

- **Primary:** Apple Vision for every processed page, cached in `work/ocr/page_###.json`. This was the successful starting point of the original Mac book experiment.
- **Secondary (selective only):** `PP-OCRv5_mobile_det` + `PP-OCRv5_mobile_rec` via `PaddleOCR`, on *uncertain source pages* only. Not PP-StructureV3, not Tesseract by default. Never infer that PaddleOCR Mobile has the same accuracy as the previous PP-StructureV3 pilot.
- **Light-Mac safety:** process one Mobile page at a time in a monitored child process, with RAM/time limits and small inputs. Skip mobile when no doubt is detected. A model must never be downloaded without permission. If Mobile fails, keep Apple results and flag the page for source review; no automatic expensive retry.
- **Typesetting:** every **non-cover page containing text** must have visible, selectable, genuinely typeset PDF text. An original full-page scan with hidden OCR is **not** a finished page. Source photos, drawings and decorations can remain as separate raster assets, but table cells, quotes and text surrounding illustrations must be digital. Only source-verified **front/back covers** may remain as whole-page scans. The current engine is incomplete on complex layouts; never claim unsupported pages were converted. Read `references/digital-text-policy.md`.

## Source-detected typography and warm-paper default

**Never hardcode one book's alignment for another.** In a blind pilot, inspect source-matching Apple Vision line boxes and verify representative body paragraphs visually. The deterministic helper `scripts/book_style.py` decides among `left` (ragged right), `justify`, or `source_uncertain`. **Only source-justified books should get bounded justification.** Normalize duplicated OCR spaces. Maintain normal word spacing; a paragraph-final line stays natural. Do not force ragged source text to fill the right margin.

- **Ordinary prose pages:** derive dominant left/right margins, leading and paragraph gaps from multiple source pages. Apply only conservative alignment/spacing corrections; never compress an entire page or shift its illustrations/table design. Genuine first-line indentation, centered quotes and exceptional sections stay source-specific. If OCR geometry is ambiguous, the agent may source-verify and record `work/book-style-override.json` with the actual PDF SHA and `source_scan_verified:true`; do not silently invent alignment.
- **Bold/italic:** Apple Vision does not certify bold or italic typography. After actually inspecting original scans, record exact phrases in `work/style-annotations.json` with `bold_spans` and/or `italic_spans`, each having `source_scan_verified:true`. If matching local font files do not exist, report the exception rather than falsely claiming emphasis was retained.
- **Background:** use `cream` (very pale warm off-white) as the default on ordinary newly typeset pages. Preserve original colors of special designs and artwork. Do **not** offer a white version at the start. **Only after the main book has been generated, source-checked and accepted**, offer once: "Apakah ingin dibuatkan juga versi dengan latar putih bersih?" If the user agrees, run `python scripts/run_book.py full --source BOOK.pdf --work-dir ./work --skip-ocr --white-variant`. This outputs a separate PDF and must not repeat OCR, alter paragraph layout or overwrite the cream original; inspect any source-colored raster footer.
- The pilot `style-profile.json` locks these source-derived choices, the optional source-reviewed override SHA, the background and the body font. Changing style requires rebuilding the pilot from cache and **new approval**. A successful CI test does not prove the finished book's visual quality.

Read `references/typography-and-style-review.md` for these details. Keep the workflow fully nontechnical for the user.

## Visual regression rule: restore the last preferred pilot

**Only when the user explicitly provides or requests a prior approved/preferred pilot after the blind test**, use it as a visual baseline. When a revised pilot looks worse, do not replace it merely to obtain more digitally typeset pages. Preserve the earlier PDF and all OCR/source caches; restore that PDF as the visual reference while recording any still-incomplete digital pages honestly. Never approve full-book conversion from a scan-fallback preview.

**Do not redesign entire pages to fix a paragraph.** Retain original relative font scale, paragraph density, margins, illustration size/placement, quote treatments and table proportions. Only modify the proven defect on affected source pages. Compare before/after page images and page QA *for every changed page*. If quality deteriorates, reject the new draft and keep the prior reference. No silent smaller fonts, collapsed whitespace, moved figures or global formatting changes.

An edited PDF produced in a separate ChatGPT Work session is **not automatically reverted by a GitHub code rollback**. When that session's prior accepted output exists, use it explicitly as a reference. If it is unavailable, compare against the original source instead of claiming to have restored it. Re-render with existing source-verified OCR caches (`--skip-ocr`), never repeat full-book OCR just for a layout rollback.

### Blind evaluation is the default

When the user submits **only the scanned PDF and repository link**, independently derive font, margins, layout styles, representative pages and OCR corrections **from the current source PDF**. This is a blind pilot. Do **not** search earlier chats, archived branches/commits, old pilot PDFs, source-specific benchmark metrics or past editorial decisions to tune the result. Do not hardcode prior page selections or preferred font sizes. Source-matched reusable OCR caches are permitted for efficiency, but their existence is not proof of editorial quality.

First create the internal two-page smoke test, then an independently selected 6–8-page representative review pilot. Show the source-vs-output comparison and per-page QA. Do not process the entire book without explicit user approval. If the user *later asks* for comparison to an earlier favorite pilot, use `scripts/visual_regression_gate.py` with an explicitly supplied baseline **after** the blind pilot has been generated; this is an optional independent validation, not part of default creation. Do not claim the metrics alone prove visual equivalence.

## Pilot: two-stage, genuinely representative

**Critical:** Two body-text samples are a useful *internal smoke test* but **not a complete editorial pilot** for books with pictures, charts, tables, or different typography. A long book must show varied archetypes before approval. User gives **only the PDF and repo link**; agent handles the workflow without questions unless permission is required.

1. **Preflight:** verify authorized macOS, source PDF hash/page count, disk and virtual environment. Apple Vision is the main OCR. No PP-StructureV3; Mobile secondary only for uncertain lines after permission. Read `references/mac-setup.md`.
2. **Internal two-page smoke:** `python scripts/run_book.py pilot --source BOOK.pdf --work-dir ./work`. It selects two text pages and checks the engine at low cost. Status `PILOT_SMOKE_COMPLETE` **must not be presented as a user-approvable final pilot**. If the technical smoke fails, stop and diagnose that fault rather than scaling up.
3. **Representative review pilot (default seven pages):** `python scripts/run_book.py pilot --stage review --source BOOK.pdf --work-dir ./work`. This reuses existing Apple OCR page caches and adds roughly five **different** source pages: a table/form, image/illustration, chapter opener, mixed typography/quote and shorter/profile content *when present*. For very short books it can use fewer pages; for long books choose **6–8 diverse pages**. The sampler uses **low-resolution visual heuristics**, not reliable table recognition: inspect `work/pilot/Source_Review_Candidates.pdf` and `review-selection.json`, visually confirm the actual page types. If a candidate is mislabeled or misses a genuine recurring format, visually confirm a replacement from this source's thumbnails and rerun review with its actual physical page numbers using the `--pages` option. Never copy page selections from documentation or older books. Choose **representatives of recurring layouts**, not merely visually odd one-offs. **Never run full-book OCR to discover sample types.**
4. **Verify the real draft:** the file `Book_Pilot_Comparison.pdf` must show the selected content as genuinely *newly typeset, visible text* rather than duplicating the source scan. A screenshot can look perfect because it is still the original scanned page. Inspect the per-page QA: `fallback_sample_pages` and `fallback_source_pages`. **If any sampled page is `searchable_scan_fallback`, the pilot status must remain `PILOT_NEEDS_LAYOUT_WORK` and the agent must not request approval for full-book digital conversion.** First reconstruct its text around photo/illustration assets, table content, chapter art or quotation formatting; reuse Apple Vision caches. Never claim image-only source artwork must turn into vector graphics, but all source textual content must be visibly digital. Source-like margins, paragraph leading, source-verified italics, footer numbers and no cross-page spill remain compulsory. Read `references/typography-and-style-review.md`, `references/pilot-and-style-lock.md` and `scripts/pilot_typeset_gate.py`.
5. **Uncertain OCR:** inspect `work/review/SUMMARY.json`. Apple Vision is primary. If a genuine text segment needs a second opinion, ask permission for optional PP-OCRv5 Mobile; then use `--reuse-apple --enable-mobile` (and `--allow-model-download` only after separate permission). Run Mobile on at most one uncertain page per batch; never all sampled pages by default. If only font/spacing changes, rerender with `--skip-ocr`. For source-verified bold/italic phrases use `work/style-annotations.json`; do not hallucinate formatting.
6. **Approval:** a complete source-inspected **review-stage** pilot with diverse source pages and **zero full-page searchable-scan fallbacks** is required for `PILOT_AWAITING_APPROVAL`. The `approve` command rejects smoke-test or `PILOT_NEEDS_LAYOUT_WORK` states. If a layout type is unsupported, accurately say `belum berhasil ditata ulang` and fix the engine, **not** quietly approve the remaining 220 pages. Present the actual verified result and ask one simple question about its appearance. Never self-approve.

## Only after explicit approval

After the user genuinely accepts the **diverse review-stage** digital pilot (not the internal smoke test), run:

```sh
python scripts/run_book.py approve --source BOOK.pdf --work-dir ./work --confirm APPROVE_PILOT
python scripts/run_book.py full --source BOOK.pdf --work-dir ./work
```

Process the remaining pages with Apple Vision first, reusing caches. Run optional selective Mobile later or with `--enable-mobile` only when it was authorized and resource feasibility is known. The full-book output is always a **REVIEW** until source comparisons and unresolved pages are resolved; it is never automatically FINAL.

**Hard page contract:** Source physical page N must remain output page N: identical total page count and reading order, **one uniform physical PDF page size across the entire output (including covers)**, and no content cropped or moved to the following page. Scanned source page-box dimensions may differ from one another; do not reproduce that scanning irregularity. No missing or overflowed content may move into N+1. Preserve any nonfitting page temporarily as an incomplete searchable-scan draft rather than losing it, but **never classify the book as finished** while any non-cover page is still fallback. After `run_book.py full`, the new mandatory `digital_text_policy_gate.py` returns `INCOMPLETE_DIGITAL_PAGES` with source page numbers and a nonzero exit code if the rule is violated. Only actual source-verified first/last covers are exempt; the AI verifies source artwork and records its hash in local `work/cover-evidence.json` **before pilot approval**. Without that evidence no cover is exempt. Passing the digital gate still requires separate editorial/source fidelity QA. Consult `references/page-fidelity.md` and `references/qa-and-handoff.md`; audit every page with `scripts/page_fidelity_audit.py` using a source-verified OCR reference.

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
