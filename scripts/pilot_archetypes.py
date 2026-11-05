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


def _groups_of_adjacent(values: list[int]) -> list[list[int]]:
    groups: list[list[int]] = []
    for n in values:
        if not groups or n-groups[-1][-1] > 1:
            groups.append([n])
        else:
            groups[-1].append(n)
    return groups


def _max_run(values) -> int:
    best=current=0
    for value in values:
        current=current+1 if value else 0
        best=max(best,current)
    return best


def page_features(page: fitz.Page) -> dict:
    """Classify visual candidates from source-only tiny grayscale rasters.

    Paper-color/text contrast varies wildly between scans, so use a bright
    percentile of *whole page* rather than the dark corner of a facing page.
    """
    pix = page.get_pixmap(matrix=fitz.Matrix(.42, .42),
                          colorspace=fitz.csGRAY, alpha=False)
    w,h = pix.width,pix.height
    if w < 20 or h < 20:
        raise ValueError("Page thumbnail too small")
    raw = pix.samples
    hist = [0]*256
    for shade in raw:
        hist[shade] += 1
    quota = len(raw)*.87
    cumulative=0
    background=255
    for color,count in enumerate(hist):
        cumulative+=count
        if cumulative>=quota:
            background=color
            break
    # Anti-aliased text at low raster scale needs a softer threshold. A
    # separate dark threshold is used below to detect thin table rules.
    threshold=max(110,min(228,background-31))
    rule_threshold=max(95,min(140,background-72))
    x0,x1=int(.10*w),int(.90*w)
    y0,y1=int(.06*h),int(.93*h)
    fractions=[]
    ink=0
    tiles=[]
    for y in range(y0,y1):
        count=sum(raw[y*w+x]<threshold for x in range(x0,x1))
        fractions.append(count/max(1,x1-x0))
        ink+=count
    text_rows=[i for i,v in enumerate(fractions) if .026 <= v <= .52]
    groups=0
    last=-3
    for y in text_rows:
        if y-last>2:
            groups+=1
        last=y
    structural_rows = [
        y for y in range(y0,y1)
        if _max_run(raw[y*w+x]<rule_threshold for x in range(x0,x1))
           >= .57*(x1-x0)
    ]
    structural_cols = [
        x for x in range(x0,x1)
        if _max_run(raw[y*w+x]<rule_threshold for y in range(y0,y1))
           >= .21*(y1-y0)
    ]
    # Discard thick filled blocks: a colored quotation card or photograph
    # must not be mislabeled as a table merely because it has dark edges.
    thin_h=sum(len(group)<=7 for group in _groups_of_adjacent(structural_rows))
    thin_v=sum(len(group)<=7 for group in _groups_of_adjacent(structural_cols))
    for gy in range(9):
        ya=y0+int((y1-y0)*gy/9)
        yb=y0+int((y1-y0)*(gy+1)/9)
        for gx in range(7):
            xa=x0+int((x1-x0)*gx/7)
            xb=x0+int((x1-x0)*(gx+1)/7)
            area=max(1,(yb-ya)*(xb-xa))
            dark=sum(raw[yy*w+xx]<threshold for yy in range(ya,yb)
                     for xx in range(xa,xb))
            tiles.append(dark/area)
    dense=sum(dark>.33 for dark in tiles)
    first_ink=next((i for i,v in enumerate(fractions) if v>.025),len(fractions))
    ink_ratio=ink/max(1,(y1-y0)*(x1-x0))
    return {
        "row_groups":groups,"horizontal_rules":thin_h,
        "vertical_rules":thin_v,
        "dense_tiles":dense,
        "ink_ratio":round(ink_ratio,4),
        "top_whitespace":round(first_ink/max(1,len(fractions)),3),
    }


def role_scores(m: dict, number: int, total: int) -> dict:
    groups=m["row_groups"]
    heavy=m["dense_tiles"]
    hlines=m["horizontal_rules"]
    vlines=m["vertical_rules"]
    ink=m["ink_ratio"]
    top=m["top_whitespace"]
    text_score = groups - heavy*1.2 - hlines*2-vlines*2
    # A real lined table should contain both horizontal and vertical rules.
    # A large colored box without cells is mixed-format, not necessarily a table.
    table_score = (10*min(5,hlines)+12*min(5,vlines)
                   - .8*heavy - (35 if not hlines or not vlines else 0))
    illustration_score = 2.0*heavy + ink*50 - hlines*2-vlines*2
    chapter_score = top*65 + max(0,30-groups)*1.1 + min(6,heavy)*.5
    mixed_score = 17 - abs(groups-20)*.55 + heavy*.85 + hlines*.7
    sparse_score = 40-max(0,groups-12)*1.2+top*12+min(6,heavy)*.4
    return {
        "body_early":text_score+(5 if number<total*.50 else -12),
        "body_late":text_score+(5 if number>total*.50 else -12),
        "table_candidate":table_score,
        "illustration_candidate":illustration_score,
        "chapter_opener_candidate":chapter_score,
        "mixed_typography_candidate":mixed_score,
        "sparse_or_profile_candidate":sparse_score,
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
        # Always survey cached smoke pages even when uniform sampling skips them.
        to_survey=sorted(set(survey_numbers(total)) | set(keep))
        if total>30:
            # Exclude covers/back covers from normal chapter/table samples.
            to_survey=[n for n in to_survey if 3 <= n <= total-2 or n in keep]
        for n in to_survey:
            try:
                features=page_features(doc[n-1])
                if total > 30 and features["ink_ratio"] < .008 and n not in keep:
                    continue  # blank/separator, never a representative pilot
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
