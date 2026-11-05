"""Synthetic tests: Apple Vision primary, bounded Mobile on doubtful pages only."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import fitz

SCRIPTS=Path(__file__).resolve().parents[1]/"scripts"
spec=importlib.util.spec_from_file_location("mac_selective_ocr",SCRIPTS/"mac_selective_ocr.py")
selective=importlib.util.module_from_spec(spec)
spec.loader.exec_module(selective)


def apple(lines, page, sha):
    return {"engine":"apple-vision","page":page,"source_sha256":sha,"lines":lines}


class SelectiveTests(unittest.TestCase):
    def test_high_confidence_needs_no_mobile(self):
        lines=[{"text":f"This is body paragraph line {i}", "confidence": .96}
               for i in range(12)]
        result=selective.apple_review(lines)
        self.assertFalse(result["needs_mobile"])

    def test_low_confidence_requests_mobile(self):
        lines=[{"text":f"Some line {i}", "confidence": .95} for i in range(12)]
        lines[4]["confidence"] = .44
        self.assertTrue(selective.apple_review(lines)["needs_mobile"])
        self.assertIn("very_low_line_confidence", selective.apple_review(lines)["reasons"])

    def test_missing_confidence_requires_review_not_false_accuracy(self):
        self.assertTrue(selective.apple_review([{"text":"Line"}]*8)["needs_mobile"])
        self.assertIn("no_confidence_data",selective.apple_review([{"text":"Line"}]*8)["reasons"])

    def test_selective_comparison_keeps_apple_as_primary(self):
        report=selective.compare_ocr([{"text":"Nama prita yang tepat."}],
                    {"engine":"paddle-ppocrv5-mobile","source_sha256":"hash",
                     "rec_texts":["Nama prita yang kurang tepat."]},3,"hash")
        self.assertEqual(report["primary_engine"],"apple-vision")
        self.assertTrue(report["issues"])

    def test_apple_only_cache_runs_without_paddle_or_tesseract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            src=root/"source.pdf"
            doc=fitz.open()
            doc.new_page();doc.new_page()
            doc.save(src);doc.close()
            work=root/"work"
            (work/"ocr").mkdir(parents=True)
            srcsha=selective.digest(src)
            for page,conf in ((1,.98),(2,.52)):
                lines=[{"text":"Sample paragraph text","confidence":conf} for _ in range(10)]
                (work/"ocr"/f"page_{page:03d}.json").write_text(
                   json.dumps(apple(lines,page,srcsha)),encoding="utf-8")
            with patch.object(selective.importlib.util,"find_spec",return_value=None):
                result=selective.run(src,work,[1,2],180,True,False,False,1,120,None,set())
            self.assertEqual(result["apple_pages"],2)
            self.assertEqual(result["mobile_candidates"],1)
            self.assertEqual(result["secondary_pending_pages"],[2])
            self.assertEqual(result["mobile_compared"],0)
            self.assertEqual(result["status"],"SOURCE_REVIEW_PENDING")
            self.assertTrue((work/"review"/"page_001.json").exists())
            self.assertFalse((work/"paddle_mobile").exists())

    def test_memory_bounded_mobile_worker_is_opt_in_and_isolated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            src=root/"src.pdf"
            pdf=fitz.open();pdf.new_page();pdf.save(src);pdf.close()
            work=root/"work"
            (work/"ocr").mkdir(parents=True)
            sha=selective.digest(src)
            (work/"ocr"/"page_001.json").write_text(json.dumps(
                apple([{"text":"Doubtful.","confidence":.4} for _ in range(8)],1,sha)))
            caps=[]
            def fake_worker(img,out,n,source_sha,img_sha,cap,timeout,allow):
                caps.append(cap)
                out.parent.mkdir(parents=True,exist_ok=True)
                out.write_text(json.dumps({
                    "engine":"paddle-ppocrv5-mobile","source_sha256":source_sha,
                    "image_sha256":img_sha,"page":n,"rec_texts":["Doubtful."]*8
                }))
                return {"status":"ok","observed_max_rss_mb":950}
            with (patch.object(selective.platform,"system",return_value="Darwin"),
                  patch.object(selective,"total_mac_memory_mb",return_value=8192),
                  patch.object(selective.importlib.util,"find_spec",return_value=object()),
                  patch.object(selective,"monitored_worker",side_effect=fake_worker)):
                result=selective.run(src,work,[1],180,True,True,True,1,120,None,set())
            self.assertEqual(result["mobile_compared"],1)
            self.assertEqual(result["secondary_pending_pages"],[])
            self.assertEqual(caps,[1600])
            self.assertTrue((work/"fusion_mobile"/"page_001.json").is_file())

    def test_mobile_worker_result_parser_nested_shape(self):
        spec=importlib.util.spec_from_file_location("paddle_mobile_worker",SCRIPTS/"paddle_mobile_worker.py")
        worker=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(worker)
        class Item:
            json={"res":{"rec_texts":["Halo dunia"],"rec_scores":[.98],"rec_boxes":[[1,2,3,4]]}}
        texts,scores,boxes=worker.parse_result(Item())
        self.assertEqual(texts,["Halo dunia"])
        self.assertEqual(scores,[.98])
        self.assertEqual(boxes,[[1,2,3,4]])


if __name__ == "__main__":
    unittest.main()
