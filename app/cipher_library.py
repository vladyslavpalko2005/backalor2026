"""Traceable ciphertext exports and deterministic symbol-inventory candidate search.

Codes are exact, case-sensitive identifiers shared by the imported documents.
Coverage is compatibility evidence, never a probability of a correct key.
"""
from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path

from .annotations import annotation_path, load_annotations
from .datasets import validate_annotations
from .digitization import effective_role, effective_type, element_issues
from .project import list_raw_images
from .storage import atomic_write, file_revision, SaveConflict


def token_value(item):
    return (item.get('symbol_code', '') if item.get('element_type') == 'cipher_symbol'
            else item.get('transcription', '') if item.get('element_type') == 'readable' else '').strip()


def build_ciphertext(root):
    """L1 sections / L2 lines / L3 tokens, explicitly ordered top-to-bottom, left-to-right."""
    from PIL import Image
    pages = []
    seen_stems = set()
    for image in list_raw_images(root):
        if image.stem.casefold() in seen_stems:
            raise ValueError('Duplicate image stems; rename source images to avoid ambiguous annotations')
        seen_stems.add(image.stem.casefold())
        page = {'image': image.name, 'lines': [], 'issues': []}
        source = annotation_path(root, image)
        if not source.exists():
            page['issues'].append('missing_annotations')
            pages.append(page)
            continue
        data = load_annotations(source)
        with Image.open(image) as scan:
            page['issues'].extend(validate_annotations(data, scan.size))
        if data.image != image.name:
            page['issues'].append('annotation_image_mismatch')
        order = lambda item: (item.bbox[1], item.bbox[0], item.id)
        sections = sorted((item for item in data.items if item.level == 'L1'), key=order)
        included = set()
        for section in sections:
            lines = sorted((item for item in data.items if item.level == 'L2' and item.parent_id == section.id), key=order)
            for line in lines:
                tokens = []
                for item in sorted((item for item in data.items if item.level == 'L3' and item.parent_id == line.id), key=lambda item: (item.bbox[0], item.bbox[1], item.id)):
                    role = effective_role(item, data.items)
                    if role == 'plaintext':
                        continue
                    included.add(item.id)
                    payload = asdict(item)
                    payload.update(element_type=effective_type(item), text_role=role,
                                   issues=element_issues(item, data.items))
                    payload['value'] = token_value(payload)
                    tokens.append(payload)
                if tokens:
                    page['lines'].append({'section_id': section.id, 'line_id': line.id,
                                          'bbox': line.bbox, 'tokens': tokens})
        if any(item.level == 'L3' and effective_role(item, data.items) != 'plaintext' and item.id not in included for item in data.items):
            page['issues'].append('unpaired_elements')
        if not page['lines']:
            page['issues'].append('no_ciphertext')
        pages.append(page)
    ready = bool(pages) and all(not page['issues'] and all(not token['issues'] for line in page['lines'] for token in line['tokens']) for page in pages)
    return {'schema_version': 1, 'document_type': 'ciphertext', 'status': 'ready' if ready else 'draft',
            'reading_order': 'section_yx_line_yx_token_xy', 'pages': pages}


def export_ciphertext(root, target):
    payload = build_ciphertext(root)
    if Path(target).suffix.lower() == '.csv':
        stream = io.StringIO(newline='')
        writer = csv.writer(stream)
        writer.writerow(['image', 'section_id', 'line_id', 'position', 'annotation_id', 'value', 'reviewed', 'issues'])
        for page in payload['pages']:
            for line in page['lines']:
                for position, token in enumerate(line['tokens']):
                    writer.writerow([page['image'], line['section_id'], line['line_id'], position, token['id'], token['value'], token['reviewed'], json.dumps(page['issues'] + token['issues'], ensure_ascii=False)])
            if not page['lines']:
                writer.writerow([page['image'], '', '', '', '', '', '', json.dumps(page['issues'], ensure_ascii=False)])
        content = stream.getvalue().encode('utf-8-sig')
    else:
        content = json.dumps(payload, ensure_ascii=False, indent=2).encode('utf-8')
    atomic_write(Path(target), content)
    return payload


def validate_document(payload):
    """Accept existing key JSON exports as well as the new typed documents."""
    if not isinstance(payload, dict) or payload.get('schema_version') != 1:
        raise ValueError('Unsupported document schema')
    kind = payload.get('document_type', 'key')
    if kind not in ('key', 'ciphertext') or payload.get('status') not in ('ready', 'draft'):
        raise ValueError('Invalid document type or status')
    pages = payload.get('pages')
    if not isinstance(pages, list) or not pages:
        raise ValueError('Document must contain pages')
    def elements(items):
        if not isinstance(items, list):
            raise ValueError('Invalid element list')
        for item in items:
            if not isinstance(item, dict) or any(not isinstance(item.get(field, ''), str) for field in ('symbol_code', 'transcription', 'element_type', 'text_role')):
                raise ValueError('Invalid element')
            if type(item.get('id')) is not int or type(item.get('transcription_ref_id')) not in (int, type(None)):
                raise ValueError('Invalid element reference')
            if not isinstance(item.get('issues', []), list) or not isinstance(item.get('reviewed'), bool):
                raise ValueError('Invalid review state')
    for page in pages:
        if not isinstance(page, dict) or not isinstance(page.get('image'), str) or not isinstance(page.get('issues'), list):
            raise ValueError('Invalid page')
        groups = page.get('pairs' if kind == 'key' else 'lines')
        if not isinstance(groups, list):
            raise ValueError('Invalid page structure')
        for group in groups:
            if not isinstance(group, dict):
                raise ValueError('Invalid group')
            if kind == 'key':
                if group.get('status') not in ('ready', 'draft'):
                    raise ValueError('Invalid pair status')
                elements(group.get('plaintext')); elements(group.get('ciphertext'))
            else:
                elements(group.get('tokens'))
    return kind


