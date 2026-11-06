"""Book-level pagination style inferred from OCR of the *current source book*.

Source page labels, not PDF physical indices, are the only authority for the
printed page number. This module standardizes *where* an existing number is
drawn; it never invents, renumbers or fills in unrecognized page labels.

The locked pilot profile holds the shared footer baseline, font size, left/
right inset, and (when strongly evidenced) a mirrored odd/even pattern.
"""
from __future__ import annotations

import statistics
from typing import Iterable

from page_typography import footer_number


def _median(values: Iterable[float], default: float) -> float:
    data=list(values)
    return float(statistics.median(data)) if data else float(default)


def fit_geometry(source_width: float, source_height: float,
                 paper_width: float, paper_height: float) -> tuple[float,float,float]:
    if min(source_width, source_height, paper_width, paper_height) <= 0:
        raise ValueError("Invalid footer page geometry")
    scale=min(paper_width/source_width,paper_height/source_height)
    return (scale,(paper_width-source_width*scale)/2,
            (paper_height-source_height*scale)/2)


def source_footer(source_number: int, source_width: float,
                  source_height: float, lines: list[dict],
                  paper_width: float, paper_height: float) -> dict | None:
    """Return confident OCR-identified numeric footer only, with paper coordinates."""
    matches=[line for line in lines if footer_number(line)]
    if len(matches)!=1:
        return None
    row=matches[0]
    scale,padx,pady=fit_geometry(source_width,source_height,
                                 paper_width,paper_height)
    x=float(row["x"])*source_width
    y=float(row["y"])*source_height
    w=float(row["width"])*source_width
    h=float(row["height"])*source_height
    center=(x+w/2)*scale+padx
    side=("left" if center<paper_width*.36 else
          "right" if center>paper_width*.64 else "center")
    baseline=(y+h*.86)*scale+pady
    return {
        "source_page":source_number,
        "label":str(row["text"]).strip(),
        "side":side,
        "left_pt":round(x*scale+padx,3),
        "right_pt":round(paper_width-(x+w)*scale-padx,3),
        "baseline_from_bottom_pt":round(paper_height-baseline,3),
        "font_size_pt":round(min(12.0,max(8.0,h*scale*.86)),2),
    }


def infer_footer_policy(records: list[tuple[int, float, float, list[dict]]],
                        paper: dict) -> dict:
    """Choose shared footer geometry, not page numbers.

    Sparse/ambiguous patterns preserve the original OCR-observed side, but
    still adopt one consistent outer inset, baseline and font size.
    """
    paper_width=float(paper["width_pt"])
    paper_height=float(paper["height_pt"])
    observations=[
        source_footer(page,width,height,lines,paper_width,paper_height)
        for page,width,height,lines in records
    ]
    samples=[row for row in observations if row]
    lefts=[row["left_pt"] for row in samples if row["side"]=="left"]
    rights=[row["right_pt"] for row in samples if row["side"]=="right"]
    inset_default=min(35.0,paper_width*.10)
    left=_median(lefts,_median(rights,inset_default))
    right=_median(rights,_median(lefts,inset_default))
    # Keep footer anchors in a plausible inset zone. Wildly off-page OCR
    # positions are a source-review issue rather than a reason to move text.
    max_inset=min(paper_width*.24,100.0)
    left=max(10.0,min(left,max_inset))
    right=max(10.0,min(right,max_inset))
    bottom=_median((row["baseline_from_bottom_pt"] for row in samples),30.0)
    bottom=max(14.0,min(bottom,min(65.0,paper_height*.11)))
    font=_median((row["font_size_pt"] for row in samples),9.5)
    observations_by_parity={parity:[
        item["side"] for item in samples if item["source_page"]%2==parity
    ] for parity in (0,1)}
    parity_sides={}
    for parity,observed in observations_by_parity.items():
        if len(observed)<2:
            continue
        counted={side:observed.count(side) for side in ("left","right","center")}
        best=max(counted,key=counted.get)
        if best!="center" and counted[best]/len(observed)>=.8:
            parity_sides[str(parity)]=best
    mirror=(len(parity_sides)==2 and parity_sides["0"]!=parity_sides["1"])
    return {
        "version":1, "source":"current_pdf_ocr_only",
        "sample_count":len(samples),
        "baseline_from_bottom_pt":round(bottom,2),
        "left_inset_pt":round(left,2),
        "right_inset_pt":round(right,2),
        "font_size_pt":round(font,2),
        "side_rule":"mirrored_source_parity" if mirror else "observed_source_side",
        "parity_sides":parity_sides if mirror else {},
        "source_review_required":len(samples)<2,
        "limitations":"Unrecognized, decorative and absent footer numbers are not "
                      "created. Footer art and anomalous numbering need visual review.",
    }


def target_footer(source_number: int, original_line: dict, policy: dict,
                  source_width: float, source_height: float,
                  paper_width: float, paper_height: float,
                  font_width_pt: float) -> dict:
    """Map one canonical-paper footer anchor back to the composer's page.

    The next vector-only paper-fitting step preserves the target canonical
    position and font size on every output page.
    """
    evidence=source_footer(source_number,source_width,source_height,
                           [original_line],paper_width,paper_height)
    if evidence is None:
        raise ValueError("Footer label is not a uniquely identified source number")
    if policy.get("version")!=1:
        raise ValueError("Invalid locked footer style version")
    side=policy.get("parity_sides",{}).get(str(source_number%2),
                                         evidence["side"])
    if side not in ("left","right"):
        raise ValueError("Centered or uncertain footer requires source visual review")
    scale,padx,pady=fit_geometry(source_width,source_height,
                                 paper_width,paper_height)
    target_font=float(policy["font_size_pt"])
    paper_baseline=paper_height-float(policy["baseline_from_bottom_pt"])
    if side=="left":
        paper_x=float(policy["left_inset_pt"])
    else:
        paper_x=paper_width-float(policy["right_inset_pt"])-font_width_pt
    source_x=(paper_x-padx)/scale
    source_baseline=(paper_baseline-pady)/scale
    # Do not push the number outside the source-page vector canvas. An unusual
    # scanner crop should be flagged; a later editorial step may adjust it.
    if (source_x < 2 or source_x + font_width_pt/scale > source_width-2
            or source_baseline < source_height*.85
            or source_baseline > source_height-4):
        raise ValueError("Canonical footer placement outside safe source footer area")
    return {
        "x":source_x,"baseline":source_baseline,
        "font_size":target_font/scale,
        "side":side,
        "canonical_paper_baseline_pt":paper_baseline,
        "canonical_paper_x_pt":paper_x,
        "canonical_font_pt":target_font,
    }
