"""Full workflow: visually verified cover preserved, other pages digitally retypeset."""
from __future__ import annotations
from io import BytesIO
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import fitz
from PIL import Image, ImageDraw

DRIVER=Path(__file__).resolve().parents[1]/"scripts"/"run_book.py"


class CoverWorkflowTests(unittest.TestCase):
    def test_cover_exemption_and_all_noncover_digital(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            source=root/"book.pdf"
            work=root/"work"
            (work/"ocr").mkdir(parents=True)
            pdf=fitz.open()
            records={}
            for n in range(1,4):
                im=Image.new("RGB",(500,700),"white")
                d=ImageDraw.Draw(im)
                lines=[]
                if n==1:
                    d.text((80,230),"COVER ART AND BOOK TITLE",fill="black")
                else:
                    for j in range(12):
                        text=f"Visible digital page {n} paragraph text line {j+1}."
                        x,y=48,55+j*28
                        d.text((x,y),text,fill="black")
                        lines.append({"text":text,"x":x/500,"y":y/700,
                                     "width":390/500,"height":16/700,"confidence":.99})
                buffer=BytesIO()
                im.save(buffer,format="PNG")
                p=pdf.new_page(width=500,height=700)
                p.insert_image(p.rect,stream=buffer.getvalue())
                if lines:
                    records[n]=lines
            pdf.save(source)
            pdf.close()
            sha=hashlib.sha256(source.read_bytes()).hexdigest()
            for n,lines in records.items():
                (work/"ocr"/f"page_{n:03d}.json").write_text(json.dumps({
                    "page":n,"engine":"apple-vision","source_sha256":sha,"lines":lines
                }))
            (work/"cover-evidence.json").write_text(json.dumps({
                "source_sha256":sha,
                "pages":[{"source_page":1,"kind":"front_cover",
                          "source_scan_verified":True,
                          "source_description":"Observed original cover art and book title"}]
            }))
            common=("--source",str(source),"--work-dir",str(work))
            def run(*parts):
                return subprocess.run([sys.executable,str(DRIVER),*parts],
                                      capture_output=True,text=True)
            smoke=run("pilot",*common,"--pages","2,3","--skip-ocr","--font-size","12")
            self.assertEqual(smoke.returncode,0,smoke.stdout+"\n"+smoke.stderr)
            review=run("pilot",*common,"--stage","review",
                       "--pages","1,2,3","--skip-ocr","--font-size","12")
            self.assertEqual(review.returncode,0,review.stdout+"\n"+review.stderr)
            pilot=json.loads((work/"pilot"/"pilot-status.json").read_text())
            self.assertEqual(pilot["status"],"PILOT_AWAITING_APPROVAL")
            self.assertEqual(pilot["fallback_source_pages"],[])
            self.assertEqual(pilot["source_verified_cover_pages"],[1])
            approve=run("approve",*common,"--confirm","APPROVE_PILOT")
            self.assertEqual(approve.returncode,0,approve.stdout+"\n"+approve.stderr)
            full=run("full",*common,"--skip-ocr")
            policy=work/"output"/"Book_Full_REVIEW.digital-policy.json"
            report=policy.read_text() if policy.is_file() else "missing policy report"
            self.assertEqual(full.returncode,0,full.stdout+"\n"+full.stderr+"\n"+report)
            status=json.loads(report)
            self.assertEqual(status["status"],"READY_FOR_EDITORIAL_FIDELITY_REVIEW")
            self.assertEqual(status["exempt_cover_pages"],[1])
            self.assertEqual(status["incomplete_noncover_pages"],[])
            modes=[page["mode"] for page in status["per_page"]]
            self.assertEqual(modes,["verified_cover_raster_exempt",
                                    "born_digital_unverified","born_digital_unverified"])
            self.assertEqual(len(fitz.open(work/"output"/"Book_Full_REVIEW.pdf")),3)


if __name__=="__main__":
    unittest.main()
