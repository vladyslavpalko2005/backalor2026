"""Semantic routing and structured key export; geometry and roles are never guessed."""
from __future__ import annotations
import copy
import csv
import io
import json
import math
from dataclasses import asdict
from pathlib import Path
from .annotations import annotation_path, load_annotations
from .datasets import validate_annotations
from .project import list_raw_images
from .storage import atomic_write

ROLES = ('plaintext', 'ciphertext')
TYPES = ('readable', 'cipher_symbol')


def effective_role(item, items):
    indexed = {entry.id: entry for entry in items}
    seen = set()
    while item is not None and item.id not in seen:
        seen.add(item.id)
        if item.text_role:
            return item.text_role if item.text_role in ROLES else ''
        if item.kind in ROLES:
            return item.kind
        item = indexed.get(item.parent_id)
    return ''


def effective_type(item):
    # A legacy plaintext/ciphertext label says nothing about visual readability.
    return item.element_type or ('cipher_symbol' if item.kind == 'symbol' else '')


def crop_element(image, item):
    if len(item.bbox) != 4:
        raise ValueError(f'#{item.id}: invalid bounding box')
    x, y, w, h = item.bbox
    if min(x, y) < 0 or min(w, h) <= 0 or x+w > image.width or y+h > image.height:
        raise ValueError(f'#{item.id}: bounding box outside image')
    return image.crop((x, y, x+w, y+h)).convert('RGB')


class LocalClassifier:
    """Load once per operation. Only explicitly selected local classification weights."""
    def __init__(self, path, expected_types=False):
        path = Path(path)
        if not path.is_file() or path.suffix.lower() != '.pt':
            raise ValueError('Select existing local classification weights (.pt)')
        from ultralytics import YOLO
        self.model = YOLO(str(path))
        if self.model.task != 'classify':
            raise ValueError('Classification weights are required; detection weights cannot classify element types')
        names = set(self.model.names.values())
        if expected_types and names != set(TYPES):
            raise ValueError('Element model classes must be exactly readable and cipher_symbol')

    def __call__(self, image):
        results = self.model.predict(source=image, verbose=False)
        if not results or results[0].probs is None:
            raise ValueError('The model did not return class probabilities')
        result = results[0]
        return result.names[result.probs.top1], float(result.probs.top1conf)


def classify_elements(image, items, classifier, threshold=.8):
    result = copy.deepcopy(items)
    counts = {'changed': 0, 'uncertain': 0, 'skipped': 0}
    for item in result:
        if item.level != 'L3':
            continue
        if effective_type(item):
            counts['skipped'] += 1
            continue
        label, score = classifier(crop_element(image, item))
        if label not in TYPES or not math.isfinite(score) or not 0 <= score <= 1:
            raise ValueError('Invalid type classification result')
        if score < threshold:
            counts['uncertain'] += 1
            continue
        item.element_type = label
        item.type_confidence = score
        item.type_source = 'model'
        item.reviewed = False
        counts['changed'] += 1
    return result, counts


def recognize_elements(image, items, text_recognizer=None, symbol_classifier=None, threshold=.8, allowed_codes=None):
    result = copy.deepcopy(items)
    changed_ids=set()
    counts = {'changed': 0, 'uncertain': 0, 'skipped': 0}
    for item in result:
        if item.level != 'L3':
            continue
        kind = effective_type(item)
        if kind == 'readable' and not item.transcription.strip() and text_recognizer:
            text = str(text_recognizer(crop_element(image, item))).strip()
            if not text:
                counts['uncertain'] += 1
                continue
            item.transcription = text
            item.recognition_confidence = None  # TrOCR text alone is not a calibrated score.
            item.recognition_source = 'trocr'
        elif kind == 'cipher_symbol' and not item.symbol_code.strip() and symbol_classifier:
            code, score = symbol_classifier(crop_element(image, item))
            if not isinstance(code, str) or not code.strip() or not math.isfinite(score) or not 0 <= score <= 1:
                raise ValueError('Invalid symbol identification result')
            if score < threshold or (allowed_codes is not None and code.strip() not in allowed_codes):
                counts['uncertain'] += 1
                continue
            item.symbol_code = code.strip()
            item.recognition_confidence = score
            item.recognition_source = 'symbol_model'
        else:
            counts['skipped'] += 1
            continue
        item.reviewed = False
        changed_ids.add(item.id)
        counts['changed'] += 1
    for item in result:
        if item.transcription_ref_id in changed_ids:item.reviewed=False
    return result, counts


