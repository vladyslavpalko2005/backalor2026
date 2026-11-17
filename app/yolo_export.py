from __future__ import annotations

import json
import random
import shutil
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import List
from PIL import Image
from .annotations import AnnotationItem, annotation_path, load_annotations
from .project import list_raw_images

LEVELS = ["L1", "L2", "L3"]

@dataclass
class ExportResult:
    images: int
    labels: int


def dataset_split(names: List[str], seed: int = 42, groups=None) -> dict:
    groups = groups or {}
    grouped = {}
    for name in sorted(names):
        grouped.setdefault(groups.get(name, name), []).append(name)
    documents = sorted(grouped)
    random.Random(seed).shuffle(documents)
    if len(documents) < 3:
        raise ValueError("At least three annotated documents are required for independent train/val/test splits")
    held_out = max(1, round(len(documents)*0.15))
    partitions = {"train": documents[held_out*2:], "val": documents[:held_out], "test": documents[held_out:held_out*2]}
    return {subset: [name for document in entries for name in grouped[document]] for subset, entries in partitions.items()}


def prepare_dataset(root: Path, levels=LEVELS):
    """Validate before touching any existing export. Geometry is never repaired silently."""
    from .datasets import validate_annotations
    records = []
    issues = []
    source_stems = set()
    for path in list_raw_images(root):
        source = annotation_path(root, path)
        if not source.exists():
            continue
        if path.stem.casefold() in source_stems:
            raise ValueError(f"Ambiguous annotation name: {path.name}. Source images must have unique names without extensions.")
        source_stems.add(path.stem.casefold())
        annotation = load_annotations(source)
        with Image.open(path) as image:
            size = image.size
        if levels == ["L1"]:
            selected = [item for item in annotation.items if item.level == "L1"]
            _items_to_yolo(selected, *size)
        else:
            issues.extend(f"{path.name}: {issue}" for issue in validate_annotations(annotation, size))
        records.append((path, annotation, size))
    if issues:
        details = "\n".join(issues[:20])
        raise ValueError(f"Fix annotation hierarchy before exporting cascade crops ({len(issues)} issues):\n{details}")
    metadata_path = root / "project.json"
    metadata = json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
    groups = metadata.get("image_groups", {})
    split = dataset_split([path.name for path, _, _ in records], groups=groups)
    return records, split, groups


def export_yolo_dataset(root: Path, level: str, use_processed: bool = False, prepared=None) -> ExportResult:
    if level not in LEVELS:
        raise ValueError(f"Unknown level: {level}")
    if use_processed:
        raise ValueError("Annotations use original-image coordinates. Export originals to preserve geometry.")
    records, split, groups = prepared or prepare_dataset(root, [level])
    indexed = {path.name: (path, annotation, size) for path, annotation, size in records}
    out_root = root / "results" / "yolo" / level
    out_root.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out_root.parent) as temporary:
        staging = Path(temporary) / level
        staging.mkdir()
        count = 0
        manifest = []
        for subset, names in split.items():
            image_dir = staging / "images" / subset
            label_dir = staging / "labels" / subset
            image_dir.mkdir(parents=True)
            label_dir.mkdir(parents=True)
            subset_count = 0
            for name in names:
                path, annotation, size = indexed[name]
                positive = [i for i in annotation.items if i.level == level and i.label != "not_symbol"]
                if level == "L1":
                    samples = [(None, [0, 0, *size], positive)]
                else:
                    parent_level = {"L2": "L1", "L3": "L2"}[level]
                    samples = [(parent.id, parent.bbox, [i for i in positive if i.parent_id == parent.id])
                               for parent in annotation.items if parent.level == parent_level]
                with Image.open(path) as image:
                    for parent_id, crop_box, items in samples:
                        x, y, w, h = crop_box
                        sample_name = path.name if parent_id is None else f"{path.stem}__{parent_level}_{parent_id}.png"
                        local = [replace(item, bbox=[item.bbox[0]-x, item.bbox[1]-y, *item.bbox[2:]]) for item in items]
                        lines = _items_to_yolo(local, w, h)
                        (label_dir/f"{Path(sample_name).stem}.txt").write_text("\n".join(lines), encoding="utf-8")
                        if parent_id is None:
                            shutil.copy2(path, image_dir/sample_name)
                        else:
                            image.crop((x, y, x+w, y+h)).convert("RGB").save(image_dir/sample_name)
                        manifest.append({"sample": f"images/{subset}/{sample_name}", "source_image": name,
                                         "document": groups.get(name, name), "parent_id": parent_id,
                                         "crop_bbox": crop_box, "object_ids": [i.id for i in items]})
                        count += 1
                        subset_count += 1
            if not subset_count:
                raise ValueError(f"{level}: {subset} has no crops. Annotate parent regions in each document partition.")
        yaml = [f"path: {json.dumps(out_root.resolve().as_posix(), ensure_ascii=False)}",
                "train: images/train", "val: images/val", "test: images/test", "names:", f"  0: {level}"]
        (staging/"data.yaml").write_text("\n".join(yaml)+"\n", encoding="utf-8")
        (staging/"split.json").write_text(json.dumps({"seed": 42, **split}, indent=2), encoding="utf-8")
        (staging/"manifest.json").write_text(json.dumps({"export_version": 2, "geometry_mode": "cascade_v1",
            "level": level, "input": {"L1":"page", "L2":"L1_crop", "L3":"L2_crop"}[level],
            "samples": manifest}, indent=2, ensure_ascii=False), encoding="utf-8")
        backup = out_root.with_name(f"{level}.previous")
        if backup.exists():
            shutil.rmtree(backup)
        if out_root.exists():
            out_root.rename(backup)
        try:
            shutil.move(str(staging), str(out_root))
        except Exception:
            if backup.exists() and not out_root.exists():
                backup.rename(out_root)
            raise
    return ExportResult(images=count, labels=count)


