# Next Steps

Current branch context: `main`.
Execution mode reference: full-sweep (DSPx + upstream MLflow + upstream DSPy), ordered waves.

## Boundary invariant (non-negotiable)

- Allowed: `apps/* -> core`
- Forbidden: `core -> apps/*`
- Never import `dspx_forge.*` from core code.

Acceptance:
- `just monorepo-check` stays green.
- No reverse imports introduced in diffs.

---

## 1) Keep baseline stable on every iteration

Actions:
1. Run:
   - `pre-commit run --all-files`
   - `just monorepo-check`
   - `just test`
2. Run extra quality gates when touching core runtime contracts:
   - `just fmt && just lint && just typecheck`

Acceptance:
- All default gates pass before/after each scoped change.

---

## 2) Package and land Wave-1 DSPx observability changes cleanly

Actions:
1. Slice reviewable commits for:
   - `dspx.*` MLflow correlation tags
   - receipt `mlflow_hints`
   - explain diagnostics + `--mlflow-remote-lookup`
   - tests/docs synchronization
2. Ensure commit messages map to one concern each.
3. Keep remote lookup bounded in explain path (HTTP timeout budget + retries `0`) and retain regression coverage for remote-unreachable URIs.

Acceptance:
- No mixed concerns per commit.
- Tests covering receipt hints + explain diagnostics remain green.
- `tests/test_run_receipts.py::test_run_explain_remote_lookup_flag_graceful` stays fast/no-hang.
- Docs reflect actual CLI flags and runtime behavior.

---

## 3) Wave-2 upstream MLflow execution (issue/PR prep)

Actions:
1. Open/update MLflow umbrella issue from RFC packet.
2. Prepare PR slicing artifacts:
   - PR1 span no-op/warning policy
   - PR2 callback concurrency state safety
   - PR3 optional autolog controls
3. Attach concrete repro notes and downstream impact.

Acceptance:
- Umbrella + slice checklists exist and are linkable.
- Scope remains additive/backward compatible by default.

---

## 4) Wave-3 upstream DSPy execution (issue/PR prep)

Actions:
1. Open/update DSPy umbrella issue from RFC packet.
2. Prepare PR slicing artifacts:
   - PR1 callback metadata envelope
   - PR2 compile lifecycle hooks
   - PR3 propagation guarantees/stress tests
3. Keep compatibility semantics explicit (missing vs null, marker rollout).

Acceptance:
- Issue/PR decomposition is concrete and test-gated.
- Legacy callback compatibility is preserved.

---

## 5) Wave-4 downstream reconciliation plan

Actions:
1. Track upstream release readiness checkpoints.
2. Define dependency floor bump steps + rollback posture.
3. Re-verify replay/explain behavior after dependency updates.

Acceptance:
- Upgrade path and rollback path both documented.
- Replay/explain determinism remains intact post-upgrade.

---

## 6) System4D extension smoke-testing track (optional focus)

If current focus is System4D extension smoke testing, prefer:
- `/status-system4d-extension-handoff`

Actions:
1. Re-run router fixture/tests and workflow gate checks.
2. Verify authoritative semantics remain intact:
   - explicit command `RUN_ID` is canonical
   - `DB_PATH_OR_NONE` semantics unchanged
3. Keep run artifacts under `docs/subagent-runs/<RUN_ID>/` synchronized.

Acceptance:
- Router behavior deterministic under fixture coverage.
- No drift between extension behavior and schema/docs.

---

## 7) Keep docs synchronized with branch reality

Actions:
1. Update together when behavior changes:
   - `README.md`
   - `PROJECT_STATUS.md`
   - `NEXT_STEPS.md`
   - `docs/MLFLOW_OBSERVABILITY_PLAN.md`
   - `docs/RUN_REPLAY_EXPLAIN.md`
2. Ensure status/roadmap language matches actual tested behavior.

Acceptance:
- No contradictory command/flag guidance across canonical docs.
- New context handoff can be copied directly from docs.
