#!/usr/bin/env python3
"""Non-destructive, lossless PDF optimization with full-page parity tests.

Requires PyMuPDF. Usage:
  python lossless_optimize.py source.pdf new-optimized.pdf --json qa.json

No image downsampling or JPEG transcoding. Original input remains unmodified.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
from pathlib import Path

try:
    import fitz
except ImportError:
    raise SystemExit("PyMuPDF missing: install into an authorized isolated environment.")

def hash_file(path: Path) -> str:
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()

def optimize(source: Path, destination: Path, dpi: int):
    if source.resolve() == destination.resolve():
        raise ValueError("Refusing to overwrite the source")
    if destination.exists():
        raise FileExistsError("Refusing to overwrite existing output")
    src_sha = hash_file(source)
    with fitz.open(source) as pdf:
        pages = len(pdf)
        pdf.save(destination, garbage=4, clean=True, deflate=True,
                 deflate_images=True, deflate_fonts=True, use_objstms=1)
    assert hash_file(source) == src_sha, "Source changed during optimization"
    report = {
        "source": str(source), "output": str(destination),
        "source_sha256": src_sha,
        "optimized_sha256": hash_file(destination),
        "source_bytes": source.stat().st_size,
        "optimized_bytes": destination.stat().st_size,
        "pages": pages,
        "dpi_checked": dpi,
        "text_changed_pages": [],
        "pixel_changed_pages": [],
        "image_count_changed_pages": [],
        "links_changed_pages": [],
        "geometry_changed_pages": [],
    }
    with fitz.open(source) as a, fitz.open(destination) as b:
        if len(a) != len(b):
            raise RuntimeError("Page count changed in optimized PDF")
        matrix = fitz.Matrix(dpi / 72, dpi / 72)
        for i in range(len(a)):
            x, y = a[i], b[i]
            if x.rect != y.rect:
                report["geometry_changed_pages"].append(i + 1)
            if x.get_text("text") != y.get_text("text"):
                report["text_changed_pages"].append(i + 1)
            if len(x.get_images(full=True)) != len(y.get_images(full=True)):
                report["image_count_changed_pages"].append(i + 1)
            if len(x.get_links()) != len(y.get_links()):
                report["links_changed_pages"].append(i + 1)
            pix1 = x.get_pixmap(matrix=matrix, alpha=False)
            pix2 = y.get_pixmap(matrix=matrix, alpha=False)
            if (pix1.width, pix1.height) != (pix2.width, pix2.height) or pix1.samples != pix2.samples:
                report["pixel_changed_pages"].append(i + 1)
    report["saved_percent"] = round(100 * (1 - report["optimized_bytes"] / report["source_bytes"]), 2)
    report["pass"] = not any(report[key] for key in (
        "text_changed_pages", "pixel_changed_pages", "image_count_changed_pages",
        "links_changed_pages", "geometry_changed_pages"))
    return report

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--dpi", type=int, default=72)
    p.add_argument("--json", type=Path, dest="json_path")
    args = p.parse_args()
    if not args.source.is_file():
        p.error("Source PDF does not exist")
    if args.dpi < 40 or args.dpi > 300:
        p.error("DPI must be 40..300")
    report = optimize(args.source, args.output, args.dpi)
    if args.json_path:
        args.json_path.parent.mkdir(parents=True, exist_ok=True)
        args.json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["pass"]:
        print("FAILED: optimized PDF differs; do not deliver as lossless.", file=sys.stderr)
        return 2
    return 0

if __name__ == "__main__":
    sys.exit(main())
