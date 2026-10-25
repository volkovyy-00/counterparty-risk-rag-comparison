#!/usr/bin/env bash
# Pack the Release assets that scripts/fetch_artifacts.sh downloads, from the local (untracked) files.
#
#   scripts/build_artifacts.sh [outdir]    (default: dist/)
#
# Deterministic (sorted names, fixed mtime, owner and mode, gzip -n): the same files give the same SHA256,
# so the hashes pinned in fetch_artifacts.sh can be checked against a rebuild.
set -euo pipefail
cd "$(dirname "$0")/.."
out=${1:-dist}; mkdir -p "$out"

pack() {  # pack <file> <paths...>
  local f=$1; shift
  tar --sort=name --mtime=2026-10-25T00:00:00Z --owner=0 --group=0 --numeric-owner --mode='u=rwX,go=rX' --format=gnu -cf - "$@" \
    | gzip -9n > "$out/$f"
}
pack fallback.tar.gz      demo/fallback
pack replay-cache.tar.gz  cache/chat cache/count
pack results-extra.tar.gz $(ls -d results/* | grep -vE '^results/(demo_run|spend)$')
( cd "$out" && sha256sum fallback.tar.gz replay-cache.tar.gz results-extra.tar.gz )
