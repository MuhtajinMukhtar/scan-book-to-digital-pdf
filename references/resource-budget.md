# Resource budget: practical on 8–16 GB Macs

**Goal:** Save both Work/Codex model quota and Mac RAM. The skill runs Apple Vision locally first and uses PP-OCRv5 Mobile selectively. No PP-StructureV3, no second OCR for every page.

## Execution budget

1. Read PDF metadata/page count and survey **low-resolution thumbnails only**. Choose two text-heavy pages from separated book sections; do not render all 220 pages at high DPI.
2. Apple Vision scans those **two pages** at ~180 DPI and stores normalized text JSON by source SHA and physical page number. It was the OCR foundation of the original successful Mac experiment.
3. Inspect line confidence. Only empty/very short, very low confidence, or partial confidence data triggers a **candidate second opinion**. Confidence is a heuristic and cannot certify perfect text.
4. If Mobile is needed, ask the user before installing packages/downloading models. Run one **PP-OCRv5 Mobile** page in an isolated monitored process; no PP-StructureV3. Downsize the Mobile image to maximum 1500px (longest edge); default process RSS cap is 1600 MB on <=10 GB machines, 2600 MB on <=18 GB and 3600 MB otherwise. The cap is deliberately conservative: if Mobile can't run within it, retain the Apple cache, flag review and **do not silently raise the limit**.
5. If the Mobile process exceeds RSS cap, 150s timeout, or crashes, stop that child, write a review flag, and do not retry repeatedly. Nothing should overwrite the source or Apple Vision cache.
6. Only expand to additional varied pilot pages after the first two are useful, and never generate the full book before explicit pilot approval.
7. **Fonts/layout changes reuse OCR** using `--skip-ocr`. For installing and running optional Mobile after Apple, use `--reuse-apple --enable-mobile`; never re-OCR unchanged source pages.
8. Full-book processing should remain checkpointed and reviewable. The user may need to approve extra resource usage for a large book; the result is REVIEW until source-based page QA passes.

## Reality checks

- A **lightweight ChatGPT model** can invoke scripts, report QA and ask for approval. It is not necessary to send whole-book text to Sol/Terra High.
- Mac RAM usage and ChatGPT Work/Codex quota are different resources. Neither can be inferred from the other.
- The RAM cap monitors child-process RSS; total Mac memory pressure can still be affected by other apps. When the user reports heat/sluggishness, **stop**, preserve caches and report the precise blocker.
- The official Mobile models are smaller than PP-StructureV3, but performance on **M2 8 GB** is not yet certified by a real pilot.
- Never describe a normal Apple-only page as having been checked by PaddleOCR. Never call a scan overlay a digitally retypeset page.
- Prevent page N text from moving to page N+1 and never silently crop, omit or shrink text.

## One-line user status

"Contoh dua halaman sudah dibuat dengan Apple Vision. Bagian yang masih meragukan: halaman X. Saya akan meminta izin hanya bila pemeriksaan tambahan diperlukan."
