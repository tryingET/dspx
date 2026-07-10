#!/bin/sh
set -eu

say() { printf '%s\n' "$*"; }
err() { printf '%s\n' "$*" >&2; }

repo_root="$(git rev-parse --show-toplevel 2>/dev/null)" || { err "error: not a git repo"; exit 1; }
cd "$repo_root"

say "==> verify-fast"
just verify-fast

log_dir="$(mktemp -d "${TMPDIR:-/tmp}/dspx-verify-full.XXXXXX")"
cleanup() {
  rm -rf "$log_dir"
}
trap cleanup EXIT INT TERM

say "==> verify-runtime + verify-tests (parallel, pytest deduplicated)"
# The complete pytest suite runs in verify-tests. The full-gate environment keeps
# verify-runtime on its non-pytest invariants so expensive tests run once, while
# preserving the stable `just verify-runtime` command contract.
(
  DSPX_VERIFY_FULL_NONOVERLAP=1 just verify-runtime >"$log_dir/runtime.log" 2>&1
) &
runtime_pid=$!
(
  just verify-tests >"$log_dir/tests.log" 2>&1
) &
tests_pid=$!

runtime_status=0
tests_status=0
wait "$runtime_pid" || runtime_status=$?
wait "$tests_pid" || tests_status=$?

say "--- verify-runtime output ---"
cat "$log_dir/runtime.log"
say "--- verify-tests output ---"
cat "$log_dir/tests.log"

if [ "$runtime_status" -ne 0 ] || [ "$tests_status" -ne 0 ]; then
  err "error: verify-full failed"
  [ "$runtime_status" -eq 0 ] || err "- verify-runtime exit=$runtime_status"
  [ "$tests_status" -eq 0 ] || err "- verify-tests exit=$tests_status"
  exit 1
fi

say "ok: verify-full"
