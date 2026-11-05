"""Tests: every non-cover page must be digitally typeset, not a searchable scan."""
from __future__ import annotations

from io import BytesIO
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

import fitz
from PIL import Image, ImageDraw

SCRIPTS=Path(__file__).resolve().parents[1]/"scripts"
sys.path.insert(0,str(SCRIPTS))
import digital_text_policy_gate as gate


class StrictDigitalPolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.src=self.root/"source.pdf"
        self.out=self.root/"output.pdf"
        self.qa=self.root/"output.qa.json"
        self.cover=self.root/"cover-evidence.json"
        image=Image.new("RGB",(420,620),"white")
        draw=ImageDraw.Draw(image)
        for n in range(9):
            draw.text((55,55+n*35),"SOURCE SCAN",fill="black")
        b=BytesIO();image.save(b,format="PNG")
        book=fitz.open()
        for _ in range(3):
            p=book.new_page(width=420,height=620)
            p.insert_image(p.rect,stream=b.getvalue())
        book.save(self.src);book.close()
        self.source_sha=hashlib.sha256(self.src.read_bytes()).hexdigest()
        self.cover.write_text(json.dumps({
            "source_sha256":self.source_sha,
            "pages":[{
                "source_page":1,"kind":"front_cover",
                "source_scan_verified":True,"source_description":"Front-cover illustration and title"
            }]
        }))

    def tearDown(self):
        self.tmp.cleanup()

    def compose(self, page_modes):
        with fitz.open(self.src) as src:
            pdf=fitz.open()
            for idx,mode in enumerate(page_modes):
                page=pdf.new_page(width=420,height=620)
                if mode in ("searchable_scan_fallback","verified_cover_raster_exempt","forged_overlay"):
                    page.show_pdf_page(page.rect,src,idx)
                if mode=="forged_overlay":
                    page.insert_text((30,35),"VISIBLE",fontsize=12)
                if mode=="born_digital_unverified":
                    for j in range(8):
                        page.insert_text((60,70+30*j),"A genuine digital paragraph on this source page.",fontsize=10)
            pdf.save(self.out)
            pdf.close()
        modes=[("born_digital_unverified" if mode=="forged_overlay" else mode)
               for mode in page_modes]
        self.qa.write_text(json.dumps({
            "source_sha256":self.source_sha,
            "per_page":[{"source_page":i+1,"output_page":i+1,"mode":mode}
                        for i,mode in enumerate(modes)]
        }))

    def test_passes_only_when_every_noncover_is_visible_vector_text(self):
        self.compose(["verified_cover_raster_exempt","born_digital_unverified","born_digital_unverified"])
        result=gate.assess(self.src,self.out,self.qa,self.cover)
        self.assertEqual(result["status"],"READY_FOR_EDITORIAL_FIDELITY_REVIEW")
        self.assertEqual(result["exempt_cover_pages"],[1])
        self.assertEqual(result["incomplete_noncover_pages"],[])

    def test_no_cover_evidence_does_not_silently_exempt_page_one(self):
        self.compose(["verified_cover_raster_exempt","born_digital_unverified","born_digital_unverified"])
        result=gate.assess(self.src,self.out,self.qa,None)
        self.assertEqual(result["status"],"INCOMPLETE_DIGITAL_PAGES")
        self.assertIn(1,result["incomplete_noncover_pages"])

    def test_fallback_table_cannot_count_as_completed(self):
        self.compose(["verified_cover_raster_exempt","born_digital_unverified","searchable_scan_fallback"])
        result=gate.assess(self.src,self.out,self.qa,self.cover)
        self.assertEqual(result["status"],"INCOMPLETE_DIGITAL_PAGES")
        self.assertEqual(result["incomplete_noncover_pages"],[3])
        self.assertIn("whole_page_scan_fallback_not_allowed", {x["type"] for x in result["issues"]})

    def test_forged_visible_overlay_on_full_page_scan_rejected(self):
        self.compose(["verified_cover_raster_exempt","born_digital_unverified","forged_overlay"])
        result=gate.assess(self.src,self.out,self.qa,self.cover)
        self.assertEqual(result["status"],"INCOMPLETE_DIGITAL_PAGES")
        self.assertIn("near_full_page_raster_requires_reconstruction", {x["type"] for x in result["issues"]})

    def test_cannot_exempt_middle_page_or_skip_scan_verification(self):
        self.compose(["verified_cover_raster_exempt","born_digital_unverified","born_digital_unverified"])
        bad={"source_sha256":self.source_sha,
             "pages":[{"source_page":2,"kind":"front_cover","source_scan_verified":True,
                       "source_description":"Unrelated middle chapter"}]}
        self.cover.write_text(json.dumps(bad))
        with self.assertRaisesRegex(ValueError,"Only physical first/last page"):
            gate.assess(self.src,self.out,self.qa,self.cover)
        bad["pages"][0]["source_page"]=1
        bad["pages"][0]["source_scan_verified"]=False
        self.cover.write_text(json.dumps(bad))
        with self.assertRaisesRegex(ValueError,"source-scan verification"):
            gate.assess(self.src,self.out,self.qa,self.cover)

if __name__=="__main__":
    unittest.main()
