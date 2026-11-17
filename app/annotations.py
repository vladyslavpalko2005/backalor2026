from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional
from .storage import atomic_write, file_revision, ANY_REVISION, SaveConflict


class UnsupportedAnnotationVersion(ValueError):
    pass


@dataclass
class AnnotationItem:
    id: int
    level: str
    parent_id: Optional[int]
    bbox: List[int]
    label: str = ""
    transcription: str = ""
    symbol_code: str = ""
    kind: str = ""
    confidence: Optional[float] = None
    notes: str = ""
    text_role: str = ""
    element_type: str = ""
    type_confidence: Optional[float] = None
    recognition_confidence: Optional[float] = None
    type_source: str = ""
    recognition_source: str = ""
    reviewed: bool = False
    transcription_ref_id: Optional[int] = None


@dataclass
class AnnotationFile:
    image: str
    items: List[AnnotationItem]
    next_id: int


def annotation_path(root: Path, image_path: Path) -> Path:
    return root / "annotations" / f"{image_path.stem}.json"


def load_annotations(path: Path) -> AnnotationFile:
    data = json.loads(path.read_text(encoding="utf-8"))
    return annotations_from_payload(data)


def annotations_from_payload(data) -> AnnotationFile:
    if data.get("schema_version", 1) > 4:
        raise UnsupportedAnnotationVersion("This annotation file uses a newer schema. Upgrade the application before editing it.")
    fields = AnnotationItem.__dataclass_fields__
    items = [AnnotationItem(**{k: v for k, v in item.items() if k in fields}) for item in data.get("items", [])]
    next_id = max(data.get("next_id", 1), _next_id(items))
    image = data.get("image", "")
    return AnnotationFile(image=image, items=items, next_id=next_id)


def annotations_payload(annotations: AnnotationFile):
    return {
        "schema_version": 4,
        "image": annotations.image,
        "next_id": annotations.next_id,
        "items": [asdict(item) for item in annotations.items],
    }


def save_annotations(path: Path, annotations: AnnotationFile, expected_revision=ANY_REVISION) -> None:
    revision = file_revision(path)
    if expected_revision is not ANY_REVISION and revision != expected_revision:
        raise SaveConflict("The annotation file changed outside this window. Your draft has been kept; reopen the image to compare versions.")
    if path.exists():
        # Do not overwrite a valid backup with an unreadable/corrupt version.
        try:
            load_annotations(path)
        except UnsupportedAnnotationVersion:
            raise
        except (ValueError, TypeError, KeyError):
            pass
        else:
            atomic_write(path.with_suffix('.json.bak'), path.read_bytes())
    content = json.dumps(annotations_payload(annotations), indent=2, ensure_ascii=False).encode('utf-8')
    atomic_write(path, content)
    return hashlib.sha256(content).hexdigest()


def _next_id(items: List[AnnotationItem]) -> int:
    if not items:
        return 1
    return max(item.id for item in items) + 1
