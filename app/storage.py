"""Durable atomic writes and optimistic conflict detection for local projects."""
from __future__ import annotations
import hashlib
import os
import tempfile
from pathlib import Path

ANY_REVISION = object()

class SaveConflict(RuntimeError):
    pass


def file_revision(path: Path):
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError:
        return None


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix='.'+path.name+'.', suffix='.tmp', dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        # Directory fsync is available on POSIX, but not on every filesystem/OS.
        try:
            directory = os.open(str(path.parent), os.O_RDONLY)
            try: os.fsync(directory)
            finally: os.close(directory)
        except OSError:
            pass
    finally:
        if temporary.exists(): temporary.unlink()
