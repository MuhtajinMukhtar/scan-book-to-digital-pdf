#!/usr/bin/env python3
"""Fail-closed digital-text policy for non-cover scanned-book pages.

The policy does not claim character-level OCR or exact editorial fidelity.
It catches incomplete full-book reconstruction, hidden OCR on full-page scans
and unreviewed cover exemptions; source-based fidelity QA is a separate gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import fitz
from book_page_size import canonical_page_size, matches_page_size


def sha256(path: Path) -> str:
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def allowed_cover_pages(source: Path, evidence_path: Path | None) -> list[int]:
    """A visually verified front/back cover is the only raster exemption."""
    if evidence_path is None or not evidence_path.is_file():
        return []
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    with fitz.open(source) as book:
        count = len(book)
    if evidence.get("source_sha256") != sha256(source):
        raise ValueError("Cover exemption belongs to another source PDF")
    listed = evidence.get("pages", [])
    if not isinstance(listed, list):
        raise ValueError("Cover evidence.pages must be a list")
    seen = set()
    for row in listed:
        if not isinstance(row, dict):
            raise ValueError("Cover evidence item must be an object")
        number = row.get("source_page")
        if not isinstance(number, int) or isinstance(number, bool) or number not in (1, count):
            raise ValueError("Only physical first/last page can be marked as a cover")
        if number in seen:
            raise ValueError("Duplicate cover exemption")
        if row.get("source_scan_verified") is not True:
            raise ValueError("Cover exemption needs explicit source-scan verification")
        if row.get("kind") not in ("front_cover", "back_cover"):
            raise ValueError("Cover exemption must be front_cover or back_cover")
        if (number == 1 and row["kind"] != "front_cover"
                or number == count and row["kind"] != "back_cover"):
            # A single-page book is ambiguous and will be reviewed instead.
            raise ValueError("Cover position and cover kind disagree")
        if not str(row.get("source_description", "")).strip():
            raise ValueError("Cover exemption needs observed visual description")
        seen.add(number)
    return sorted(seen)


def largest_effective_raster_ratio(page: fitz.Page) -> float:
    """Account for *visible clipping* of images nested in PDF Form XObjects.

    PyMuPDF get_image_info() alone reports full 100% image bboxes even when a
    page's source scan is *only painted in a 36-pt footer crop*. Follow the
    image's referencing Form parents and intersect their effective bboxes.
    """
    forms = {xref: {"parent": parent, "bbox": fitz.Rect(bbox)}
             for xref, _name, parent, bbox in page.get_xobjects()}
    parents_by_image = {}
    for row in page.get_images(full=True):
        if len(row) >= 10:
            parents_by_image.setdefault(row[0], set()).add(row[-1])
    ratios=[]
    for info in page.get_image_info(xrefs=True):
        bbox=info.get("bbox")
        if not bbox:
            continue
        image_box=fitz.Rect(bbox) & page.rect
        if image_box.is_empty:
            continue
        xref=info.get("xref",0)
        parents=parents_by_image.get(xref,{0})
        for direct_parent in parents:
            clipped=fitz.Rect(image_box)
            current=direct_parent
            visited=set()
            while current:
                if current in visited or current not in forms:
                    # Unknown/damaged form graph: treat it conservatively.
                    clipped=image_box
                    break
                visited.add(current)
                form=forms[current]
                clipped &= form["bbox"]
                if clipped.is_empty:
                    break
                current=form["parent"]
            if not clipped.is_empty:
                ratios.append(clipped.get_area()/max(.01,page.rect.get_area()))
    return round(max(ratios,default=0.0),3)


def assess(source: Path, output: Path, qa_file: Path,
           cover_evidence: Path | None = None) -> dict:
    issues = []
    if not qa_file.is_file():
        raise ValueError("Missing compositor per-page QA JSON")
    qa = json.loads(qa_file.read_text(encoding="utf-8"))
    source_hash = sha256(source)
    if qa.get("source_sha256") != source_hash:
        raise ValueError("Compositor QA source PDF hash mismatch")
    covers = allowed_cover_pages(source, cover_evidence)
    with fitz.open(source) as original, fitz.open(output) as out:
        count = len(original)
        paper = canonical_page_size(original,set(covers))
        reported_paper = qa.get("canonical_page_size")
        if reported_paper is not None and (
            abs(float(reported_paper.get("width_pt", 0)) - paper["width_pt"]) > .02
            or abs(float(reported_paper.get("height_pt", 0)) - paper["height_pt"]) > .02
        ):
            issues.append({"type":"canonical_paper_report_mismatch"})
        if len(out) != count:
            issues.append({"type":"page_count_mismatch","expected":count,"got":len(out)})
        rows=qa.get("per_page",[])
        if not isinstance(rows,list):
            raise ValueError("Compositor QA per_page must be a list")
        mapped={}
        for row in rows:
            if not isinstance(row,dict):
                issues.append({"type":"invalid_per_page_entry"})
                continue
            number=row.get("source_page")
            if not isinstance(number,int) or isinstance(number,bool) or number in mapped:
                issues.append({"type":"duplicate_or_invalid_source_page","page":number})
                continue
            mapped[number]=row
            if row.get("output_page") != number:
                issues.append({"type":"source_output_mapping_mismatch","page":number})
        if set(mapped)!=set(range(1,count+1)):
            issues.append({"type":"incomplete_page_qa_mapping"})
        page_results=[]
        for number in range(1,count+1):
            if number>len(out):
                break
            src=original[number-1]
            page=out[number-1]
            mode=mapped.get(number,{}).get("mode")
            if not matches_page_size(page,paper):
                issues.append({
                    "type":"page_size_not_uniform","page":number,
                    "expected_width_pt":paper["width_pt"],
                    "expected_height_pt":paper["height_pt"],
                    "actual_width_pt":round(page.rect.width,2),
                    "actual_height_pt":round(page.rect.height,2)
                })
            trace=page.get_texttrace()
            visible_chars=sum(len(item.get("chars",[])) for item in trace
                              if item.get("type") != 3 and float(item.get("opacity",1))>.5)
            max_raster=largest_effective_raster_ratio(page)
            exempt=number in covers
            problems=[]
            if not exempt:
                if mode!="born_digital_unverified":
                    problems.append("whole_page_scan_fallback_not_allowed")
                if visible_chars<3:
                    problems.append("no_visible_selectable_digital_text")
                if max_raster>=.85:
                    problems.append("near_full_page_raster_requires_reconstruction")
            for code in problems:
                issues.append({"type":code,"page":number})
            page_results.append({
                "source_page":number, "mode":mode,
                "cover_exempt_with_source_evidence":exempt,
                "visible_vector_chars":visible_chars,
                "largest_raster_page_ratio":max_raster,
                "digital_text_policy_pass":not problems
            })
    return {
        "policy":"DIGITAL_TEXT_ALL_PAGES_EXCEPT_VERIFIED_COVERS_V1",
        "status":"READY_FOR_EDITORIAL_FIDELITY_REVIEW" if not issues else "INCOMPLETE_DIGITAL_PAGES",
        "source_sha256":source_hash,
        "source_pages":count,
        "canonical_page_size":paper,
        "all_pages_same_paper":not any(i.get("type")=="page_size_not_uniform" for i in issues),
        "exempt_cover_pages":covers,
        "incomplete_noncover_pages":sorted({
            i.get("page") for i in issues if isinstance(i.get("page"),int) and i.get("page") not in covers
        }),
        "issues":issues,
        "per_page":page_results,
        "limitations":"Visible vector text and no full-page scan are necessary, not sufficient. "
                      "Tables, captions, italics, sequence and characters require source review. "
                      "Raster photos/illustrations remain permitted as individual assets, "
                      "not as the unconverted full scanned page.",
    }


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--qa",type=Path,required=True)
    p.add_argument("--cover-evidence",type=Path)
    p.add_argument("--json",type=Path,required=True)
    args=p.parse_args()
    try:
        for path in (args.source,args.output,args.qa):
            if not path.is_file():
                raise ValueError(f"Missing required file: {path}")
        result=assess(args.source,args.output,args.qa,args.cover_evidence)
        args.json.parent.mkdir(parents=True,exist_ok=True)
        args.json.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        print(json.dumps({
            "status":result["status"],
            "incomplete_noncover_pages":result["incomplete_noncover_pages"],
            "cover_pages":result["exempt_cover_pages"],
            "report":str(args.json)
        },ensure_ascii=False))
        return 0 if not result["issues"] else 2
    except (ValueError,OSError,RuntimeError,fitz.FileDataError) as exc:
        print("POLICY_GATE_ERROR: "+str(exc),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
