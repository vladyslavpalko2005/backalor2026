"""Project-local canonical symbol descriptions and occurrence index."""
from __future__ import annotations
import json
from pathlib import Path
from .annotations import annotation_path,load_annotations
from .digitization import effective_type
from .project import list_raw_images
from .storage import atomic_write,file_revision,SaveConflict


def read_catalog(root):
    path=Path(root)/'project.json'
    data=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    catalog=data.get('symbol_catalog',{})
    if not isinstance(catalog,dict):raise ValueError('Invalid symbol catalog')
    for code,entry in catalog.items():
        if not code.strip() or len(code)>200 or not isinstance(entry,dict):raise ValueError('Invalid symbol catalog entry')
        if any(not isinstance(entry.get(key,''),str) for key in ('title','notes')):raise ValueError('Invalid symbol description')
        rep=entry.get('representative')
        if rep is not None and (not isinstance(rep,dict) or not isinstance(rep.get('image'),str) or not isinstance(rep.get('annotation_id'),int)):
            raise ValueError('Invalid representative reference')
    return catalog


def update_symbol(root,code,title='',notes='',representative=None,delete=False):
    code=code.strip()
    if not code or len(code)>200:raise ValueError('Symbol code must contain 1–200 characters')
    root=Path(root);path=root/'project.json';revision=file_revision(path)
    original=path.read_bytes() if path.exists() else None
    metadata=json.loads(original.decode('utf-8')) if original is not None else {}
    catalog=metadata.setdefault('symbol_catalog',{})
    if not isinstance(catalog,dict):raise ValueError('Invalid symbol catalog')
    if delete:
        samples=catalog.get(code,{}).get('samples',[])
        if samples:catalog[code]={'title':'','notes':'','representative':None,'samples':samples}
        else:catalog.pop(code,None)
    else:
        if representative is not None:
            image=representative.get('image','');annotation_id=representative.get('annotation_id')
            if Path(image).name!=image or image not in {entry.name for entry in list_raw_images(root)}:raise ValueError('Invalid representative image')
            annotations=load_annotations(annotation_path(root,root/'images_raw'/image))
            if not any(item.id==annotation_id and item.level=='L3' and effective_type(item)=='cipher_symbol' and item.symbol_code==code for item in annotations.items):
                raise ValueError('Representative must be an occurrence of this symbol')
        catalog[code]={**catalog.get(code,{}),'title':title.strip(),'notes':notes.strip(),'representative':representative}
    if file_revision(path)!=revision:raise SaveConflict('Project metadata changed; refresh the catalog before saving')
    if original is not None:atomic_write(path.with_suffix('.json.bak'),original)
    atomic_write(path,json.dumps(metadata,ensure_ascii=False,indent=2).encode('utf-8'))
    return catalog


def occurrence_index(root):
    catalog=read_catalog(root);occurrences={code:[] for code in catalog};failures=[]
    for image in list_raw_images(root):
        path=annotation_path(root,image)
        if not path.exists():continue
        try:
            data=load_annotations(path)
            if data.image!=image.name:raise ValueError('Annotation belongs to a different scan')
            for item in data.items:
                if item.level!='L3' or effective_type(item)!='cipher_symbol':continue
                occurrences.setdefault(item.symbol_code,[]).append({'image':image.name,'annotation_id':item.id,
                    'bbox':item.bbox,'transcription':item.transcription,'reviewed':item.reviewed})
        except Exception as exc:failures.append(f'{image.name}: {exc}')
    return {'catalog':catalog,'occurrences':occurrences,'failures':failures}
