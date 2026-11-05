"""Regression tests: paragraph rhythm, mirrored margins and verified styles."""
import importlib.util
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from page_typography import plan_body, split_footer, verified_italics, styled_tokens


class TypographyTests(unittest.TestCase):
    def test_separates_page_number_without_reflow(self):
        body = [{"text": "This paragraph continues", "x": .14, "y": .20,
                 "width": .65, "height": .026},
                {"text": "on the same original page", "x": .14, "y": .235,
                 "width": .60, "height": .026}]
        footer = {"text": "93", "x": .88, "y": .935, "width": .035, "height": .02}
        content, numbers=split_footer(body+[footer])
        self.assertEqual(len(content),2)
        self.assertEqual(numbers,[footer])

    def test_mirrored_margin_source_anchors_are_preserved(self):
        left = [{"text": f"Line {i} of the original chapter source", "x": .18, "y": .12+i*.038,
                 "width": .64, "height": .025} for i in range(6)]
        right = [{**x,"x": .075} for x in left]
        a=plan_body(left,500,700,13)
        b=plan_body(right,500,700,13)
        self.assertGreater(a[0]["draw_x"],b[0]["draw_x"])
        self.assertAlmostEqual(a[0]["draw_x"],90)
        self.assertAlmostEqual(b[0]["draw_x"],37.5)

    def test_regularizes_jitter_without_page_spill(self):
        jitter = [0,1,-1,2,-1,1]
        sample = [{"text": f"Sentence line {i} is always preserved.", "x": .11,
                   "y": (70+i*26+jitter[i])/700, "width": .75, "height": .024}
                  for i in range(len(jitter))]
        laid=plan_body(sample,500,700,14)
        gaps=[laid[i+1]["baseline"]-laid[i]["baseline"]
              for i in range(len(laid)-1)]
        self.assertLess(max(gaps)-min(gaps),0.01)
        self.assertEqual([r["text"] for r in laid],[r["text"] for r in sample])

    def test_source_verified_italic_only(self):
        self.assertRaisesRegex(ValueError,"source-verified",
            verified_italics, {"pages":{"124":{"italic_spans":[{"text":"advertising"}]}}},124)
        phrases=verified_italics({"pages":{"124":{"italic_spans":[{
            "text":"advertising","source_scan_verified":True}]}}},124)
        styles=styled_tokens("Buku ini membahas advertising juga.", phrases)
        self.assertIn(("advertising", True),styles)
        self.assertIn(("membahas",False),styles)

    def test_no_italic_without_source_evidence(self):
        words=styled_tokens("image advertising hati yang terjaga",[])
        self.assertFalse(any(italic for _,italic in words))


if __name__=="__main__":
    unittest.main()
