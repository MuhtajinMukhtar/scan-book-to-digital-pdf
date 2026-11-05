# Mac setup — Apple Vision primary, PaddleOCR Mobile selective

For the AI Agent. A nontechnical user must only supply the scanned PDF and repository URL.

## Step 1: basic Mac environment (no Paddle required)

Verify actual macOS on the authorized Mac, free disk, available RAM and a compatible Python 3 environment. Do not run Apple Vision on Ubuntu/Work Linux and do not install in global Python.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
swiftc --version
python scripts/run_book.py pilot --source "/path/to/book.pdf" --work-dir ./work
```

This stage uses **Apple Vision only**, automatically caches source page OCR, and builds a pilot. The Apple Vision Swift binary is only compiled if a page actually needs reading; if the existing cache matches the source, it is reused.

## Step 2: only if Apple OCR flags an uncertain page

Read `work/review/SUMMARY.json` and `work/pilot/pilot-status.json`. If the report shows uncertain text needing a second opinion, ask in one ordinary sentence whether you may install/download a **lightweight, optional checker**.

After affirmative permission and compatibility checks, install only the necessary PaddleOCR 3.x CPU environment in the isolated venv; do not install `paddleocr[doc-parser]` or invoke `PPStructureV3`. Check the official installation guide for the specific macOS/Apple Silicon/Python combination before pip installation:

- https://www.paddleocr.ai/main/en/version3.x/installation.html
- https://www.paddleocr.ai/main/en/version3.x/pipeline_usage/OCR.html

The app explicitly selects **`PP-OCRv5_mobile_det`** and **`PP-OCRv5_mobile_rec`**, disables image orientation/deskew/textline orientation add-ons and runs on CPU. The worker checks for cached model directories, and model download **requires `--allow-model-download`**, tied to user permission.

Once ready:

```sh
python scripts/run_book.py pilot --source "/path/to/book.pdf" --work-dir ./work \
  --reuse-apple --enable-mobile --allow-model-download
```

If Mobile weights are already installed, omit `--allow-model-download`. `--reuse-apple` is important: do not redo successful Apple Vision OCR.

**Safety for M2 8 GB:** one Mobile page per run by default, image <=1500px on longest edge, limited CPU threads, child-process RSS cap (default conservative 1600 MB on Mac <=10 GB), and timeout (150s). If the limit is exceeded, the worker is stopped while Apple caches remain intact. Treat this as a genuine pilot blocker/exception and report it; do not automatically retry with a higher RAM cap or switch to an Ubuntu host.

The new Mobile checker and previous PP-StructureV3 cannot be assumed to have equivalent accuracy. Compare discrepant names, punctuation, dropped lines, and source scan before accepting changes.

## Important prohibitions

- Never run `scripts/mac_hybrid_ocr.py` as part of the default. Its PP-StructureV3 flow caused native crash/high RAM in the previous Work test and remains legacy opt-in only.
- Do not run the full book without explicit approval of a genuine digital pilot.
- Do not silently replace PaddleOCR with Tesseract or claim two OCR engines when only Apple ran.
- Do not store original book files, OCR caches or licensed fonts in the public GitHub repository.
- GitHub Actions tests do **not** validate Mobile memory/stability on real Mac M2 hardware.

## Reuse/QA

- Apple OCR: `work/ocr/page_###.json`
- Mobile OCR: `work/paddle_mobile/page_###.json`
- Discrepancies: `work/fusion_mobile/page_###.json`
- Page triage: `work/review/page_###.json` and `SUMMARY.json`
- Actual pilot PDF: `work/pilot/Book_Pilot_REVIEW.pdf` and `Book_Pilot_Comparison.pdf`

All source hashes must match; edits to font or spacing should use `--skip-ocr` rather than rerunning OCR.
