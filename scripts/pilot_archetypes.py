#!/usr/bin/env python3
"""Low-cost, source-only candidate selection for an editorially diverse pilot.

Page archetypes are inferred from tiny raster thumbnails; this is NOT an OCR,
layout-recognition, or proof-of-table detector. A human/agent must verify page
types in the included contact sheet before asking for pilot approval.
"""
from __future__ import annotations

import io
import math
from pathlib import Path
import statistics

import fitz
from PIL import Image, ImageDraw, ImageFont


ROLE_NAMES = (
    "body_early", "body_late", "table_candidate",
    "illustration_candidate", "chapter_opener_candidate",
    "mixed_typography_candidate", "sparse_or_profile_candidate",
)


def page_features(page: fitz.Page) -> dict:
    pix = page.get_pixmap(matrix=fitz.Matrix(.27, .27), colorspace=fitz.csGRAY, alpha=False)
    im = Image.frombytes("L", (pix.width, pix.height), pix.samples)
    im.thumbnail((180, 240))
    w, h = im.size
    if w < 20 or h < 20:
        raise ValueError("Page thumbnail is too small")
    raw = im.tobytes()
    border = [raw[y*w+x] for y in (0, min(h-1, 3), h-1)
              for x in (0, min(w-1, 3), w-1)]
    background = max(195, int(statistics.median(border)))
    threshold = max(90, min(183, background-43))
    x0, x1 = int(.095*w), int(.905*w)
    y0, y1 = int(.065*h), int(.935*h)
    row_fractions = []
    column_counts = [0] * (x1-x0)
    ink = 0
    for y in range(y0,y1):
        active=0
        for x in range(x0,x1):
            if raw[y*w+x] < threshold:
                active+=1
                column_counts[x-x0]+=1
        row_fractions.append(active/max(1,x1-x0))
        ink += active
    col_fractions = [v/max(1,y1-y0) for v in column_counts]
    text_rows = [i for i,v in enumerate(row_fractions) if .035 <= v <= .48]
    row_groups=0
    prior=-3
    for i in text_rows:
        if i-prior>2:
            row_groups+=1
        prior=i
    horiz_rules = sum(v>.66 for v in row_fractions)
    vertical_rules = sum(v>.60 for v in col_fractions)
    first_mark=next((i for i,v in enumerate(row_fractions) if v>.02), len(row_fractions))
    top_whitespace=first_mark/max(1,len(row_fractions))
    tile_heavy=0
    tiles_checked=0
    # Dense rectangular grayscale regions are image/diagram *candidates*.
    for gy in range(9):
        ya=y0+int((y1-y0)*gy/9)
        yb=y0+int((y1-y0)*(gy+1)/9)
        for gx in range(7):
            xa=x0+int((x1-x0)*gx/7)
            xb=x0+int((x1-x0)*(gx+1)/7)
            total=max(1,(yb-ya)*(xb-xa))
            dark=sum(raw[yy*w+xx] < threshold for yy in range(ya,yb) for xx in range(xa,xb))
            tile_heavy += dark/total > .28
            tiles_checked+=1
    ink_ratio=ink/max(1,(y1-y0)*(x1-x0))
    return {
        "row_groups": row_groups,
        "horizontal_rules": horiz_rules,
        "vertical_rules": vertical_rules,
        "dense_tiles": tile_heavy,
        "ink_ratio": round(ink_ratio, 4),
        "top_whitespace": round(top_whitespace, 3),
    }


def role_scores(m: dict, number: int, total: int) -> dict:
    groups=m["row_groups"]
    heavy=m["dense_tiles"]
    hlines=m["horizontal_rules"]
    vlines=m["vertical_rules"]
    ink=m["ink_ratio"]
    top=m["top_whitespace"]
    text_score = groups - heavy*1.5 - hlines - vlines
    table_score = (hlines*2.8 + vlines*2.0 +
                   min(6, groups)*.3 - heavy*.6)
    illustration_score = heavy*2.2 + ink*80 - hlines*.7 - vlines*.7
    chapter_score = top*85 + (max(0,22-groups)*.5) - heavy*.4
    mixed_score = 15 - abs(groups-18)*.6 + min(10, heavy)*.6 + hlines*.3
    sparse_score = 35-max(0,groups-9)*1.4 + top*20
    return {
        "body_early": text_score + (5 if number<total*.5 else -12),
        "body_late": text_score + (5 if number>total*.5 else -12),
        "table_candidate": table_score,
        "illustration_candidate": illustration_score,
        "chapter_opener_candidate": chapter_score,
        "mixed_typography_candidate": mixed_score,
        "sparse_or_profile_candidate": sparse_score,
    }


