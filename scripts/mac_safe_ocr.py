#!/usr/bin/env python3
"""Low-memory Mac OCR: Apple Vision + Tesseract (no Paddle import).

Preserves existing Apple Vision caches, never overwrites Paddle fusion results.
This is a DIFFERENT, less-proven dual-OCR combination than PP-StructureV3.
All disagreements require source-image verification, not blind auto-merging.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys

import fitz
from PIL import Image

from ocr_book import tesseract as recognize_tesseract

HERE = Path(__file__).resolve().parent


def digest(path: Path) -> str:
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def words(text: str) -> Counter:
    return Counter(re.findall(r"[^\W_]+(?:['’-][^\W_]+)*", text.casefold(), re.UNICODE))


def compare(vision: list[dict], secondary: list[dict], page: int, source_sha: str) -> dict:
    a = words(" ".join(x.get("text", "") for x in vision))
    b = words(" ".join(x.get("text", "") for x in secondary))
    # Deliberately flag even minor differences. This is a triage report, not a
    # decision to discard the Apple text or silently select Tesseract.
    missing_apple = b - a
    missing_secondary = a - b
    issues = (
        [{"type": "tesseract_not_in_apple", "token": token, "count": count}
         for token, count in sorted(missing_apple.items())] +
        [{"type": "apple_not_in_tesseract", "token": token, "count": count}
         for token, count in sorted(missing_secondary.items())]
    )
    return {
        "page": page, "source_sha256": source_sha,
        "primary_engine": "apple-vision", "secondary_engine": "tesseract",
        "primary_words": sum(a.values()), "secondary_words": sum(b.values()),
        "issues": issues,
        "editorial_status": "SOURCE_VISUAL_REVIEW_REQUIRED",
        "warning": "Apple Vision+Tesseract is NOT equivalent to the prior Apple Vision+PP-StructureV3 benchmark.",
    }


def installed_languages() -> set[str]:
    cmd = shutil.which("tesseract")
    if not cmd:
        raise RuntimeError(
            "Lightweight OCR checker Tesseract is not installed. "
            "Stop safely and ask permission to install Tesseract and ind+eng language packs on Mac."
        )
    result = subprocess.run([cmd, "--list-langs"], capture_output=True, text=True, timeout=20)
    if result.returncode:
        raise RuntimeError("Cannot inspect Tesseract languages: " + result.stderr[-500:])
    return set(x.strip() for x in (result.stdout + "\n" + result.stderr).splitlines()
               if x.strip() and not x.lower().startswith("list of available"))


def selected_pages(source: Path, spec: str | None) -> list[int]:
    with fitz.open(source) as doc:
        if spec:
            try:
                result = [int(x.strip()) for x in spec.split(",") if x.strip()]
            except ValueError as e:
                raise ValueError("Invalid --pages (use comma separated source page numbers)") from e
        else:
            result = list(range(1, len(doc) + 1))
        if not result or len(result) != len(set(result)) or min(result) < 1 or max(result) > len(doc):
            raise ValueError("Invalid, repeated or out-of-range physical page numbers")
        return result


def render_missing_image(source: Path, dest: Path, number: int, dpi: int) -> None:
    """Regenerate image only; NEVER redo an Apple OCR cache just because JPG is absent."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    with fitz.open(source) as doc:
        pix = doc[number-1].get_pixmap(
            matrix=fitz.Matrix(dpi / 72, dpi / 72), colorspace=fitz.csRGB, alpha=False
        )
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        img.save(dest, "JPEG", quality=90, optimize=True)


