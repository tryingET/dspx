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

## 2) Highest impact: land pending signature-quality CI wiring

Current state:
- Working tree contains uncommitted changes that wire CI enforcement:
  - provider-corpus log builder (`scripts/build_signature_provider_quality_log.py`)
  - strict corpus gate profile (`packages/dspx-core/src/dspx/services/signature_quality_corpus.py`)
  - CI gate run + artifact + PR summary (`.github/workflows/ci.yml`)
- Local validation is green (`pre-commit`, `monorepo-check`, `just test`).

Next actions:
1. Keep the change-set scoped/reviewable and commit the CI-gate wiring slice.
2. Push branch and verify GitHub `core` job behavior:
   - quality gate command runs with `--json --fail-on-gate`
   - `signature-quality-summary` artifact is uploaded
   - PR-facing summary table is rendered in job summary.
3. If needed, run one intentional threshold-tightening test branch to confirm failure path is obvious/auditable.

Acceptance:
- CI fails when corpus quality gates fail.
- CI always publishes gate JSON/log artifacts.
- Reviewers can read a concise gate summary directly in PR/job UI.

---

## 3) Calibrate signature quality gates with runtime telemetry

Current state:
- CI gates are strict and deterministic from provider-corpus fixtures.
- Runtime telemetry exists (`generated/cache/signature/quality_runs.jsonl`) but is not yet used as a CI gate source.

Next actions:
1. Collect rolling telemetry windows from real provider runs (pi-rpc/openrouter/codex/claude/gemini).
2. Recalibrate default/runtime thresholds using observed trend data (not only corpus fixtures).
3. Keep provider corpus growth continuous for new edge-shape regressions.
4. Consider explicit per-provider gate checks once sample volume is stable.

Acceptance:
- Deterministic corpus gates stay strict.
- Runtime thresholds are justified by tracked provider trend data.
- Corpus growth catches provider-specific regressions deterministically.

---

## 4) Extend the same quality contract beyond signatures

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

## 5) Keep forge/core compatibility deterministic (`min` track)

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

## 6) Keep forge/core test slicing robust

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

## 7) Continue MLflow hardening with offline-first CLI behavior

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

## 8) Keep docs and operator guidance synchronized

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

## 9) Upstream leverage path (without adding heavy submodules)

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
