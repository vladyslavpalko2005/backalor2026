"""Versioned symbol-library and settings interchange without credentials or model weights."""
from __future__ import annotations
import base64
import copy
import io
import json
import math
from pathlib import Path
from PIL import Image
from .annotations import annotation_path, load_annotations
from .digitization import crop_element, effective_type
from .project import list_raw_images
from .storage import atomic_write, file_revision, SaveConflict
from .symbol_catalog import read_catalog
from .pipeline import STEP_DEFS


def encode_sample(image):
    image = image.convert('RGB'); image.thumbnail((256, 256))
    stream = io.BytesIO(); image.save(stream, format='PNG')
    return base64.b64encode(stream.getvalue()).decode('ascii')


def decode_sample(value):
    if not isinstance(value, str) or len(value) > 1024 * 1024:
        raise ValueError('Invalid or oversized library sample')
    try:
        raw = base64.b64decode(value, validate=True)
        with Image.open(io.BytesIO(raw)) as image:
            if image.format != 'PNG' or not 1 <= image.width <= 256 or not 1 <= image.height <= 256:
                raise ValueError('Library samples must be PNG images up to 256 × 256')
            return image.convert('RGB')
    except Exception as exc:
        raise ValueError('Invalid library PNG sample') from exc


def validate_library(payload):
    if not isinstance(payload, dict) or payload.get('schema_version') != 1 or payload.get('document_type') != 'symbol_library':
        raise ValueError('Select a Backalor symbol library JSON, version 1')
    symbols = payload.get('symbols'); readable = payload.get('readable_samples', [])
    if not isinstance(symbols, dict) or len(symbols) > 10000 or not isinstance(readable, list) or len(readable) > 2000:
        raise ValueError('Invalid symbol library')
    sample_count = len(readable)
    for code, entry in symbols.items():
        if not isinstance(code, str) or not code.strip() or code != code.strip() or len(code) > 200 or not isinstance(entry, dict):
            raise ValueError('Invalid library code')
        if any(not isinstance(entry.get(key, ''), str) or len(entry.get(key, '')) > 4000 for key in ('title', 'notes')):
            raise ValueError('Invalid library description')
        samples = entry.get('samples', [])
        if not isinstance(samples, list) or len(samples) > 100:
            raise ValueError('At most 100 samples per symbol are supported')
        sample_count += len(samples)
        for sample in samples: decode_sample(sample)
    if sample_count > 10000: raise ValueError('Library has too many samples')
    for sample in readable:
        if not isinstance(sample, dict) or not isinstance(sample.get('transcription'), str) or not sample['transcription'].strip() or len(sample['transcription']) > 4000:
            raise ValueError('Readable sample requires a transcription')
        decode_sample(sample.get('png'))
    return payload


def build_symbol_library(root):
    root = Path(root); catalog = read_catalog(root)
    metadata = json.loads((root/'project.json').read_text(encoding='utf-8')) if (root/'project.json').exists() else {}
    result = {'schema_version': 1, 'document_type': 'symbol_library',
              'symbols': {code: {key: copy.deepcopy(entry.get(key, [] if key == 'samples' else '')) for key in ('title', 'notes', 'samples')} for code, entry in catalog.items()},
              'readable_samples': copy.deepcopy(metadata.get('readable_samples', []))}
    for image in list_raw_images(root):
        source = annotation_path(root, image)
        if not source.exists(): continue
        data = load_annotations(source)
        if data.image != image.name: raise ValueError('Annotation belongs to a different scan')
        with Image.open(image) as scan:
            for item in data.items:
                if item.level != 'L3' or not item.reviewed or item.label == 'not_symbol': continue
                kind = effective_type(item)
                if kind == 'cipher_symbol' and item.symbol_code.strip():
                    entry = result['symbols'].setdefault(item.symbol_code.strip(), {'title': '', 'notes': '', 'samples': []})
                    png = encode_sample(crop_element(scan, item))
                    if png not in entry['samples'] and len(entry['samples']) < 100: entry['samples'].append(png)
                elif kind == 'readable' and item.transcription.strip():
                    sample = {'png': encode_sample(crop_element(scan, item)), 'transcription': item.transcription.strip()}
                    if sample not in result['readable_samples'] and len(result['readable_samples']) < 2000: result['readable_samples'].append(sample)
    return validate_library(result)


def export_symbol_library(root, target):
    payload = build_symbol_library(root)
    atomic_write(Path(target), json.dumps(payload, ensure_ascii=False, indent=2).encode('utf-8'))
    return payload


def import_symbol_library(root, payload, expected_revision=None):
    validate_library(payload)
    root = Path(root); path = root/'project.json'; revision = file_revision(path)
    if expected_revision is not None and revision != expected_revision: raise SaveConflict('Project metadata changed; reopen the library before importing')
    original = path.read_bytes() if path.exists() else None
    metadata = json.loads(original.decode('utf-8')) if original else {}
    catalog = metadata.setdefault('symbol_catalog', {})
    read_catalog(root)  # Validate incumbent metadata before merging.
    for code, entry in payload['symbols'].items():
        if code in catalog:
            current = catalog[code]
            # Shared code means the same visual symbol. Never replace existing descriptions.
            for key in ('title', 'notes'):
                if not current.get(key): current[key] = entry.get(key, '')
            samples = current.setdefault('samples', [])
            for sample in entry.get('samples', []):
                if sample not in samples: samples.append(sample)
            if len(samples) > 100: raise ValueError(f'{code}: merged sample limit exceeded')
        else:
            catalog[code] = {key: copy.deepcopy(entry.get(key, [] if key == 'samples' else '')) for key in ('title', 'notes', 'samples')}
            catalog[code]['representative'] = None
    readable = metadata.setdefault('readable_samples', [])
    for sample in payload.get('readable_samples', []):
        if sample not in readable: readable.append(copy.deepcopy(sample))
    validate_library({'schema_version': 1, 'document_type': 'symbol_library', 'symbols': catalog, 'readable_samples': readable})
    if file_revision(path) != revision: raise SaveConflict('Project metadata changed; retry the import')
    if original is not None: atomic_write(path.with_suffix('.json.bak'), original)
    atomic_write(path, json.dumps(metadata, ensure_ascii=False, indent=2).encode('utf-8'))
    return len(payload['symbols'])


