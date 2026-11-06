"""Synthetic regression: preferred pilot remains bigger/less compressed, with art."""
from __future__ import annotations

import importlib.util
from io import BytesIO
import json
from pathlib import Path
import sys
import tempfile
import unittest

import fitz
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location(
    "visual_regression_gate",ROOT/"scripts"/"visual_regression_gate.py")
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class GoldenVisualGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.base=Path(self.tmp.name)
        self.source=self.base/"book.pdf"
        book=fitz.open()
        for _ in range(2):
            book.new_page(width=500,height=700)
        book.save(self.source)
        book.close()

    def tearDown(self):
        self.tmp.cleanup()

    def make(self,name,font_size,art=True):
        path=self.base/name
        doc=fitz.open()
        for number in range(2):
            p=doc.new_page(width=1250,height=900)
            for i in range(12):
                p.insert_text((680,110+i*font_size*1.65),
                              "An original source paragraph in digital type",
                              fontsize=font_size)
            if art and number==0:
                raster=Image.new("RGB",(350,220),(.77*255,.79*255,.80*255))
                data=BytesIO()
                raster.save(data,format="PNG")
                p.insert_image(fitz.Rect(750,525,1110,735),stream=data.getvalue())
        doc.save(path)
        doc.close()
        return path

    def test_accepted_sample_remains_within_thresholds(self):
        good=self.make("good.pdf",16)
        baseline={"schema_version":1,"format":"side_by_side_comparison",
                  "source_sha256":mod.sha256(self.source),
                  "source_page_order":[1,2],
                  "page_metrics":mod.extract(good,[1,2])}
        report=mod.verify(good,baseline,self.source)
        self.assertEqual(report["status"],"PASS_VISUAL_THRESHOLDS_ONLY")
        self.assertFalse(report["issues"])

    def test_shrunk_text_is_blocked_even_when_words_match(self):
        golden=self.make("golden.pdf",16)
        bad=self.make("shrunk.pdf",12)
        baseline={"schema_version":1,"format":"side_by_side_comparison",
                  "source_sha256":mod.sha256(self.source),
                  "source_page_order":[1,2],
                  "page_metrics":mod.extract(golden,[1,2])}
        report=mod.verify(bad,baseline,self.source)
        self.assertEqual(report["status"],"PILOT_VISUAL_REGRESSION")
        self.assertTrue(any(x.get("issue")=="font_regressed" for x in report["issues"]))

    def test_lost_illustration_is_blocked(self):
        golden=self.make("golden.pdf",16,art=True)
        no_art=self.make("without_illustration.pdf",16,art=False)
        baseline={"schema_version":1,"format":"side_by_side_comparison",
                  "source_sha256":mod.sha256(self.source),
                  "source_page_order":[1,2],
                  "page_metrics":mod.extract(golden,[1,2])}
        report=mod.verify(no_art,baseline,self.source)
        self.assertEqual(report["status"],"PILOT_VISUAL_REGRESSION")
        self.assertTrue(any(x.get("issue")=="illustration_or_graphic_area_lost"
                            for x in report["issues"]))

    def test_wrong_source_pdf_cannot_reuse_golden_reference(self):
        golden=self.make("golden.pdf",16)
        baseline={"schema_version":1,"format":"side_by_side_comparison",
                  "source_sha256":"does-not-match",
                  "source_page_order":[1,2],
                  "page_metrics":mod.extract(golden,[1,2])}
        with self.assertRaisesRegex(ValueError,"checksum differs"):
            mod.verify(golden,baseline,self.source)

    def test_missing_or_reordered_pages_detected(self):
        golden=self.make("golden.pdf",16)
        baseline={"schema_version":1,"format":"side_by_side_comparison",
                  "source_sha256":mod.sha256(self.source),
                  "source_page_order":[1,2],
                  "page_metrics":mod.extract(golden,[1,2])}
        report=mod.verify(golden,baseline,self.source,[3,4])
        self.assertEqual(report["status"],"PILOT_VISUAL_REGRESSION")
        self.assertTrue(any(x.get("issue")=="no_golden_sample_for_this_page"
                            for x in report["issues"]))


if __name__=="__main__":
    unittest.main()
