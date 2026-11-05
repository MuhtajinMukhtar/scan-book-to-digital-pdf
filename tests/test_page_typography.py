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

    def test_printed_page_27_ocr_outlier_does_not_indent_third_line(self):
        """Regression for uneven starts on the short multi-line paragraph."""
        words = [
            "A guest told the team the welcome ritual should stop there.",
            "The reply was surprising because another visitor interrupted.",
            "Someone suddenly exclaimed a sentence from the audience.",
            "The others laughed together afterwards.",
        ]
        x_points = [55, 55.5, 76, 56]  # third line has a false +20 pt indent
        y_points = [120, 142, 163, 185]  # OCR baseline jitter +/- 1 pt
        widths = [365, 360, 333, 310]
        lines = [
            {"text": text, "x": x / 500, "y": y / 700,
             "width": w / 500, "height": 17 / 700}
            for text, x, y, w in zip(words, x_points, y_points, widths)
        ]
        rendered = plan_body(lines, 500, 700, 13)
        self.assertEqual([r["text"] for r in rendered], words)
        self.assertLess(max(r["draw_x"] for r in rendered) -
                        min(r["draw_x"] for r in rendered), 2.5)
        self.assertTrue(rendered[2]["alignment_corrected"])
        baselines = [r["baseline"] for r in rendered]
        gaps = [b-a for a, b in zip(baselines, baselines[1:])]
        self.assertLess(max(gaps)-min(gaps), .01)
        self.assertTrue(all(0 < y < 700 for y in baselines))

    def test_same_leading_across_separate_prose_paragraphs(self):
        ys = [90, 112, 133, 166, 189, 209]
        lines = [{"text": f"An ordinary paragraph sample from line {i}.",
                  "x": .14, "y": y / 700, "width": .72, "height": .025}
                 for i, y in enumerate(ys)]
        result = plan_body(lines, 500, 700, 13)
        self.assertNotEqual(result[2]["paragraph_index"], result[3]["paragraph_index"])
        first = result[1]["baseline"] - result[0]["baseline"]
        second = result[4]["baseline"] - result[3]["baseline"]
        self.assertAlmostEqual(first, second, places=3)
        self.assertGreater(result[3]["baseline"] - result[2]["baseline"], first * 1.3)

    def test_preserves_actual_first_line_indent(self):
        starts = [78, 60, 60, 61]
        lines = [{"text": f"An intentional paragraph with meaningful text {i}.",
                  "x": x / 500, "y": (80+i*24)/700,
                  "width": .68, "height": .024}
                 for i, x in enumerate(starts)]
        result = plan_body(lines, 500, 700, 13)
        self.assertAlmostEqual(result[0]["draw_x"], 78, delta=.2)
        self.assertLess(max(r["draw_x"] for r in result[1:]) -
                        min(r["draw_x"] for r in result[1:]), 1)

    def test_does_not_left_align_centered_quote_or_title(self):
        starts = [140, 160, 150]
        widths = [240, 200, 220]  # common center x = 260 pt
        lines = [{"text": f"A centered multiline quotation with long line {i}.",
                  "x": x / 500, "y": (120+i*26)/700,
                  "width": w / 500, "height": .025}
                 for i, (x, w) in enumerate(zip(starts, widths))]
        result = plan_body(lines, 500, 700, 13)
        self.assertEqual([round(r["draw_x"]) for r in result], starts)
        self.assertTrue(all(not r["alignment_corrected"] for r in result))

    def test_short_indented_closing_signature_is_preserved(self):
        xs = [55, 55, 55, 77]
        texts = [
            "A longer quoted paragraph makes a consistent left edge.",
            "The reader can compare multiple original aligned lines.",
            "Further lines help establish the meaningful left margin.",
            "Signed.",
        ]
        lines = [{"text": txt, "x": x / 500, "y": (160+i*23)/700,
                  "width": .70, "height": .024}
                 for i, (txt, x) in enumerate(zip(texts, xs))]
        result = plan_body(lines, 500, 700, 13)
        self.assertAlmostEqual(result[-1]["draw_x"], 77)

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
