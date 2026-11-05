#!/usr/bin/env python3
"""Cache source page images and per-page OCR as normalized top-left line JSON.

Requires PyMuPDF and Pillow. For --engine apple-vision: macOS with swiftc.
For --engine tesseract: tesseract CLI with installed language packs.
Example:
  python ocr_book.py scanned.pdf --out-dir ./work --engine auto --dpi 230
This script does not perform retypesetting; see SKILL.md and page archetypes.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import io
import json
import platform
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
try:
    import fitz
    from PIL import Image
except ImportError:
    raise SystemExit("Missing PyMuPDF or Pillow. Use an isolated authorized Python env.")

HERE = Path(__file__).resolve().parent

def filehash(path: Path) -> str:
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()

def prep_vision_binary(out: Path):
    compiler = shutil.which("swiftc")
    script = HERE / "vision_ocr.swift"
    if not compiler or not script.exists():
        raise RuntimeError("Apple Vision OCR requires macOS swiftc and bundled vision_ocr.swift.")
    binary = out / "vision_ocr_cli"
    if not binary.exists() or binary.stat().st_mtime < script.stat().st_mtime:
        result = subprocess.run([compiler, str(script), "-o", str(binary)],
                                capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError("Swift Apple Vision compile failed: " + result.stderr[-1600:])
    return binary

def apple_vision(image: Path, binary: Path, langs: list[str]):
    r = subprocess.run([str(binary), str(image), ",".join(langs)],
                       capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError("Apple Vision failed: " + r.stderr[-1100:])
    data = json.loads(r.stdout)
    return data["lines"]

def tesseract(image: Path, languages: str):
    cmd = shutil.which("tesseract")
    if not cmd:
        raise RuntimeError("Tesseract CLI unavailable. Install authorized tesseract and language data.")
    r = subprocess.run([cmd, str(image), "stdout", "-l", languages, "tsv"],
                       capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError("Tesseract failed: " + r.stderr[-1200:])
    groups = defaultdict(list)
    for row in csv.DictReader(io.StringIO(r.stdout), delimiter="\t"):
        word = row.get("text", "").strip()
        if not word:
            continue
        try:
            confidence = float(row.get("conf", -1))
            if confidence < 0:
                continue
            key = tuple(int(row[k]) for k in ("block_num", "par_num", "line_num"))
            groups[key].append({
                "text": word, "left": int(row["left"]), "top": int(row["top"]),
                "width": int(row["width"]), "height": int(row["height"]),
                "confidence": confidence / 100,
            })
        except (ValueError, KeyError):
            continue
    iw, ih = Image.open(image).size
    lines = []
    for words in groups.values():
        words.sort(key=lambda a: a["left"])
        x0=min(x["left"] for x in words);y0=min(x["top"] for x in words)
        x1=max(x["left"]+x["width"] for x in words)
        y1=max(x["top"]+x["height"] for x in words)
        lines.append({
            "text": " ".join(x["text"] for x in words),
            "x": round(x0/iw, 6), "y": round(y0/ih, 6),
            "width": round((x1-x0)/iw, 6), "height": round((y1-y0)/ih, 6),
            "confidence": round(sum(x["confidence"] for x in words)/len(words), 4),
        })
    return sorted(lines, key=lambda x: (round(x["y"], 3), x["x"]))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--engine", choices=["auto", "apple-vision", "tesseract"], default="auto")
    parser.add_argument("--dpi", type=int, default=230)
    parser.add_argument("--languages", default="id-ID,en-US",
                        help="Comma separated Apple Vision locales, e.g. id-ID,en-US")
    parser.add_argument("--pages", help="Nonconsecutive 1-based page numbers, e.g. 18,40,74. Avoid OCR of unwanted intermediate pages.")
    parser.add_argument("--start-page", type=int, default=1)
    parser.add_argument("--end-page", type=int)
    parser.add_argument("--replace-cache", action="store_true",
                        help="Explicit opt-in to replace per-page cached OCR.")
    args=parser.parse_args()
    if not args.source.is_file():
        parser.error("Source PDF missing")
    if args.dpi < 100 or args.dpi > 400:
        parser.error("DPI must be between 100 and 400")
    if args.out_dir.resolve() == args.source.resolve():
        parser.error("Output directory must differ from source")
    images = args.out_dir / "page_images"
    ocr = args.out_dir / "ocr"
    images.mkdir(parents=True, exist_ok=True)
    ocr.mkdir(parents=True, exist_ok=True)
    engine=args.engine
    if engine=="auto":
        engine="apple-vision" if platform.system()=="Darwin" and shutil.which("swiftc") else "tesseract"
    locales=[z.strip() for z in args.languages.split(",") if z.strip()]
    # Compile the Swift helper only if an uncached page actually needs Apple Vision.
    binary=None
    source_sha=filehash(args.source)
    with fitz.open(args.source) as document:
        end=args.end_page or len(document)
        if args.start_page < 1 or end > len(document) or end < args.start_page:
            parser.error("Invalid page range")
        if args.pages:
            try:
                selected = [int(x.strip()) for x in args.pages.split(",") if x.strip()]
            except ValueError:
                parser.error("--pages requires comma-separated integers")
            if not selected or len(selected) != len(set(selected)) or min(selected) < 1 or max(selected) > len(document):
                parser.error("Invalid or duplicate --pages values")
            page_numbers = sorted(selected)
        else:
            page_numbers = range(args.start_page, end+1)
        for page_no in page_numbers:
            target=ocr / f"page_{page_no:03d}.json"
            img=images / f"page_{page_no:03d}.jpg"
            if target.exists() and not args.replace_cache:
                previous=json.loads(target.read_text())
                if previous.get("source_sha256")!=source_sha:
                    raise RuntimeError(f"Cache source checksum mismatch: page {page_no}; don't reuse.")
                print(f"CACHED {page_no}/{len(document)}",flush=True)
                continue
            page=document[page_no-1]
            pix=page.get_pixmap(matrix=fitz.Matrix(args.dpi/72,args.dpi/72),alpha=False,colorspace=fitz.csRGB)
            im=Image.frombytes("RGB",(pix.width,pix.height),pix.samples)
            im.save(img,"JPEG",quality=92,optimize=True)
            if engine=="apple-vision":
                if binary is None:
                    binary=prep_vision_binary(args.out_dir)
                lines=apple_vision(img,binary,locales)
            else:
                # Map Apple locale language names to installed Tesseract codes,
                # override if source uses languages not available locally.
                lang_codes={"id-ID":"ind","en-US":"eng"}
                lng="+".join(lang_codes.get(x,x.split("-")[0]) for x in locales)
                lines=tesseract(img,lng)
            record={
                "page": page_no, "source_sha256":source_sha,
                "source_page_pt":[round(page.rect.width,2),round(page.rect.height,2)],
                "engine":engine,"dpi":args.dpi,"languages":locales,
                "lines": lines,
            }
            temp=target.with_suffix(".json.tmp")
            temp.write_text(json.dumps(record,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
            temp.replace(target)
            print(f"OCR {page_no}/{len(document)} lines={len(lines)}",flush=True)

if __name__=="__main__":
    sys.exit(main())
