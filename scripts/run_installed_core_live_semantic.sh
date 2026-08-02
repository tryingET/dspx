#!/usr/bin/env bash
# ---
# summary: "Runs one opt-in exact-wheel live semantic journey with local-only evidence and no release authority."
# read_when:
#   - "Running or changing the installed-wheel live-provider semantic dogfood path."
# ---
set -euo pipefail
umask 077

AUTH_WHEEL_URL='https://github.com/tryingET/dspy-lm-auth/releases/download/v0.1.4/dspy_lm_auth-0.1.4-py3-none-any.whl'
AUTH_WHEEL_SHA256='ea24c9534fa80c30fc3f3c95f522c36931b67a0b820e275b1de5b2db714931c6'
AUTH_WHEEL_NAME='dspy_lm_auth-0.1.4-py3-none-any.whl'

usage() {
  cat >&2 <<'EOF'
usage: scripts/run_installed_core_live_semantic.sh \
  --wheel <absolute-wheel> --wheel-sha256 <hex> \
  --root <new-absolute-root> --provider dspy-lm-auth --model <codex/model>
EOF
  exit 2
}

wheel=""; wheel_sha256=""; journey_root=""; provider=""; model=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --wheel) [ "$#" -ge 2 ] || usage; wheel="$2"; shift 2 ;;
    --wheel-sha256) [ "$#" -ge 2 ] || usage; wheel_sha256="$2"; shift 2 ;;
    --root) [ "$#" -ge 2 ] || usage; journey_root="$2"; shift 2 ;;
    --provider) [ "$#" -ge 2 ] || usage; provider="$2"; shift 2 ;;
    --model) [ "$#" -ge 2 ] || usage; model="$2"; shift 2 ;;
    *) usage ;;
  esac
done

[ -n "$wheel" ] && [ -n "$wheel_sha256" ] && [ -n "$journey_root" ] \
  && [ -n "$provider" ] && [ -n "$model" ] || usage
