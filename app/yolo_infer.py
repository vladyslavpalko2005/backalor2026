from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Tuple

from PIL import Image

from .i18n import tr


@dataclass
class DetectedBox:
    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float


def _load_model(weights_path: Path):
    try:
        from ultralytics import YOLO
    except Exception as exc:  # pragma: no cover - import error path
        raise RuntimeError(tr("error.ultralytics_missing")) from exc
    return YOLO(str(weights_path))


def _boxes_from_results(results) -> List[DetectedBox]:
    boxes: List[DetectedBox] = []
    for r in results:
        if not hasattr(r, "boxes"):
            continue
        for box in r.boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            conf = float(box.conf[0]) if box.conf is not None else 0.0
            boxes.append(DetectedBox(x1=x1, y1=y1, x2=x2, y2=y2, confidence=conf))
    return boxes


def _run_detect(model, image: Image.Image, conf: float) -> List[DetectedBox]:
    results = model.predict(source=image, conf=conf, verbose=False)
    return _boxes_from_results(results)


def _crop(image: Image.Image, box: DetectedBox) -> Image.Image:
    return image.crop((int(box.x1), int(box.y1), int(box.x2), int(box.y2)))


def _crop_region(image: Image.Image, box: DetectedBox):
    left, top = max(0, int(box.x1)), max(0, int(box.y1))
    right, bottom = min(image.width, int(box.x2)), min(image.height, int(box.y2))
    if right <= left or bottom <= top:
        return None
    return image.crop((left, top, right, bottom)), left, top


def _offset_boxes(boxes: Iterable[DetectedBox], offset_x: float, offset_y: float) -> List[DetectedBox]:
    out: List[DetectedBox] = []
    for b in boxes:
        out.append(
            DetectedBox(
                x1=b.x1 + offset_x,
                y1=b.y1 + offset_y,
                x2=b.x2 + offset_x,
                y2=b.y2 + offset_y,
                confidence=b.confidence,
            )
        )
    return out


def cascade_detect(
    image: Image.Image,
    weights_l1: Path,
    weights_l2: Path,
    weights_l3: Path,
    conf_l1: float = 0.25,
    conf_l2: float = 0.25,
    conf_l3: float = 0.25,
) -> Tuple[List[DetectedBox], List[DetectedBox], List[DetectedBox]]:
    model_l1 = _load_model(weights_l1)
    model_l2 = _load_model(weights_l2)
    model_l3 = _load_model(weights_l3)

    l1_boxes = _run_detect(model_l1, image, conf_l1)
    l2_boxes_all: List[DetectedBox] = []
    l3_boxes_all: List[DetectedBox] = []

    for l1 in l1_boxes:
        region1 = _crop_region(image, l1)
        if region1 is None:
            continue
        crop1, left1, top1 = region1
        l2_boxes = _run_detect(model_l2, crop1, conf_l2)
        l2_boxes = _offset_boxes(l2_boxes, left1, top1)
        l2_boxes_all.extend(l2_boxes)

        for l2 in l2_boxes:
            region2 = _crop_region(image, l2)
            if region2 is None:
                continue
            crop2, left2, top2 = region2
            l3_boxes = _run_detect(model_l3, crop2, conf_l3)
            l3_boxes = _offset_boxes(l3_boxes, left2, top2)
            l3_boxes_all.extend(l3_boxes)

    return l1_boxes, l2_boxes_all, l3_boxes_all
