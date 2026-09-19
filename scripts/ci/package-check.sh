#!/usr/bin/env bash
# ---
# summary: "Build, inspect, install, and smoke-test all distributable DSPx packages."
# read_when:
#   - "Changing package metadata, console entry points, or release artifact validation."
# ---
set -euo pipefail

retain_core_bundle=""
release_output=""
scope_evidence=""
usage() {
  printf 'usage: %s [--retain-core-evidence <output.zip>] [--release-output <new-absolute-dir> --scope-evidence AK-evidence:<id>]\n' "$0" >&2
  exit 2
}
while [[ $# -gt 0 ]]; do
  [[ $# -ge 2 && -n "$2" ]] || usage
  case "$1" in
    --retain-core-evidence) [[ -z "$retain_core_bundle" ]] || usage; retain_core_bundle="$2" ;;
    --release-output) [[ -z "$release_output" ]] || usage; release_output="$2" ;;
    --scope-evidence) [[ -z "$scope_evidence" ]] || usage; scope_evidence="$2" ;;
    *) usage ;;
  esac
  shift 2
done
if [[ -n "$release_output" || -n "$scope_evidence" ]]; then
  [[ "$release_output" == /* && ! -e "$release_output" && ! -L "$release_output" ]] || usage
  [[ "$scope_evidence" =~ ^AK-evidence:[1-9][0-9]*$ ]] || usage
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

printf '[package-check] install the exact locked Core dependency graph plus the selected wheel\n'
core_requirements="$work_dir/core-locked-requirements.txt"
uv export --frozen --package dspx-core --no-dev --no-hashes \
  --no-emit-package dspx-core --output-file "$core_requirements"
uv venv --python 3.13 "$core_venv_dir"
uv pip install --python "$core_venv_dir/bin/python" --requirements "$core_requirements"
uv pip install --python "$core_venv_dir/bin/python" --no-deps \
  "dspx-core @ ${core_wheel_uri}#sha256=${core_wheel_sha256}"
printf '[package-check] prove installed dependency versions agree with the lock and Core metadata\n'
"$core_venv_dir/bin/python" - "$repo_root/uv.lock" <<'PY'
from importlib.metadata import PackageNotFoundError, distribution, distributions, version
from pathlib import Path
import sys
import tomllib
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name

expected = {"dspy": "3.3.1", "dspy-ai": "3.3.1", "gepa": "0.1.4"}
with Path(sys.argv[1]).open("rb") as stream:
    lock = tomllib.load(stream)
locked = {
    canonicalize_name(row["name"]): row["version"] for row in lock["package"]
}
for installed in distributions():
    name = canonicalize_name(installed.metadata["Name"])
    if name == "dspx-core":
        continue
    assert name in locked, f"installed distribution absent from lock: {name}"
    assert installed.version == locked[name], (
        name,
        installed.version,
        locked[name],
    )
for name, required_version in expected.items():
    assert locked.get(name) == required_version, (name, locked.get(name))
    assert version(name) == required_version, (name, version(name))
core = distribution("dspx-core")
assert core.version == locked["dspx-core"], (core.version, locked["dspx-core"])
assert SpecifierSet(core.metadata["Requires-Python"]) == SpecifierSet(">=3.13,<3.15")
requirements = set(core.requires or ())
assert "dspy==3.3.1" in requirements
assert "dspy-ai==3.3.1" in requirements
try:
    distribution("tryinget-dspy-lm-auth")
except PackageNotFoundError:
    pass
else:
    raise AssertionError("removed dspy-lm-auth distribution is installed")
PY
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

printf '[package-check] install and smoke Forge against its exact locked graph\n'
forge_requirements="$work_dir/forge-locked-requirements.txt"
uv export --frozen --package dspx-forge --no-dev --no-hashes \
  --no-emit-package dspx-core --no-emit-package dspx-forge \
  --output-file "$forge_requirements"
uv venv --python 3.13 "$forge_venv_dir"
uv pip install --python "$forge_venv_dir/bin/python" --requirements "$forge_requirements"
uv pip install --python "$forge_venv_dir/bin/python" --no-deps \
  "$core_wheel" "$forge_wheel"
"$forge_venv_dir/bin/dspx-forge" --help >/dev/null
"$forge_venv_dir/bin/python" - "$repo_root/uv.lock" <<'PY'
from importlib.metadata import distributions, entry_points
from pathlib import Path
import sys
import tomllib
from packaging.utils import canonicalize_name

with Path(sys.argv[1]).open("rb") as stream:
    lock = tomllib.load(stream)
locked = {
    canonicalize_name(row["name"]): row["version"] for row in lock["package"]
}
for installed in distributions():
    name = canonicalize_name(installed.metadata["Name"])
    assert name in locked, f"installed distribution absent from lock: {name}"
    assert installed.version == locked[name], (
        name,
        installed.version,
        locked[name],
    )
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

printf '[package-check] validate selected Core signer policy and fail-closed unbound roster\n'
"$core_venv_dir/bin/python" scripts/ci/core_release_signing.py preflight-policy \
  --policy governance/release-signing/trust-policy-v001.json \
  --selector governance/release-signing/policy-selector-v001.json \
  --roster governance/release-signing/release-owner-roster-v001.json \
  > "$work_dir/release-signing-policy-preflight.json"

printf 'ok: built and metadata-checked all artifacts; exact Core wheel bytes passed the stub-backed product journey and release-claim truth check; CycloneDX wheel-payload/direct-dependency and point-in-time resolved-environment SBOM generation and verification passed; selected signer-policy schemas and the intentionally unbound owner roster passed offline preflight; signature authenticity, live CI custody, release authorization, package publication, technical completeness, and release readiness remain unproven; Forge passed separate install/CLI smoke\n'

# Preserve the tested bytes for the separate publication channel. The manifest is
# evidence, not approval; downstream resolver/sdist checks and owner approval remain.
if [[ -n "$release_output" ]]; then
  mkdir -- "$release_output"
  cp -- "$dist_dir"/*.whl "$dist_dir"/*.tar.gz "$release_output/"
  "$core_venv_dir/bin/python" scripts/release/artifacts.py create \
    --dist "$release_output" --repo "$repo_root" \
    --commit "$(git rev-parse HEAD)" --scope-evidence "$scope_evidence"
fi
