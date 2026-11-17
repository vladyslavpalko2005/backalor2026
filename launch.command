#!/bin/zsh
set -eu
PROJECT_ROOT="${0:A:h}"
cd "$PROJECT_ROOT"
APP_ENV="$PROJECT_ROOT/.venv-desktop"
if [[ ! -x "$APP_ENV/bin/python" ]]; then
  python3 -m venv "$APP_ENV"
  "$APP_ENV/bin/python" -m pip install -r "$PROJECT_ROOT/requirements.txt"
fi
if ! "$APP_ENV/bin/python" -c 'import keyring' >/dev/null 2>&1; then
  "$APP_ENV/bin/python" -m pip install -r "$PROJECT_ROOT/requirements.txt"
fi
# A remote desktop client never installs or starts the backend or a local database.
REMOTE_API="$("$APP_ENV/bin/python" -c 'from pathlib import Path; from app.client_config import configured_api_url; print(configured_api_url(Path.cwd()) or "")')"
if [[ -n "$REMOTE_API" ]]; then
  exec "$APP_ENV/bin/python" -m app.main --project "$PROJECT_ROOT" --server "$REMOTE_API"
fi
if [[ "${BACKALOR_LOCAL_DEV:-0}" != "1" ]]; then
  # Show cloud setup in the application; do not silently create a local database.
  exec "$APP_ENV/bin/python" -m app.main --project "$PROJECT_ROOT"
fi
BACKEND_ENV="$PROJECT_ROOT/.venv-backend"
if [[ ! -x "$BACKEND_ENV/bin/python" ]]; then
  python3 -m venv "$BACKEND_ENV"
  "$BACKEND_ENV/bin/python" -m pip install -r "$PROJECT_ROOT/requirements-backend.txt"
fi
if ! "$BACKEND_ENV/bin/python" -c 'import psycopg' >/dev/null 2>&1; then
  "$BACKEND_ENV/bin/python" -m pip install -r "$PROJECT_ROOT/requirements-backend.txt"
fi
exec "$APP_ENV/bin/python" -m app.main --project "$PROJECT_ROOT" --local-backend
