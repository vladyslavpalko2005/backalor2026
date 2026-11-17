#!/bin/sh
set -eu
# Render mounts the persistent disk at runtime. Prepare only the owned directories.
if [ "$(id -u)" = "0" ]; then
    mkdir -p "${BACKALOR_DATA_DIR:-/var/data}/snapshots"
    chown 10001:10001 "${BACKALOR_DATA_DIR:-/var/data}" "${BACKALOR_DATA_DIR:-/var/data}/snapshots"
    exec gosu 10001:10001 "$@"
fi
exec "$@"
