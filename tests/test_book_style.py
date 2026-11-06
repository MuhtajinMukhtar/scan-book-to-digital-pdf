"""Book-specific typography selection: left vs justify, safe margins and background."""
from __future__ import annotations

import sys
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from book_style import observe_page, infer_style, validate_style, palette, source_verified_override
from page_typography import plan_body, verified_bolds, styled_runs


def prose_page(number: int, alignment: str, offset: float = 0.0) -> tuple:
    body=[]
    for para in range(3):
        for row in range(6):
            index=para*6+row
            ends=[.78,.83,.73,.88,.80,.63]
            right=.89 if alignment=="justify" and row<5 else ends[row]
            if row==5:
                right=.69
            left=.12+offset
            body.append({
                "text":f"Source paragraph {para+1} continues with meaningful words, line {row+1}.",
                "x":left, "y":(90+para*150+row*21)/700,
                "width":right-left, "height":16/700
            })
    class Rect:
        width=500
        height=700
    return number,Rect(),body


class SourceTypographyTests(unittest.TestCase):
    def test_ragged_right_detected_from_source_not_hardcoded(self):
        records=[prose_page(n,"left",offset=(n-2)*.004)
                 for n in (1,2,3)]
        inferred=infer_style(records)
        self.assertEqual(inferred["alignment"],"left")
        self.assertEqual(inferred["background"],"cream")
        self.assertEqual(inferred["pages_observed"],3)
        validate_style(inferred)

    def test_justified_source_detected_with_same_code(self):
        inferred=infer_style([prose_page(n,"justify") for n in (1,2,3)])
        self.assertEqual(inferred["alignment"],"justify")
        self.assertGreaterEqual(inferred["justified_votes"],2)

    def test_unknown_style_does_not_force_justification(self):
        _,bounds,lines=prose_page(1,"left")
        inferred=infer_style([(1,bounds,lines)])
        self.assertEqual(inferred["alignment"],"source_uncertain")
        self.assertTrue(inferred["source_review_required"])

    def test_book_margin_applies_only_to_prose_with_small_scan_offset(self):
        _,bounds,lines=prose_page(2,"left",offset=.012)
        planned=plan_body(lines,500,700,13,body_margin=60)
        # Every continued body line should move to the book-wide left edge,
        # while its text and source page assignment are unchanged.
        self.assertEqual(len(planned),len(lines))
        self.assertAlmostEqual(planned[1]["draw_x"],60,delta=1)
        self.assertEqual([row["text"] for row in planned],[row["text"] for row in lines])

    def test_intentional_first_line_indentation_remains(self):
        _,bounds,lines=prose_page(2,"left")
        lines[0]["x"]+=.04
        planned=plan_body(lines,500,700,13,body_margin=60)
        self.assertAlmostEqual(planned[0]["draw_x"],80,delta=1)
        self.assertAlmostEqual(planned[1]["draw_x"],60,delta=1)

    def test_cream_and_white_colors_distinct(self):
        cream=palette("cream")
        self.assertTrue(all(.94<x<1 for x in cream))
        self.assertEqual(palette("white"),(1,1,1))
        self.assertNotEqual(cream,palette("white"))

    def test_ambiguous_alignment_requires_source_visual_evidence(self):
        detected=infer_style([prose_page(1,"left")])
        self.assertEqual(detected["alignment"],"source_uncertain")
        with self.assertRaisesRegex(ValueError,"source visual verification"):
            source_verified_override(detected,{
                "source_sha256":"abc","alignment":"justify"
            },"abc")
        approved=source_verified_override(detected,{
            "source_sha256":"abc","source_scan_verified":True,
            "alignment":"justify"
        },"abc")
        self.assertEqual(approved["alignment"],"justify")
        self.assertFalse(approved["source_review_required"])
        self.assertTrue(approved["visual_review_override"])
        with self.assertRaisesRegex(ValueError,"another source"):
            source_verified_override(detected,{
                "source_sha256":"abc","source_scan_verified":True,
                "alignment":"left"
            },"other")

    def test_verified_bold_and_italic_can_overlap(self):
        annotations={"pages":{"7":{"bold_spans":[
            {"text":"Important word","source_scan_verified":True}]}}}
        bold=verified_bolds(annotations,7)
        mixed=styled_runs("An Important word matters.",["word"],bold)
        self.assertIn(("Important",False,True),mixed)
        self.assertIn(("word",True,True),mixed)
        with self.assertRaisesRegex(ValueError,"source-verified"):
            verified_bolds({"pages":{"7":{"bold_spans":[{"text":"fake"}]}}},7)


if __name__=="__main__":
    unittest.main()
