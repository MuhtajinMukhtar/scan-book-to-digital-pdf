# Cost- and device-safe pilot execution (for AI agents)

The intended experience is **attach a scanned PDF + give the repository URL**. Users must not need to manage tools, engines, caches, hardware, or CLI options. The agent owns the complexity.

## Why this rule exists

Two OCR engines, high-resolution page images, repeated visual comparison and typesetting can be resource-intensive. The previous PP-StructureV3 method caused a high-memory segmentation fault on Mac and is now disabled in the safe default. macOS local CPU/GPU/memory usage is **not equivalent** to a ChatGPT Work/Codex usage allowance; neither can be deduced exactly from the other. A six-page example is not acceptable if it consumes most of the user's allowance or significantly slows down the Mac.

## Lightweight internal progression

1. **Preflight without heavy OCR.** Check the source page count, SHA-256, the existing cache, local resources and file type. Survey *low-resolution thumbnails* to choose representative pages. Don't load 220 high-resolution scans into model context or run full-book OCR.
2. **First two pages only.** Select one text-heavy and one visually unusual page. Run safe Apple Vision + Tesseract for these two; generate the true digitally typeset PDF, not a same-image searchable scan. Verify visible text and one-to-one page contents using `pilot_typeset_gate.py`, actual PDF fonts and side-by-side visual inspection.
3. **Reuse everything.** Cache raw Apple OCR, raw Tesseract results, page rasters, and accepted text corrections keyed to the original source SHA and page number. Re-running font/layout experiments must reuse these outputs. Rebuild **only altered page(s)**. Do not rerun dual OCR or regenerate all pages for font, margin, color or line-spacing edits.
4. **Expand only if the two-page output succeeds.** Add the remaining source-representative pages (total **5–8** or fewer for a short/simple book). Process *sequentially*, a page or small bounded batch at a time. Keep a checkpoint for each page. Do not start Paddle/PPStructureV3 or duplicate OCR workers. The safe driver defaults to 180 DPI and two local OCR threads.
5. **No approval of incomplete preview.** The actual typeset pilot needs a verified comparison and explicit user approval before the full book. A scan overlaid with invisible text is a failed/incomplete pilot.
6. **Full book only after approval + resource feasibility.** Confirm the approved style profile, available local disk/RAM, processing location, and that the user wants to spend the required compute/Work allowance. Run resumably in modest sequential batches. The original PDF must remain unchanged and page N content remain on page N.

## Operational stop conditions

- **Device:** Mac becomes unusually hot, sluggish, memory-pressure elevated, fans/runaway OCR workers, or the user reports degraded responsiveness. Save the current checkpoint; don't immediately launch another batch. Give the computer a chance to cool and ask for permission before heavy continuation. Never alter system power settings or override thermal protection.
- **Work/Codex usage:** The user reports major allowance consumption (e.g., most of a quota used) or significant concern about cost. Stop model-driven rendering/repeated iteration. Preserve all outputs and explain what is already complete and what remains. Do not claim to know a user's exact quota unless surfaced in the product UI.
- **Failed pilot:** A stage fails two attempts for the same page/layout without a new identified root cause. Stop repeated high-cost retries. Preserve the error, minimize future context, and ask for a single targeted decision when necessary.
- **No cache:** Before repeating a heavy OCR page, check why the cache is missing or invalid; do not bypass source-SHA guards.

## Optimizing quality without cutting corners

- Always use both OCR engines on pages actually processed in the approved method; compare Apple Vision and Tesseract token/line evidence against the original scan; their results are not equivalent to previous PaddleOCR benchmark results. Do **not** replace the dual-OCR requirement with a superficial text copy.
- Use script-driven extraction, comparison, rendering and testing instead of repeated reasoning over every raw text line or endless screenshots.
- Keep the same fixed source-page mapping, source-faithful typography profile, and strict QA gates. Saving resources must not mean accepting omitted text, a fake digital pilot, or silent PDF page spill.
- The correct response to resource exhaustion is **checkpoint/pause**, not an unverified final PDF.

## User-facing summary

Say, briefly, for example: "Contoh dua halaman awal sudah diperiksa. Saya melanjutkan halaman contoh lain hanya jika kualitas dan penggunaan sumber daya masih aman." If a stop condition occurs: "Saya hentikan pekerjaan berat agar komputer dan kuota tidak terkuras. Hasil sementara sudah disimpan; belum memproses seluruh buku."
