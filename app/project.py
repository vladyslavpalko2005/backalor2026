from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List

from .pipeline import Step, steps_from_json, steps_to_json


PROJECT_DIRS = [
    "images_raw",
    "images_processed",
    "annotations",
    "models",
    "results",
]


@dataclass
class ProjectState:
    root: Path
    pipeline_steps: List[Step]

    @property
    def pipeline_path(self) -> Path:
        return self.root / "results" / "preprocess_pipeline.json"


def ensure_project_structure(root: Path) -> None:
    for name in PROJECT_DIRS:
        (root / name).mkdir(parents=True, exist_ok=True)


def load_pipeline(root: Path) -> List[Step]:
    path = root / "results" / "preprocess_pipeline.json"
    if not path.exists():
        return []
    return steps_from_json(path.read_text(encoding="utf-8"))


def save_pipeline(root: Path, steps: List[Step]) -> None:
    path = root / "results" / "preprocess_pipeline.json"
    path.write_text(steps_to_json(steps), encoding="utf-8")


def list_raw_images(root: Path) -> List[Path]:
    raw_dir = root / "images_raw"
    if not raw_dir.exists():
        return []
    extensions = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
    def natural_key(path):
        return tuple((1, int(part)) if part.isdigit() else (0, part.casefold()) for part in re.split(r'(\d+)', path.name))
    return sorted((p for p in raw_dir.iterdir() if p.is_file() and p.suffix.lower() in extensions), key=natural_key)
