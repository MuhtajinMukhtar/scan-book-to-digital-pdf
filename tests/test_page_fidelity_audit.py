"""Synthetic regression tests for content loss, page spill and no-silent-pass."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import fitz

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("page_fidelity_audit", ROOT / "scripts" / "page_fidelity_audit.py")
auditmod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(auditmod)


class PageFidelityTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root / "scan.pdf"
        self.output = self.root / "output.pdf"
        self.ocr = self.root / "ocr"
        self.ocr.mkdir()
        self.manifest = self.root / "manifest.json"
        self.make_pdf(self.source, ["Alpha beta gamma", "Delta epsilon zeta"])
        self.write_ocr()
        self.write_manifest()

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def make_pdf(path, texts):
        pdf = fitz.open()
        for text in texts:
            page = pdf.new_page(width=400, height=500)
            page.insert_text((30, 40), text, fontsize=12)
        pdf.save(path)
        pdf.close()

    def write_ocr(self):
        for idx, value in enumerate(["Alpha beta gamma", "Delta epsilon zeta"], 1):
            (self.ocr / f"page_{idx:03d}.json").write_text(json.dumps({
                "source_sha256": auditmod.sha256(self.source), "page": idx,
                "lines": [{"text": value}]
            }))

    def write_manifest(self):
        self.manifest.write_text(json.dumps({
            "source_sha256": auditmod.sha256(self.source),
            "source_pages": 2, "output_pages": 2,
            "pages": [{"source_page": i, "output_page": i, "mode": "born_digital",
                       "content_verified": True, "images_verified": True,
                       "visual_checked": True, "page_boundary_verified": True,
                       "reading_order_verified": True}
                      for i in range(1, 3)]
        }))

    def run_audit(self):
        return auditmod.audit(self.source, self.output, self.ocr, self.manifest)

    def test_identical_pages_pass(self):
        self.make_pdf(self.output, ["Alpha beta gamma", "Delta epsilon zeta"])
        self.assertEqual(self.run_audit()["status"], "PASS")

    def test_missing_content_is_rejected(self):
        self.make_pdf(self.output, ["Alpha beta", "Delta epsilon zeta"])
        types = {x["type"] for x in self.run_audit()["issues"]}
        self.assertIn("missing_page_text", types)

    def test_spill_detected_even_with_same_page_count(self):
        self.make_pdf(self.output, ["Alpha beta", "Gamma delta epsilon zeta"])
        types = {x["type"] for x in self.run_audit()["issues"]}
        self.assertIn("possible_cross_page_spill", types)

    def test_additional_page_rejected(self):
        self.make_pdf(self.output, ["Alpha beta gamma", "Delta epsilon zeta", "Extra"])
        types = {x["type"] for x in self.run_audit()["issues"]}
        self.assertIn("page_count_mismatch", types)

    def test_missing_ocr_fails_closed(self):
        self.make_pdf(self.output, ["Alpha beta gamma", "Delta epsilon zeta"])
        (self.ocr / "page_002.json").unlink()
        types = {x["type"] for x in self.run_audit()["issues"]}
        self.assertIn("missing_source_ocr", types)

    def test_requires_visual_verification(self):
        self.make_pdf(self.output, ["Alpha beta gamma", "Delta epsilon zeta"])
        doc = json.loads(self.manifest.read_text())
        doc["pages"][0]["visual_checked"] = False
        self.manifest.write_text(json.dumps(doc))
        types = {x["type"] for x in self.run_audit()["issues"]}
        self.assertIn("unverified_page", types)

    def test_justified_verified_ocr_correction(self):
        self.make_pdf(self.output, ["Alpha beta", "Delta epsilon zeta"])
        doc = json.loads(self.manifest.read_text())
        doc["pages"][0]["reviewed_ocr_errors"] = [{"token": "gamma", "count": 1,
          "reason": "Original scan shows beta is final word, OCR hallucinated gamma",
          "reviewer": "editor", "source_excerpt": "Alpha beta", "source_scan_verified": True}]
        self.manifest.write_text(json.dumps(doc))
        self.assertEqual(self.run_audit()["status"], "PASS")

    def test_unverified_ocr_exception_rejected(self):
        self.make_pdf(self.output, ["Alpha beta", "Delta epsilon zeta"])
        doc = json.loads(self.manifest.read_text())
        doc["pages"][0]["reviewed_ocr_errors"] = [{"token": "gamma", "count": 1,
            "reason": "guess", "reviewer": "editor", "source_excerpt": "Alpha beta",
            "source_scan_verified": False}]
        self.manifest.write_text(json.dumps(doc))
        self.assertEqual(self.run_audit()["status"], "FAIL_REVIEW_REQUIRED")


if __name__ == "__main__":
    unittest.main()
