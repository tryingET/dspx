#!/usr/bin/env bash
# ---
# summary: "Build, inspect, install, and smoke-test all distributable DSPx packages."
# read_when:
#   - "Changing package metadata, console entry points, or release artifact validation."
# ---
set -euo pipefail

retain_core_bundle=""
if [[ $# -gt 0 ]]; then
  if [[ $# -ne 2 || "$1" != "--retain-core-evidence" || -z "$2" ]]; then
    printf 'usage: %s [--retain-core-evidence <output.zip>]\n' "$0" >&2
    exit 2
  fi
  retain_core_bundle="$2"
fi

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

printf '[package-check] generate and verify exact Core wheel SBOM\n'
"$core_venv_dir/bin/python" scripts/ci/core_release_sbom.py generate \
  --wheel "$core_wheel" \
  --out "$work_dir/dspx-core-wheel-sbom.cdx.json" \
  > "$work_dir/sbom-generation-output.json"
"$core_venv_dir/bin/python" scripts/ci/core_release_sbom.py validate \
  --wheel "$core_wheel" \
  --sbom "$work_dir/dspx-core-wheel-sbom.cdx.json" \
  > "$work_dir/sbom-validation-output.json"

printf '[package-check] generate and verify resolved Core environment SBOM\n'
"$core_venv_dir/bin/python" scripts/ci/core_release_environment_sbom.py generate \
  --wheel "$core_wheel" \
  --installed-proof "$core_journey_dir/installed-core-golden-path-proof.json" \
  --out "$work_dir/dspx-core-installed-environment-sbom.cdx.json" \
  > "$work_dir/environment-sbom-generation-output.json"
"$core_venv_dir/bin/python" scripts/ci/core_release_environment_sbom.py validate \
  --wheel "$core_wheel" \
  --installed-proof "$core_journey_dir/installed-core-golden-path-proof.json" \
  --sbom "$work_dir/dspx-core-installed-environment-sbom.cdx.json" \
  > "$work_dir/environment-sbom-validation-output.json"

printf '[package-check] build fail-closed Core release-evidence claim matrix\n'
"$core_venv_dir/bin/python" scripts/ci/core_release_evidence.py \
  --repo-root "$repo_root" \
  --wheel "$core_wheel" \
  --sdist "$core_sdist" \
  --installed-proof "$core_journey_dir/installed-core-golden-path-proof.json" \
  --sbom "$work_dir/dspx-core-wheel-sbom.cdx.json" \
  --out "$work_dir/dspx-core-release-evidence.json" \
  --resolved-environment-sbom "$work_dir/dspx-core-installed-environment-sbom.cdx.json" \
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

if [[ -n "$retain_core_bundle" ]]; then
  printf '[package-check] retain SBOM-bound unsigned Core release evidence bundle\n'
  "$core_venv_dir/bin/python" scripts/ci/core_release_bundle.py build \
    --repo-root "$repo_root" \
    --wheel "$core_wheel" \
    --sdist "$core_sdist" \
    --installed-proof "$core_journey_dir/installed-core-golden-path-proof.json" \
    --release-evidence "$work_dir/dspx-core-release-evidence.json" \
    --sbom "$work_dir/dspx-core-wheel-sbom.cdx.json" \
    --resolved-environment-sbom "$work_dir/dspx-core-installed-environment-sbom.cdx.json" \
    --out "$retain_core_bundle" \
    > "$work_dir/release-bundle-output.json"
  "$core_venv_dir/bin/python" scripts/ci/core_release_bundle.py validate \
    --bundle "$retain_core_bundle" \
    > "$work_dir/release-bundle-validation.json"
  printf '[package-check] retained bundle: %s\n' "$retain_core_bundle"
fi

printf 'ok: built and metadata-checked all artifacts; exact Core wheel bytes passed the stub-backed product journey and release-claim truth check; CycloneDX wheel-payload/direct-dependency and point-in-time resolved-environment SBOM generation and verification passed; signing, CI custody, publication, technical completeness, and release readiness remain unproven; Forge passed separate install/CLI smoke\n'
