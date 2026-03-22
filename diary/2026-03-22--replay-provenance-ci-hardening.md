# 2026-03-22 — Replay Provenance CI Hardening

## What I Did
- Reviewed the current replay/check-only coverage path and confirmed the main gap was CI wiring: unit tests already covered replay drift, but neither `./scripts/ci/full.sh` nor `just verify-full` executed a deterministic receipt-first provenance check end-to-end.
- Added `scripts/check_replay_provenance.py`, a deterministic guard that:
  - generates a stub-backed signature + receipt in a temp dir,
  - verifies `dspx run replay --check-only --json` passes in the clean case,
  - mutates the cache payload code,
  - requires replay to fail with `cache_code_hash_mismatch`.
- Wired that guard into both `./scripts/ci/full.sh` and `just verify-full`.
- Updated the canonical workflow and replay-contract docs to describe the new provenance check.
- Marked `DSPX-M3-01` done and advanced the session handoff.

## What Surprised Me
- The strict replay behavior was already present and well-covered in `tests/test_run_receipts.py`; the highest-leverage improvement was not more replay logic, but making CI exercise the contract directly with a clean-path plus induced-drift path.

## Patterns
- For receipt-first reproducibility, pair one positive control (clean replay passes) with one negative control (deliberate provenance drift fails with a stable code) inside the same deterministic CI script.
- When replay strictness matters operationally, wire the guard into the executable validation path (`verify-full` / CI scripts), not just into unit tests.

## Crystallization Candidates
- If more replay drift modes become operationally important, expand the provenance guard to emit a small machine-readable matrix of drift classes rather than adding separate ad-hoc CI scripts.
