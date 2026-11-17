"""Portable exports and non-destructive dataset checks."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import List
from PIL import Image
from .annotations import AnnotationFile, AnnotationItem, annotation_path, load_annotations
from .project import list_raw_images


def validate_annotations(annotations: AnnotationFile, size: tuple[int, int]) -> List[str]:
    issues = []
    indexed = {item.id: item for item in annotations.items}
    if len(indexed) != len(annotations.items):
        issues.append("duplicate_ids")
    for item in annotations.items:
        prefix = f"#{item.id}"
        from .annotation_ops import reference_issues
        issues.extend(f'{prefix}: {issue}' for issue in reference_issues(item,annotations.items))
        if item.text_role not in ('','plaintext','ciphertext'):
            issues.append(f"{prefix}: invalid_text_role")
        if item.element_type not in ('','readable','cipher_symbol'):
            issues.append(f"{prefix}: invalid_element_type")
        if item.level not in ("L1", "L2", "L3"):
            issues.append(f"{prefix}: unknown_level")
        if len(item.bbox) != 4:
            issues.append(f"{prefix}: invalid_bbox")
            continue
        x, y, w, h = item.bbox
        if min(x, y) < 0 or min(w, h) <= 0 or x + w > size[0] or y + h > size[1]:
            issues.append(f"{prefix}: outside_image")
        parent = indexed.get(item.parent_id)
        if item.level == "L1":
            if item.parent_id is not None:
                issues.append(f"{prefix}: root_has_parent")
        elif parent is None:
            issues.append(f"{prefix}: missing_parent")
        elif parent.level != {"L2": "L1", "L3": "L2"}.get(item.level):
            issues.append(f"{prefix}: parent_level")
        if parent and len(parent.bbox) == 4:
            px, py, pw, ph = parent.bbox
            if not (px <= x and py <= y and x+w <= px+pw and y+h <= py+ph):
                issues.append(f"{prefix}: outside_parent")
    return issues


def export_coco(root: Path, target: Path) -> dict:
    categories = [{"id": i+1, "name": level} for i, level in enumerate(("L1", "L2", "L3"))]
    payload = {"info": {"description": "Backalor hierarchical annotations", "schema_version": 4},
               "images": [], "annotations": [], "categories": categories}
    next_id = 1
    for image_id, path in enumerate(list_raw_images(root), 1):
        source = annotation_path(root, path)
        if not source.exists():
            continue
        with Image.open(path) as image:
            width, height = image.size
        annotation = load_annotations(source)
        id_map = {item.id: next_id+i for i, item in enumerate(annotation.items)}
        payload["images"].append({"id": image_id, "file_name": path.name, "width": width, "height": height})
        for item in annotation.items:
            x, y, w, h = item.bbox
            if item.level not in ("L1", "L2", "L3") or w <= 0 or h <= 0:
                raise ValueError(f"{path.name}: invalid annotation #{item.id}")
            payload["annotations"].append({
                "id": id_map[item.id], "image_id": image_id, "category_id": ("L1", "L2", "L3").index(item.level)+1,
                "bbox": item.bbox, "area": w*h, "iscrowd": 0,
                "parent_id": id_map.get(item.parent_id), "source_id": item.id,
                "attributes": {"label": item.label, "transcription": item.transcription,
                               "symbol_code": item.symbol_code, "kind": item.kind,
                               "confidence": item.confidence, "notes": item.notes,
                               "text_role": item.text_role, "element_type": item.element_type,
                               "type_confidence": item.type_confidence, "recognition_confidence": item.recognition_confidence,
                               "type_source": item.type_source, "recognition_source": item.recognition_source,
                               "reviewed": item.reviewed,
                               "transcription_ref_id": item.transcription_ref_id,
                               "transcription_ref_annotation_id": id_map.get(item.transcription_ref_id)}})
        next_id += len(annotation.items)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def export_bundle(root: Path, target: Path) -> None:
    """Only portable source data; training artifacts are intentionally excluded."""
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for folder in ("images_raw", "images_processed", "annotations"):
            for path in sorted((root/folder).rglob("*")):
                if path.is_file() and not path.is_symlink() and path.resolve() != target.resolve():
                    archive.write(path, path.relative_to(root))
        for name in ("project.json", "results/preprocess_pipeline.json", "results/yolo_config.json", "results/cipher_library.json"):
            if (root/name).is_file():
                archive.write(root/name, name)


def import_bundle(source: Path, target: Path) -> None:
    """Import into an empty directory; validate all paths before extracting."""
    if target.exists() and any(target.iterdir()):
        raise ValueError("Choose an empty project directory")
    root = target.resolve()
    with zipfile.ZipFile(source) as archive:
        entries = archive.infolist()
        if sum(i.file_size for i in entries) > 4 * 1024**3:
            raise ValueError("Archive exceeds 4 GiB")
        for entry in entries:
            destination = (root/entry.filename).resolve()
            if not destination.is_relative_to(root) or '\\' in entry.filename:
                raise ValueError("Unsafe archive path")
            if entry.filename.split('/')[0] not in {"images_raw", "images_processed", "annotations", "results", "project.json"}:
                raise ValueError("Unknown project file")
        target.mkdir(parents=True, exist_ok=True)
        archive.extractall(target)