def run(source: Path, work: Path, pages: list[int], dpi: int, langs: str) -> dict:
    if platform.system() != "Darwin":
        raise RuntimeError("Apple Vision must run on an authorized macOS host, not Ubuntu/Linux")
    source = source.resolve()
    work = work.resolve()
    if work == source.parent or source == work or source.is_relative_to(work):
        raise ValueError("Use an isolated work folder separate from the original file")
    if not source.is_file():
        raise FileNotFoundError(source)
    codes = langs.split("+")
    available = installed_languages()
    missing = sorted(set(codes) - available)
    if missing:
        raise RuntimeError(
            "Missing Tesseract language packs: " + ", ".join(missing) +
            ". Install them with permission; do not silently drop Indonesian verification."
        )
    source_sha = digest(source)
    # The Apple command reuses source-hash-verified cache if it already exists.
    cmd = [
        sys.executable, str(HERE / "ocr_book.py"), str(source), "--out-dir", str(work),
        "--engine", "apple-vision", "--pages", ",".join(map(str, pages)), "--dpi", str(dpi),
        "--languages", "id-ID,en-US",
    ]
    subprocess.run(cmd, check=True)
    saved = 0
    reused = 0
    issues_total = 0
    for number in pages:
        apple_path = work / "ocr" / f"page_{number:03d}.json"
        apple = json.loads(apple_path.read_text(encoding="utf-8"))
        if apple.get("engine") != "apple-vision" or apple.get("source_sha256") != source_sha:
            raise RuntimeError(f"Apple cache identity mismatch for page {number}")
        image_path = work / "page_images" / f"page_{number:03d}.jpg"
        if not image_path.exists():
            render_missing_image(source, image_path, number, dpi)
        image_sha = digest(image_path)
        second = work / "tesseract" / f"page_{number:03d}.json"
        fused = work / "fusion_safe" / f"page_{number:03d}.json"
        second.parent.mkdir(parents=True, exist_ok=True)
        fused.parent.mkdir(parents=True, exist_ok=True)
        if second.exists():
            cached = json.loads(second.read_text(encoding="utf-8"))
            if (cached.get("source_sha256") != source_sha or
                cached.get("image_sha256") != image_sha or
                cached.get("languages") != langs or cached.get("engine") != "tesseract"):
                raise RuntimeError(f"Existing Tesseract cache changed, refused overwrite at {number}")
            recognized = cached.get("lines", [])
            reused += 1
        else:
            recognized = recognize_tesseract(image_path, langs)
            cached = {
                "engine": "tesseract", "page": number,
                "source_sha256": source_sha, "image_sha256": image_sha,
                "languages": langs, "lines": recognized,
            }
            second.write_text(json.dumps(cached, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
            saved += 1
        report = compare(apple.get("lines", []), recognized, number, source_sha)
        if fused.exists():
            old = json.loads(fused.read_text(encoding="utf-8"))
            if old.get("primary_engine") != "apple-vision" or old.get("secondary_engine") != "tesseract":
                raise RuntimeError(f"Another OCR method owns existing fusion-safe result page {number}")
        fused.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        issues_total += len(report["issues"])
    if digest(source) != source_sha:
        raise RuntimeError("The original source PDF changed during processing")
    summary = {
        "status": "SOURCE_VISUAL_REVIEW_REQUIRED", "engine_pair": "Apple Vision + Tesseract",
        "processed_pages": len(pages), "new_secondary_pages": saved,
        "cached_secondary_pages": reused, "discrepancy_tokens": issues_total,
        "note": "This path does not load PaddlePaddle. OCR fidelity still needs source comparison.",
    }
    (work / "fusion_safe" / "SUMMARY.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source", type=Path)
    p.add_argument("--work-dir", type=Path, required=True)
    p.add_argument("--pages", help="e.g. 49,124; omitted means all pages, only after pilot approval")
    p.add_argument("--dpi", type=int, default=180)
    p.add_argument("--tesseract-langs", default="ind+eng")
    args = p.parse_args()
    if not args.source.is_file():
        p.error("Original PDF is missing")
    if not 120 <= args.dpi <= 230:
        p.error("Use 120..230 DPI only for the safe OCR workflow")
    try:
        pages = selected_pages(args.source, args.pages)
        result = run(args.source, args.work_dir, pages, args.dpi, args.tesseract_langs)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, RuntimeError, OSError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired, FileNotFoundError) as exc:
        print(f"STOP_SAFE: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
