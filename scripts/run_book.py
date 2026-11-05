#!/usr/bin/env python3
"""Mac-friendly low-token driver: pilot -> human approval -> full book.

The AI's job is to call this program, review exceptional pages, and present
the pilot to the user. The OCR engines and PDF layout run locally without
per-page LLM calls. Run --help for controls.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

import fitz
from local_book_engine import build, comparison, font_path, parse_pages, sha256


HERE = Path(__file__).resolve().parent


def run_ocr(source: Path, work: Path, pages: list[int] | None, dpi: int) -> None:
    cmd = [sys.executable, str(HERE / "mac_hybrid_ocr.py"), str(source),
           "--work-dir", str(work), "--dpi", str(dpi)]
    if pages is not None:
        cmd += ["--pages", ",".join(str(i) for i in pages)]
    subprocess.run(cmd, check=True)


def json_write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def pilot(args: argparse.Namespace) -> int:
    with fitz.open(args.source) as doc:
        pages = parse_pages(args.pages, len(doc), "pilot")
    if len(pages) < 2:
        raise ValueError("A meaningful typographic pilot requires at least 2 source pages")
    if not args.skip_ocr:
        run_ocr(args.source, args.work_dir, pages, args.dpi)
    local_font = font_path(args.font_family, args.font_file)
    pilot_dir = args.work_dir / "pilot"
    out = pilot_dir / "Book_Pilot_REVIEW.pdf"
    report = build(args.source, args.work_dir, out, "pilot", pages,
                   args.font_family, local_font, args.font_size)
    comparison(args.source, out, pages, pilot_dir / "Book_Pilot_Comparison.pdf")
    style = {
        "source_sha256": report["source_sha256"],
        "source_pages": report["source_page_count"],
        "selected_source_pages": pages,
        "font_family": args.font_family,
        "font_file": str(local_font.resolve()),
        "font_file_sha256": sha256(local_font),
        "body_font_size_pt": report["body_font_size_pt"],
        "engine_version": 1,
    }
    style_path = pilot_dir / "style-profile.json"
    json_write(style_path, style)
    needs_more = report["digital_pages"] < 2
    summary = {
        "status": "PILOT_INCOMPLETE" if needs_more else "PILOT_AWAITING_APPROVAL",
        "digital_sample_pages": report["digital_pages"],
        "fallback_sample_pages": report["fallback_pages"],
        "style_profile_sha256": sha256(style_path),
        "pilot_pdf": str(out), "comparison_pdf": str(pilot_dir / "Book_Pilot_Comparison.pdf"),
        "note": "Source text, graphics, and typography still need human review; no full-book run authorized.",
    }
    json_write(pilot_dir / "pilot-status.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not needs_more else 2


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
    if status.get("status") != "PILOT_AWAITING_APPROVAL":
        raise ValueError("Pilot has fewer than two verified visible typeset candidates")
    if style.get("source_sha256") != sha256(args.source):
        raise ValueError("Pilot belongs to a different original PDF")
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
    if approval.get("source_sha256") != source_sha or approval.get("decision") != "PILOT_APPROVED":
        raise ValueError("Pilot approval is absent or belongs to a different PDF")
    if approval.get("style_profile_sha256") != sha256(style_path) or style.get("source_sha256") != source_sha:
        raise ValueError("Locked typography style was modified after approval")
    local_font = Path(style["font_file"])
    if not local_font.is_file() or sha256(local_font) != style.get("font_file_sha256"):
        raise ValueError("Approved font file changed or is unavailable")
    if not args.skip_ocr:
        run_ocr(args.source, args.work_dir, None, args.dpi)
    with fitz.open(args.source) as src:
        pages = list(range(1, len(src)+1))
    out = args.output or (args.work_dir / "output" / "Book_Full_REVIEW.pdf")
    result = build(args.source, args.work_dir, out, "full", pages,
                   style["font_family"], local_font, style["body_font_size_pt"],
                   approval=approval_path)
    print(json.dumps({
        "status": result["status"], "source_pages": result["source_page_count"],
        "output_pages": result["output_page_count"],
        "digitally_typeset_pages": result["digital_pages"],
        "searchable_scan_fallback_pages": result["fallback_pages"],
        "needs_editorial_review": True,
        "pdf": str(out),
    }, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("pilot", "approve", "full"):
        p = sub.add_parser(name)
        p.add_argument("--source", type=Path, required=True)
        p.add_argument("--work-dir", type=Path, required=True)
        if name in ("pilot", "full"):
            p.add_argument("--skip-ocr", action="store_true", help="Reuse already verified OCR/fusion caches (works off-Mac)")
            p.add_argument("--dpi", type=int, default=230)
        if name == "pilot":
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
    if hasattr(args, "dpi") and not 120 <= args.dpi <= 300:
        parser.error("DPI must be 120..300 to bound resource usage")
    try:
        return {"pilot": pilot, "approve": approve, "full": full}[args.command](args)
    except (ValueError, RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
