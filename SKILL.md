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
- **Typesetting:** deterministic engine composes visible PDF text from source page geometry and a locked font choice; illustrated/table/uncertain layouts may need reviewed searchable-scan fallback. The current engine does not fully reproduce all italics, images, paragraph shapes or decorative layouts automatically. Never claim that it does.

## Pilot: first two pages only

1. Verify actual authorized **macOS** execution, input SHA/page count, available local disk, and a Python virtual environment with `requirements.txt`. No Ubuntu fallback for Apple Vision. Read `references/mac-setup.md`.
2. Run `python scripts/run_book.py pilot --source BOOK.pdf --work-dir ./work`. This selects two representative text pages from low-res thumbnails, performs Apple Vision only and checks each page's confidence; the model is **not** used for every page.
3. Inspect `work/pilot/Book_Pilot_REVIEW.pdf` and `Book_Pilot_Comparison.pdf`. Compare *real visible text* against the source, including font family/size, punctuation, italic emphasis, margins (allow intentional mirrored margins), first/last lines, images, and fixed page boundaries. Use `scripts/pilot_typeset_gate.py`. The same raster scan with an invisible OCR overlay is **not** a satisfactory pilot.
4. If `work/pilot/pilot-status.json` says `PILOT_NEEDS_OCR_REVIEW`, check `work/review/SUMMARY.json`. For doubtful pages, request permission in ordinary language: **"Boleh saya pasang pemeriksa teks ringan untuk bagian yang belum jelas?"** Only with permission, install a compatible PaddleOCR Mobile environment and download its Mobile model weights as needed, per `references/mac-setup.md`. Then use:
   `python scripts/run_book.py pilot --source BOOK.pdf --work-dir ./work --reuse-apple --enable-mobile --allow-model-download`
   This must **reuse Apple Vision cache**. Run Mobile only for selected low-confidence pages, never all pages. If models were previously cached and download not needed, omit `--allow-model-download`.
5. Review actual disagreements in `work/fusion_mobile/` against the source scan. A secondary OCR result is *suggestion*, not an automatically accepted correction. Maintain a per-page ledger; fix verified textual mistakes without inventing words. If a pilot is incomplete or source review remains unresolved, do not seek approval yet. Additional distinct sample pages are allowed **only after the first two-page trial is feasible**, and should reuse existing caches.
6. Present the real pilot and ask: **"Apakah contoh ini sudah cocok, atau perlu diperbaiki?"**. Stop before processing the entire book. No silent approval.

## Only after explicit approval

After the user genuinely accepts the specific digital pilot, run:

```sh
python scripts/run_book.py approve --source BOOK.pdf --work-dir ./work --confirm APPROVE_PILOT
python scripts/run_book.py full --source BOOK.pdf --work-dir ./work
```

Process the remaining pages with Apple Vision first, reusing caches. Run optional selective Mobile later or with `--enable-mobile` only when it was authorized and resource feasibility is known. The full-book output is always a **REVIEW** until source comparisons and unresolved pages are resolved; it is never automatically FINAL.

**Hard page contract:** Source physical page N must remain output page N: same total count, dimensions and reading order. No missing or overflowed content may move into N+1. Preserve any nonfitting page on its own source page as a labeled searchable-scan fallback instead of clipping, shrinking or silently discarding text. Consult `references/page-fidelity.md` and `references/qa-and-handoff.md`; audit every page with `scripts/page_fidelity_audit.py` using a source-verified OCR reference.

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
