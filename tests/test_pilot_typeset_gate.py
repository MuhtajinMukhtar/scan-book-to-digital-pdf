"""Synthetic regression tests: scan + hidden OCR cannot pass as a digital pilot."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest

import fitz
from PIL import Image, ImageDraw
import io

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("pilot_typeset_gate", ROOT / "scripts" / "pilot_typeset_gate.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def scanned_page_png() -> bytes:
    img = Image.new("RGB", (400, 500), "white")
    draw = ImageDraw.Draw(img)
    for i in range(14):
        draw.text((20, 25+i*26), "Scanned bitmap words of a book page", fill="black")
    data = io.BytesIO()
    img.save(data, format="PNG")
    return data.getvalue()


class PilotTypesetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root / "source.pdf"
        self.pilot = self.root / "pilot.pdf"
        pdf = fitz.open()
        png = scanned_page_png()
        for _ in range(3):
            page = pdf.new_page(width=400, height=500)
            page.insert_image(page.rect, stream=png)
        pdf.save(self.source)
        pdf.close()

    def tearDown(self):
        self.tmp.cleanup()

    def make_pilot(self, kinds):
        pdf = fitz.open()
        png = scanned_page_png()
        for kind in kinds:
            page = pdf.new_page(width=400, height=500)
            if kind == "scan":
                page.insert_image(page.rect, stream=png)
                page.insert_text((20, 20), "Hidden OCR for search " * 20, render_mode=3, fontsize=9)
            else:
                for n in range(12):
                    page.insert_text((20, 28+n*30), "This is visible digital text in a book chapter.", fontsize=12)
                if kind == "illustrated":
                    small = fitz.Rect(300, 100, 380, 200)
                    page.insert_image(small, stream=png)
        pdf.save(self.pilot)
        pdf.close()

    def test_rejects_scan_with_hidden_ocr(self):
        self.make_pilot(["scan", "scan", "scan"])
        report = mod.assess_pilot(self.source, self.pilot, [1, 2, 3], min_typeset=2)
        self.assertEqual(report["status"], "FAIL_NOT_DIGITALLY_TYPESET_PILOT")
        self.assertEqual(report["real_typeset_sample_pages"], 0)
        self.assertIn("scan_image_dominates_page", {x["type"] for x in report["issues"]})

    def test_passes_visible_typeset_examples_pending_editorial_review(self):
        self.make_pilot(["digital", "digital", "illustrated"])
        report = mod.assess_pilot(self.source, self.pilot, [1, 2, 3], min_typeset=2)
        self.assertEqual(report["status"], "PASS_NEEDS_EDITORIAL_REVIEW")
        self.assertEqual(report["real_typeset_sample_pages"], 3)

    def test_mixed_pilot_rejected_until_real_samples_exist(self):
        self.make_pilot(["scan", "digital", "scan"])
        report = mod.assess_pilot(self.source, self.pilot, [1, 2, 3], min_typeset=2)
        self.assertEqual(report["status"], "FAIL_NOT_DIGITALLY_TYPESET_PILOT")

    def test_mismatched_mapping_fails(self):
        self.make_pilot(["digital", "digital"])
        report = mod.assess_pilot(self.source, self.pilot, [1, 2, 3], min_typeset=2)
        self.assertEqual(report["status"], "FAIL_NOT_DIGITALLY_TYPESET_PILOT")
        self.assertIn("pilot_count_mapping_mismatch", {x["type"] for x in report["issues"]})


if __name__ == "__main__":
    unittest.main()
