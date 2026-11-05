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

if __name__=="__main__":
    unittest.main()
