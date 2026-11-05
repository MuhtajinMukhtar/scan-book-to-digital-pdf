"""Review pilot must not authorize a 220-page digital conversion based on 2/7 pages."""
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


DRIVER = Path(__file__).resolve().parents[1] / "scripts" / "run_book.py"


class FallbackApprovalGateTests(unittest.TestCase):
    def test_review_with_2_digital_and_3_scans_is_not_approvable(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            source = directory / "scanned.pdf"
            work = directory / "work"
            (work / "ocr").mkdir(parents=True)
            pdf = fitz.open()
            recorded = []
            for n in range(1,6):
                im = Image.new("RGB", (500,700), "white")
                dr = ImageDraw.Draw(im)
                lines = []
                for j in range(12 if n <= 2 else 2):
                    text = f"Readable paragraph text on page {n}, line {j+1}."
                    x,y = 47, 51+j*26
                    dr.text((x,y),text,fill="black")
                    lines.append({"text":text,"x":x/500,"y":y/700,
                                  "width":390/500,"height":17/700,
                                  "confidence":.97})
                raw=BytesIO()
                im.save(raw,format="PNG")
                page=pdf.new_page(width=500,height=700)
                page.insert_image(page.rect,stream=raw.getvalue())
                recorded.append(lines)
            pdf.save(source);pdf.close()
            source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
            for n,lines in enumerate(recorded,1):
                (work/"ocr"/f"page_{n:03d}.json").write_text(json.dumps({
                    "engine":"apple-vision", "page":n,
                    "source_sha256":source_hash,"lines":lines
                }),encoding="utf-8")
            common=("--source",str(source),"--work-dir",str(work))
            def run(*opts):
                return subprocess.run([sys.executable,str(DRIVER),*opts],
                                      capture_output=True,text=True)
            result=run("pilot",*common,"--stage","review",
                       "--pages","1,2,3,4,5",
                       "--skip-ocr","--font-size","12")
            self.assertEqual(result.returncode,0,result.stdout+"\n"+result.stderr)
            status=json.loads((work/"pilot"/"pilot-status.json").read_text())
            self.assertEqual(status["digital_sample_pages"],2)
            self.assertEqual(status["fallback_sample_pages"],3)
            self.assertEqual(status["fallback_source_pages"],[3,4,5])
            self.assertEqual(status["status"],"PILOT_NEEDS_LAYOUT_WORK")
            self.assertFalse(status["layout_reconstruction_complete"])
            approval=run("approve",*common,"--confirm","APPROVE_PILOT")
            self.assertEqual(approval.returncode,2)
            self.assertIn("source-checked REVIEW pilot",approval.stderr)
            self.assertFalse((work/"pilot"/"approval.json").exists())


if __name__ == "__main__":
    unittest.main()
