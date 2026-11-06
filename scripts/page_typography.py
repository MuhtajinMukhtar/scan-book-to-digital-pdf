"""Source-anchored paragraph layout with explicit, source-verified italic spans.

Apple Vision does not produce reliable font-style tags. Never guess italics
from word meaning; a reviewed per-page style file supplies those spans.
"""
from __future__ import annotations

import re
import statistics

def footer_number(item: dict) -> bool:
    text = str(item.get("text", "")).strip()
    return bool(
        re.fullmatch(r"\d{1,4}|[ivxlcdmIVXLCDM]{1,8}", text)
        and float(item["y"]) >= .875
        and (float(item["x"]) < .27 or float(item["x"]) > .67)
    )

def split_footer(lines: list[dict]) -> tuple[list[dict], list[dict]]:
    return ([line for line in lines if not footer_number(line)],
            [line for line in lines if footer_number(line)])

def plan_body(body: list[dict], width: float, height: float, font_size: float,
              body_margin: float | None = None,
              preferred_leading: float | None = None,
              preferred_paragraph_gap: float | None = None) -> list[dict]:
    """Keep every original line on its source page with regular paragraph leading.

    No reflow across source lines: recover paragraph groups from vertical gaps,
    stabilize continuation x and within-paragraph leading. Reject unsafe fits.
    """
    if not body:
        return []
    ordered = sorted(body, key=lambda item: (round(float(item["y"]), 4), float(item["x"])))
    ys = [float(line["y"])*height for line in ordered]
    dy = [b-a for a,b in zip(ys,ys[1:]) if b>a and font_size*.72 < b-a < font_size*3.5]
    base_step = statistics.median(dy) if dy else font_size*1.4
    groups: list[list[dict]] = [[]]
    for i,line in enumerate(ordered):
        if i and (ys[i]-ys[i-1] > max(base_step*1.46,font_size*1.75)
                  or ys[i]-ys[i-1] < font_size*.72):
            groups.append([])
        groups[-1].append(line)
    positions = []
    prev_last_source_y = None
    for group_index,group in enumerate(groups):
        original_y = [float(x["y"])*height for x in group]
        steps = [b-a for a,b in zip(original_y,original_y[1:]) if b>a]
        step = max(font_size*1.14,
                   min(font_size*1.85, statistics.median(steps) if steps else base_step))
        if preferred_leading and abs(step-preferred_leading) <= max(.8, step*.07):
            # Small adjustment only: global leading changes previously harmed
            # the visual pilot. Never compress/expand a whole paragraph.
            step = (step + preferred_leading) / 2
        xs = [float(item["x"])*width for item in group]
        continuity = xs[1:] if len(xs)>1 else xs
        base_x = statistics.median(continuity)
        support = sum(abs(x-base_x) <= font_size*.62 for x in continuity)
        centers = [x + float(row["width"])*width/2 for x,row in zip(xs,group)]
        centered = (len(group)>2 and max(xs)-min(xs)>font_size
                    and max(centers)-min(centers)<font_size*.85)
        # A majority of left-starts can correct a single malformed OCR x.
        uniform = bool(len(group)>=3 and not centered
                       and support >= max(2,(len(continuity)+1)//2)
                       and max(len(str(line["text"])) for line in group)>=25)
        if (uniform and body_margin is not None
                and abs(base_x-body_margin)<=width*.035):
            base_x = body_margin
        first_y = original_y[0] + font_size*.89
        if (prev_last_source_y is not None and preferred_paragraph_gap
                and abs((original_y[0]-prev_last_source_y)-preferred_paragraph_gap)<=1.5):
            # Normalize only tiny OCR y jitter between existing paragraphs.
            first_y += max(-1.5,min(1.5,
                (preferred_paragraph_gap-(original_y[0]-prev_last_source_y))*.5))
        prev_last_source_y = original_y[-1]
        for j,item in enumerate(group):
            x = xs[j]
            if uniform and j > 0 and abs(xs[j]-base_x) <= font_size*2.25:
                short_indented_final = (
                    j == len(group)-1 and len(str(item["text"]).strip()) < 18
                    and xs[j]-base_x > font_size*.85
                )
                if not short_indented_final:
                    x = base_x
            elif uniform and j == 0 and abs(xs[0]-base_x) <= font_size*.45:
                x = base_x
            baseline = first_y + j*step
            positions.append({
                **item,
                "draw_x": x,
                "baseline": baseline,
                "paragraph_index": group_index,
                "paragraph_last": j == len(group)-1,
                "paragraph_line_count": len(group),
                "line_step": round(step, 3),
            })
    # Check both consecutive glyph baseline gaps and page limits before drawing.
    for i,item in enumerate(positions):
        if item["draw_x"] < 4 or item["baseline"] > height-15:
            raise ValueError("Text line would leave original source page")
        if i and item["baseline"]-positions[i-1]["baseline"] < font_size*.89:
            raise ValueError("Paragraph spacing would overlap neighboring lines")
    return positions

def verified_italics(annotations: dict, source_page: int) -> list[str]:
    entry = annotations.get("pages", {}).get(str(source_page), {})
    spans = entry.get("italic_spans", [])
    phrases = []
    for span in spans:
        if span.get("source_scan_verified") is not True or not span.get("text"):
            raise ValueError("Italic annotation requires exact source-verified text")
        phrases.append(str(span["text"]))
    return phrases

def styled_tokens(text: str, italic_phrases: list[str]) -> list[tuple[str,bool]]:
    spans: list[tuple[int,int]] = []
    for phrase in italic_phrases:
        start = 0
        while True:
            pos = text.find(phrase, start)
            if pos < 0:
                break
            spans.append((pos,pos+len(phrase)))
            start=pos+len(phrase)
    result=[]
    for m in re.finditer(r"\S+|\s+",text):
        chunk=m.group(0)
        is_italic = not chunk.isspace() and any(a <= m.start() and b >= m.end()
                    or a < m.end() and b > m.start() for a,b in spans)
        result.append((chunk,is_italic))
    return result


def verified_bolds(annotations: dict, source_page: int) -> list[str]:
    """Only exact bold phrases confirmed against the actual source scan."""
    entry = annotations.get("pages", {}).get(str(source_page), {})
    phrases = []
    for span in entry.get("bold_spans", []):
        if span.get("source_scan_verified") is not True or not span.get("text"):
            raise ValueError("Bold annotation requires exact source-verified text")
        phrases.append(str(span["text"]))
    return phrases


def styled_runs(text: str, italic_phrases: list[str],
                bold_phrases: list[str]) -> list[tuple[str, bool, bool]]:
    """Whitespace-aware runs with independent bold/italic flags.

    Preserve the legacy styled_tokens() interface for existing consumers.
    """
    def offsets(phrases):
        spans=[]
        for phrase in phrases:
            pos=0
            while True:
                start=text.find(phrase,pos)
                if start < 0:
                    break
                spans.append((start,start+len(phrase)))
                pos=start+len(phrase)
        return spans
    italics=offsets(italic_phrases)
    bolds=offsets(bold_phrases)
    def intersects(a,b,spans):
        return any(x<b and y>a for x,y in spans)
    return [
        (match.group(0),
         intersects(match.start(),match.end(),italics) and not match.group(0).isspace(),
         intersects(match.start(),match.end(),bolds) and not match.group(0).isspace())
        for match in re.finditer(r"\S+|\s+",text)
    ]
