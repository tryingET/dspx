#!/usr/bin/env bash
# ---
# summary: "Build, inspect, install, and smoke-test all distributable DSPx packages."
# read_when:
#   - "Changing package metadata, console entry points, or release artifact validation."
# ---
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

work_dir="$(mktemp -d "${TMPDIR:-/tmp}/dspx-package-check.XXXXXX")"
trap 'rm -rf "$work_dir"' EXIT INT TERM
dist_dir="$work_dir/dist"
core_venv_dir="$work_dir/core-venv"
forge_venv_dir="$work_dir/forge-venv"
core_journey_dir="$work_dir/core-journey"
export PYTHONDONTWRITEBYTECODE=1

uv build --all-packages --out-dir "$dist_dir"
uvx --from 'twine>=6,<7' twine check "$dist_dir"/*

for package in dspx_core dspx_forge; do
  test "$(find "$dist_dir" -maxdepth 1 -name "${package}-*.whl" | wc -l)" -eq 1
  test "$(find "$dist_dir" -maxdepth 1 -name "${package}-*.tar.gz" | wc -l)" -eq 1
done

core_wheel="$(find "$dist_dir" -maxdepth 1 -name 'dspx_core-*.whl' -print -quit)"
core_sdist="$(find "$dist_dir" -maxdepth 1 -name 'dspx_core-*.tar.gz' -print -quit)"
forge_wheel="$(find "$dist_dir" -maxdepth 1 -name 'dspx_forge-*.whl' -print -quit)"
core_wheel_sha256="$(sha256sum -- "$core_wheel" | cut -d' ' -f1)"
core_wheel_uri="$(python3 - "$core_wheel" <<'PY'
from pathlib import Path
import sys

print(Path(sys.argv[1]).resolve().as_uri())
PY
)"

printf '[package-check] install Core wheel alone\n'
uv venv --python 3.13 "$core_venv_dir"
uv pip install --python "$core_venv_dir/bin/python" \
  "dspx-core @ ${core_wheel_uri}#sha256=${core_wheel_sha256}"
"$core_venv_dir/bin/python" - <<'PY'
from importlib.metadata import entry_points

scripts = {entry.name: entry.value for entry in entry_points(group="console_scripts")}
assert scripts["dspx"] == "dspx.cli.dspx:main"
assert scripts["dspx-server"] == "dspx.server.app:main"
assert "dspx-forge" not in scripts
from dspx.server.app import app  # noqa: E402
assert app is not None
PY
bash scripts/ci/installed-core-golden-path.sh \
  "$core_venv_dir" "$core_journey_dir" "$repo_root" \
  "$core_wheel" "$core_wheel_sha256"

printf '[package-check] build fail-closed Core release-evidence claim matrix\n'
"$core_venv_dir/bin/python" scripts/ci/core_release_evidence.py \
  --repo-root "$repo_root" \
  --wheel "$core_wheel" \
  --sdist "$core_sdist" \
  --installed-proof "$core_journey_dir/installed-core-golden-path-proof.json" \
  --out "$work_dir/dspx-core-release-evidence.json" \
  > "$work_dir/release-evidence-output.json"

printf '[package-check] install and smoke Forge separately\n'
uv venv --python 3.13 "$forge_venv_dir"
uv pip install --python "$forge_venv_dir/bin/python" "$core_wheel" "$forge_wheel"
"$forge_venv_dir/bin/dspx-forge" --help >/dev/null
"$forge_venv_dir/bin/python" - <<'PY'
from importlib.metadata import entry_points

scripts = {entry.name: entry.value for entry in entry_points(group="console_scripts")}
assert scripts["dspx-forge"] == "dspx_forge.cli:main"
PY

printf 'ok: built and metadata-checked all artifacts; exact Core wheel bytes passed the stub-backed product journey and release-claim truth check; SBOM, signing, publication, and release readiness remain unproven; Forge passed separate install/CLI smoke\n'
