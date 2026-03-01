#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-latest}"
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="${FORGE_CORE_COMPAT_DIST:-$(mktemp -d)}"
KEEP_DIST="${FORGE_CORE_COMPAT_KEEP_DIST:-0}"
WORKTREE_DIR=""

cleanup() {
  if [ -n "$WORKTREE_DIR" ]; then
    git -C "$ROOT" worktree remove --force "$WORKTREE_DIR" >/dev/null 2>&1 || true
  fi
  if [ "$KEEP_DIST" != "1" ]; then
    rm -rf "$DIST_DIR"
  fi
}
trap cleanup EXIT

if [ "$MODE" != "latest" ] && [ "$MODE" != "min" ]; then
  echo "usage: $0 [latest|min]" >&2
  exit 2
fi

cd "$ROOT"

CORE_BUILD_ROOT="$ROOT"
if [ "$MODE" = "min" ]; then
  MIN_CORE_VERSION="$(python - <<'PY'
import re
import tomllib
from pathlib import Path

pyproject = tomllib.loads(Path('apps/forge/pyproject.toml').read_text(encoding='utf-8'))
deps = pyproject.get('project', {}).get('dependencies', [])
entry = next((d for d in deps if isinstance(d, str) and d.startswith('dspx-core')), '')
if not entry:
    raise SystemExit('missing dspx-core dependency in apps/forge/pyproject.toml')

spec = entry[len('dspx-core'):]
match = re.search(r">=\s*([^,;\s]+)", spec)
if not match:
    raise SystemExit('dspx-core dependency must include a >= lower bound')
print(match.group(1))
PY
  )"

  MIN_TAG="dspx-core-v${MIN_CORE_VERSION}"
  if ! git -C "$ROOT" rev-parse --verify "refs/tags/$MIN_TAG" >/dev/null 2>&1; then
    echo "[forge-core-compat] error: required tag $MIN_TAG not found" >&2
    exit 1
  fi

  WORKTREE_DIR="$(mktemp -d)"
  git -C "$ROOT" worktree add --detach "$WORKTREE_DIR" "$MIN_TAG" >/dev/null
  if [ ! -d "$WORKTREE_DIR/packages/dspx-core" ]; then
    echo "[forge-core-compat] error: tag $MIN_TAG has no packages/dspx-core" >&2
    exit 1
  fi

  CORE_BUILD_ROOT="$WORKTREE_DIR"
  echo "[forge-core-compat] mode=min tag=$MIN_TAG"
else
  echo "[forge-core-compat] mode=latest"
fi

echo "[forge-core-compat] dist=$DIST_DIR"
mkdir -p "$DIST_DIR/core" "$DIST_DIR/forge"

# Forge is always built from current branch state.
uv build --package dspx-forge --out-dir "$DIST_DIR/forge" --clear

# Core is built from latest or the minimum supported tag.
if [ "$CORE_BUILD_ROOT" = "$ROOT" ]; then
  uv build --package dspx-core --out-dir "$DIST_DIR/core" --clear
else
  (
    cd "$CORE_BUILD_ROOT"
    uv build --package dspx-core --out-dir "$DIST_DIR/core" --clear
  )
fi

VENV="$DIST_DIR/.venv-$MODE"
uv venv "$VENV" >/dev/null
uv pip install --python "$VENV/bin/python" \
  "$DIST_DIR"/core/dspx_core-*.whl \
  "$DIST_DIR"/forge/dspx_forge-*.whl \
  pytest >/dev/null

"$VENV/bin/dspx-forge" --help >/dev/null
"$VENV/bin/python" -m pytest -q tests -k forge

echo "[forge-core-compat] ok mode=$MODE"
