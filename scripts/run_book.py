#!/usr/bin/env python3
"""Mac-friendly low-token driver: pilot -> human approval -> full book.

The AI's job is to call this program, review exceptional pages, and present
the pilot to the user. Apple Vision primary and optional PP-OCRv5 Mobile review run locally without
per-page LLM calls. Run --help for controls.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

import fitz
from local_book_engine import build, comparison, font_path, parse_pages, sha256
from select_pilot_pages import choose
from pilot_archetypes import select_diverse, contact_sheet
from digital_text_policy_gate import assess as assess_digital_text, allowed_cover_pages
from page_typography import LAYOUT_REVISION


HERE = Path(__file__).resolve().parent


def run_ocr(source: Path, work: Path, pages: list[int], dpi: int,
            cpu_threads: int = 2, mobile: bool = False,
            allow_download: bool = False, max_mobile_pages: int = 1,
            skip_vision: bool = False) -> dict:
    """Always read with Apple Vision; compare suspicious pages only, if authorized."""
    cmd = [sys.executable, str(HERE / "mac_selective_ocr.py"), str(source),
           "--work-dir", str(work), "--dpi", str(dpi),
           "--pages", ",".join(str(x) for x in pages),
           "--max-mobile-pages", str(max_mobile_pages)]
    if mobile:
        cmd.append("--enable-mobile")
    if allow_download:
        cmd.append("--allow-model-download")
    if skip_vision:
        cmd.append("--skip-vision")
    env = os.environ.copy()
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
                 "VECLIB_MAXIMUM_THREADS"):
        env[name] = str(cpu_threads)
    result = subprocess.run(cmd, check=True, env=env, capture_output=True, text=True)
    return json.loads(result.stdout)


def json_write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def pilot(args: argparse.Namespace) -> int:
    """Two-page smoke test, then distinct-source archetype review before approval."""
    pilot_dir = args.work_dir / "pilot"
    with fitz.open(args.source) as doc:
        total = len(doc)
    src_hash = sha256(args.source)
    if args.pages == "auto":
        if args.stage == "smoke":
            selection = choose(args.source, count=2)
            selection["source_sha256"] = src_hash
            selection["pilot_stage"] = "smoke"
            pages = selection["pages"]
            json_write(pilot_dir / "selection.json", selection)
        else:
            smoke_file = pilot_dir / "selection.json"
            keep = []
            if smoke_file.is_file():
                old = json.loads(smoke_file.read_text(encoding="utf-8"))
                if old.get("source_sha256") == src_hash:
                    keep = old.get("pages", [])
            selection = select_diverse(args.source, count=args.review_count,
                                       keep_pages=keep)
            selection["source_sha256"] = src_hash
            selection["pilot_stage"] = "review"
            pages = selection["pages"]
            json_write(pilot_dir / "review-selection.json", selection)
            contact_sheet(args.source, selection,
                          pilot_dir / "Source_Review_Candidates.pdf")
    else:
        with fitz.open(args.source) as doc:
            pages = parse_pages(args.pages, len(doc), "pilot")
        selection = {
            "pilot_stage": args.stage, "pages": pages, "source_sha256": src_hash,
            "method": "manual selection of source physical page numbers",
            "human_visual_verification_required": True,
        }
        json_write(pilot_dir / ("selection.json" if args.stage=="smoke"
                                else "review-selection.json"), selection)
    if len(pages) < min(2, total):
        raise ValueError("Pilot must contain at least two pages for a multi-page book")
    min_review = min(total, 5)
    enough_variety = args.stage == "review" and len(pages) >= min_review
    cover_file = args.work_dir / "cover-evidence.json"
    verified_covers = allowed_cover_pages(args.source, cover_file)
    ocr_pages = [n for n in pages if n not in verified_covers]
    ocr_summary = None
    if not args.skip_ocr and ocr_pages:
        ocr_summary = run_ocr(args.source, args.work_dir, ocr_pages, args.dpi,
                              args.cpu_threads, args.enable_mobile,
                              args.allow_model_download, args.max_mobile_pages,
                              skip_vision=args.reuse_apple)
    local_font = font_path(args.font_family, args.font_file)
    out = pilot_dir / "Book_Pilot_REVIEW.pdf"
    source_styles = args.work_dir / "style-annotations.json"
    report = build(args.source, args.work_dir, out, "pilot", pages,
                   args.font_family, local_font, args.font_size,
                   strict_hybrid=False, fusion_subdir="fusion_mobile",
                   style_annotations=source_styles,
                   verified_cover_pages=set(verified_covers))
    comparison(args.source, out, pages, pilot_dir / "Book_Pilot_Comparison.pdf")
    style = {
        "source_sha256": report["source_sha256"],
        "source_pages": report["source_page_count"],
        "selected_source_pages": pages,
        "font_family": args.font_family,
        "font_file": str(local_font.resolve()),
        "font_file_sha256": sha256(local_font),
        "body_font_size_pt": report["body_font_size_pt"],
        "style_annotations_sha256": (sha256(source_styles) if source_styles.is_file() else None),
        "cover_evidence_sha256": (sha256(cover_file) if cover_file.is_file() else None),
        "verified_cover_pages": verified_covers,
        "digital_text_policy": "all_noncover_text_must_be_visible_vector",
        "engine_version": LAYOUT_REVISION,
        "ocr_backend": "apple-vision-primary+paddle-mobile-selective",
        "pilot_stage": args.stage,
    }
    style_path = pilot_dir / "style-profile.json"
    json_write(style_path, style)
    # A representative pilot with scanned fallback pages is NOT proof that the
    # engine digitally reconstructs tables, images or formatted text. Report
    # the honest limitation and block approval instead of promising 220 pages.
    fallback_source_pages = [entry["source_page"] for entry in report["per_page"]
                             if entry["mode"] not in (
                                 "born_digital_unverified", "verified_cover_raster_exempt"
                             )]
    insufficient_digital = report["digital_pages"] < min(2,len(ocr_pages))
    if ocr_summary is None:
        review_path = args.work_dir / "review" / "SUMMARY.json"
        if review_path.exists():
            previous = json.loads(review_path.read_text(encoding="utf-8"))
            if previous.get("source_sha256") == src_hash:
                ocr_summary = previous
    pending = sorted(set((ocr_summary or {}).get("secondary_pending_pages", []))
                     & set(pages))
    status = ("PILOT_INCOMPLETE" if insufficient_digital else
              "PILOT_SMOKE_COMPLETE" if args.stage == "smoke" else
              "PILOT_INSUFFICIENT_VARIETY" if not enough_variety else
              "PILOT_NEEDS_LAYOUT_WORK" if fallback_source_pages else
              "PILOT_NEEDS_OCR_REVIEW" if pending else
              "PILOT_AWAITING_APPROVAL")
    summary = {
        "status": status,
        "pilot_stage": args.stage,
        "source_page_count": total,
        "selected_pages": pages,
        "pilot_pages": len(pages),
        "minimum_representative_pages": min_review,
        "candidate_roles": selection.get("roles", {}),
        "candidate_roles_not_verified": True,
        "needs_agent_inspection_of_thumbnails": args.stage=="review",
        "source_thumbnail_overview": (str(pilot_dir / "Source_Review_Candidates.pdf")
                                       if args.stage=="review" and args.pages=="auto" else None),
        "digital_sample_pages": report["digital_pages"],
        "ocr_primary": "apple-vision",
        "ocr_secondary": "paddle-ppocrv5-mobile-only-if-needed",
        "secondary_pending_pages": pending,
        "secondary_pending_reasons": (ocr_summary or {}).get("secondary_pending_reasons", {}),
        "fallback_sample_pages": report["fallback_pages"],
        "source_verified_cover_pages": verified_covers,
        "fallback_source_pages": fallback_source_pages,
        "layout_reconstruction_complete": not fallback_source_pages,
        "approval_blocked_reason": (
            "Some representative pages are still whole-page scanned fallbacks. "
            "Reconstruct their visible text and preserve illustration/photo assets "
            "before asking approval for a digitally typeset book."
            if fallback_source_pages else None
        ),
        "style_profile_sha256": sha256(style_path),
        "pilot_pdf": str(out),
        "comparison_pdf": str(pilot_dir / "Book_Pilot_Comparison.pdf"),
        "note": ("Two pages are a technical smoke test, NOT enough for final "
                 "user approval. Review must include distinct source archetypes; "
                 "label scan fallbacks; verify page types in the contact sheet."),
        "styles_need_visual_review": True,
    }
    json_write(pilot_dir / "pilot-status.json", summary)
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    return 0 if not insufficient_digital else 2


def approve(args: argparse.Namespace) -> int:
    pilot_dir = args.work_dir / "pilot"
    status_path = pilot_dir / "pilot-status.json"
    style_path = pilot_dir / "style-profile.json"
    if args.confirm != "APPROVE_PILOT":
        raise ValueError("Approval must be an explicit user choice, not inferred from running a script")
    if not status_path.is_file() or not style_path.is_file():
        raise ValueError("No completed pilot found")
    status = json.loads(status_path.read_text(encoding="utf-8"))
    style = json.loads(style_path.read_text(encoding="utf-8"))
    if status.get("pilot_stage") != "review" or status.get("status") != "PILOT_AWAITING_APPROVAL":
        raise ValueError("Full-book approval requires a fully typeset, source-checked REVIEW pilot, not an incomplete or scan-fallback sample")
    if status.get("fallback_sample_pages", 0) or status.get("fallback_source_pages"):
        raise ValueError("Scan-fallback pilot pages cannot authorize full-book digital conversion")
    with fitz.open(args.source) as original:
        source_pages = len(original)
    if status.get("source_page_count") != source_pages:
        raise ValueError("Pilot summary count does not match the supplied book")
    required = min(status["source_page_count"],5)
    if len(set(status.get("selected_pages",[]))) < required:
        raise ValueError("Pilot samples do not cover enough distinct physical pages")
    if style.get("source_sha256") != sha256(args.source):
        raise ValueError("Pilot belongs to a different original PDF")
    if style.get("engine_version") != LAYOUT_REVISION:
        raise ValueError("Pilot uses an older paragraph layout engine; regenerate PDF from cached OCR")
    cover_file = args.work_dir / "cover-evidence.json"
    if style.get("cover_evidence_sha256") != (
        sha256(cover_file) if cover_file.is_file() else None
    ):
        raise ValueError("Cover evidence changed since the reviewed pilot")
    record = {
        "decision": "PILOT_APPROVED",
        "source_sha256": style["source_sha256"],
        "style_profile_sha256": sha256(style_path),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "approval_note": args.note or "User explicitly approved displayed digital pilot",
    }
    json_write(pilot_dir / "approval.json", record)
    print("PILOT_APPROVED (user confirmation recorded).")
    return 0


def full(args: argparse.Namespace) -> int:
    pilot_dir = args.work_dir / "pilot"
    approval_path = pilot_dir / "approval.json"
    style_path = pilot_dir / "style-profile.json"
    if not approval_path.exists() or not style_path.exists():
        raise ValueError("Cannot process full book without explicit, source-matching pilot approval")
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    style = json.loads(style_path.read_text(encoding="utf-8"))
    source_sha = sha256(args.source)
    if style.get("engine_version") != LAYOUT_REVISION:
        raise ValueError("Paragraph layout algorithm changed; rerender and reapprove pilot using OCR cache")
    if approval.get("source_sha256") != source_sha or approval.get("decision") != "PILOT_APPROVED":
        raise ValueError("Pilot approval is absent or belongs to a different PDF")
    if approval.get("style_profile_sha256") != sha256(style_path) or style.get("source_sha256") != source_sha:
        raise ValueError("Locked typography style was modified after approval")
    source_styles = args.work_dir / "style-annotations.json"
    old_style_sha = style.get("style_annotations_sha256")
    new_style_sha = sha256(source_styles) if source_styles.is_file() else None
    if old_style_sha != new_style_sha:
        raise ValueError("Source-verified italic styles changed since pilot approval; redo pilot")
    cover_file = args.work_dir / "cover-evidence.json"
    if style.get("cover_evidence_sha256") != (
        sha256(cover_file) if cover_file.is_file() else None
    ):
        raise ValueError("Cover evidence has changed since pilot approval")
    verified_covers = allowed_cover_pages(args.source, cover_file)
    if style.get("verified_cover_pages", []) != verified_covers:
        raise ValueError("Verified cover page list changed since the pilot")
    if style.get("digital_text_policy") != "all_noncover_text_must_be_visible_vector":
        raise ValueError("Pilot was approved before strict all-noncover-digital policy")
    if style.get("ocr_backend") != "apple-vision-primary+paddle-mobile-selective":
        raise ValueError("Pilot approved for a different OCR backend; run a fresh safe pilot")
    local_font = Path(style["font_file"])
    if not local_font.is_file() or sha256(local_font) != style.get("font_file_sha256"):
        raise ValueError("Approved font file changed or is unavailable")
    with fitz.open(args.source) as src:
        pages = list(range(1, len(src)+1))
    ocr_summary = None
    ocr_pages = [n for n in pages if n not in verified_covers]
    if not args.skip_ocr and ocr_pages:
        ocr_summary = run_ocr(args.source, args.work_dir, ocr_pages, args.dpi,
                              args.cpu_threads, args.enable_mobile,
                              args.allow_model_download, args.max_mobile_pages,
                              skip_vision=args.reuse_apple)
    out = args.output or (args.work_dir / "output" / "Book_Full_REVIEW.pdf")
    result = build(args.source, args.work_dir, out, "full", pages,
                   style["font_family"], local_font, style["body_font_size_pt"],
                   approval=approval_path, strict_hybrid=False,
                   fusion_subdir="fusion_mobile", style_annotations=source_styles,
                   verified_cover_pages=set(verified_covers))
    policy = assess_digital_text(
        args.source, out, out.with_suffix(".qa.json"),
        cover_file if cover_file.is_file() else None
    )
    policy_file = out.with_suffix(".digital-policy.json")
    json_write(policy_file, policy)
    print(json.dumps({
        "status": policy["status"], "source_pages": result["source_page_count"],
        "output_pages": result["output_page_count"],
        "digitally_typeset_pages": result["digital_pages"],
        "searchable_scan_fallback_pages": result["fallback_pages"],
        "needs_editorial_review": True,
        "incomplete_noncover_pages": policy["incomplete_noncover_pages"],
        "verified_cover_pages": policy["exempt_cover_pages"],
        "digital_policy_report": str(policy_file),
        "secondary_pending_pages": (ocr_summary or {}).get("secondary_pending_pages", []),
        "pdf": str(out),
        "note": ("Draft preserved for correction; NOT a completed digital book"
                 if policy["issues"] else "Digital-text gate passed; source fidelity review still mandatory"),
    }, ensure_ascii=False, indent=2))
    return 0 if not policy["issues"] else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("pilot", "approve", "full"):
        p = sub.add_parser(name)
        p.add_argument("--source", type=Path, required=True)
        p.add_argument("--work-dir", type=Path, required=True)
        if name in ("pilot", "full"):
            p.add_argument("--skip-ocr", action="store_true",
                           help="Rerender layout using existing OCR caches; no OCR invoked")
            p.add_argument("--reuse-apple", action="store_true",
                           help="Reuse Apple Vision cache; evaluate optional Mobile on uncertain pages")
            p.add_argument("--dpi", type=int, default=180)
            p.add_argument("--cpu-threads", type=int, default=2,
                           help="Bound local OCR thread count")
            p.add_argument("--enable-mobile", action="store_true",
                           help="Explicit user opt-in: selectively run PP-OCRv5 Mobile only")
            p.add_argument("--allow-model-download", action="store_true",
                           help="Separate user consent to download lightweight Mobile models")
            p.add_argument("--max-mobile-pages", type=int, default=1,
                           help="Hard cap on additional Mobile OCR pages per run")
        if name == "pilot":
            p.add_argument("--stage", choices=["smoke","review"], default="smoke",
                           help="First 2-page smoke test, then 6-8-page representative review")
            p.add_argument("--review-count", type=int, default=7,
                           help="Count of distinct physical sample pages, 5..8")
            p.add_argument("--pages", default="auto")
            p.add_argument("--font-family", choices=["serif", "sans"], default="sans")
            p.add_argument("--font-file")
            p.add_argument("--font-size", type=float)
        if name == "approve":
            p.add_argument("--confirm", required=True, help="Use APPROVE_PILOT only after actual user acceptance")
            p.add_argument("--note")
        if name == "full":
            p.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.source.is_file():
        parser.error("Source PDF not found")
    if hasattr(args,"review_count") and not 5 <= args.review_count <= 8:
        parser.error("--review-count must be between 5 and 8")
    if hasattr(args, "reuse_apple") and args.reuse_apple and args.skip_ocr:
        parser.error("--reuse-apple and --skip-ocr are mutually exclusive")
    if hasattr(args, "max_mobile_pages") and not 0 <= args.max_mobile_pages <= 5:
        parser.error("--max-mobile-pages must be 0..5")
    if hasattr(args, "allow_model_download") and args.allow_model_download and not args.enable_mobile:
        parser.error("--allow-model-download requires --enable-mobile")
    if hasattr(args, "cpu_threads") and not 1 <= args.cpu_threads <= 8:
        parser.error("--cpu-threads must be 1..8")
    if hasattr(args, "dpi") and not 120 <= args.dpi <= 230:
        parser.error("Safe OCR DPI must be 120..230 to bound resource usage")
    try:
        return {"pilot": pilot, "approve": approve, "full": full}[args.command](args)
    except (ValueError, RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