def export_all_levels(root: Path):
    prepared = prepare_dataset(root)
    # Ensure every level has parents in every partition before replacing any export.
    records, split, _ = prepared
    indexed = {path.name: annotation for path, annotation, _ in records}
    for level, parent in (("L2", "L1"), ("L3", "L2")):
        for subset, names in split.items():
            if not any(i.level == parent for name in names for i in indexed[name].items):
                raise ValueError(f"{level}: {subset} has no {parent} parent regions")
    return [(level, export_yolo_dataset(root, level, prepared=prepared)) for level in LEVELS]


def validate_cascade_dataset(root: Path, level: str):
    target = root / "results" / "yolo" / level
    manifest_path = target / "manifest.json"
    if not manifest_path.exists():
        raise ValueError("Export YOLO again: the old dataset does not contain cascade crops")
    manifest = json.loads(manifest_path.read_text())
    expected = {"L1":"page", "L2":"L1_crop", "L3":"L2_crop"}[level]
    if manifest.get("geometry_mode") != "cascade_v1" or manifest.get("level") != level or manifest.get("input") != expected:
        raise ValueError("Dataset geometry does not match cascade inference. Export YOLO again.")
    split = json.loads((target/"split.json").read_text())
    partitions = [set(split.get(key, [])) for key in ("train", "val", "test")]
    if not all(partitions) or any(partitions[i] & partitions[j] for i in range(3) for j in range(i+1, 3)):
        raise ValueError("Dataset partitions overlap or are empty")
    yaml_lines = (target/'data.yaml').read_text().splitlines()
    for subset in ('train', 'val', 'test'):
        entries = [line.strip() for line in yaml_lines if line.strip().startswith(subset+':')]
        if entries != [f'{subset}: images/{subset}']:
            raise ValueError("Dataset YAML does not match the independent partitions. Export YOLO again.")
    documents = {}
    for sample in manifest.get('samples', []):
        subset = Path(sample['sample']).parts[1]
        if subset not in ('train', 'val', 'test') or sample['source_image'] not in split[subset]:
            raise ValueError("Crop provenance does not match the source partition")
        previous = documents.setdefault(sample['document'], subset)
        if previous != subset:
            raise ValueError("Pages from the same document occur in different partitions")
    return manifest


def _items_to_yolo(items: List[AnnotationItem], img_w: int, img_h: int) -> List[str]:
    if min(img_w, img_h) <= 0:
        raise ValueError("Invalid image dimensions")
    lines = []
    for item in items:
        x, y, w, h = item.bbox
        if x < 0 or y < 0 or min(w, h) <= 0 or x+w > img_w or y+h > img_h:
            raise ValueError(f"Annotation #{item.id} is outside the source image")
        lines.append(f"0 {(x+w/2)/img_w:.6f} {(y+h/2)/img_h:.6f} {w/img_w:.6f} {h/img_h:.6f}")
    return lines
