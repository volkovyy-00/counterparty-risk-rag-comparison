#!/usr/bin/env bash
# Download the large artifacts that are not tracked in git, from the GitHub Release.
#
#   scripts/fetch_artifacts.sh [fallback|cache|results|all]    (default: all)
#
#   fallback  demo/fallback/*.png      screenshots of every screen, for when the browser fails on stage
#   cache     cache/chat, cache/count  LLM replay cache: LLM_CACHE=replay reproduces run A with no API key
#   results   results/graph_*, graph_ab/, taxonomy_ab/, reports   graph snapshot, resolution audit, A/B outputs
#
# Not needed for `make demo`: the page is built from results/demo_run/, which is in git.
# Public release, no token. Each file is checked against the SHA256 pinned below before it is unpacked; scripts/build_artifacts.sh rebuilds the assets.
set -euo pipefail
cd "$(dirname "$0")/.."

TAG=demo-artifacts-2026-10-25
BASE=${ARTIFACTS_BASE:-"https://github.com/volkovyy-00/counterparty-risk-rag-comparison/releases/download/$TAG"}  # or a mirror
declare -A FILE=([fallback]=fallback.tar.gz [cache]=replay-cache.tar.gz [results]=results-extra.tar.gz)
declare -A SHA=(
  [fallback]=a3e568f5828a5d8a090cd2e82c612e6677dcdda168f4c22c1a2eab39ef11666d
  [cache]=6543e75a5bfc49c6c9da68f6b8192a59a526113c3cb22f97d4e4cfd2c932920f
  [results]=7048a6d18655e5a41649c64382eccd97fb830ff75b036859c61fc4cb6bc67b35
)

what=${1:-all}
case "$what" in
  all) parts="fallback cache results" ;;
  fallback|cache|results) parts=$what ;;
  *) echo "usage: $0 [fallback|cache|results|all]" >&2; exit 2 ;;
esac

tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
for p in $parts; do
  f=${FILE[$p]}
  echo "-> $f"
  curl -fsSL --retry 3 -o "$tmp/$f" "$BASE/$f"
  echo "${SHA[$p]}  $tmp/$f" | sha256sum -c --quiet - || { echo "checksum mismatch for $f" >&2; exit 1; }
  tar xzf "$tmp/$f"   # paths inside are repo-relative (demo/fallback/..., cache/..., results/...)
done
echo "done: $parts"
