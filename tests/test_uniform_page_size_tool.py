"""Existing digital output can be resized without OCR or overwriting the source."""
from pathlib import Path
import sys
import tempfile
import unittest

import fitz

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from uniform_page_size import normalize_existing


class ExistingOutputPaperTests(unittest.TestCase):
    def test_existing_work_pdf_gets_new_same_size_copy(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            source=root/"scan.pdf"
            existing=root/"digital.pdf"
            result=root/"uniform.pdf"
            book=fitz.open()
            composed=fitz.open()
            for n,(width,height) in enumerate([(630,850),(480,650),(500,664),(490,660)],1):
                book.new_page(width=width,height=height)
                p=composed.new_page(width=width,height=height)
                p.insert_text((45,95),f"Digital book chapter page {n}.",fontsize=13)
            book.save(source)
            composed.save(existing)
            book.close();composed.close()
            report=normalize_existing(source,existing,result,{1})
            self.assertEqual(report["source_pages"],4)
            self.assertEqual(report["canonical_page_size"]["width_pt"],490)
            self.assertEqual(report["canonical_page_size"]["height_pt"],660)
            self.assertTrue(report["changed_paper_dimensions"])
            self.assertEqual(report["output_pages"],4)
            self.assertTrue(result.exists())
            with fitz.open(existing) as previous, fitz.open(result) as updated:
                self.assertNotEqual(previous[0].rect.width,updated[0].rect.width)
                self.assertEqual([round(page.rect.width,2) for page in updated],[490]*4)
                self.assertEqual([round(page.rect.height,2) for page in updated],[660]*4)
                for i in range(4):
                    self.assertEqual(previous[i].get_text("text"),updated[i].get_text("text"))
            with self.assertRaisesRegex(ValueError,"Output already exists"):
                normalize_existing(source,existing,result,{1})

    def test_same_size_input_is_still_a_safe_new_copy(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            source=root/"scan.pdf"
            book=fitz.open()
            for n in range(3):
                p=book.new_page(width=500,height=700)
                p.insert_text((40,90),f"A book page number {n+1}",fontsize=12)
            book.save(source);book.close()
            existing=root/"existing-digital.pdf"
            existing.write_bytes(source.read_bytes())
            out=root/"new.pdf"
            report=normalize_existing(source,existing,out)
            self.assertFalse(report["changed_paper_dimensions"])
            self.assertTrue(out.exists())
            self.assertEqual(out.read_bytes(),existing.read_bytes())


if __name__ == "__main__":
    unittest.main()
