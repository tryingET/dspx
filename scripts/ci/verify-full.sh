#!/bin/sh
# summary: "Closed-startup, fail-closed full-gate dispatcher; defaults to blocked plan."
set -eu
# No ambient dotenv, Python startup, provider or command-selection variables.
script_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
exec /usr/bin/env -i PATH=/usr/bin:/bin HOME=/home/tryinget LANG=C.UTF-8 LC_ALL=C.UTF-8 \
    /usr/bin/python3 -I -S -B "$script_dir/verify_full_isolation.py" "$@"
