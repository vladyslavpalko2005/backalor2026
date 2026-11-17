"""Read only the public API origin; remote clients do not need backend dependencies."""
from pathlib import Path
import os
import re
from .api_client import normalize_server_url


def configured_api_url(repo_root, environment=None):
    environment=os.environ if environment is None else environment
    if 'BACKALOR_API_URL' in environment:
        value=environment['BACKALOR_API_URL'].strip()
        return normalize_server_url(value) if value else None
    value=''
    if not value:
        path=Path(repo_root)/'.env'
        if path.is_file():
            for line in path.read_text(encoding='utf-8').splitlines():
                match=re.fullmatch(r"\s*(?:export\s+)?BACKALOR_API_URL\s*=\s*(?:'([^']*)'|\"([^\"]*)\"|([^\s#]*))\s*(?:#.*)?",line)
                if match:value=next((part for part in match.groups() if part is not None),'').strip()
    return normalize_server_url(value) if value else None
