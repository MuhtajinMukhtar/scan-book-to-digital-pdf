#!/usr/bin/env python3
"""Isolated PP-OCRv5 Mobile worker for ONE selected page (never PP-StructureV3).

The parent launches this in its own process group and watches RSS/time. No
model downloads unless --allow-download was authorized by the user.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

MODELS = ("PP-OCRv5_mobile_det", "PP-OCRv5_mobile_rec")


def digest(path: Path) -> str:
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def parse_result(item: object) -> tuple[list[str], list[float], list]:
    data = item if isinstance(item, dict) else getattr(item, "json", None)
    if callable(data):
        data = data()
    if isinstance(data, dict) and isinstance(data.get("res"), dict):
        data = data["res"]
    if not isinstance(data, dict):
        raise ValueError("Unsupported PaddleOCR 3.x result JSON shape")
    texts = data.get("rec_texts")
    if not isinstance(texts, list):
        raise ValueError("Paddle Mobile did not return rec_texts")
    scores = data.get("rec_scores", [])
    boxes = data.get("rec_boxes", [])
    if hasattr(scores, "tolist"):
        scores = scores.tolist()
    if hasattr(boxes, "tolist"):
        boxes = boxes.tolist()
    return ([str(t) for t in texts],
            [float(x) for x in scores] if scores is not None else [],
            boxes or [])


def run(image: Path, output: Path, page: int, source_sha: str, image_sha: str,
        allow_download: bool) -> dict:
    if digest(image) != image_sha:
        raise ValueError("Input image checksum mismatch")
    if output.exists():
        raise ValueError("Existing OCR output may not be overwritten")
    # Only import Paddle here, in the monitored subprocess.
    from paddleocr import PaddleOCR
    options = dict(
        text_detection_model_name=MODELS[0],
        text_recognition_model_name=MODELS[1],
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        device="cpu",
    )
    if not allow_download:
        model_root = Path.home() / ".paddlex" / "official_models"
        if not all((model_root / name).is_dir() for name in MODELS):
            raise ValueError("Mobile model files not cached; request download permission")
        options["text_detection_model_dir"] = str(model_root / MODELS[0])
        options["text_recognition_model_dir"] = str(model_root / MODELS[1])
    predictor = PaddleOCR(**options)
    result = predictor.predict(input=str(image))
    items = list(result)
    if len(items) != 1:
        raise ValueError("Expected one PaddleOCR result for a single image")
    texts, scores, boxes = parse_result(items[0])
    if digest(image) != image_sha:
        raise ValueError("Image changed during OCR")
    record = {
        "engine": "paddle-ppocrv5-mobile", "model_names": list(MODELS),
        "page": page, "source_sha256": source_sha, "image_sha256": image_sha,
        "rec_texts": texts, "rec_scores": scores, "rec_boxes": boxes,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(".json.partial")
    tmp.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(output)
    return {"page": page, "recognized_lines": len(texts), "engine": record["engine"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--page", type=int, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--image-sha", required=True)
    parser.add_argument("--allow-download", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.image, args.output, args.page, args.source_sha,
                             args.image_sha, args.allow_download)), flush=True)
    except (ImportError, ValueError, RuntimeError, OSError) as exc:
        print("MOBILE_CHECK_FAILED: " + str(exc), file=sys.stderr, flush=True)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
