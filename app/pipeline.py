from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from typing import Any, Dict, List

from PIL import Image, ImageEnhance, ImageFilter, ImageOps


@dataclass
class Step:
    step_type: str
    enabled: bool
    params: Dict[str, Any]


STEP_DEFS: Dict[str, Dict[str, Any]] = {
    "grayscale": {
        "label_key": "step.grayscale",
        "params": {},
    },
    "invert": {
        "label_key": "step.invert",
        "params": {},
    },
    "brightness": {
        "label_key": "step.brightness",
        "params": {"factor": 1.0},
    },
    "contrast": {
        "label_key": "step.contrast",
        "params": {"factor": 1.0},
    },
    "sharpness": {
        "label_key": "step.sharpness",
        "params": {"factor": 1.0},
    },
    "gaussian_blur": {
        "label_key": "step.gaussian_blur",
        "params": {"radius": 1.0},
    },
    "median_blur": {
        "label_key": "step.median_blur",
        "params": {"size": 3},
    },
    "threshold": {
        "label_key": "step.threshold",
        "params": {"threshold": 128},
    },
    "gamma": {
        "label_key": "step.gamma",
        "params": {"gamma": 1.0},
    },
    "rotate": {
        "label_key": "step.rotate",
        "params": {"degrees": 0},
    },
    "resize": {
        "label_key": "step.resize",
        "params": {"width": 0, "height": 0, "keep_aspect": True},
    },
    "crop": {
        "label_key": "step.crop",
        "params": {"left": 0, "top": 0, "right": 0, "bottom": 0},
    },
}


def default_step(step_type: str) -> Step:
    if step_type not in STEP_DEFS:
        raise ValueError(f"Unknown step type: {step_type}")
    return Step(step_type=step_type, enabled=True, params=STEP_DEFS[step_type]["params"].copy())


def apply_pipeline(image: Image.Image, steps: List[Step]) -> Image.Image:
    output = image.copy()
    for step in steps:
        if not step.enabled:
            continue
        output = apply_step(output, step)
    return output


def apply_step(image: Image.Image, step: Step) -> Image.Image:
    stype = step.step_type
    p = step.params

    if stype == "grayscale":
        return image.convert("L")
    if stype == "invert":
        if image.mode not in ("RGB", "L"):
            base = image.convert("RGB")
            return ImageOps.invert(base)
        return ImageOps.invert(image)
    if stype == "brightness":
        return ImageEnhance.Brightness(image).enhance(float(p.get("factor", 1.0)))
    if stype == "contrast":
        return ImageEnhance.Contrast(image).enhance(float(p.get("factor", 1.0)))
    if stype == "sharpness":
        return ImageEnhance.Sharpness(image).enhance(float(p.get("factor", 1.0)))
    if stype == "gaussian_blur":
        return image.filter(ImageFilter.GaussianBlur(radius=float(p.get("radius", 1.0))))
    if stype == "median_blur":
        size = int(p.get("size", 3))
        if size < 1:
            size = 1
        if size % 2 == 0:
            size += 1
        return image.filter(ImageFilter.MedianFilter(size=size))
    if stype == "threshold":
        threshold = int(p.get("threshold", 128))
        gray = image.convert("L")
        return gray.point(lambda x: 255 if x >= threshold else 0)
    if stype == "gamma":
        gamma = float(p.get("gamma", 1.0))
        if gamma <= 0:
            gamma = 1.0
        inv = 1.0 / gamma
        return image.point(lambda x: int((x / 255.0) ** inv * 255))
    if stype == "rotate":
        degrees = float(p.get("degrees", 0))
        if degrees == 0:
            return image
        return image.rotate(degrees, expand=True)
    if stype == "resize":
        width = int(p.get("width", 0))
        height = int(p.get("height", 0))
        keep_aspect = bool(p.get("keep_aspect", True))
        if width <= 0 and height <= 0:
            return image
        if keep_aspect:
            base_w, base_h = image.size
            ratios = []
            if width > 0:
                ratios.append(width / base_w)
            if height > 0:
                ratios.append(height / base_h)
            ratio = min(ratios)
            width = round(base_w * ratio)
            height = round(base_h * ratio)
        return image.resize((max(1, width), max(1, height)))
    if stype == "crop":
        left = int(p.get("left", 0))
        top = int(p.get("top", 0))
        right = int(p.get("right", 0))
        bottom = int(p.get("bottom", 0))
        if right <= 0:
            right = image.size[0]
        if bottom <= 0:
            bottom = image.size[1]
        box = (left, top, right, bottom)
        if left < 0 or top < 0 or right > image.width or bottom > image.height or right <= left or bottom <= top:
            raise ValueError("Crop must be a non-empty rectangle inside the image")
        return image.crop(box)

    return image


def steps_to_json(steps: List[Step]) -> str:
    return json.dumps([asdict(s) for s in steps], indent=2, ensure_ascii=False)


def steps_from_json(text: str) -> List[Step]:
    raw = json.loads(text)
    steps: List[Step] = []
    for item in raw:
        steps.append(Step(step_type=item["step_type"], enabled=item.get("enabled", True), params=item.get("params", {})))
    return steps
