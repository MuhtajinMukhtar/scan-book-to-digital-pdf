# Resource budget: practical on 8–16 GB Macs

**Goal:** Save both Work/Codex model quota and Mac RAM. The skill runs Apple Vision locally first and uses PP-OCRv5 Mobile selectively. No PP-StructureV3, no second OCR for every page.

## Execution budget

1. Read PDF metadata/page count and survey **low-resolution thumbnails only**. Choose two text pages for an **internal** technical smoke test; do not call those pages a complete user-approved pilot. Do not render all 220 pages at high DPI.
2. Apple Vision scans those **two pages** at ~180 DPI and stores normalized text JSON by source SHA and physical page number. It was the OCR foundation of the original successful Mac experiment.
3. Inspect line confidence. Only empty/very short, very low confidence, or partial confidence data triggers a **candidate second opinion**. Confidence is a heuristic and cannot certify perfect text.
4. If Mobile is needed, ask the user before installing packages/downloading models. Run one **PP-OCRv5 Mobile** page in an isolated monitored process; no PP-StructureV3. Downsize the Mobile image to maximum 1500px (longest edge); default process RSS cap is 1600 MB on <=10 GB machines, 2600 MB on <=18 GB and 3600 MB otherwise. The cap is deliberately conservative: if Mobile can't run within it, retain the Apple cache, flag review and **do not silently raise the limit**.
5. If the Mobile process exceeds RSS cap, 150s timeout, or crashes, stop that child, write a review flag, and do not retry repeatedly. Nothing should overwrite the source or Apple Vision cache.
6. If the two-page smoke works, automatically expand to **6–8 distinct, visually confirmed sample pages** (default seven), incorporating table, illustration, chapter opening, rich typography/quotation and sparse/profile pages when they exist. Inspect low-resolution contact sheets and reuse existing OCR pages. Process only new pages; keep optional Paddle Mobile selective. Stop if Mac slows or quota is strained. Two-pages-only cannot be approved for a substantial book.
7. **Fonts/layout changes reuse OCR** using `--skip-ocr`. Final representative review uses `python scripts/run_book.py pilot --stage review ...` rather than repeating the initial two-page smoke. For installing and running optional Mobile after Apple, use `--reuse-apple --enable-mobile`; never re-OCR unchanged source pages.
8. Full-book processing should remain checkpointed and reviewable. The user may need to approve extra resource usage for a large book; the result is REVIEW until source-based page QA passes.

## Reality checks

- A **lightweight ChatGPT model** can invoke scripts, report QA and ask for approval. It is not necessary to send whole-book text to Sol/Terra High.
- Mac RAM usage and ChatGPT Work/Codex quota are different resources. Neither can be inferred from the other.
- The RAM cap monitors child-process RSS; total Mac memory pressure can still be affected by other apps. When the user reports heat/sluggishness, **stop**, preserve caches and report the precise blocker.
- The official Mobile models are smaller than PP-StructureV3, but performance on **M2 8 GB** is not yet certified by a real pilot.
- Never describe a normal Apple-only page as having been checked by PaddleOCR. Never call a scan overlay a digitally retypeset page.
- Prevent page N text from moving to page N+1 and never silently crop, omit or shrink text.

## One-line user status

"Uji teknis dua halaman sudah berhasil. Saya pilih contoh tambahan yang benar-benar berbeda—termasuk tabel atau ilustrasi jika ada—sebelum meminta persetujuan Anda."
