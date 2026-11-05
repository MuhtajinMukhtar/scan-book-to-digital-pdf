"""Synthetic PDF: a verified italic phrase and a numeric footer become visible text."""
from __future__ import annotations

import importlib.util
from io import BytesIO
from pathlib import Path
import sys
import unittest

import fitz
from PIL import Image,ImageDraw

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
spec=importlib.util.spec_from_file_location("local_book_engine",ROOT/"scripts"/"local_book_engine.py")
engine=importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)


class DigitalStylesTests(unittest.TestCase):
    def test_italic_and_source_page_number_are_vector_text(self):
        fontfile=engine.font_path("sans")
        if engine.italic_font_file(fontfile) is None:
            self.skipTest("No matching local italic font on this CI host")
        source=fitz.open()
        page=source.new_page(width=480,height=620)
        raster=Image.new("RGB",(480,620),(246,244,235))
        draw=ImageDraw.Draw(raster)
        draw.text((414,572),"93",fill=(70,70,70))
        buffer=BytesIO()
        raster.save(buffer,format="PNG")
        page.insert_image(page.rect,stream=buffer.getvalue())
        lines=[]
        for k in range(10):
            text=("This discusses advertising in a faithful paragraph." if k==3
                  else f"The author wrote a readable sentence on line {k+1}.")
            lines.append({"text":text,"x":.12,"y":.12+k*.042,
                          "width":.76,"height":.032})
        lines.append({"text":"93","x":.865,"y":.928,"width":.041,"height":.02})
        out=fitz.open()
        ok,warning=engine.typeset_page(out,source,0,lines,fontfile,
                         fitz.Font(fontfile=str(fontfile)),12,True,
                         italic_phrases=["advertising"])
        self.assertTrue(ok,warning)
        page=out[0]
        text=page.get_text("text")
        self.assertIn("advertising",text)
        self.assertIn("93",text)
        self.assertGreater(len(page.get_texttrace()),10)
        styles={span["font"] for block in page.get_text("dict")["blocks"]
                if block["type"]==0 for line in block["lines"] for span in line["spans"]}
        self.assertTrue(any(("Italic" in name or "Oblique" in name) for name in styles),styles)
        footer_words=[w for w in page.get_text("words") if w[4]=="93"]
        self.assertTrue(any(w[1]>560 for w in footer_words),footer_words)
        out.close();source.close()

    def test_unverified_style_cannot_be_inserted(self):
        from page_typography import verified_italics
        with self.assertRaisesRegex(ValueError,"source-verified"):
            verified_italics({"pages":{"124":{"italic_spans":[{"text":"image"}]}}},124)


if __name__=="__main__":
    unittest.main()
