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

## 2) Highest impact: keep local-native docs command-accurate

Current state:
- README local-native workflow rewrite is now in place
  (signature/refine -> module -> GEPA -> replay/explain).
- Examples were cross-checked against current `dspx` CLI help.

Next actions:
1. Re-verify README command examples on every CLI flag/behavior change.
2. Keep signature quality-summary and provider-corpus gate examples aligned
   with the CI profile.
3. Keep `PROJECT_STATUS.md` / `NEXT_STEPS.md` synced to README framing.

Acceptance:
- README commands run as written (modulo provider credentials/live access).
- No conflicting guidance across README/STATUS/NEXT_STEPS.

---

## 3) Extend quality contract beyond signatures

Why now:
- Signature/refine path is hardened first; module/codegen/mermaid should
  converge on same quality posture.

Next actions:
1. Reuse validation/scoring primitives for LM-backed `module-gen` and
   `codegen` outputs.
2. Add smoke/import checks where generated outputs are executable/importable.
3. Define per-service acceptance metrics in one shared doc section.

Acceptance:
- Core generative services share quality vocabulary + gates.
- Regressions are blocked by tests, not discovered in runtime usage.

---

## 4) Calibrate runtime telemetry thresholds

Current state:
- CI gate profile is deterministic from provider-corpus fixtures.
- Runtime telemetry exists (`generated/cache/signature/quality_runs.jsonl`).

Next actions:
1. Collect rolling telemetry windows from real provider runs
   (pi-rpc/openrouter/codex/claude/gemini).
2. Compare corpus profile vs runtime profile and tune defaults deliberately.
3. Add explicit per-provider reporting if sample volume supports it.

Acceptance:
- Thresholds are backed by observed provider trend data.
- Corpus gates remain strict and deterministic.

---

## 5) Tighten replay + explain UX

Current state:
- Replay source-of-truth is local artifacts/manifests/cache.
- MLflow is optional explainability sink.

Next actions:
1. Document canonical replay path from generated artifacts + cache metadata.
2. Define/implement first-class replay/explain CLI surface incrementally.
3. Add tests that verify replay flows remain valid with `MLFLOW_ENABLE=0`.

Acceptance:
- Replay does not depend on MLflow availability.
- Explainability remains additive, never execution-gating.

---

## 6) Keep forge/core compatibility deterministic (`min` track)

Why:
- CI `min` compatibility is only as strict as remote lower-bound tag
  availability.

Next actions:
1. Ensure remote contains `dspx-core-v0.1.0` (and future lower-bound tags).
2. Keep release checklist note that lower-bound tags are part of compat
   contract.
3. Re-run `just forge-core-compat-matrix` after any bound bump.

Acceptance:
- Remote CI `forge-core-compat` `min` track is deterministic.
- Operators have clear lower-bound tag expectations.

---

## 7) Keep docs and operator guidance synchronized

Next actions:
1. Keep these docs aligned on each behavior change:
   - `README.md`
   - `PROJECT_STATUS.md`
   - `NEXT_STEPS.md`
   - `docs/MONOREPO_TRANSITION.md`
   - `docs/SIGNATURE_NATIVE_PIPELINE.md`
   - `docs/MLFLOW_OBSERVABILITY_PLAN.md`
2. Keep root `PROJECT_STATUS.md` and `NEXT_STEPS.md` as canonical
   status/roadmap docs.

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
2. Keep upstream deps as sibling clones under `~/programming/upstream`
   (not repo submodules), including `attachments`, `dspy`, `mlflow`.
3. Prefer upstream PR + released version bump over long-lived local forks.

Acceptance:
- Upstream fixes can be developed/tested quickly.
- Repo complexity does not increase via submodule maintenance burden.
