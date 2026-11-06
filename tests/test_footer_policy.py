"""Footer labels follow the source; layout becomes one consistent book style."""
from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import sys
import tempfile
import unittest

import fitz
from PIL import Image, ImageDraw

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from footer_policy import infer_footer_policy, target_footer, source_footer
from local_book_engine import build, font_path, sha256
from digital_text_policy_gate import assess


def sample(number:int, left:bool, width=500.,height=700., dx=0., dy=0.):
    line={
        "text":str(100+number),
        "x":(.09 if left else .855)+dx,
        "y":.922+dy,
        "width":.045, "height":.018
    }
    return (number,width,height,[line])


class FooterGeometryTests(unittest.TestCase):
    def test_shared_font_baseline_and_mirrored_source_sides(self):
        paper={"width_pt":500.,"height_pt":700.}
        samples=[
            sample(1,False,dx=-.015,dy=.003),
            sample(2,True,dx=.008,dy=-.004),
            sample(3,False,dx=.009,dy=.002),
            sample(4,True,dx=-.012,dy=-.003),
            sample(5,False,dx=.013,dy=.004),
            sample(6,True,dx=.006,dy=0),
        ]
        p=infer_footer_policy(samples,paper)
        self.assertEqual(p["side_rule"],"mirrored_source_parity")
        self.assertEqual(p["parity_sides"],{"0":"left","1":"right"})
        self.assertEqual(p["sample_count"],6)
        self.assertGreaterEqual(p["font_size_pt"],8)
        targets=[]
        for n,w,h,lines in samples:
            t=target_footer(n,lines[0],p,w,h,500,700,font_width_pt=16)
            targets.append(t)
        self.assertEqual({t["canonical_paper_baseline_pt"] for t in targets},
                         {targets[0]["canonical_paper_baseline_pt"]})
        self.assertEqual({t["canonical_font_pt"] for t in targets},
                         {targets[0]["canonical_font_pt"]})
        self.assertEqual({round(t["canonical_paper_x_pt"],3)
                          for t in targets if t["side"]=="left"}, {p["left_inset_pt"]})
        self.assertEqual({round(500-t["canonical_paper_x_pt"]-16,3)
                          for t in targets if t["side"]=="right"}, {p["right_inset_pt"]})

    def test_source_label_not_guessed_and_ambiguous_not_replaced(self):
        p={"width_pt":500,"height_pt":700}
        self.assertIsNone(source_footer(3,500,700,[],500,700))
        row=sample(3,False)[3][0]
        self.assertIsNone(source_footer(3,500,700,[row,row],500,700))
        policy=infer_footer_policy([sample(3,False)],p)
        self.assertEqual(policy["sample_count"],1)
        self.assertTrue(policy["source_review_required"])
        with self.assertRaisesRegex(ValueError,"uniquely identified"):
            target_footer(3,{"text":"invented","x":.8,"y":.93,
                        "width":.04,"height":.02},policy,500,700,500,700,20)

    def test_integrated_compositor_digitizes_source_labels_at_same_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);work=root/"work";(work/"ocr").mkdir(parents=True)
            source=root/"scanned.pdf";out=root/"digital.pdf"
            pdf=fitz.open()
            records=[]
            for n in range(1,7):
                width,height=500+((n%3)-1)*5,700+((n%2)-.5)*4
                page=pdf.new_page(width=width,height=height)
                im=Image.new("RGB",(round(width),round(height)),(251,249,241))
                draw=ImageDraw.Draw(im)
                side_left=n%2==0
                foot=sample(n,side_left,float(width),float(height),
                            dx=(n%3-1)*.006,dy=(n%4-2)*.002)[3][0]
                x=int(foot["x"]*width);y=int(foot["y"]*height)
                draw.text((x,y),foot["text"],fill=(65,65,65))
                data=BytesIO();im.save(data,format="PNG")
                page.insert_image(page.rect,stream=data.getvalue())
                records.append((n,float(width),float(height),foot))
            pdf.save(source);pdf.close()
            src_sha=sha256(source)
            for n,w,h,foot in records:
                lines=[
                    {"text":f"Ordinary sentence in scanned book on page {n} line {j} here.",
                     "x":.13,"y":.15+j*.04,"width":.73,"height":.025}
                    for j in range(11)
                ]+[foot]
                (work/"ocr"/f"page_{n:03d}.json").write_text(json.dumps({
                    "page":n,"engine":"apple-vision","source_sha256":src_sha,
                    "lines":lines
                }))
            report=build(source,work,out,"pilot",list(range(1,7)),
                         "sans",font_path("sans"),12,strict_hybrid=False,
                         fusion_subdir="fusion_mobile")
            self.assertEqual(report["digital_pages"],6,report["per_page"])
            self.assertEqual(report["book_style"]["footer_policy"]["sample_count"],6)
            qa=assess(source,out,out.with_suffix(".qa.json"))
            self.assertEqual(qa["status"],"READY_FOR_EDITORIAL_FIDELITY_REVIEW",
                             qa["issues"])
            self.assertEqual(len(qa["footer_position_evidence"]),6)
            self.assertLess(max(x["bottom_from_page_pt"] for x in qa["footer_position_evidence"])-
                            min(x["bottom_from_page_pt"] for x in qa["footer_position_evidence"]),3)
            with fitz.open(out) as printed:
                self.assertEqual(len(printed),6)
                for n,page in enumerate(printed,1):
                    label=str(100+n)
                    self.assertIn(label,page.get_text("text"))
                    words=[w for w in page.get_text("words") if w[4]==label]
                    self.assertEqual(len(words),1)
                    self.assertGreater(words[0][1],page.rect.height*.85)


if __name__=="__main__":
    unittest.main()
