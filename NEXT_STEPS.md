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
- `DSPX_RUN_LIVE_TESTS=1 uv run -m pytest -q tests/test_pi_rpc_provider_live.py -rs`

Acceptance:
- Quality gates stay green.
- Offline/deterministic defaults remain intact.

---

## 2) Highest impact: keep signature quality telemetry operational (now implemented)

Current state:
- Native signature generation/refine is spec-first and capability-aware.
- Validation/smoke scoring and bounded retries are active.
- Golden corpus + provider-shaped corpus cases exist.
- Run telemetry and promotion-gate summary command exist:
  - `dspx signature quality-summary`
  - metrics: fallback-rate, attempts-used distribution, validation/smoke pass rates.

Next actions:
1. Wire quality-summary JSON output into CI artifacts and PR surfaces.
2. Tune gate thresholds with real provider data (pi-rpc/openrouter/codex/claude/gemini).
3. Keep corpus growth continuous for new provider edge behaviors.

Acceptance:
- Quality drift is visible before user-facing regressions.
- Retry/fallback behavior remains bounded and auditable.
- Corpus growth catches provider-specific regressions deterministically.

---

## 3) Extend the same quality contract beyond signatures

Why now:
- Signature/refine path is hardened first; module/codegen/mermaid should converge on the same quality posture.

Next actions:
1. Reuse validation/scoring primitives for LM-backed `module-gen` and `codegen` flows.
2. Add post-generation smoke checks where outputs are executable/importable.
3. Define per-service acceptance metrics in one shared doc section.

Acceptance:
- Core generative services use consistent quality gates and metrics vocabulary.
- New regressions are blocked by tests, not discovered in runtime usage.

---

## 4) Keep forge/core compatibility deterministic (`min` track)

Why:
- CI `min` compatibility is only as strict as remote lower-bound tag availability.

Next actions:
1. Ensure remote contains `dspx-core-v0.1.0` (and future lower-bound tags).
2. Keep release checklist note that lower-bound tags are part of compat contract.
3. Re-run `just forge-core-compat-matrix` after any bound bump.

Acceptance:
- Remote CI `forge-core-compat` `min` track is deterministic.
- Operators have clear lower-bound tag expectations.

---

## 5) Keep forge/core test slicing robust

Current state:
- Slices are marker-based (`pytest.mark.forge`) instead of name-based `-k` filters.

Next actions:
1. Require `pytest.mark.forge` for new Forge/boundary tests.
2. Periodically spot-check collected tests:
   - `uv run -m pytest tests -m "forge" --collect-only -q`
3. Evaluate path-based split later only if marker maintenance cost grows.

Acceptance:
- `just test-core` and `just test-forge` remain stable as tests grow.
- No accidental slice drift from unmarked Forge tests.

---

## 6) Continue MLflow hardening with offline-first CLI behavior

Current state:
- Read-only metadata commands skip MLflow bootstrap and stay instant.

Next actions:
1. Keep read-only command sets free of eager tracing initialization.
2. Keep tracing best-effort/non-blocking for mutating/generative flows.
3. Extend regression tests when adding new read-only command groups.

Acceptance:
- Read-only commands do not stall on unreachable tracking URIs.
- MLflow remains an explainability sink, never an execution gate.

---

## 7) Keep docs and operator guidance synchronized

Next actions:
1. Keep these docs aligned on each behavior change:
   - `README.md`
   - `PROJECT_STATUS.md`
   - `NEXT_STEPS.md`
   - `docs/MONOREPO_TRANSITION.md`
   - `docs/MLFLOW_OBSERVABILITY_PLAN.md`
   - `docs/SIGNATURE_NATIVE_PIPELINE.md`
2. Keep root `PROJECT_STATUS.md` and `NEXT_STEPS.md` as canonical status/roadmap docs.

Acceptance:
- No conflicting setup/command guidance across canonical docs.
- Handoff context can be copied directly from docs.

---

## 8) Upstream leverage path (without adding heavy submodules)

Next actions:
1. Use sibling clones + editable installs for upstream debugging/patching:
   - `just upstream-link-dspy path=...`
   - `just upstream-link-mlflow path=...`
   - `just upstream-reset`
2. Keep upstream deps as sibling clones under `~/programming/upstream` (not repo submodules), including `attachments`, `dspy`, `mlflow`.
3. Prefer upstream PR + released version bump over long-lived local forks.

Acceptance:
- Upstream fixes can be developed/tested quickly.
- Repo complexity does not increase via submodule maintenance burden.