case "$wheel" in /*) ;; *) printf 'error: --wheel must be absolute\n' >&2; exit 2 ;; esac
case "$journey_root" in /*) ;; *) printf 'error: --root must be absolute\n' >&2; exit 2 ;; esac
case "$wheel_sha256" in *[!0-9a-f]*|'') printf 'error: invalid wheel SHA-256\n' >&2; exit 2 ;; esac
[ "${#wheel_sha256}" -eq 64 ] || { printf 'error: wheel SHA-256 must contain 64 characters\n' >&2; exit 2; }
[ "$provider" = "dspy-lm-auth" ] || { printf 'error: only dspy-lm-auth is supported\n' >&2; exit 2; }
[ "$model" = "codex/gpt-5.6-sol" ] \
  || { printf 'error: --model must match the precommitted route\n' >&2; exit 2; }
[ -f "$wheel" ] && [ ! -L "$wheel" ] || { printf 'error: wheel must be a regular non-symlink file\n' >&2; exit 2; }
[ "$(sha256sum "$wheel" | awk '{print $1}')" = "$wheel_sha256" ] \
  || { printf 'error: wheel SHA-256 mismatch\n' >&2; exit 2; }

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd -- "$script_dir/.." && pwd -P)"
python3 "$repo_root/scripts/ci/validate_installed_live_oracle_evaluation.py" >/dev/null
parent="$(dirname -- "$journey_root")"; name="$(basename -- "$journey_root")"
[ "$name" != "." ] && [ "$name" != ".." ] || { printf 'error: root must name a new child\n' >&2; exit 2; }
[ -d "$parent" ] && [ ! -L "$parent" ] || { printf 'error: root parent must be an existing non-symlink directory\n' >&2; exit 2; }
parent="$(cd -- "$parent" && pwd -P)"; journey_root="$parent/$name"
case "$journey_root/" in "$repo_root/"*) printf 'error: root must be outside the checkout\n' >&2; exit 2 ;; esac
[ ! -e "$journey_root" ] && [ ! -L "$journey_root" ] || { printf 'error: root must not exist\n' >&2; exit 2; }

install -d -m 0700 "$journey_root"
exec {journey_fd}<"$journey_root"
[ ! -L "$journey_root" ] && [ "$(stat -c '%F' "$journey_root")" = "directory" ] \
  || { printf 'error: journey root changed before descriptor pinning\n' >&2; exit 1; }
journey_identity="$(stat -Lc '%d:%i' "/proc/$$/fd/$journey_fd")"
cd "/proc/$$/fd/$journey_fd"
assert_root_identity() {
  local fd_identity path_identity
  fd_identity="$(stat -Lc '%d:%i' "/proc/$$/fd/$journey_fd")"
  path_identity="$(stat -Lc '%d:%i' "$journey_root" 2>/dev/null || true)"
  [ "$fd_identity" = "$journey_identity" ] && [ "$path_identity" = "$journey_identity" ] \
    || { printf 'error: journey root identity changed\n' >&2; return 1; }
}
assert_root_identity

current_step="preflight"
write_status() {
  local status="$1" exit_code="$2" ak_observation="not_observed_by_path_canary"
  local bounded_error="false"
  [ ! -e ak-called ] && [ ! -L ak-called ] || ak_observation="detected_by_path_canary"
  [ ! -e benchmark-result.json ] || bounded_error="true"
  JOURNEY_STATUS="$status" JOURNEY_STEP="$current_step" JOURNEY_EXIT="$exit_code" \
  JOURNEY_AK="$ak_observation" JOURNEY_ERROR="$bounded_error" python3 - journey-status.json.tmp <<'PY'
import json, os, pathlib
payload = {
    "schema_version": "dspx-installed-core-live-semantic-status-v1",
    "status": os.environ["JOURNEY_STATUS"],
    "last_step": os.environ["JOURNEY_STEP"],
    "exit_code": int(os.environ["JOURNEY_EXIT"]),
    "bounded_sanitized_benchmark_detail_may_be_retained": os.environ["JOURNEY_ERROR"] == "true",
    "ak_path_canary_observation": os.environ["JOURNEY_AK"],
    "shared_oracle_request": "not_requested_by_runner",
    "release_authority": False,
    "package_publication": False,
}
pathlib.Path("journey-status.json.tmp").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
PY
  chmod 0600 journey-status.json.tmp
  mv -f journey-status.json.tmp journey-status.json
}
write_attempt() {
  # The terminal disposition covers only the single benchmark invocation.
  local disposition="$1"
  ATTEMPT_DISPOSITION="$disposition" python3 - <<'PY'
import json, os, pathlib
payload = {
    "schema_version": "dspx-installed-core-live-attempt-v2",
    "benchmark_invocation_count": 1,
    "disposition": os.environ["ATTEMPT_DISPOSITION"],
    "dspx_stream_compatibility_retry_enabled": False,
    "provider_internal_retry_behavior": "not_proven",
    "separate_health_probe_run": False,
    "mechanical_retry_run": False,
    "selective_quality_rerun_allowed": False,
    "case_execution_order": [
        "single-module-authority-boundary",
        "pipeline-evidence-calibration",
        "pdf-transition-review-runtime-replay",
    ],
}
pathlib.Path("provider-attempt.json.tmp").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
PY
  chmod 0600 provider-attempt.json.tmp
  mv -f provider-attempt.json.tmp provider-attempt.json
}
attempt_terminal="false"
on_exit() {
  rc=$?
  if [ "$rc" -ne 0 ]; then
    if [ -e provider-attempt.json ] && [ "$attempt_terminal" = "false" ]; then
      write_attempt failed || true
    fi
    write_status failed "$rc" || true
    printf 'installed live semantic journey failed at step %s; bounded artifacts remain under the original root inode\n' "$current_step" >&2
  fi
  return "$rc"
}
trap on_exit EXIT
write_status running 0

current_step="create_clean_environment"
uv venv --python 3.13 venv
assert_root_identity

current_step="fetch_hash_bound_released_auth_wheel"
install -d -m 0700 inputs
curl --proto '=https' --tlsv1.2 --fail --location --silent --show-error \
  "$AUTH_WHEEL_URL" --output "inputs/$AUTH_WHEEL_NAME.partial"
[ "$(sha256sum "inputs/$AUTH_WHEEL_NAME.partial" | awk '{print $1}')" = "$AUTH_WHEEL_SHA256" ] \
  || { printf 'error: released auth wheel SHA-256 mismatch\n' >&2; exit 1; }
mv "inputs/$AUTH_WHEEL_NAME.partial" "inputs/$AUTH_WHEEL_NAME"
chmod 0600 "inputs/$AUTH_WHEEL_NAME"
assert_root_identity

current_step="install_exact_wheels"
core_requirement="$(python3 - "$wheel" "$wheel_sha256" <<'PY'
from pathlib import Path
import sys
print(f"dspx-core[lm-auth] @ {Path(sys.argv[1]).as_uri()}#sha256={sys.argv[2]}")
PY
)"
auth_wheel="$journey_root/inputs/$AUTH_WHEEL_NAME"
uv pip install --python ./venv/bin/python "$core_requirement"
assert_root_identity

current_step="snapshot_exact_three_strata_contract"
cp -- "$repo_root/benchmarks/semantic/program-corpus-v2.json" corpus.json
cp -- "$repo_root/benchmarks/semantic/installed-live-oracle-evaluation-v1.json" \
  evaluation-contract.json
[ "$(sha256sum corpus.json | awk '{print $1}')" = \
  "4c877c7992d8b70044645c57e2753ea9f170da027179376cafbc4d6000db0ec9" ] \
  || { printf 'error: corpus snapshot hash drift\n' >&2; exit 1; }
[ "$(sha256sum evaluation-contract.json | awk '{print $1}')" = \
  "9ff735cd4ba29cfe430c9bce12d697877fa18a91cff78bd98defedcdeed5201a" ] \
  || { printf 'error: evaluation contract snapshot hash drift\n' >&2; exit 1; }
chmod 0600 corpus.json evaluation-contract.json
install -d -m 0700 canary-bin oracle replay
cat > canary-bin/ak <<'SH'
#!/usr/bin/env bash
printf 'forbidden AK invocation\n' > "${DSPX_INSTALLED_LIVE_AK_MARKER:?}"
exit 97
SH
chmod 0700 canary-bin/ak
assert_root_identity

export PATH="/proc/$$/fd/$journey_fd/canary-bin:/proc/$$/fd/$journey_fd/venv/bin:$PATH"
unset PYTHONPATH PYTHONHOME VIRTUAL_ENV
export PYTHONDONTWRITEBYTECODE=1
export DSPX_INSTALLED_LIVE_AK_MARKER="/proc/$$/fd/$journey_fd/ak-called"
export DSPX_PROVIDER="$provider" DSPX_LM_AUTH_MODEL="$model" DSPX_LM_AUTH_PROVIDER=codex
export DSPX_LM_AUTH_REASONING_EFFORT=high DSPX_LM_AUTH_TIMEOUT=120
export DSPX_PROGRAM_CODEX_STREAM_COMPAT_RETRY=0
export DSPX_CACHE_ENABLE=0 MLFLOW_ENABLE=0
export DSPX_ORACLE_EMBEDDING_BACKEND=mock DSPX_ORACLE_STORE=sqlite

current_step="record_runtime_identity"
./venv/bin/python - runtime-environment.json "$provider" "$model" "$AUTH_WHEEL_SHA256" <<'PY'
from importlib import import_module
from importlib.metadata import version
import json, os, pathlib, sys
import dspx
lm_auth = import_module("dspy_lm_auth")
payload = {
    "schema_version": "dspx-installed-core-live-runtime-v1",
    "provider": sys.argv[2], "requested_model": sys.argv[3],
    "resolved_model_identity": "not_proven",
    "pythonpath_unset": not bool(os.environ.get("PYTHONPATH")),
    "dspx_core_version": version("dspx-core"),
    "dspx_module_path": str(pathlib.Path(dspx.__file__).resolve()),
    "dspy_lm_auth_version": version("dspy-lm-auth"),
    "dspy_lm_auth_module_path": str(pathlib.Path(lm_auth.__file__).resolve()),
    "dspy_lm_auth_wheel_sha256": sys.argv[4],
    "dspx_stream_compatibility_retry_enabled": False,
    "provider_internal_retry_behavior": "not_proven",
    "auth_store_nonmutation_proven": False,
    "network_isolation_proven": False,
    "unbounded_raw_provider_response_retained": False,
    "bounded_benchmark_behavior_output_retained": True,
}
pathlib.Path("runtime-environment.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
PY
chmod 0600 runtime-environment.json
assert_root_identity

current_step="one_live_program_semantic_attempt"
write_attempt pending
set +e
./venv/bin/python "$repo_root/scripts/run_program_semantic_benchmarks.py" \
  --corpus corpus.json --work-root benchmark --out benchmark-result.json \
  --result-schema "$repo_root/benchmarks/semantic/program-result-schema-v2.json" \
  --stop-after-case-error --live --provider "$provider" >/dev/null
benchmark_rc=$?
set -e
if [ "$benchmark_rc" -ne 0 ]; then
  write_attempt failed
  attempt_terminal="true"
  exit "$benchmark_rc"
fi
write_attempt passed
attempt_terminal="true"
chmod 0600 benchmark-result.json provider-attempt.json
assert_root_identity

current_step="receipt_integrity_replay_all_cases"
for case_id in \
  single-module-authority-boundary \
  pipeline-evidence-calibration \
  pdf-transition-review-runtime-replay
do
  candidate_root="benchmark/$case_id"
  export DSPX_CACHE_DIR="benchmark/.cache/$case_id"
  ./venv/bin/dspx run replay --from "$candidate_root/manifest.json.meta.json" \
    --check-only --json > "replay/$case_id.json"
  chmod 0600 "replay/$case_id.json"
  assert_root_identity
done

current_step="candidate_local_oracle_index_all_cases"
./venv/bin/dspx oracle index --from-program-evidence --path benchmark \
  --index-path oracle/coordinates.db --json > oracle-index-result.json
chmod 0600 oracle-index-result.json
assert_root_identity

current_step="candidate_local_oracle_report"
./venv/bin/dspx oracle program-evidence report --index-path oracle/coordinates.db \
  --json > oracle-report.json
chmod 0600 oracle-report.json
assert_root_identity

[ ! -e ak-called ] && [ ! -L ak-called ] || { printf 'error: AK canary detected invocation\n' >&2; exit 1; }
current_step="independent_evidence_verification"
./venv/bin/python "$repo_root/scripts/ci/verify_installed_core_live_semantic.py" \
  --journey-root . --venv-root venv --repo-root "$repo_root" \
  --wheel "$wheel" --expected-wheel-sha256 "$wheel_sha256" \
  --auth-wheel "$auth_wheel" --expected-auth-wheel-sha256 "$AUTH_WHEEL_SHA256" \
  --provider "$provider" --requested-model "$model" > verification-output.json
chmod 0600 verification-output.json
assert_root_identity

current_step="complete"
write_status passed 0
assert_root_identity
trap - EXIT
printf 'installed live semantic journey passed; evidence: %s\n' \
  "$journey_root/installed-core-live-semantic-proof.json"
