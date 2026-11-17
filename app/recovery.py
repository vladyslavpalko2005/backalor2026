"""Crash-recovery drafts are separate from the last committed annotation file."""
from __future__ import annotations
import json
from pathlib import Path
from .annotations import AnnotationFile, annotations_payload, annotations_from_payload
from .storage import atomic_write


def draft_path(root: Path, image: Path) -> Path:
    return root/'.recovery'/f'{image.stem}.json'


def save_draft(root: Path, image: Path, annotations: AnnotationFile, revision, pending=None):
    payload = {'draft_version':1, 'image':image.name, 'base_revision':revision,
               'annotations':annotations_payload(annotations), 'pending':pending}
    atomic_write(draft_path(root,image),json.dumps(payload,ensure_ascii=False,indent=2).encode('utf-8'))


def read_draft(root: Path, image: Path):
    path = draft_path(root,image)
    if not path.exists(): return None
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('draft_version') != 1 or data.get('image') != image.name:
        raise ValueError('Unsupported recovery draft')
    data['data'] = annotations_from_payload(data['annotations'])
    return data


def clear_draft(root: Path, image: Path):
    draft_path(root,image).unlink(missing_ok=True)
