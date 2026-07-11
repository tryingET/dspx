#!/usr/bin/env bash
# ---
# summary: "Partition offline pytest coverage into deterministic core, Forge, and slow shards."
# read_when:
#   - "Changing CI test sharding, marker selection, parallelism, or coverage collection."
# ---
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

shard="${1:-}"
shard="${shard#shard=}"
jobs="${CI_TEST_JOBS:-4}"
offline='not live and not network and not model and not gpu and not postgres'
mapfile -t test_files < <(find tests -type f -name 'test_*.py' -print | LC_ALL=C sort)

case "$shard" in
  core-[0-3])
    shard_index="${shard#core-}"
    selected=()
    for index in "${!test_files[@]}"; do
      if (( index % 4 == shard_index )); then
        selected+=("${test_files[$index]}")
      fi
    done
    marker="not forge and not slow and $offline"
    ;;
  forge)
    selected=("${test_files[@]}")
    marker="forge and not slow and $offline"
    ;;
  slow)
    selected=("${test_files[@]}")
    marker="slow and $offline"
    ;;
  *)
    printf 'usage: %s {core-0|core-1|core-2|core-3|forge|slow}\n' "$0" >&2
    exit 2
    ;;
esac

pytest_args=(-q -n "$jobs" --dist load -m "$marker")
if [[ "${CI_COVERAGE:-0}" == "1" ]]; then
  pytest_args+=(--cov=dspx --cov=dspx_forge --cov-branch --cov-report= --cov-fail-under=0)
fi

printf '==> test shard %s (%s files; marker: %s)\n' "$shard" "${#selected[@]}" "$marker"
uv run --frozen --no-sync python -m pytest "${pytest_args[@]}" "${selected[@]}"