def key_mapping(key):
    mapping = defaultdict(set)
    for page in key['pages']:
        if page['issues']:
            continue
        for pair in page['pairs']:
            if pair['status'] != 'ready':
                continue
            plains = {item['id']: item['transcription'].strip() for item in pair['plaintext']
                      if item['reviewed'] and not item.get('issues') and item.get('transcription', '').strip()}
            for item in pair['ciphertext']:
                if not item['reviewed'] or item.get('issues'):
                    continue
                # Several ciphertext entries in a pair are homophones. Several
                # plaintext entries require an explicit reference, not a guess.
                target = plains.get(item.get('transcription_ref_id'))
                if item.get('transcription_ref_id') is None and len(plains) == 1:
                    target = next(iter(plains.values()))
                value = token_value(item)
                if target and value:
                    mapping[value].add(target)
    return {code: sorted(values) for code, values in mapping.items()}


def compare_documents(key, ciphertext, reviewed_only=True):
    mapping = key_mapping(key)
    counts = Counter()
    preview = []
    excluded = 0
    for page in ciphertext['pages']:
        for line in page['lines']:
            decoded = []
            for token in line['tokens']:
                value = token_value(token)
                valid = not page['issues'] and not token.get('issues') and token.get('text_role') == 'ciphertext' and token['reviewed']
                if not value or (reviewed_only and not valid):
                    excluded += 1
                    decoded.append('⟨?⟩')
                    continue
                counts[value] += 1
                options = mapping.get(value, [])
                decoded.append(options[0] if len(options) == 1 else '[' + ' / '.join(options) + ']' if options else '⟨' + value + '⟩')
            preview.append({'image': page['image'], 'line_id': line.get('line_id'), 'text': ' '.join(decoded)})
    total = sum(counts.values())
    matched = sum(count for code, count in counts.items() if code in mapping)
    return {'coverage': matched / total if total else 0, 'matched': matched, 'total': total,
            'distinct_matched': len(set(counts) & set(mapping)), 'distinct_total': len(counts),
            'unknown': sorted(set(counts) - set(mapping)), 'ambiguous': {code: mapping[code] for code in counts if len(mapping.get(code, [])) > 1},
            'excluded': excluded, 'preview': preview}


def search_library(query, entries):
    kind = validate_document(query)
    results = []
    for entry in entries:
        other = entry['document']
        if validate_document(other) == kind:
            continue
        key, text = (query, other) if kind == 'key' else (other, query)
        result = compare_documents(key, text)
        result.update(id=entry['id'], name=entry['name'], status=other['status'])
        results.append(result)
    return sorted(results, key=lambda row: (-row['coverage'], -row['distinct_matched'], -row['matched'], row['name'], row['id']))


class CipherLibrary:
    """Project-local snapshots, portable with the existing results/ ZIP export."""
    def __init__(self, root):
        self.path = Path(root) / 'results' / 'cipher_library.json'
        self.revision = file_revision(self.path)
        payload = json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {'schema_version': 1, 'entries': []}
        if payload.get('schema_version') != 1 or not isinstance(payload.get('entries'), list):
            raise ValueError('Invalid cipher library')
        self.entries = payload['entries']
        seen = set()
        for entry in self.entries:
            if not isinstance(entry, dict) or not isinstance(entry.get('id'), str) or not isinstance(entry.get('name'), str) or entry['id'] in seen:
                raise ValueError('Invalid library entry')
            validate_document(entry.get('document'))
            seen.add(entry['id'])

    def add(self, name, document):
        validate_document(document)
        if not name.strip():
            raise ValueError('Document name is required')
        document = copy.deepcopy(document)
        document.setdefault('document_type', 'key')
        identifier = hashlib.sha256(json.dumps(document, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()
        if any(entry['id'] == identifier for entry in self.entries):
            return identifier
        entries = self.entries + [{'id': identifier, 'name': name.strip(), 'document': document}]
        self._save(entries)
        return identifier

    def _save(self, entries):
        if file_revision(self.path) != self.revision:
            raise SaveConflict('Library changed in another window; reopen it before saving')
        atomic_write(self.path, json.dumps({'schema_version': 1, 'entries': entries}, ensure_ascii=False, indent=2).encode('utf-8'))
        self.entries = entries
        self.revision = file_revision(self.path)
