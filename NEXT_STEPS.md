# Next Steps

Current branch context: `main`.

## Boundary invariant (non-negotiable)

- Allowed: `apps/* -> core`
- Forbidden: `core -> apps/*`
- Never import `dspx_forge.*` from core code.

Acceptance:
- `just monorepo-check` remains green.
- No new reverse-dependency imports in diffs.

---

## 1) Keep baseline stable (always)

Run routinely:
- `pre-commit run --all-files`
- `just monorepo-check`
- `just test`

Optional live sanity (opt-in):
- `DSPX_RUN_LIVE_TESTS=1 just pi-live-smoke`
- `DSPX_RUN_LIVE_TESTS=1 uv run -m pytest -q tests/test_optimize_gepa_codex_live.py -rs`

Acceptance:
- Quality gates stay green.
- Offline/deterministic defaults remain intact.

---

## 2) Highest impact: lock strict remote min-compat reproducibility

Why first:
- CI `min` forge/core compatibility is only as strict as remote tag availability.

Next actions:
1. Ensure remote contains `dspx-core-v0.1.0` (and future lower-bound tags).
2. Add/keep release checklist note that lower-bound tags are part of compat contract.
3. Re-verify `just forge-core-compat-matrix` after any dependency bound bump.

Acceptance:
- Remote CI `forge-core-compat` `min` track is deterministic.
- Lower-bound tag is present and documented for operators.

---

## 3) Keep forge/core test slicing robust

Current state:
- Slices are marker-based (`pytest.mark.forge`) instead of name-based `-k` filters.

Next actions:
1. Require `pytest.mark.forge` for new Forge and boundary-focused tests.
2. Periodically spot-check collected tests:
   - `uv run -m pytest tests -m "forge" --collect-only -q`
3. If marker maintenance cost grows, evaluate path-based split as a follow-up (without regressing clarity).

Acceptance:
- `just test-core` and `just test-forge` remain stable across test additions.
- No accidental slice drift from unmarked Forge tests.

---

## 4) Continue MLflow hardening with offline-first CLI behavior

Current state:
- Read-only metadata commands skip MLflow bootstrap and stay instant.

Next actions:
1. Keep read-only command set free of eager tracing initialization.
2. For mutating/generative flows, keep tracing best-effort/non-blocking.
3. Extend regression tests when adding new read-only command groups.

Acceptance:
- Read-only commands do not stall on unreachable remote tracking URIs.
- MLflow remains useful for generative/mutating flows when enabled.

---

## 5) Keep docs and operator guidance synchronized

Next actions:
1. Keep these docs aligned with runtime behavior on each structural change:
   - `README.md`
   - `PROJECT_STATUS.md`
   - `NEXT_STEPS.md`
   - `docs/MONOREPO_TRANSITION.md`
   - `docs/MLFLOW_OBSERVABILITY_PLAN.md`
   - `docs/UPSTREAM_CONTRIBUTING_WORKFLOW.md`
2. Avoid duplicate status/roadmap docs; keep root `PROJECT_STATUS.md` and `NEXT_STEPS.md` as canonical.

Acceptance:
- No conflicting setup/command guidance across canonical docs.
- Handoff context can be copied from docs without caveats.

---

## 6) Upstream leverage path (without adding new heavy submodules)

Next actions:
1. Use sibling clones + editable installs for upstream debugging/patching:
   - `just upstream-link-dspy path=...`
   - `just upstream-link-mlflow path=...`
   - `just upstream-reset`
2. Keep `vibe-dspy` + `attachments` as sibling clones under `~/programming/upstream` (not repo submodules).
3. Prefer upstream PR + released version bump over long-lived local forks.

Acceptance:
- Upstream fixes can be developed/tested quickly.
- Repo complexity does not increase via extra submodule maintenance burden.
