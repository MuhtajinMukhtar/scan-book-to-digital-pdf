"""Synthetic tests: no scans or private book contents."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("mac_hybrid_ocr", HERE / "scripts" / "mac_hybrid_ocr.py")
hybrid = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hybrid)

class TestFusion(unittest.TestCase):
    def test_recovers_lines_dropped_in_markdown(self):
        apple = {"lines":[{"text":"A complete start. A long continuation remains at the bottom."}]}
        paddle = {"overall_ocr_res":{"rec_texts":["A complete start.", "A long continuation remains at the bottom."],"rec_scores":[.96,.94]}}
        report = hybrid.reconcile(apple, paddle, "A complete start.")
        missing = [x for x in report["issues"] if x["type"] == "paddle_raw_not_in_markdown"]
        self.assertEqual(len(missing), 1)
        self.assertIn("continuation", missing[0]["text"])
        self.assertEqual(len([x for x in report["issues"] if x["type"] == "paddle_not_in_apple"]), 0)

    def test_apple_and_paddle_disagree_about_name(self):
        apple = {"lines":[{"text":"A writer called A. Reed is here."}]}
        paddle = {"overall_ocr_res":{"rec_texts":["A writer called A. Reid is here."]}}
        report = hybrid.reconcile(apple, paddle)
        self.assertTrue(report["markdown_checked"] is False)
        self.assertTrue(any(x["type"] == "paddle_apple_variant" for x in report["issues"]))
        self.assertEqual(report["editorial_status"], "SOURCE_VISUAL_REVIEW_REQUIRED")

    def test_cache_sha_guard_and_review_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/"ocr").mkdir();(root/"paddle").mkdir()
            (root/"ocr/page_001.json").write_text(json.dumps({"engine":"apple-vision","source_sha256":"abc","lines":[{"text":"Text from the original page."}]}))
            (root/"paddle/page_001.json").write_text(json.dumps({"overall_ocr_res":{"rec_texts":["Text from the original page.","An entire missing sentence of text."]}}))
            (root/"paddle/page_001.meta.json").write_text(json.dumps({"source_sha256":"xyz"}))
            with self.assertRaisesRegex(ValueError, "mismatch"):
                hybrid.compare_cached(root)
            (root/"paddle/page_001.meta.json").write_text(json.dumps({"source_sha256":"abc"}))
            report = hybrid.compare_cached(root)
            self.assertEqual(report["pages_with_issues"], [1])
            self.assertTrue((root/"fusion/OCR_REVIEW.json").is_file())

if __name__ == "__main__":
    unittest.main()
