#!/usr/bin/env bash
# ---
# summary: "Runs one stub-backed Core product journey from an installed wheel outside the checkout."
# read_when:
#   - "Changing Core packaging, the installed-wheel acceptance journey, or package CI claims."
# ---
set -euo pipefail

if [ "$#" -ne 3 ] && [ "$#" -ne 5 ]; then
  printf 'usage: %s <core-venv> <journey-root> <repo-root> [<core-wheel> <wheel-sha256>]\n' "$0" >&2
  exit 2
fi

venv_root="$(cd -- "$1" && pwd -P)"
journey_root="$2"
repo_root="$(cd -- "$3" && pwd -P)"
core_wheel="${4:-}"
expected_wheel_sha256="${5:-}"
if [ "$#" -eq 5 ] && { [ -z "$core_wheel" ] || [ -z "$expected_wheel_sha256" ]; }; then
  printf 'error: Core wheel path and SHA-256 must both be non-empty\n' >&2
  exit 2
fi
if [ -n "$core_wheel" ]; then
  case "$core_wheel" in
    /*) ;;
    *) printf 'error: Core wheel path must be absolute\n' >&2; exit 2 ;;
  esac
fi

case "$journey_root" in
  /*) ;;
  *) printf 'error: journey root must be absolute\n' >&2; exit 2 ;;
esac
journey_parent="$(dirname -- "$journey_root")"
journey_name="$(basename -- "$journey_root")"
if [ "$journey_name" = "." ] || [ "$journey_name" = ".." ]; then
  printf 'error: journey root must name a new child directory\n' >&2
  exit 2
fi
journey_parent="$(cd -- "$journey_parent" && pwd -P)"
journey_root="$journey_parent/$journey_name"
case "$journey_root/" in
  "$repo_root/"*)
    printf 'error: journey root must be outside the source checkout: %s\n' "$journey_root" >&2
    exit 2
    ;;
esac
if [ -e "$journey_root" ] || [ -L "$journey_root" ]; then
  printf 'error: journey root must not already exist: %s\n' "$journey_root" >&2
  exit 2
fi

journey_identity="pending"
cleanup_failed_journey() {
  status=$?
  if [ "$status" -ne 0 ] && [ -d "$journey_root" ] && [ ! -L "$journey_root" ]; then
    if [ "$journey_identity" = "pending" ]; then
      rmdir -- "$journey_root" 2>/dev/null || true
    else
      current_identity="$(stat -c '%d:%i:%F' -- "$journey_root" 2>/dev/null || true)"
      if [ "$current_identity" = "$journey_identity" ]; then
        rm -rf --one-file-system -- "$journey_root"
      fi
    fi
  fi
  return "$status"
}
trap cleanup_failed_journey EXIT
install -d -m 0700 "$journey_root"
journey_identity="$(stat -c '%d:%i:%F' -- "$journey_root")"
install -d -m 0700 "$journey_root/canary-bin"
install -d -m 0700 "$journey_root/home" "$journey_root/xdg-config" "$journey_root/xdg-cache"
cat > "$journey_root/canary-bin/ak" <<'SH'
#!/usr/bin/env bash
printf 'forbidden AK invocation\n' > "${DSPX_INSTALL_PROOF_AK_MARKER:?}"
exit 97
SH
chmod 0700 "$journey_root/canary-bin/ak"

cat > "$journey_root/intent.json" <<'JSON'
{
  "name": "InstalledWheelTicketProgram",
  "objective": "Classify support ticket urgency from the supplied ticket text.",
  "inputs": ["ticket_text"],
  "outputs": ["urgency"],
  "metric": "exact_match",
  "examples": [
    {
      "inputs": {"ticket_text": "Production outage for all users"},
      "outputs": {"urgency": "high"}
    }
  ]
}
JSON
chmod 0600 "$journey_root/intent.json"

export PATH="$journey_root/canary-bin:$venv_root/bin:/usr/bin:/bin"
unset PYTHONPATH PYTHONHOME VIRTUAL_ENV
export PYTHONDONTWRITEBYTECODE=1
export HOME="$journey_root/home"
export XDG_CONFIG_HOME="$journey_root/xdg-config"
export XDG_CACHE_HOME="$journey_root/xdg-cache"
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy
export NO_PROXY='*'
export DSPX_INSTALL_PROOF_AK_MARKER="$journey_root/ak-called"
export DSPX_CACHE_DIR="$journey_root/cache"
export DSPX_CACHE_ENABLE=1
export DSPX_PROVIDER=stub
export DSPX_STUB_RESPONSE_JSON='{"urgency":"high"}'
export DSPX_ORACLE_EMBEDDING_BACKEND=mock
export MLFLOW_ENABLE=0
export DSPX_ORACLE_STORE=sqlite
export DSPX_ORACLE_INDEX_PATH="$journey_root/program/oracle/coordinates.db"

cd "$journey_root"

printf '[installed-core] import/entrypoint smoke\n'
"$venv_root/bin/dspx" --help >/dev/null

printf '[installed-core] program-loop with candidate-local Oracle evidence\n'
"$venv_root/bin/dspx" program-loop \
  --intent "$journey_root/intent.json" \
  --outdir "$journey_root/program" \
  --index-path "$journey_root/program/oracle/coordinates.db" \
  --json > "$journey_root/program-loop-result.json"
chmod 0600 "$journey_root/program-loop-result.json"

printf '[installed-core] explicit receipt integrity check\n'
"$venv_root/bin/dspx" run replay \
  --from "$journey_root/program/manifest.json.meta.json" \
  --check-only \
  --json > "$journey_root/replay-check.json"
chmod 0600 "$journey_root/replay-check.json"

if [ -e "$DSPX_INSTALL_PROOF_AK_MARKER" ] || [ -L "$DSPX_INSTALL_PROOF_AK_MARKER" ]; then
  printf 'error: installed Core journey attempted to call AK\n' >&2
  exit 1
fi

printf '[installed-core] independently verify installed origin and artifact truth\n'
verifier_args=(
  --journey-root "$journey_root"
  --venv-root "$venv_root"
  --repo-root "$repo_root"
)
if [ -n "$core_wheel" ]; then
  verifier_args+=(--wheel "$core_wheel" --expected-wheel-sha256 "$expected_wheel_sha256")
fi
"$venv_root/bin/python" "$repo_root/scripts/ci/verify_installed_core_golden_path.py" \
  "${verifier_args[@]}" \
  > "$journey_root/verification-output.json"
chmod 0600 "$journey_root/verification-output.json"

printf '[installed-core] ok: stub-backed wheel plumbing proven; network isolation and production semantics are not claimed\n'
