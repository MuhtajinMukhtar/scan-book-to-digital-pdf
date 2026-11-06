# Uniform physical paper size throughout one digital book

Every page of the **final digital PDF, including verified front/back covers, tables, illustrations, and chapter openers**, must use **exactly one physical PDF paper size** (both MediaBox and CropBox). This is independent of the different raster resolutions in scanned images.

## Source-driven selection; no arbitrary A4 requirement

- Inspect the original source PDF page rectangles.
- Compute **one canonical width and height** from the median of its body-page sizes (excluding visually verified first/last covers when known). This resists slight per-scan cropping errors.
- Do not assume that every book is A4, Letter or the same dimensions as the previous book.
- Record the canonical page dimensions in PDF points in the pilot style profile and compositor QA. An engine revision that changes the paper policy invalidates old pilot approvals.

## Safe transformation

- Compose text/artwork on the original page's own coordinate system as before. Only after the whole source page is complete, place that *PDF page* onto the canonical page canvas.
- Use **one uniform scale factor** to preserve its aspect ratio. Center the entire page within the paper; never distort or crop it, and never copy content from a neighboring page.
- Preserve real PDF text, selectable type and vector graphics as PDF objects rather than rasterizing the whole page.
- Use the existing warm-cream default as background for newly exposed paper margins on normal pages; do not obscure special artwork or verified covers.
- Preserve one-to-one source page mapping and total count. A cover is not exempt from the **paper size** rule, even when its content is allowed to be an image.
- Extra-large scaling changes or unusually wide blank margins must be flagged for **visual review**; these are not silently deemed equivalent to the original book.

## Automatic verification

`run_book.py pilot` and `run_book.py full` use `scripts/book_page_size.py` through the compositor. The digital-text QA and page-fidelity auditor check the **single canonical output page size**, not each irregular scan's original MediaBox. Checks cover all output pages, including covers.

The result must have the same width and height (within 0.02 PDF points) in each page's MediaBox, CropBox and displayed rectangle, while retaining page count and each page's extracted word inventory during paper normalization.

This does **not** replace content, OCR, line-layout, footer or typography verification. A uniform paper size alone is not a certificate of a complete digital book.

## An already-running Work conversion

Do **not** interrupt an in-progress 220-page conversion solely because this code changed. When its output exists, first inspect its page sizes. If inconsistent, an agent can use **the existing result PDF**, without OCR reruns:

~~~sh
python scripts/uniform_page_size.py \
  --reference SOURCE_SCANNED.pdf \
  --input Book_Full_REVIEW.pdf \
  --output Book_Full_UNIFORM_REVIEW.pdf
~~~

This creates a new file, preserves the original Work output, reports any pages with substantial scaling changes and checks page count plus extracted text. It never replaces the original scan or original output. The agent must still visually inspect unusual pages and rerun broader editorial QA before labeling it final.

In a blind Work session, source PDF + repository link remains enough; the user need not operate this command.