def element_issues(item, items):
    issues = []
    from .annotation_ops import reference_issues
    issues.extend(reference_issues(item,items))
    if not effective_role(item, items): issues.append('missing_role')
    kind = effective_type(item)
    if kind not in TYPES: issues.append('missing_type')
    elif kind == 'readable' and not item.transcription.strip(): issues.append('missing_transcription')
    elif kind == 'cipher_symbol' and not item.symbol_code.strip(): issues.append('missing_symbol_code')
    if not item.reviewed: issues.append('needs_review')
    return issues


def structured_page(annotation, size):
    issues = validate_annotations(annotation, size)
    items = annotation.items
    elements = [item for item in items if item.level == 'L3']
    pairs = []
    for pair in (item for item in items if item.level == 'L2'):
        entry = {'id': pair.id, 'section_id': pair.parent_id, 'bbox': pair.bbox,
                 'plaintext': [], 'ciphertext': [], 'unassigned': [], 'issues': []}
        for item in sorted((item for item in elements if item.parent_id == pair.id), key=lambda item:(item.bbox[1],item.bbox[0],item.id)):
            role = effective_role(item, items)
            payload = asdict(item)
            payload.update(text_role=role, element_type=effective_type(item), issues=element_issues(item, items))
            if item.transcription_ref_id is not None and not reference_issues_for_export(item,items):
                target=next(entry for entry in items if entry.id==item.transcription_ref_id)
                payload['linked_transcription']=target.transcription
            entry[role if role in ROLES else 'unassigned'].append(payload)
            if payload['issues']: entry['issues'].append(f'#{item.id}: '+', '.join(payload['issues']))
        for role in ROLES:
            if not entry[role]: entry['issues'].append('missing_'+role)
        entry['status'] = 'ready' if not issues and not entry['issues'] else 'draft'
        pairs.append(entry)
    pair_ids = {pair['id'] for pair in pairs}
    orphans = [asdict(item) for item in elements if item.parent_id not in pair_ids]
    if not pairs: issues.append('no_pairs')
    return {'image': annotation.image, 'size': list(size), 'issues': issues, 'pairs': pairs, 'unpaired_elements': orphans}


def reference_issues_for_export(item,items):
    from .annotation_ops import reference_issues
    return reference_issues(item,items)


def build_key(root):
    from PIL import Image
    pages = []
    for path in list_raw_images(root):
        source = annotation_path(root, path)
        with Image.open(path) as image:
            if source.exists():
                annotation=load_annotations(source)
                page=structured_page(annotation,image.size)
                if annotation.image!=path.name:
                    page['issues'].append('annotation_image_mismatch')
                    for pair in page['pairs']:pair['status']='draft'
                pages.append(page)
            else:pages.append({'image':path.name,'size':list(image.size),'issues':['missing_annotations'], 'pairs':[], 'unpaired_elements':[]})
    ready = bool(pages) and all(not page['issues'] and not page['unpaired_elements'] and
                               all(pair['status'] == 'ready' for pair in page['pairs']) for page in pages)
    from .symbol_catalog import read_catalog
    return {'schema_version': 1, 'status': 'ready' if ready else 'draft', 'pages': pages,
            'symbol_catalog':read_catalog(root)}


