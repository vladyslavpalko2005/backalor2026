"""Non-mutating annotation commands shared by tree and bulk editor."""
from __future__ import annotations
import copy
from .digitization import effective_role, effective_type


def reference_issues(item, items):
    if item.transcription_ref_id is None:return []
    target=next((entry for entry in items if entry.id==item.transcription_ref_id),None)
    if (item.level!='L3' or effective_type(item)!='cipher_symbol' or target is None or
        target.id==item.id or target.level!='L3' or target.parent_id!=item.parent_id or
        effective_type(target)!='readable' or effective_role(target,items)!='plaintext'):
        return ['invalid_transcription_reference']
    return []


def descendant_ids(items, annotation_id):
    result={annotation_id}
    while True:
        expanded=result|{entry.id for entry in items if entry.parent_id in result}
        if expanded==result:return result
        result=expanded


def bulk_update(items, selected_ids, changes):
    if not changes or set(changes)-{'text_role','element_type','symbol_code','label'}:
        raise ValueError('Select supported properties to change')
    selected_ids=set(selected_ids)
    if not selected_ids or not selected_ids<={entry.id for entry in items}:raise ValueError('Invalid annotation selection')
    if 'text_role' in changes and changes['text_role'] not in ('','plaintext','ciphertext'):raise ValueError('Invalid text role')
    if 'element_type' in changes and changes['element_type'] not in ('','readable','cipher_symbol'):raise ValueError('Invalid element type')
    result=copy.deepcopy(items);affected=set();changed=0
    for item in result:
        if item.id not in selected_ids:continue
        if {'element_type','symbol_code'}&set(changes) and item.level!='L3':raise ValueError('Type and symbol code apply only to L3 elements')
        before=copy.deepcopy(item)
        if item.kind in ('plaintext','ciphertext'):item.text_role=item.text_role or item.kind;item.kind=''
        elif item.kind=='symbol':item.element_type=item.element_type or 'cipher_symbol';item.kind=''
        for key,value in changes.items():setattr(item,key,str(value).strip())
        if item.element_type!=before.element_type:
            item.type_confidence=None;item.type_source='manual'
            if item.element_type!='cipher_symbol':item.transcription_ref_id=None
        if item.symbol_code!=before.symbol_code:item.recognition_confidence=None;item.recognition_source='manual'
        if (effective_role(item,result),effective_type(item),item.symbol_code)!=(effective_role(before,items),effective_type(before),before.symbol_code):
            affected|=descendant_ids(result,item.id)
        if item!=before:changed+=1
    for item in result:
        if item.id in affected or item.transcription_ref_id in affected:item.reviewed=False
    return result,changed


def duplicate_subtree(items, annotation_id, size, dx=12, dy=12):
    from .annotations import AnnotationFile
    from .datasets import validate_annotations
    ids=descendant_ids(items,annotation_id)
    if not any(item.id==annotation_id for item in items):raise ValueError('Annotation does not exist')
    result=copy.deepcopy(items);next_id=max((item.id for item in items),default=0)+1
    remap={item.id:next_id+index for index,item in enumerate(item for item in items if item.id in ids)}
    for source in items:
        if source.id not in ids:continue
        item=copy.deepcopy(source);item.id=remap[source.id];item.parent_id=remap.get(source.parent_id,source.parent_id)
        item.transcription_ref_id=remap.get(source.transcription_ref_id,source.transcription_ref_id)
        x,y,w,h=item.bbox;item.bbox=[x+dx,y+dy,w,h];item.reviewed=False
        result.append(item)
    issues=validate_annotations(AnnotationFile('',result,max(remap.values())+1),size)
    if issues:raise ValueError('The duplicate would have invalid geometry or references; move the source inward first')
    return result,remap[annotation_id]
