"""Regression: one book has exactly one PDF paper size, not one per scan."""
from __future__ import annotations

from collections import Counter
from io import BytesIO
import json
from pathlib import Path
import sys
import tempfile
import unittest

import fitz
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from book_page_size import (canonical_page_size, normalized_copy,
                            all_pages_uniform, verify_uniform_pdf)
from local_book_engine import build, font_path, sha256
from digital_text_policy_gate import assess


class UniformPaperTests(unittest.TestCase):
    def test_three_scan_sizes_and_cover_fit_common_paper_without_word_loss(self):
        source = fitz.open()
        sizes = [(610,850),(442,630),(460,646),(451,640)]
        for number,(w,h) in enumerate(sizes,1):
            p=source.new_page(width=w,height=h)
            p.insert_text((45,85),f"Physical source page {number} always remains here.",
                          fontsize=12)
            if number==1:
                im=Image.new("RGB",(110,125),(124,153,180))
                buffer=BytesIO()
                im.save(buffer,format="PNG")
                p.insert_image(fitz.Rect(180,225,290,350),stream=buffer.getvalue())
        paper=canonical_page_size(source,{1})
        self.assertEqual((paper["width_pt"],paper["height_pt"]),(451,640))
        uniform,evidence=normalized_copy(source,paper,
                           background=(.98,.97,.95),verified_cover_pages={1})
        try:
            self.assertEqual(len(uniform),4)
            self.assertTrue(all_pages_uniform(uniform,paper))
            self.assertTrue(evidence[0]["visual_review_recommended"])
            self.assertTrue(all(x["aspect_ratio_preserved"] for x in evidence))
            for original, result in zip(source,uniform):
                a=Counter(x[4] for x in original.get_text("words"))
                b=Counter(x[4] for x in result.get_text("words"))
                self.assertEqual(a,b)
                self.assertEqual(result.rect.width,451)
                self.assertEqual(result.rect.height,640)
                self.assertLess(result.rect.width+result.rect.height,1200)
            self.assertTrue(uniform[0].get_images())
        finally:
            source.close();uniform.close()

    def test_invalid_canonical_paper_and_preservation_of_original(self):
        source=fitz.open()
        page=source.new_page(width=450,height=640)
        page.insert_text((25,80),"A selectable word",fontsize=12)
        original=page.get_text("text")
        with self.assertRaisesRegex(ValueError,"Invalid canonical"):
            normalized_copy(source,{"width_pt":10,"height_pt":12})
        self.assertEqual(page.get_text("text"),original)
        source.close()

    def test_full_composer_and_policy_share_exact_canonical_dimensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            src=root/"source.pdf"
            work=root/"work"
            (work/"ocr").mkdir(parents=True)
            pdf=fitz.open()
            dims=[(500,700),(510,706),(493,696),(506,703)]
            for w,h in dims:
                pdf.new_page(width=w,height=h)
            pdf.save(src)
            pdf.close()
            key=sha256(src)
            for n in range(1,5):
                lines=[
                    {"text":f"Ordinary book sentence for page {n} line {i} with words.",
                     "x":.12,"y":(.13+i*.04),"width":.76,"height":.025,
                     "confidence":.98}
                    for i in range(11)
                ]
                (work/"ocr"/f"page_{n:03d}.json").write_text(json.dumps({
                    "page":n,"engine":"apple-vision","source_sha256":key,
                    "lines":lines
                }),encoding="utf-8")
            dest=root/"pilot.pdf"
            report=build(src,work,dest,"pilot",[1,2,3,4],
                         "sans",font_path("sans"),12,keep_footer=False,
                         strict_hybrid=False, fusion_subdir="fusion_mobile")
            self.assertEqual(report["digital_pages"],4,report["per_page"])
            self.assertEqual(report["canonical_page_size"]["width_pt"],503)
            self.assertEqual(report["canonical_page_size"]["height_pt"],701.5)
            self.assertTrue(report["page_size_normalization_required"])
            self.assertEqual(len(report["per_page"]),4)
            with fitz.open(dest) as rendered:
                self.assertEqual(len(rendered),4)
                verify_uniform_pdf(rendered,report["canonical_page_size"])
                self.assertTrue(all(p.get_text("text").strip() for p in rendered))
            # Standalone digital-text QA verifies the *book* paper, rather than
            # wrongly demanding each scanned source's uneven canvas size.
            result = assess(src,dest,dest.with_suffix(".qa.json"))
            self.assertTrue(result["all_pages_same_paper"])
            self.assertEqual(result["canonical_page_size"]["width_pt"],503)
            self.assertEqual(result["status"],"READY_FOR_EDITORIAL_FIDELITY_REVIEW",
                             result["issues"])


if __name__ == "__main__":
    unittest.main()
