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

## 2) Highest impact now: ship `run explain` local-first MVP

Current state:
- Replay verification is now first-class (`dspx run replay --check-only`).
- Explainability data already exists in receipts/meta/manifests.
- MLflow remains optional and must stay additive only.

Next actions:
1. Add `dspx run explain --from <receipt>` in core CLI (`dspx run ...`).
2. Build explanation output from local receipt/manifest first.
3. Add optional MLflow enrichment mode that never blocks baseline output.
4. Add tests for no-MLflow/no-network behavior and graceful enrichment fallback.

Acceptance:
- Explain command works with `MLFLOW_ENABLE=0`.
- Output clearly separates local facts vs optional traced context.
- Non-local enrichment failures never fail baseline explain output.

---

## 3) Harden `run replay` drift coverage + provenance strictness

Current state:
- `dspx run replay --from <receipt> --check-only` validates schema, output hash,
  cache linkage, and cache provenance.

Next actions:
1. Add focused tests for additional drift classes (missing cache file,
   wrong kind folder, malformed cache JSON).
2. Audit/reconcile legacy LM signature cache-key shape vs replay recomputation.
3. Add optional strict mode once more artifact producers emit stable receipts.

Acceptance:
- Replay checks remain deterministic and offline in CI.
- Drift diagnostics stay actionable and machine-readable.
- Replay key/provenance checks are consistent across template + LM paths.

---

## 4) Harden receipt contract coverage/governance

Current state:
- Receipt helper is centralized, but not all artifact producers are guaranteed
  on the same contract yet.

Next actions:
1. Audit remaining emitters (`mermaid`, optimize artifacts, any legacy paths).
2. Ensure each producer either emits v1 receipts or explicit manifests.
3. Add regression tests for schema compatibility + required fields.

Acceptance:
- Receipt/manifests are consistent across core generators.
- Backward-compatible fields (`hash`, `cache_key`, `cache_file`,
  `cache_enabled`) stay stable.

---

## 5) Extend quality contract beyond signatures

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

## 6) Calibrate runtime telemetry thresholds

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

## 7) Keep forge/core compatibility deterministic (`min` track)

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

## 8) Keep docs and operator guidance synchronized

Next actions:
1. Keep these docs aligned on each behavior change:
   - `README.md`
   - `PROJECT_STATUS.md`
   - `NEXT_STEPS.md`
   - `docs/MONOREPO_TRANSITION.md`
   - `docs/SIGNATURE_NATIVE_PIPELINE.md`
   - `docs/MLFLOW_OBSERVABILITY_PLAN.md`
   - `docs/RUN_REPLAY_EXPLAIN.md`
2. Keep root `PROJECT_STATUS.md` and `NEXT_STEPS.md` as canonical
   status/roadmap docs.

Acceptance:
- No conflicting setup/command guidance across canonical docs.
- Handoff context can be copied directly from docs.
