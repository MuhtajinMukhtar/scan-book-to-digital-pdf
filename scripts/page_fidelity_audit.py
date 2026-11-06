#!/usr/bin/env python3
"""Fail-closed audit: scanned source page N maps to output page N on uniform paper.

This is evidence-based QA, not proof OCR read the scan perfectly. A human must
verify uncertain text and image/layout fidelity against each source page.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys

import fitz
from book_page_size import canonical_page_size, matches_page_size


def sha256(path: Path) -> str:
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def tokens(value: str) -> Counter[str]:
    return Counter(re.findall(r"[^\W_]+(?:['’-][^\W_]+)*", value.casefold(), re.UNICODE))


def details(counter: Counter[str], limit: int = 16) -> dict[str, int]:
    return dict(counter.most_common(limit))


def supported_exceptions(entry: dict, kind: str) -> Counter[str]:
    """Require itemized source-reviewed OCR errors, not arbitrary threshold changes."""
    accepted: Counter[str] = Counter()
    for item in entry.get(kind, []):
        if not isinstance(item, dict) or item.get("source_scan_verified") is not True:
            raise ValueError("OCR exception lacks explicit source_scan_verified evidence")
        if not item.get("reason") or not item.get("reviewer") or not item.get("source_excerpt"):
            raise ValueError("OCR exception needs reason, reviewer and source_excerpt")
        word = str(item.get("token", "")).casefold()
        count = item.get("count")
        if len(tokens(word)) != 1 or next(iter(tokens(word)), None) != word:
            raise ValueError("OCR exception must name exactly one normalized token")
        if not isinstance(count, int) or count <= 0:
            raise ValueError("OCR exception count must be a positive integer")
        accepted[word] += count
    return accepted


def audit(source: Path, output: Path, ocr_dir: Path, manifest_file: Path) -> dict:
    source_hash = sha256(source)
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    issues: list[dict] = []
    page_rows: list[dict] = []
    with fitz.open(source) as src, fitz.open(output) as dst:
        n = len(src)
        paper = canonical_page_size(src)
        output_count = len(dst)
        if n != len(dst):
            issues.append({"type": "page_count_mismatch", "source": n, "output": len(dst)})
        if manifest.get("source_sha256") != source_hash:
            issues.append({"type": "manifest_source_sha_mismatch"})
        if manifest.get("source_pages") != n or manifest.get("output_pages") != len(dst):
            issues.append({"type": "manifest_count_mismatch"})
        entries = manifest.get("pages")
        if not isinstance(entries, list):
            entries = []
        by_page = {}
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("source_page"), int):
                issues.append({"type": "invalid_manifest_entry"})
                continue
            i = entry["source_page"]
            if i in by_page:
                issues.append({"type": "duplicate_manifest_page", "page": i})
            by_page[i] = entry
            if entry.get("output_page") != i:
                issues.append({"type": "page_mapping_not_identity", "page": i,
                               "output_page": entry.get("output_page")})
        if set(by_page) != set(range(1, n + 1)) or len(entries) != n:
            issues.append({"type": "incomplete_page_manifest"})
        expected: dict[int, Counter[str]] = {}
        actual: dict[int, Counter[str]] = {}
        extras: dict[int, Counter[str]] = {}
        missing: dict[int, Counter[str]] = {}
        for i in range(1, n + 1):
            entry = by_page.get(i, {})
            if entry.get("mode") not in ("born_digital", "searchable_scan_fallback"):
                issues.append({"type": "missing_page_mode", "page": i})
            for flag in ("content_verified", "images_verified", "visual_checked", "page_boundary_verified", "reading_order_verified"):
                if entry.get(flag) is not True:
                    issues.append({"type": "unverified_page", "page": i, "flag": flag})
            record = ocr_dir / f"page_{i:03d}.json"
            if not record.is_file():
                issues.append({"type": "missing_source_ocr", "page": i})
                continue
            data = json.loads(record.read_text(encoding="utf-8"))
            if data.get("source_sha256") != source_hash or data.get("page") != i:
                issues.append({"type": "source_ocr_identity_mismatch", "page": i})
                continue
            lines = data.get("lines")
            if not isinstance(lines, list):
                issues.append({"type": "invalid_source_ocr", "page": i})
                continue
            expected[i] = tokens(" ".join(x.get("text", "") for x in lines))
            if not expected[i] and entry.get("source_page_has_no_text_verified") is not True:
                issues.append({"type": "empty_source_ocr_unverified", "page": i})
            if i > len(dst):
                continue
            page = dst[i-1]
            actual[i] = tokens(page.get_text("text"))
            if entry.get("mode") == "born_digital" and actual[i]:
                traces = page.get_texttrace()
                if not any(t.get("type") != 3 and t.get("chars") for t in traces):
                    issues.append({"type": "no_visible_digital_text", "page": i})
            size_b = page.rect
            if not matches_page_size(page, paper):
                issues.append({
                    "type": "page_size_not_uniform", "page": i,
                    "expected": [paper["width_pt"], paper["height_pt"]],
                    "actual": [round(size_b.width,2), round(size_b.height,2)]
                })
            outside = [word[4] for word in page.get_text("words") if
                       word[0] < -.5 or word[1] < -.5 or
                       word[2] > size_b.width + .5 or word[3] > size_b.height + .5]
            if outside:
                issues.append({"type": "text_out_of_bounds", "page": i, "examples": outside[:8]})
            m = expected[i] - actual[i]
            e = actual[i] - expected[i]
            missing[i], extras[i] = m, e
            try:
                allowed_missing = supported_exceptions(entry, "reviewed_ocr_errors")
                allowed_extra = supported_exceptions(entry, "reviewed_output_additions")
            except ValueError as err:
                issues.append({"type": "invalid_review_exception", "page": i, "detail": str(err)})
                allowed_missing = Counter()
                allowed_extra = Counter()
            if allowed_missing - m or allowed_extra - e:
                issues.append({"type": "review_exception_does_not_match", "page": i})
            unexplained_missing = m - allowed_missing
            unexplained_extra = e - allowed_extra
            if unexplained_missing:
                issues.append({"type": "missing_page_text", "page": i,
                               "tokens": details(unexplained_missing)})
            if unexplained_extra:
                issues.append({"type": "extra_page_text", "page": i,
                               "tokens": details(unexplained_extra)})
            page_rows.append({"page": i, "source_words": sum(expected[i].values()),
                              "output_words": sum(actual[i].values()),
                              "missing": details(m), "extra": details(e),
                              "reviewed_ocr_errors": details(allowed_missing),
                              "reviewed_output_additions": details(allowed_extra)})
        for i in sorted(missing):
            for neighbor in (i - 1, i + 1):
                if neighbor not in extras:
                    continue
                leaked = missing[i] & extras[neighbor]
                if leaked:
                    issues.append({"type": "possible_cross_page_spill", "from_page": i,
                                   "to_page": neighbor, "tokens": details(leaked)})
    if sha256(source) != source_hash:
        issues.append({"type": "source_modified_during_audit"})
    return {"status": "PASS" if not issues else "FAIL_REVIEW_REQUIRED",
            "source_pages": n, "output_pages": output_count,
            "canonical_page_size": paper,
            "source_sha256": source_hash, "issues": issues,
            "page_data": page_rows,
            "limitations": "OCR and extracted PDF text are imperfect; visual checks and verified corrections remain mandatory."}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--source-ocr-dir", type=Path, required=True)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--json", type=Path, required=True)
    args = p.parse_args()
    for f in (args.source, args.output, args.manifest):
        if not f.is_file():
            p.error(f"Missing file: {f}")
    if not args.source_ocr_dir.is_dir():
        p.error("Missing source OCR directory")
    report = audit(args.source, args.output, args.source_ocr_dir, args.manifest)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "source_pages": report["source_pages"],
                      "output_pages": report["output_pages"], "issue_count": len(report["issues"]),
                      "report": str(args.json)}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
