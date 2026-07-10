#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

work_dir="$(mktemp -d "${TMPDIR:-/tmp}/dspx-package-check.XXXXXX")"
trap 'rm -rf "$work_dir"' EXIT INT TERM
dist_dir="$work_dir/dist"
venv_dir="$work_dir/venv"

uv build --all-packages --out-dir "$dist_dir"
uvx --from 'twine>=6,<7' twine check "$dist_dir"/*

for package in dspx_core dspx_forge; do
  test "$(find "$dist_dir" -maxdepth 1 -name "${package}-*.whl" | wc -l)" -eq 1
  test "$(find "$dist_dir" -maxdepth 1 -name "${package}-*.tar.gz" | wc -l)" -eq 1
done

uv venv --python 3.13 "$venv_dir"
uv pip install --python "$venv_dir/bin/python" "$dist_dir"/*.whl
"$venv_dir/bin/dspx" --help >/dev/null
"$venv_dir/bin/dspx-forge" --help >/dev/null
"$venv_dir/bin/python" - <<'PY'
from importlib.metadata import entry_points

scripts = {entry.name: entry.value for entry in entry_points(group="console_scripts")}
assert scripts["dspx"] == "dspx.cli.dspx:main"
assert scripts["dspx-server"] == "dspx.server.app:main"
assert scripts["dspx-forge"] == "dspx_forge.cli:main"
from dspx.server.app import app  # noqa: E402
assert app is not None
PY

printf 'ok: built, metadata-checked, installed, and smoke-tested all package artifacts\n'
