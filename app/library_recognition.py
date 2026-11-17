"""Conservative local reference matching. Similarity is not a calibrated confidence."""
from __future__ import annotations
import copy
from collections import OrderedDict
from functools import lru_cache
from heapq import nsmallest
from PIL import Image, ImageOps
from .portable import decode_sample
from .digitization import crop_element, effective_type


def ink_signature(image):
    gray = ImageOps.autocontrast(image.convert('L'))
    # Blank crops have no visual evidence and must never match one another.
    if gray.getextrema()[1] - gray.getextrema()[0] < 16:
        return frozenset()
    ink = ImageOps.invert(gray).point(lambda value: 255 if value >= 128 else 0)
    bounds = ink.getbbox()
    if bounds is None: return frozenset()
    ink = ink.crop(bounds)
    ink.thumbnail((28, 28), Image.Resampling.NEAREST)
    canvas = Image.new('L', (32, 32)); canvas.paste(ink, ((32-ink.width)//2, (32-ink.height)//2))
    return frozenset((index % 32, index // 32) for index, value in enumerate(canvas.getdata()) if value >= 128)


_popcount = getattr(int,'bit_count',lambda value:bin(value).count('1'))


def packed_signature(signature):
    return sum(1 << (y*32+x) for x,y in signature)


@lru_cache(maxsize=128)
def sample_signature(png):
    return packed_signature(ink_signature(decode_sample(png)))


class LibraryMatcher:
    def __init__(self, payload):
        self.templates = []
        self._seen = set()
        self._matches = OrderedDict()
        for code, entry in payload['symbols'].items():
            for png in entry.get('samples', []): self.add('cipher_symbol', code, png)
        for sample in payload.get('readable_samples', []): self.add('readable', sample['transcription'], sample['png'])

    def add(self, kind, value, png):
        signature = sample_signature(png)
        key = (kind,value,signature)
        if signature and key not in self._seen:
            self._seen.add(key)
            self.templates.append((kind,value,signature,_popcount(signature)))

    def match(self, image, kind=''):
        signature = packed_signature(ink_signature(image))
        if not signature: return None
        cache_key = (signature,kind)
        if cache_key in self._matches:
            self._matches.move_to_end(cache_key)
            return self._matches[cache_key]
        # Normalization leaves a two-pixel border. Every ±1 shift stays inside
        # the 32×32 plane, so packed intersections equal the original set IoU.
        variants = [signature << shift if shift >= 0 else signature >> -shift
                    for dx in (-1,0,1) for dy in (-1,0,1) for shift in (dy*32+dx,)]
        query_size = _popcount(signature)
        scores = {}
        for candidate_kind,value,template,template_size in self.templates:
            if kind and candidate_kind != kind: continue
            overlaps = (_popcount(variant & template) for variant in variants)
            score = max(overlap/(query_size+template_size-overlap) for overlap in overlaps)
            key=(candidate_kind,value); scores[key]=max(score,scores.get(key,0))
        ranked=nsmallest(2,scores.items(),key=lambda entry:(-entry[1],entry[0]))
        result=None
        if ranked:
            (candidate_kind,value),score=ranked[0]
            runner_up=ranked[1][1] if len(ranked)>1 else 0
            result=(candidate_kind,value,score,score-runner_up)
        self._matches[cache_key]=result
        if len(self._matches)>256:self._matches.popitem(last=False)
        return result


def recognize_from_library(image, items, payload, threshold=.85, margin=.10):
    if not 0 < threshold <= 1 or not 0 < margin <= 1: raise ValueError('Similarity and margin must be in (0, 1]')
    matcher = LibraryMatcher(payload)
    if not matcher.templates: raise ValueError('The library has no usable samples. Add reviewed nonblank L3 examples or import a library with PNG samples.')
    result = copy.deepcopy(items); counts = {'changed': 0, 'uncertain': 0, 'skipped': 0}; changed_ids = set()
    for item in result:
        kind = effective_type(item)
        if item.level != 'L3' or item.label == 'not_symbol' or item.reviewed or (kind == 'readable' and item.transcription.strip()) or (kind == 'cipher_symbol' and item.symbol_code.strip()):
            counts['skipped'] += 1; continue
        # Existing text/code is retained; classification never overwrites content.
        if not kind and (item.transcription.strip() or item.symbol_code.strip()):
            counts['skipped'] += 1; continue
        match = matcher.match(crop_element(image, item), kind)
        if match is None or match[2] < threshold or match[3] < margin:
            counts['uncertain'] += 1; continue
        predicted_kind, value, score, _ = match
        if not kind:
            item.element_type = predicted_kind; item.type_source = 'library_similarity'; item.type_confidence = None
        if predicted_kind == 'cipher_symbol': item.symbol_code = value
        else: item.transcription = value
        item.recognition_source = 'library_similarity'
        item.recognition_confidence = None  # Template similarity must not be shown as model confidence.
        item.reviewed = False; changed_ids.add(item.id); counts['changed'] += 1
    for item in result:
        if item.transcription_ref_id in changed_ids: item.reviewed = False
    return result, counts