MODEL_KEYS = {'L1', 'L2', 'L3', 'conf', 'ocr_model', 'type_model', 'symbol_model', 'recognition_threshold', 'library_threshold', 'library_margin'}


def validate_settings(payload):
    if not isinstance(payload, dict) or payload.get('schema_version') != 1 or payload.get('document_type') != 'backalor_settings':
        raise ValueError('Select a Backalor settings JSON, version 1')
    pipeline = payload.get('pipeline'); models = payload.get('models')
    if not isinstance(pipeline, list) or len(pipeline) > 100 or not isinstance(models, dict) or set(models) - MODEL_KEYS:
        raise ValueError('Invalid settings structure')
    def number(value): return type(value) in (int, float) and math.isfinite(value)
    for step in pipeline:
        if not isinstance(step, dict) or step.get('step_type') not in STEP_DEFS or type(step.get('enabled')) is not bool or not isinstance(step.get('params'), dict):
            raise ValueError('Invalid preprocessing step')
        defaults = STEP_DEFS[step['step_type']]['params']
        if set(step['params']) - set(defaults): raise ValueError('Unknown preprocessing parameter')
        for key, value in step['params'].items():
            if isinstance(defaults[key], bool):
                if type(value) is not bool: raise ValueError('Invalid preprocessing flag')
            elif not number(value) or abs(value) > 100000: raise ValueError('Invalid preprocessing number')
        params = step['params']; kind = step['step_type']
        if kind == 'gamma' and params.get('gamma', 1) <= 0: raise ValueError('Gamma must be positive')
        if kind in ('brightness', 'contrast', 'sharpness') and params.get('factor', 1) < 0: raise ValueError('Factor must be nonnegative')
        if kind == 'gaussian_blur' and params.get('radius', 1) < 0: raise ValueError('Radius must be nonnegative')
        if kind == 'median_blur' and (type(params.get('size', 3)) is not int or params.get('size', 3) < 3 or params.get('size', 3) % 2 != 1): raise ValueError('Median size must be odd and at least 3')
        if kind == 'threshold' and not 0 <= params.get('threshold', 128) <= 255: raise ValueError('Threshold must be 0–255')
        if kind == 'crop':
            if any(type(params.get(k, 0)) is not int or params.get(k, 0) < 0 for k in ('left', 'top', 'right', 'bottom')): raise ValueError('Invalid crop coordinates')
            if (params.get('right', 0) and params['right'] <= params.get('left', 0)) or (params.get('bottom', 0) and params['bottom'] <= params.get('top', 0)): raise ValueError('Crop rectangle must be nonempty')
        if kind == 'resize' and any(type(params.get(k, 0)) is not int or params.get(k, 0) < 0 for k in ('width', 'height')): raise ValueError('Invalid resize dimensions')
    for key, value in models.items():
        if key == 'conf':
            if not isinstance(value, dict) or set(value) - {'L1', 'L2', 'L3'} or any(not number(v) or not 0 <= v <= 1 for v in value.values()): raise ValueError('Invalid detection thresholds')
        elif key.endswith('threshold') or key == 'library_margin':
            if not number(value) or not 0 <= value <= 1: raise ValueError('Invalid recognition threshold')
        elif not isinstance(value, str) or len(value) > 4000: raise ValueError('Invalid model path')
    return payload


def export_settings(root, target):
    root = Path(root)
    def read(name, default):
        path = root/'results'/name
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default
    payload = validate_settings({'schema_version': 1, 'document_type': 'backalor_settings',
                                 'pipeline': read('preprocess_pipeline.json', []),
                                 'models': {key: value for key, value in read('yolo_config.json', {}).items() if key in MODEL_KEYS}})
    atomic_write(Path(target), json.dumps(payload, ensure_ascii=False, indent=2).encode('utf-8'))
    return payload


def import_settings(root, payload):
    validate_settings(payload)
    # Validate everything before touching existing files; roll back on a partial write failure.
    root = Path(root)
    updates = [(root/'results'/name, value) for name, value in
               [('preprocess_pipeline.json', payload['pipeline']), ('yolo_config.json', payload['models'])]]
    originals = {path: path.read_bytes() if path.exists() else None for path, _ in updates}
    written = []
    try:
        for path, value in updates:
            if originals[path] is not None: atomic_write(path.with_suffix('.json.bak'), originals[path])
            atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2).encode('utf-8'))
            written.append(path)
    except Exception:
        for path in reversed(written):
            if originals[path] is None: path.unlink(missing_ok=True)
            else: atomic_write(path, originals[path])
        raise
