#!/bin/zsh
set -eu
BACKALOR_ROOT="${0:A:h}"
cd "$BACKALOR_ROOT"
BACKEND_ENV="$BACKALOR_ROOT/.venv-backend"
if [[ ! -x "$BACKEND_ENV/bin/python" ]]; then
  python3 -m venv "$BACKEND_ENV"
  "$BACKEND_ENV/bin/python" -m pip install -r requirements-backend.txt
fi
exec "$BACKEND_ENV/bin/python" -m uvicorn backend.main:create_app --factory --host 127.0.0.1 --port 8000 --no-access-log
