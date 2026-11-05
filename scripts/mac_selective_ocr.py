#!/usr/bin/env python3
"""Apple Vision first; selectively check uncertain pages with PP-OCRv5 Mobile.

No PP-StructureV3 and no Tesseract in this workflow. PaddleOCR is optional and
runs in a monitored child process only on flagged source pages after opt-in.
Never replace the original Apple OCR lines with secondary OCR guesses.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import signal
import subprocess
import sys
import time

import fitz
from PIL import Image

HERE = Path(__file__).resolve().parent
MODEL_NAMES = ("PP-OCRv5_mobile_det", "PP-OCRv5_mobile_rec")


def digest(path: Path) -> str:
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def dump(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".partial")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def apple_review(lines: list[dict]) -> dict:
    """Conservative triage, not an OCR accuracy certification."""
    if not lines:
        return {"needs_mobile": True, "reasons": ["no_apple_text"], "scored_lines": 0}
    scored = []
    for item in lines:
        try:
            val = float(item.get("confidence"))
            if 0 <= val <= 1:
                scored.append(val)
        except (ValueError, TypeError):
            continue
    reasons = []
    if len(lines) < 4:
        reasons.append("very_few_text_lines")
    if scored:
        mean = sum(scored) / len(scored)
        if mean < 0.87:
            reasons.append("low_average_confidence")
        if any(c < 0.74 for c in scored):
            reasons.append("very_low_line_confidence")
        if len(scored) < max(1, len(lines) // 2):
            reasons.append("partial_confidence_data")
    else:
        mean = None
        reasons.append("no_confidence_data")
    return {
        "needs_mobile": bool(reasons),
        "reasons": reasons,
        "scored_lines": len(scored),
        "average_confidence": (round(mean, 4) if mean is not None else None),
        "text_lines": len(lines),
    }


def word_bag(lines: list[str]) -> Counter:
    text = " ".join(lines).casefold()
    return Counter(re.findall(r"[^\W_]+(?:['’-][^\W_]+)*", text, re.UNICODE))


def compare_ocr(apple: list[dict], mobile: dict, page: int, sha: str) -> dict:
    if mobile.get("engine") != "paddle-ppocrv5-mobile" or mobile.get("source_sha256") != sha:
        raise ValueError("Mobile OCR source provenance invalid")
    primary = word_bag([x.get("text", "") for x in apple])
    secondary = word_bag([str(x) for x in mobile.get("rec_texts", [])])
    disagreements = []
    for kind, bag in (("paddle_mobile_not_in_apple", secondary - primary),
                      ("apple_not_in_paddle_mobile", primary - secondary)):
        for token, count in bag.most_common():
            disagreements.append({"type": kind, "token": token, "count": count})
    return {
        "page": page, "source_sha256": sha, "primary_engine": "apple-vision",
        "secondary_engine": "paddle-ppocrv5-mobile",
        "issues": disagreements,
        "editorial_status": "SOURCE_VISUAL_REVIEW_REQUIRED",
        "note": "Differences are suggestions only; do not silently replace Apple text.",
    }


def total_mac_memory_mb() -> int | None:
    try:
        cmd = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True,
                             text=True, timeout=3, check=True)
        return int(cmd.stdout.strip()) // (1024 * 1024)
    except (ValueError, OSError, subprocess.SubprocessError):
        return None


def worker_rss_mb(pgid: int) -> int:
    """Track the process group, including native children of the OCR worker."""
    proc = subprocess.run(["ps", "-A", "-o", "pgid=", "-o", "rss="],
                          capture_output=True, text=True, timeout=8, check=True)
    total = 0
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].isdigit() and int(parts[0]) == pgid:
            try:
                total += int(parts[1])
            except ValueError:
                pass
    return total // 1024


def stop_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=3)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait(timeout=3)


def monitored_worker(image: Path, output: Path, number: int, source_sha: str,
                     image_sha: str, memory_cap_mb: int, timeout_s: int,
                     allow_download: bool) -> dict:
    cmd = [sys.executable, str(HERE / "paddle_mobile_worker.py"),
           "--image", str(image), "--output", str(output),
           "--page", str(number), "--source-sha", source_sha,
           "--image-sha", image_sha]
    if allow_download:
        cmd.append("--allow-download")
    output.parent.mkdir(parents=True, exist_ok=True)
    log = output.with_suffix(".worker.log")
    env = os.environ.copy()
    for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
                "VECLIB_MAXIMUM_THREADS"):
        env[key] = "2"
    started = time.monotonic()
    highest = 0
    reason = None
    with log.open("w", encoding="utf-8") as fd:
        proc = subprocess.Popen(cmd, stdout=fd, stderr=subprocess.STDOUT, env=env,
                                start_new_session=True)
        while proc.poll() is None:
            elapsed = time.monotonic() - started
            if elapsed > timeout_s:
                reason = "worker_timeout"
                stop_group(proc)
                break
            try:
                rss = worker_rss_mb(proc.pid)
                highest = max(highest, rss)
                if rss > memory_cap_mb:
                    reason = "worker_memory_limit"
                    stop_group(proc)
                    break
            except (OSError, subprocess.SubprocessError, ValueError):
                # Never disable a guard silently.
                reason = "memory_monitor_failed"
                stop_group(proc)
                break
            time.sleep(0.8)
    return {
        "status": "ok" if reason is None and proc.returncode == 0 and output.is_file()
                  else (reason or "worker_failed"),
        "exit_code": proc.returncode,
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "observed_max_rss_mb": highest,
        "rss_limit_mb": memory_cap_mb,
        "log": str(log),
    }


def ensure_image(source: Path, work: Path, number: int, dpi: int) -> Path:
    image = work / "page_images" / f"page_{number:03d}.jpg"
    if image.exists():
        return image
    image.parent.mkdir(parents=True, exist_ok=True)
    with fitz.open(source) as doc:
        pix = doc[number - 1].get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72),
                                          colorspace=fitz.csRGB, alpha=False)
        im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        im.save(image, "JPEG", quality=90)
    return image


def bound_image(source: Path, target: Path, max_dimension: int = 1500) -> Path:
    # Avoid running Mobile on a full 200-300 dpi scan with huge memory spikes.
    with Image.open(source) as im:
        if max(im.size) <= max_dimension:
            return source
        target.parent.mkdir(parents=True, exist_ok=True)
        im = im.convert("RGB")
        im.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
        im.save(target, "JPEG", quality=86)
    return target


def run(source: Path, work: Path, pages: list[int], dpi: int, skip_vision: bool,
        enable_mobile: bool, allow_download: bool, max_mobile_pages: int,
        timeout_s: int, memory_cap_mb: int | None, force_pages: set[int]) -> dict:
    source = source.resolve()
    work = work.resolve()
    if not source.is_file() or source.suffix.lower() != ".pdf":
        raise ValueError("Original source must be an existing PDF")
    if source.is_relative_to(work) or work == source.parent:
        raise ValueError("Work dir must not contain the original PDF or be its parent")
    source_sha = digest(source)
    with fitz.open(source) as doc:
        count = len(doc)
    if not pages or len(set(pages)) != len(pages) or min(pages) < 1 or max(pages) > count:
        raise ValueError("Invalid/duplicate source page selection")
    if not skip_vision:
        if platform.system() != "Darwin":
            raise RuntimeError("Apple Vision requires actual macOS; no Linux substitution")
        cmd = [sys.executable, str(HERE / "ocr_book.py"), str(source),
               "--out-dir", str(work), "--engine", "apple-vision",
               "--dpi", str(dpi), "--pages", ",".join(map(str, pages))]
        subprocess.run(cmd, check=True)
    reviews = {}
    pending = []
    for number in pages:
        f = work / "ocr" / f"page_{number:03d}.json"
        if not f.is_file():
            raise ValueError(f"Missing Apple Vision cache: source page {number}")
        data = json.loads(f.read_text(encoding="utf-8"))
        if (data.get("engine") != "apple-vision" or data.get("page") != number
                or data.get("source_sha256") != source_sha):
            raise ValueError(f"Apple Vision source/hash cache mismatch at page {number}")
        assessment = apple_review(data.get("lines", []))
        if number in force_pages and "requested_secondary_review" not in assessment["reasons"]:
            assessment["reasons"].append("requested_secondary_review")
            assessment["needs_mobile"] = True
        reviews[number] = {"page": number, "source_sha256": source_sha,
                           "primary_engine": "apple-vision",
                           "secondary_engine": None,
                           "assessment": assessment, "secondary_status": "not_needed"}
        if assessment["needs_mobile"]:
            pending.append(number)
    memory = total_mac_memory_mb() if platform.system() == "Darwin" else None
    cap = memory_cap_mb if memory_cap_mb is not None else (
        1600 if memory is not None and memory <= 10 * 1024 else
        2600 if memory is not None and memory <= 18 * 1024 else 3600
    )
    available = importlib.util.find_spec("paddleocr") is not None
    processed = 0
    for number in pending:
        review = reviews[number]
        if not enable_mobile:
            review["secondary_status"] = "opt_in_required"
            continue
        if not available:
            review["secondary_status"] = "dependency_missing"
            continue
        if not allow_download and not all(
            (Path.home() / ".paddlex" / "official_models" / name).is_dir()
            for name in MODEL_NAMES
        ):
            review["secondary_status"] = "model_download_permission_required"
            continue
        if processed >= max_mobile_pages:
            review["secondary_status"] = "deferred_page_budget"
            continue
        processed += 1
        orig = ensure_image(source, work, number, dpi)
        image = bound_image(orig, work / "mobile_inputs" / f"page_{number:03d}.jpg")
        output = work / "paddle_mobile" / f"page_{number:03d}.json"
        image_sha = digest(image)
        if output.exists():
            cached = json.loads(output.read_text(encoding="utf-8"))
            if (cached.get("source_sha256") != source_sha or
                    cached.get("image_sha256") != image_sha or
                    cached.get("engine") != "paddle-ppocrv5-mobile" or
                    cached.get("page") != number):
                raise ValueError(f"Paddle Mobile cache identity mismatch for page {number}")
            result = {"status": "cached", "observed_max_rss_mb": None}
        else:
            result = monitored_worker(image, output, number, source_sha, image_sha,
                                      cap, timeout_s, allow_download)
        review["worker"] = result
        if result["status"] in ("ok", "cached"):
            mobile = json.loads(output.read_text(encoding="utf-8"))
            fused = compare_ocr(
                json.loads((work/"ocr"/f"page_{number:03d}.json").read_text())["lines"],
                mobile, number, source_sha)
            dump(work / "fusion_mobile" / f"page_{number:03d}.json", fused)
            review["secondary_engine"] = "paddle-ppocrv5-mobile"
            review["secondary_status"] = "compared_needs_source_review" if fused["issues"] else "compared_no_token_disagreement"
            review["disagreement_count"] = len(fused["issues"])
        else:
            review["secondary_status"] = result["status"]
    for number, record in reviews.items():
        dump(work / "review" / f"page_{number:03d}.json", record)
    pending_pages = [n for n in pages if reviews[n]["assessment"]["needs_mobile"] and
                     reviews[n]["secondary_engine"] is None]
    summary = {
        "status": "SOURCE_REVIEW_PENDING" if pending_pages else "APPLE_PRIMARY_CHECKED",
        "source_sha256": source_sha,
        "apple_pages": len(pages), "mobile_candidates": len(pending),
        "mobile_compared": len([n for n in pages if reviews[n]["secondary_engine"]]),
        "secondary_pending_pages": pending_pages,
        "secondary_pending_reasons": {str(n): reviews[n]["secondary_status"] for n in pending_pages},
        "rss_guard_mb": cap, "model": "PP-OCRv5_mobile_det+rec (selective only)",
        "no_paddle_structurev3": True,
        "note": "No OCR engine guarantees source fidelity; visually review exceptions before accepting.",
    }
    dump(work / "review" / "SUMMARY.json", summary)
    if digest(source) != source_sha:
        raise RuntimeError("Source PDF changed during processing")
    return summary


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source", type=Path)
    p.add_argument("--work-dir", type=Path, required=True)
    p.add_argument("--pages", required=True, help="Physical pages, e.g. 49,124")
    p.add_argument("--dpi", type=int, default=180)
    p.add_argument("--skip-vision", action="store_true", help="Reuse Apple caches (e.g. from earlier Work session)")
    p.add_argument("--enable-mobile", action="store_true", help="Explicit opt-in for selective Mobile OCR")
    p.add_argument("--allow-model-download", action="store_true", help="Requires separate user download permission")
    p.add_argument("--max-mobile-pages", type=int, default=1)
    p.add_argument("--mobile-timeout", type=int, default=150)
    p.add_argument("--mobile-rss-limit-mb", type=int)
    p.add_argument("--force-mobile-pages", default="")
    args = p.parse_args()
    if not args.source.is_file():
        p.error("Source PDF not found")
    if not 120 <= args.dpi <= 230 or not 0 <= args.max_mobile_pages <= 5:
        p.error("Invalid DPI (120..230) or Mobile page cap (0..5)")
    try:
        pages = [int(x) for x in args.pages.split(",")]
        forced = {int(x) for x in args.force_mobile_pages.split(",") if x}
        if not forced.issubset(set(pages)):
            raise ValueError("--force-mobile-pages must be within --pages")
        result = run(args.source, args.work_dir, pages, args.dpi, args.skip_vision,
                     args.enable_mobile, args.allow_model_download, args.max_mobile_pages,
                     args.mobile_timeout, args.mobile_rss_limit_mb, forced)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
