"""Keep Python and native fault tracebacks after a desktop crash."""
from __future__ import annotations
import faulthandler
import sys
import traceback
from datetime import datetime
from pathlib import Path

_fault_stream = None


def install_diagnostics(root: Path):
    global _fault_stream
    destination = root/'results'/'application_crash.log'
    try:
        destination.parent.mkdir(parents=True,exist_ok=True)
        if destination.exists() and destination.stat().st_size > 3*1024*1024:
            destination.replace(destination.with_suffix('.log.previous'))
        _fault_stream = destination.open('a',encoding='utf-8',buffering=1)
        _fault_stream.write(f'\nApplication start: {datetime.now().astimezone().isoformat()}\n')
        _fault_stream.flush()
        faulthandler.enable(file=_fault_stream,all_threads=True)
    except OSError:
        faulthandler.enable()
        return
    previous_hook = sys.excepthook
    def exception_hook(exc_type,exc_value,exc_traceback):
        try:
            traceback.print_exception(exc_type,exc_value,exc_traceback,file=_fault_stream)
            _fault_stream.flush()
        except OSError:
            pass
        previous_hook(exc_type,exc_value,exc_traceback)
    sys.excepthook = exception_hook
