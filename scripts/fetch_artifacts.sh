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
# Public release, no token. Each file is checked against the SHA256 pinned below before it is unpacked.
set -euo pipefail
cd "$(dirname "$0")/.."

TAG=demo-artifacts-2026-10-25
BASE="https://github.com/volkovyy-00/counterparty-risk-rag-comparison/releases/download/$TAG"
declare -A FILE=([fallback]=fallback.tar.gz [cache]=replay-cache.tar.gz [results]=results-extra.tar.gz)
declare -A SHA=(
  [fallback]=a5563f589ddc3b68f1e8706a9d99dbd0b01d3b15eaf07998d694bb079ec2063b
  [cache]=ac792fd142f9e58e3c0a24fb1e536cd9b688c9dc8bde86ba68d34c1d8376796f
  [results]=6424622bd0f2b362fcf5670f7442777e6bffcc80b218406b70b175cb08422f3f
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
