#!/usr/bin/env python3
"""Mac-first Apple Vision + PP-StructureV3 OCR with source-review candidates.

The two OCR results are preserved separately. This does NOT auto-merge guesses
into the final book or replace editorial review of the original page images.

Full run (macOS):
  python scripts/mac_hybrid_ocr.py book.pdf --work-dir work
Inspect existing cached results without PaddleOCR installed (any OS):
  python scripts/mac_hybrid_ocr.py --work-dir work --compare-only
"""
from __future__ import annotations

import argparse
from difflib import SequenceMatcher
import hashlib
import json
import platform
from pathlib import Path
import subprocess
import sys
import unicodedata


def digest(path: Path) -> str:
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def normalized(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKC", str(text)).casefold() if c.isalnum())


def near_in(text: str, document: str, threshold: float = 0.85) -> bool:
    """Conservative approximate substring match; disagreements require source review."""
    a, b = normalized(text), normalized(document)
    if not a:
        return True
    if a in b:
        return True
    if not b:
        return False
    if len(a) < 12:
        return False
    starts = list(range(0, max(1, len(b)-len(a)+1), max(1, len(a)//4)))
    if len(b) >= len(a):
        starts.append(len(b)-len(a))
    for start in starts:
        snippet = b[start:start+len(a)]
        if SequenceMatcher(None, a, snippet, autojunk=False).ratio() >= threshold:
            return True
    return False


def paddle_result(data: object) -> dict:
    if isinstance(data, dict) and "overall_ocr_res" in data:
        return data
    if isinstance(data, dict) and isinstance(data.get("res"), dict):
        return paddle_result(data["res"])
    if isinstance(data, list) and len(data) == 1:
        return paddle_result(data[0])
    raise ValueError("Paddle raw PP-StructureV3 overall_ocr_res not found")


def reconcile(apple: dict, paddle: dict, markdown: str | None = None) -> dict:
    result = paddle_result(paddle)
    raw = result["overall_ocr_res"]
    texts = raw.get("rec_texts")
    scores = raw.get("rec_scores") or []
    boxes = raw.get("rec_boxes") or []
    if not isinstance(texts, list):
        raise ValueError("Paddle OCR result lacks rec_texts list; never trust only Markdown")
    apple_lines = [str(item.get("text", "")).strip() for item in apple.get("lines", []) if str(item.get("text", "")).strip()]
    p_lines = [str(item).strip() for item in texts if str(item).strip()]
    vision_body = " ".join(apple_lines)
    paddle_body = " ".join(p_lines)
    issues = []
    for i, line in enumerate(texts):
        if not str(line).strip():
            continue
        extra = {"paddle_line": i + 1, "text": str(line)}
        if i < len(scores):
            try: extra["paddle_confidence"] = round(float(scores[i]), 4)
            except (ValueError, TypeError): pass
        if i < len(boxes):
            extra["paddle_box"] = boxes[i]
        if normalized(line) not in normalized(vision_body):
            kind = "paddle_apple_variant" if near_in(line, vision_body) else "paddle_not_in_apple"
            issues.append({"type": kind, **extra})
        if markdown is not None and not near_in(line, markdown):
            issues.append({"type": "paddle_raw_not_in_markdown", **extra})
    for i, line in enumerate(apple_lines):
        if normalized(line) not in normalized(paddle_body):
            kind = "apple_paddle_variant" if near_in(line, paddle_body) else "apple_not_in_paddle"
            issues.append({"type": kind, "apple_line": i + 1, "text": line})
    return {
        "apple_lines": len(apple_lines),
        "paddle_raw_lines": len(p_lines),
        "markdown_checked": markdown is not None,
        "issues": issues,
        "editorial_status": "SOURCE_VISUAL_REVIEW_REQUIRED",
        "important": "OCR engines may both be wrong. Inspect the actual scan before accepting/rejecting any suggestion.",
    }


def compare_cached(work_dir: Path, start: int = 1, end: int | None = None) -> dict:
    ocr = work_dir / "ocr"
    output = work_dir / "fusion"
    output.mkdir(parents=True, exist_ok=True)
    pages = sorted(ocr.glob("page_*.json"))
    pages = [p for p in pages if p.stem[5:].isdigit() and int(p.stem[5:]) >= start and (end is None or int(p.stem[5:]) <= end)]
    if not pages:
        raise ValueError("No Apple Vision page JSON found; cannot compare OCR")
    summary = {"pages": 0, "pages_with_issues": [], "candidate_issues": 0, "mode": "Apple Vision + PaddleOCR PP-StructureV3", "status": "SOURCE_VISUAL_REVIEW_REQUIRED"}
    for file in pages:
        page = int(file.stem.split("_")[-1])
        apple = json.loads(file.read_text(encoding="utf-8"))
        if apple.get("engine") != "apple-vision":
            raise ValueError(f"Page {page} not Apple Vision. Refusing false hybrid label")
        paddle_file = work_dir / "paddle" / file.name
        meta = work_dir / "paddle" / f"{file.stem}.meta.json"
        if not paddle_file.is_file() or not meta.is_file():
            raise ValueError(f"Missing raw Paddle result or hash metadata for page {page}")
        if json.loads(meta.read_text(encoding="utf-8")).get("source_sha256") != apple.get("source_sha256"):
            raise ValueError(f"Paddle/Apple source SHA-256 mismatch at page {page}")
        markdown_path = work_dir / "paddle" / f"{file.stem}.md"
        md = markdown_path.read_text(encoding="utf-8") if markdown_path.is_file() else None
        report = reconcile(apple, json.loads(paddle_file.read_text(encoding="utf-8")), md)
        report["page"] = page
        report["source_sha256"] = apple.get("source_sha256")
        (output / file.name).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        summary["pages"] += 1
        summary["candidate_issues"] += len(report["issues"])
        if report["issues"]:
            summary["pages_with_issues"].append(page)
    (output / "OCR_REVIEW.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return summary


def run_hybrid(source: Path, work_dir: Path, dpi: int, start: int, end: int | None, languages: str) -> None:
    if platform.system() != "Darwin":
        raise RuntimeError("Full hybrid run requires macOS Apple Vision. Use --compare-only on other OSes.")
    if not source.is_file() or source.suffix.lower() != ".pdf":
        raise ValueError("Source must be an existing PDF")
    source = source.resolve()
    work_dir = work_dir.resolve()
    if work_dir == source.parent or work_dir == source:
        raise ValueError("Use a dedicated work folder that is not the source folder")
    source_sha = digest(source)
    command = [sys.executable, str(Path(__file__).with_name("ocr_book.py")), str(source),
               "--engine", "apple-vision", "--out-dir", str(work_dir), "--dpi", str(dpi),
               "--start-page", str(start), "--languages", languages]
    if end is not None:
        command += ["--end-page", str(end)]
    subprocess.run(command, check=True)
    try:
        from paddleocr import PPStructureV3
    except ImportError as exc:
        raise RuntimeError("PaddleOCR PP-StructureV3 missing. See references/mac-setup.md; no Apple-only shortcut.") from exc
    pipeline = PPStructureV3(use_doc_orientation_classify=False, use_doc_unwarping=False)
    target_dir = work_dir / "paddle"
    target_dir.mkdir(parents=True, exist_ok=True)
    for apple_path in sorted((work_dir / "ocr").glob("page_*.json")):
        page = int(apple_path.stem.split("_")[-1])
        if page < start or (end is not None and page > end):
            continue
        image = work_dir / "page_images" / f"page_{page:03d}.jpg"
        result_path = target_dir / f"page_{page:03d}.json"
        meta_path = target_dir / f"page_{page:03d}.meta.json"
        meta = {"source_sha256": source_sha, "image_sha256": digest(image), "engine": "PP-StructureV3"}
        if result_path.exists() or meta_path.exists():
            if not (result_path.exists() and meta_path.exists() and json.loads(meta_path.read_text()) == meta):
                raise RuntimeError(f"Paddle cache mismatch or incomplete page {page}; keep old files for inspection")
            print(f"PADDLE CACHED {page}", flush=True)
            continue
        predictions = pipeline.predict(input=str(image))
        for item in predictions:
            item.save_to_json(save_path=str(result_path))
            item.save_to_markdown(save_path=str(target_dir))
            break
        else:
            raise RuntimeError(f"PP-StructureV3 yielded no result for page {page}")
        paddle_result(json.loads(result_path.read_text(encoding="utf-8")))
        meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        print(f"PADDLE OCR {page}", flush=True)
    if digest(source) != source_sha:
        raise RuntimeError("Original PDF hash changed during OCR; stop")
    report = compare_cached(work_dir, start, end)
    print(json.dumps(report, ensure_ascii=False, indent=2))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source", nargs="?", type=Path)
    p.add_argument("--work-dir", type=Path, required=True)
    p.add_argument("--dpi", type=int, default=230)
    p.add_argument("--start-page", type=int, default=1)
    p.add_argument("--end-page", type=int)
    p.add_argument("--languages", default="id-ID,en-US")
    p.add_argument("--compare-only", action="store_true", help="Compare cached raw Apple/Paddle outputs without running OCR")
    a = p.parse_args()
    try:
        if a.compare_only:
            print(json.dumps(compare_cached(a.work_dir, a.start_page, a.end_page), ensure_ascii=False, indent=2))
        else:
            if a.source is None:
                p.error("Source PDF required unless --compare-only")
            if a.dpi < 100 or a.dpi > 400:
                p.error("DPI must be 100–400")
            run_hybrid(a.source, a.work_dir, a.dpi, a.start_page, a.end_page, a.languages)
    except (ValueError, RuntimeError, subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
