"""Safe OCR regression tests; deliberately no PaddlePaddle inference or macOS requirement."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE/"scripts"))
spec=importlib.util.spec_from_file_location("mac_safe_ocr",HERE/"scripts"/"mac_safe_ocr.py")
safe=importlib.util.module_from_spec(spec)
spec.loader.exec_module(safe)


class SafeOCRTests(unittest.TestCase):
    def test_detects_both_directions_without_automatic_text_replacement(self):
        a=[{"text":"Ini contoh kata asli juga."}]
        b=[{"text":"Ini contoh kata salah juga."}]
        result=safe.compare(a,b,49,"source-sha")
        types={x["type"] for x in result["issues"]}
        self.assertIn("tesseract_not_in_apple",types)
        self.assertIn("apple_not_in_tesseract",types)
        self.assertEqual(result["primary_engine"],"apple-vision")
        self.assertEqual(result["secondary_engine"],"tesseract")
        self.assertEqual(result["editorial_status"],"SOURCE_VISUAL_REVIEW_REQUIRED")

    def test_no_disagreement_for_identical_tokens_different_line_breaks(self):
        a=[{"text":"Kata awal."},{"text":"Kata akhir."}]
        b=[{"text":"Kata awal. Kata akhir."}]
        result=safe.compare(a,b,1,"sha")
        self.assertEqual(result["issues"],[])

    def test_missing_language_pack_has_clear_preflight_error(self):
        with patch.object(safe,"installed_languages",return_value={"eng"}):
            with tempfile.TemporaryDirectory() as t:
                from fitz import open as open_pdf
                original=Path(t)/"original.pdf"
                pdf=open_pdf()
                pdf.new_page()
                pdf.save(original)
                pdf.close()
                with patch.object(safe.platform,"system",return_value="Darwin"):
                    with self.assertRaisesRegex(RuntimeError,"Missing Tesseract language packs: ind"):
                        safe.run(original,Path(t)/"work",[1],180,"ind+eng")

    def test_safe_source_never_imports_paddle(self):
        src=(HERE/"scripts"/"mac_safe_ocr.py").read_text(encoding="utf-8")
        self.assertNotIn("from paddleocr import",src)
        self.assertNotIn("import paddle",src)
        self.assertIn("fusion_safe",src)


    def test_cache_reuse_and_legacy_paddle_results_not_overwritten(self):
        import fitz
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source = root / "book.pdf"
            book = fitz.open()
            book.new_page(width=300, height=400)
            book.save(source)
            book.close()
            work = root / "work"
            (work / "ocr").mkdir(parents=True)
            (work / "page_images").mkdir(parents=True)
            (work / "fusion").mkdir(parents=True)
            Image.new("RGB", (300, 400), "white").save(
                work / "page_images" / "page_001.jpg"
            )
            source_hash = safe.digest(source)
            lines = [{"text": "A complete sample sentence."}]
            (work / "ocr" / "page_001.json").write_text(json.dumps({
                "page": 1, "engine": "apple-vision",
                "source_sha256": source_hash, "lines": lines
            }))
            old = work / "fusion" / "page_001.json"
            old.write_text('{"engine":"legacy-paddle"}')
            with (patch.object(safe.platform, "system", return_value="Darwin"),
                  patch.object(safe, "installed_languages", return_value={"ind","eng"}),
                  patch.object(safe.subprocess, "run") as apple_ran,
                  patch.object(safe, "recognize_tesseract", return_value=lines) as tess):
                first = safe.run(source, work, [1], 180, "ind+eng")
                second = safe.run(source, work, [1], 180, "ind+eng")
            self.assertEqual(first["new_secondary_pages"], 1)
            self.assertEqual(second["cached_secondary_pages"], 1)
            self.assertEqual(tess.call_count, 1)
            self.assertEqual(apple_ran.call_count, 2)
            self.assertEqual(json.loads(old.read_text())["engine"], "legacy-paddle")
            self.assertEqual(json.loads(
                (work/"fusion_safe"/"page_001.json").read_text()
            )["secondary_engine"], "tesseract")

if __name__=="__main__":
    unittest.main()