def export_key(root, target):
    payload = build_key(root)
    if Path(target).suffix.lower() == '.csv':
        stream = io.StringIO(newline='')
        writer = csv.writer(stream)
        writer.writerow(['image', 'section_id', 'pair_id', 'status', 'plaintext', 'ciphertext', 'unassigned', 'issues'])
        for page in payload['pages']:
            for pair in page['pairs']:
                writer.writerow([page['image'],pair['section_id'],pair['id'],pair['status'],
                    *[json.dumps(pair[key],ensure_ascii=False) for key in ('plaintext','ciphertext','unassigned')],
                    json.dumps(page['issues']+pair['issues'],ensure_ascii=False)])
            for item in page['unpaired_elements']:
                writer.writerow([page['image'],'',item['parent_id'],'draft','[]','[]',json.dumps([item],ensure_ascii=False),'unpaired_element'])
            if not page['pairs'] and not page['unpaired_elements']:
                writer.writerow([page['image'],'','','draft','[]','[]','[]',json.dumps(page['issues'],ensure_ascii=False)])
        content = stream.getvalue().encode('utf-8-sig')
    else:
        content = json.dumps(payload,ensure_ascii=False,indent=2).encode('utf-8')
    atomic_write(Path(target),content)
    return payload


def export_classification_dataset(root, target, task='types'):
    """Reviewed crops, document-isolated splits, no mutation of source annotations."""
    import re
    import shutil
    import tempfile
    from PIL import Image
    from .yolo_export import dataset_split
    if task not in ('types','symbols'): raise ValueError('Unknown classification task')
    target = Path(target)
    if target.exists() and any(target.iterdir()): raise ValueError('Choose an empty dataset directory')
    records = []
    seen_stems=set()
    for image in list_raw_images(root):
        if image.stem.casefold() in seen_stems:raise ValueError('Duplicate image stems; rename source images to avoid ambiguous annotations')
        seen_stems.add(image.stem.casefold())
        path = annotation_path(root,image)
        if not path.exists(): continue
        annotation = load_annotations(path)
        if annotation.image!=image.name:raise ValueError(f'{image.name}: annotation belongs to a different image')
        with Image.open(image) as scan:
            issues = validate_annotations(annotation,scan.size)
        if issues: raise ValueError(f'{image.name}: fix annotation geometry before exporting')
        for item in annotation.items:
            if item.level != 'L3' or not item.reviewed: continue
            kind = effective_type(item)
            label = kind if task == 'types' else item.symbol_code.strip() if kind == 'cipher_symbol' else ''
            if task == 'types' and label not in TYPES: continue
            if not label: continue
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',label):
                raise ValueError('Use portable symbol codes such as S001 (letters, digits, underscore, hyphen)')
            records.append((image,item,label))
    if not records: raise ValueError('No reviewed L3 examples for this task')
    metadata = root/'project.json'
    groups = json.loads(metadata.read_text()).get('image_groups',{}) if metadata.exists() else {}
    split = dataset_split(sorted({path.name for path,_,_ in records}),groups=groups)
    classes = sorted({label for _,_,label in records})
    if len(classes) < 2: raise ValueError('At least two classes are required')
    for subset,names in split.items():
        if {label for image,_,label in records if image.name in names} != set(classes):
            raise ValueError(f'{subset}: missing classes; annotate more independent documents')
    target.parent.mkdir(parents=True,exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.classification-',dir=target.parent))
    manifest = []
    try:
        for index,(image,item,label) in enumerate(records):
            subset = next(key for key,names in split.items() if image.name in names)
            relative = Path(subset)/label/f'{index:07d}.png'
            destination = staging/relative;destination.parent.mkdir(parents=True,exist_ok=True)
            with Image.open(image) as scan: crop_element(scan,item).save(destination)
            manifest.append({'file':relative.as_posix(),'image':image.name,'id':item.id,
                             'document':groups.get(image.name,image.name),'class':label})
        (staging/'manifest.json').write_text(json.dumps({'task':task,'classes':classes,'split':split,'samples':manifest},ensure_ascii=False,indent=2))
        if target.exists(): target.rmdir()
        staging.rename(target)
    finally:
        if staging.exists(): shutil.rmtree(staging)
    return len(records)
