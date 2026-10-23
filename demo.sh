#!/usr/bin/env sh
# Same as `make demo` for machines without make. ./demo.sh --live enables the live step.
set -e
cd "$(dirname "$0")"
PY="${PY:-python}"
[ -f results/demo_run/manifest.json ] || { echo "results/demo_run/ is missing: nothing to show (see README)"; exit 1; }
"$PY" build_demo.py
exec "$PY" serve.py "$@"
