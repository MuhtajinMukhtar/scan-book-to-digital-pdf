"""Deterministic engine regression tests with synthetic scans; no OCR models, no LLM."""
from __future__ import annotations

from io import BytesIO
import importlib.util
import sys
import json
from pathlib import Path
import tempfile
import unittest

import fitz
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("local_book_engine", ROOT / "scripts" / "local_book_engine.py")
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)


class BookEngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root / "scan.pdf"
        self.work = self.root / "work"
        (self.work / "ocr").mkdir(parents=True)
        (self.work / "fusion").mkdir(parents=True)
        self.output = self.root / "pilot.pdf"
        self.fontfile = engine.font_path("sans")
        self.make_scan()
        self.make_caches()

    def tearDown(self):
        self.tmp.cleanup()

    def make_scan(self):
        doc = fitz.open()
        self.records = []
        for pagenum in (1, 2):
            img = Image.new("RGB", (500, 700), "white")
            dr = ImageDraw.Draw(img)
            lines = []
            for i in range(11):
                text = f"Chapter {pagenum}, a clear example line {i+1} to preserve correctly."
                x, y, w, h = 45, 40 + i * 28, 399, 17
                lines.append({"text": text, "x": x/500, "y": y/700,
                              "width": w/500, "height": h/700})
                dr.text((x, y), text, fill="black")
            if pagenum == 2:
                # Ambiguous illustration must be preserved in a fallback.
                dr.rectangle((120, 385, 390, 620), fill="black")
            buf = BytesIO()
            img.save(buf, format="PNG")
            page = doc.new_page(width=500, height=700)
            page.insert_image(page.rect, stream=buf.getvalue())
            self.records.append(lines)
        doc.save(self.source)
        doc.close()

    def make_caches(self):
        src_hash = engine.sha256(self.source)
        for i, lines in enumerate(self.records, start=1):
            (self.work / "ocr" / f"page_{i:03d}.json").write_text(json.dumps({
                "page": i, "source_sha256": src_hash, "engine": "apple-vision", "lines": lines}))
            (self.work / "fusion" / f"page_{i:03d}.json").write_text(json.dumps({
                "page": i, "source_sha256": src_hash, "issues": []}))

    def test_two_page_pilot_composes_vector_text_and_falls_back_for_figure(self):
        report = engine.build(self.source, self.work, self.output, "pilot", [1,2],
                              "sans", self.fontfile, 13.0)
        self.assertEqual(report["output_page_count"], 2)
        self.assertEqual(report["digital_pages"], 1)
        self.assertEqual(report["fallback_pages"], 1)
        self.assertEqual(report["per_page"][1]["source_page"], 2)
        with fitz.open(self.output) as pdf:
            self.assertEqual(len(pdf), 2)
            self.assertTrue(any(x.get("chars") and x.get("type") != 3 for x in pdf[0].get_texttrace()))
            self.assertTrue(pdf[1].get_images())
            self.assertGreater(len(pdf[0].get_text("words")), 90)
        engine.comparison(self.source, self.output, [1,2], self.root / "comparison.pdf")
        self.assertEqual(len(fitz.open(self.root / "comparison.pdf")), 2)

    def test_hybrid_provenance_cannot_be_faked(self):
        (self.work / "fusion" / "page_001.json").unlink()
        with self.assertRaisesRegex(ValueError, "Paddle comparison absent"):
            engine.build(self.source, self.work, self.output, "pilot", [1],
                         "sans", self.fontfile, 13.0)

    def test_full_book_requires_approval_and_identity(self):
        with self.assertRaisesRegex(ValueError, "approval"):
            engine.build(self.source, self.work, self.output, "full", [1,2],
                         "sans", self.fontfile, 13.0)
        approval = self.root / "approval.json"
        approval.write_text(json.dumps({"decision": "PILOT_APPROVED", "source_sha256": "wrong"}))
        with self.assertRaisesRegex(ValueError, "another scanned book"):
            engine.build(self.source, self.work, self.output, "full", [1,2],
                         "sans", self.fontfile, 13.0, approval=approval)

    def test_page_number_mapping_rejects_duplicates(self):
        self.assertEqual(engine.parse_pages("1,2",2,"pilot"), [1,2])
        with self.assertRaises(ValueError):
            engine.parse_pages("1,1",2,"pilot")
        with self.assertRaises(ValueError):
            engine.parse_pages("2,1",2,"full")

    def test_style_is_locked_across_pages(self):
        report = engine.build(self.source, self.work, self.output, "pilot", [1,2],
                              "sans", self.fontfile, 13.0)
        self.assertEqual(report["body_font_size_pt"], 13.0)

if __name__ == "__main__":
    unittest.main()
