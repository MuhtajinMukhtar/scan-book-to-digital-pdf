#!/usr/bin/env python3
"""Make an already-generated book PDF use one paper size without repeating OCR.

This is a physical-canvas repair, not a rewrite of text or an OCR correction.
Never overwrite the scanned source, the Work result or other book versions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

import fitz

from book_page_size import canonical_page_size, normalized_copy, all_pages_uniform


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def normalize_existing(source: Path, input_pdf: Path, output: Path,
                       covers: set[int] | None = None) -> dict:
    for required in (source,input_pdf):
        if not required.is_file():
            raise ValueError(f"Missing PDF: {required}")
    if len({source.resolve(),input_pdf.resolve(),output.resolve()}) < 3:
        raise ValueError("Source, existing digital book and new output must be separate files")
    if output.exists():
        raise ValueError("Output already exists; do not overwrite book results")
    covers = set(covers or ())
    with fitz.open(source) as original, fitz.open(input_pdf) as current:
        if len(original) != len(current):
            raise ValueError("Source and digital book have different page counts")
        if covers - {1,len(original)}:
            raise ValueError("Only visually verified first or last book cover may be excluded")
        paper = canonical_page_size(original,covers)
        already = all_pages_uniform(current,paper)
        report_rows = []
        output.parent.mkdir(parents=True,exist_ok=True)
        temp = output.with_suffix(".partial.pdf")
        if temp.exists():
            raise ValueError("A previous partial output exists: inspect it before retrying")
        try:
            if already:
                shutil.copyfile(input_pdf,temp)
                for n,page in enumerate(current,1):
                    report_rows.append({
                        "source_page":n,"scale":1.0,
                        "before_width_pt":round(page.rect.width,2),
                        "before_height_pt":round(page.rect.height,2),
                        "after_width_pt":paper["width_pt"],
                        "after_height_pt":paper["height_pt"],
                        "visual_review_recommended":False,
                    })
            else:
                fixed, report_rows = normalized_copy(
                    current,paper,verified_cover_pages=covers
                )
                try:
                    fixed.set_metadata({
                        k:v for k,v in current.metadata.items()
                        if k in ("title","author","subject","keywords","creator","producer",
                                 "creationDate","modDate") and isinstance(v,str)
                    })
                    fixed.save(temp,garbage=3,deflate=True)
                finally:
                    fixed.close()
            with fitz.open(temp) as check:
                if len(check) != len(original) or not all_pages_uniform(check,paper):
                    raise ValueError("Normalized PDF failed final page-size verification")
            temp.replace(output)
        except Exception:
            # Preserve partial evidence for inspection, never touch input.
            raise
        return {
            "status":"UNIFORM_PAPER_REVIEW_REQUIRED",
            "source_pdf_sha256":sha256(source),
            "existing_digital_sha256":sha256(input_pdf),
            "result_sha256":sha256(output),
            "source_pages":len(original),
            "output_pages":len(current),
            "canonical_page_size":paper,
            "changed_paper_dimensions":not already,
            "pages_requiring_visual_review":[
                row["source_page"] for row in report_rows
                if row["visual_review_recommended"]
            ],
            "per_page":report_rows,
            "note":"Paper-size-only repair: PDF text and artwork are preserved in "
                   "their original physical page; source OCR/editorial QA is separate.",
        }


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--reference",required=True,type=Path,
                   help="Original scanned PDF, used only to choose canonical paper")
    p.add_argument("--input",required=True,type=Path,
                   help="Existing digitally retypeset PDF, never changed")
    p.add_argument("--output",required=True,type=Path,
                   help="New uniform-paper PDF path")
    p.add_argument("--verified-covers",default="",
                   help="Optional source-verified physical cover pages: 1,last")
    args=p.parse_args()
    try:
        covers=set(int(token.strip()) for token in args.verified_covers.split(",")
                   if token.strip())
        result=normalize_existing(args.reference,args.input,args.output,covers)
        report=args.output.with_suffix(".paper-size.json")
        report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",
                          encoding="utf-8")
        print(json.dumps({
            "status":result["status"],"pages":result["output_pages"],
            "paper_size":result["canonical_page_size"],
            "visual_review_pages":result["pages_requiring_visual_review"],
            "result":str(args.output),"report":str(report)
        },ensure_ascii=False))
        return 0
    except (ValueError,RuntimeError,OSError,fitz.FileDataError) as exc:
        print(f"ERROR: {exc}",file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