def survey_numbers(total: int, max_survey: int = 120) -> list[int]:
    if total<=max_survey:
        return list(range(1,total+1))
    numbers={1,total}
    for i in range(max_survey):
        numbers.add(1+round(i*(total-1)/(max_survey-1)))
    return sorted(numbers)


def select_diverse(source: Path, count: int = 7, keep_pages: list[int] | None = None) -> dict:
    """Recommend 5-8 distinct physical pages for visual review, preserving smoke pages."""
    with fitz.open(source) as doc:
        total=len(doc)
        if not total:
            raise ValueError("PDF is empty")
        count=min(total,max(1,count))
        keep=list(dict.fromkeys(keep_pages or []))
        if any(x<1 or x>total for x in keep) or len(keep)>count:
            raise ValueError("Invalid smoke-test pages")
        candidates=[]
        for n in survey_numbers(total):
            try:
                features=page_features(doc[n-1])
            except (ValueError,RuntimeError):
                continue
            candidates.append({"source_page":n,"features":features,
                               "scores":role_scores(features,n,total)})
    if len(candidates)<count:
        raise ValueError("Insufficient readable low-res thumbnails")
    chosen=list(keep)
    assigned={str(n):"retained_smoke_test" for n in keep}
    # Include all retained smoke pages. Reserve remaining slots for novel roles.
    priorities=("table_candidate","illustration_candidate",
                "chapter_opener_candidate","mixed_typography_candidate",
                "sparse_or_profile_candidate","body_early","body_late")
    for role in priorities:
        if len(chosen)>=count:
            break
        ranked=sorted(
            (c for c in candidates if c["source_page"] not in chosen),
            key=lambda c:(-c["scores"][role], c["source_page"]),
        )
        # Avoid near-adjacent source pages unless no alternatives exist.
        eligible=[c for c in ranked if all(abs(c["source_page"]-p)>=3 for p in chosen)]
        if not eligible:
            eligible=ranked
        if not eligible:
            break
        number=eligible[0]["source_page"]
        chosen.append(number)
        assigned[str(number)]=role
    while len(chosen)<count:
        for c in candidates:
            if c["source_page"] not in chosen:
                chosen.append(c["source_page"])
                assigned[str(c["source_page"])]= "additional_candidate"
                break
        else:
            break
    chosen=sorted(chosen)
    matched={c["source_page"]:c for c in candidates}
    return {
        "pages":chosen,
        "roles":{str(n):assigned[str(n)] for n in chosen},
        "method":"low-res visual heuristics; must be verified from original scanned pages",
        "surveyed_pages":len(candidates),"source_page_count":total,
        "candidates":[{"source_page":n, "assigned_role":assigned[str(n)],
                       "features":matched[n]["features"],
                       "role_score":round(matched[n]["scores"].get(assigned[str(n)],0),2)}
                      for n in chosen],
        "human_visual_verification_required":True,
        "coverage_not_proven":["table","illustration","chapter opener","italic/complex typography"],
    }


def contact_sheet(source: Path, selection: dict, dest: Path) -> None:
    """Make a small PDF of original-page thumbnails. Never embed source full-res scans."""
    dest.parent.mkdir(parents=True,exist_ok=True)
    pages=selection["pages"]
    with fitz.open(source) as doc:
        out=fitz.open()
        for offset in range(0,len(pages),9):
            canvas=out.new_page(width=780,height=920)
            for cell_index,n in enumerate(pages[offset:offset+9]):
                col=cell_index%3
                row=cell_index//3
                x=14+col*255
                y=25+row*298
                role=selection["roles"].get(str(n),"candidate")
                canvas.insert_text((x,y),f"Source PDF {n}",fontsize=11)
                canvas.insert_text((x,y+15),role[:32],fontsize=7)
                pix=doc[n-1].get_pixmap(matrix=fitz.Matrix(.25,.25),colorspace=fitz.csRGB,alpha=False)
                im=Image.frombytes("RGB",(pix.width,pix.height),pix.samples)
                im.thumbnail((235,260))
                stream=io.BytesIO()
                im.save(stream,format="JPEG",quality=76)
                rect=fitz.Rect(x,y+21,x+im.width,y+21+im.height)
                canvas.insert_image(rect,stream=stream.getvalue())
        out.save(dest,garbage=3,deflate=True)
        out.close()
