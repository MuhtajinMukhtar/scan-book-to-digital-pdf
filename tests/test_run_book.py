"""No-model end-to-end workflow test: cached OCR -> pilot -> approval -> full."""
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

ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "scripts" / "run_book.py"


class OneClickWorkflowTests(unittest.TestCase):
    def test_synthetic_full_path_reuses_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work = root / "work"
            (work / "ocr").mkdir(parents=True)
            (work / "fusion_safe").mkdir(parents=True)
            src = root / "book.pdf"
            pdf = fitz.open()
            records = []
            for num in (1, 2):
                im = Image.new("RGB", (500, 700), "white")
                d = ImageDraw.Draw(im)
                lines = []
                for j in range(12):
                    text = f"The scanned paragraph line number {j+1} on page {num}."
                    x, y = 44, 45+27*j
                    d.text((x,y), text, fill="black")
                    lines.append({"text":text,"x":x/500,"y":y/700,
                                  "width":400/500,"height":16/700})
                bio = BytesIO()
                im.save(bio,format="PNG")
                page = pdf.new_page(width=500,height=700)
                page.insert_image(page.rect,stream=bio.getvalue())
                records.append(lines)
            pdf.save(src)
            pdf.close()
            source_hash = hashlib.sha256(src.read_bytes()).hexdigest()
            for i, lines in enumerate(records, 1):
                (work/"ocr"/f"page_{i:03d}.json").write_text(json.dumps({
                    "page":i,"source_sha256":source_hash,"engine":"apple-vision","lines":lines}))
                (work/"fusion_safe"/f"page_{i:03d}.json").write_text(json.dumps({
                    "page":i,"source_sha256":source_hash,"issues":[],
                    "primary_engine":"apple-vision","secondary_engine":"tesseract"}))
            def run(*rest):
                return subprocess.run([sys.executable,str(DRIVER),*rest],
                        capture_output=True,text=True)
            common=("--source",str(src),"--work-dir",str(work))
            p=run("pilot",*common,"--pages","1,2","--skip-ocr","--font-size","12")
            self.assertEqual(p.returncode,0,p.stdout+"\n"+p.stderr)
            self.assertTrue((work/"pilot/Book_Pilot_Comparison.pdf").is_file())
            full_before=run("full",*common,"--skip-ocr")
            self.assertEqual(full_before.returncode,2)
            reject=run("approve",*common,"--confirm","NO")
            self.assertEqual(reject.returncode,2)
            a=run("approve",*common,"--confirm","APPROVE_PILOT")
            self.assertEqual(a.returncode,0,a.stdout+"\n"+a.stderr)
            f=run("full",*common,"--skip-ocr")
            self.assertEqual(f.returncode,0,f.stdout+"\n"+f.stderr)
            with fitz.open(work/"output/Book_Full_REVIEW.pdf") as result:
                self.assertEqual(len(result),2)
                self.assertGreater(len(result[0].get_text("text")),100)
            style=work/"pilot/style-profile.json"
            profile=json.loads(style.read_text())
            profile["body_font_size_pt"]=18
            style.write_text(json.dumps(profile))
            blocked=run("full",*common,"--skip-ocr")
            self.assertEqual(blocked.returncode,2)


if __name__ == "__main__":
    unittest.main()
