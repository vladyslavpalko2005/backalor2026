"""Per-account recent local folders. Project data is never moved by this index."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from .storage import atomic_write


class ProjectRegistry:
    def __init__(self,directory,user_id):
        if not isinstance(user_id,str) or not user_id:raise ValueError('A verified account is required')
        self.path=Path(directory)/(hashlib.sha256(user_id.encode()).hexdigest()+'.json')
    def list(self):
        try:data=json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError,ValueError):return []
        if not isinstance(data,list):return []
        return [record for record in data if isinstance(record,dict) and isinstance(record.get('path'),str) and Path(record['path']).is_dir()]
    def add(self,path):
        path=Path(path).resolve()
        if not path.is_dir():raise ValueError('Project directory does not exist')
        title=path.name
        try:title=json.loads((path/'project.json').read_text(encoding='utf-8')).get('title') or title
        except (OSError,ValueError,AttributeError):pass
        records=[{'path':str(path),'title':str(title)}]+[record for record in self.list() if record['path']!=str(path)]
        atomic_write(self.path,json.dumps(records[:30],ensure_ascii=False,indent=2).encode('utf-8'))
