"""No-model, no-OCR tests of diversified pilot page selection."""
from pathlib import Path
import sys
import tempfile
import unittest

import fitz

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from pilot_archetypes import select_diverse, contact_sheet, page_features


class DiversePilotTests(unittest.TestCase):
    def make_source(self, path: Path) -> None:
        doc=fitz.open()
        for n in range(1,25):
            page=doc.new_page(width=480,height=660)
            if n==6:
                # Strongly bordered data table distinct from prose.
                for y in range(105,520,42):
                    page.draw_line((35,y),(445,y),width=2,color=(0,0,0))
                for x in (35,145,280,445):
                    page.draw_line((x,105),(x,483),width=2,color=(0,0,0))
                for k in range(9):
                    page.insert_text((54,130+k*42),f"Entry {k}  $23.00",fontsize=10)
            elif n==12:
                # Figure/photo-like dense region in the central area.
                page.draw_rect(fitz.Rect(85,135,400,505),color=None,fill=(.35,.37,.38))
                for x in range(93,390,16):
                    for y in range(140,505,14):
                        if (x+y)%3==0:
                            page.draw_rect(fitz.Rect(x,y,x+9,y+8),
                                           color=None,fill=(.75,.76,.77))
                page.insert_text((70,550),"Figure 1 - An image",fontsize=12)
            elif n==18:
                page.insert_text((70,235),"CHAPTER FOUR",fontsize=28)
                page.insert_text((70,280),"An unusually large chapter title",fontsize=14)
                page.insert_text((70,530),"Introductory caption",fontsize=12)
            else:
                count=26 if n%2==0 else 21
                for j in range(count):
                    page.insert_text((45,100+j*18),f"This is the main body paragraph line {j+1}.",fontsize=10)
        doc.save(path)
        doc.close()

    def test_survey_finds_distinct_candidates_and_preserves_smoke_pages(self):
        with tempfile.TemporaryDirectory() as directory:
            src=Path(directory)/"source.pdf"
            self.make_source(src)
            selected=select_diverse(src,count=7,keep_pages=[3,21])
            self.assertEqual(len(selected["pages"]),7)
            self.assertEqual(len(set(selected["pages"])),7)
            self.assertTrue({3,21}.issubset(set(selected["pages"])))
            self.assertIn("table_candidate", selected["roles"].values())
            self.assertIn("illustration_candidate", selected["roles"].values())
            self.assertTrue(selected["human_visual_verification_required"])
            overview=Path(directory)/"contact.pdf"
            contact_sheet(src,selected,overview)
            with fitz.open(overview) as pdf:
                self.assertGreaterEqual(len(pdf),1)
                self.assertIn("Source PDF",pdf[0].get_text("text"))

    def test_table_and_photo_have_measurably_different_thumbnail_features(self):
        with tempfile.TemporaryDirectory() as directory:
            src=Path(directory)/"source.pdf"
            self.make_source(src)
            with fitz.open(src) as pdf:
                body=page_features(pdf[3])
                table=page_features(pdf[5])
                illustration=page_features(pdf[11])
            self.assertGreater(table["horizontal_rules"],body["horizontal_rules"])
            self.assertGreater(illustration["dense_tiles"],body["dense_tiles"])

    def test_tiny_book_uses_available_distinct_pages_only(self):
        with tempfile.TemporaryDirectory() as directory:
            src=Path(directory)/"tiny.pdf"
            book=fitz.open()
            for i in range(3):
                p=book.new_page(width=300,height=400)
                p.insert_text((25,45),"Small book text",fontsize=12)
            book.save(src);book.close()
            selected=select_diverse(src,count=7,keep_pages=[1])
            self.assertEqual(selected["pages"],[1,2,3])


if __name__=="__main__":
    unittest.main()
