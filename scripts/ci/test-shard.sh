#!/usr/bin/env bash
# ---
# summary: "Partition offline pytest coverage into deterministic core, Forge, and slow shards."
# read_when:
#   - "Changing CI test sharding, marker selection, parallelism, or coverage collection."
# ---
set -euo pipefail

# Ambient pytest options could suppress the rows the outcome baseline reads.
unset PYTEST_ADDOPTS

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

shard="${1:-}"
shard="${shard#shard=}"
jobs="${CI_TEST_JOBS:-4}"
offline='not live and not network and not model and not gpu and not postgres and not workstation'
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

# Collection-integrity mode: print this shard's node ids and run nothing.
if [[ "${CI_COLLECT_ONLY:-0}" == "1" ]]; then
  exec uv run --frozen --no-sync python -m pytest --collect-only -q \
    -p no:cacheprovider -m "$marker" "${selected[@]}"
fi

pytest_args=(-q -rsxX -n "$jobs" --dist load -m "$marker")
if [[ "${CI_COVERAGE:-0}" == "1" ]]; then
  pytest_args+=(--cov=dspx --cov=dspx_forge --cov-branch --cov-report= --cov-fail-under=0)
fi

# CLI help assertions match plain option names; Rich forces ANSI styling and an
# 80-column wrap under GITHUB_ACTIONS, which splits those names.
export NO_COLOR=1 TERM=dumb COLUMNS=200

printf '==> test shard %s (%s files; marker: %s)\n' "$shard" "${#selected[@]}" "$marker"
shard_log="$(mktemp "${TMPDIR:-/tmp}/dspx-shard-$shard.XXXXXX")"
trap 'rm -f "$shard_log"' EXIT
uv run --frozen --no-sync python -m pytest "${pytest_args[@]}" "${selected[@]}" 2>&1 | tee "$shard_log"
# A new skip, xfail or xpass must be reviewed into tests/fixtures/ci-skip-baseline.txt first.
uv run --frozen --no-sync python scripts/ci/ci_evidence_predicate.py skips "$shard_log"
