#!/bin/sh
set -eu

script_dir="$(cd "$(dirname "$0")" && pwd)"

"$script_dir/smoke.sh"

repo_root="$(git rev-parse --show-toplevel 2>/dev/null)" || { echo "error: not a git repo" >&2; exit 1; }
cd "$repo_root"

if [ -x "./scripts/rocs.sh" ] && [ -f "./ontology/manifest.yaml" ]; then
  workspace_root="${ROCS_WORKSPACE_ROOT:-$HOME}"
  workspace_ref_mode="${ROCS_WORKSPACE_REF_MODE:-loose}"
  core_rocs_default="$HOME/ai-society/core/rocs-cli/.venv/bin/rocs"
  rocs_bin="${ROCS_BIN:-}"

  if [ -z "$rocs_bin" ] && [ -x "$core_rocs_default" ]; then
    rocs_bin="$core_rocs_default"
  fi

  if [ -n "$rocs_bin" ]; then
    ROCS_BIN="$rocs_bin" ROCS_WORKSPACE_ROOT="$workspace_root" ROCS_WORKSPACE_REF_MODE="$workspace_ref_mode" ./scripts/rocs.sh version
    ROCS_BIN="$rocs_bin" ROCS_WORKSPACE_ROOT="$workspace_root" ROCS_WORKSPACE_REF_MODE="$workspace_ref_mode" ./scripts/rocs.sh build --repo . --resolve-refs --clean
    ROCS_BIN="$rocs_bin" ROCS_WORKSPACE_ROOT="$workspace_root" ROCS_WORKSPACE_REF_MODE="$workspace_ref_mode" ./scripts/rocs.sh validate --repo . --resolve-refs
  else
    ROCS_WORKSPACE_ROOT="$workspace_root" ROCS_WORKSPACE_REF_MODE="$workspace_ref_mode" ./scripts/rocs.sh version
    ROCS_WORKSPACE_ROOT="$workspace_root" ROCS_WORKSPACE_REF_MODE="$workspace_ref_mode" ./scripts/rocs.sh build --repo . --resolve-refs --clean
    ROCS_WORKSPACE_ROOT="$workspace_root" ROCS_WORKSPACE_REF_MODE="$workspace_ref_mode" ./scripts/rocs.sh validate --repo . --resolve-refs
  fi
fi
