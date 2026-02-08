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

## 2) Architecture draft kickoff (domain experts)

Prepared handoff packet:
- `docs/OBSERVABILITY_ARCH_DRAFTS.md`
- `docs/ARCH_DRAFT_DSPX_NEXT.md`
- `docs/ARCH_DRAFT_UPSTREAM_MLFLOW.md`
- `docs/ARCH_DRAFT_UPSTREAM_DSPY.md`
- templates:
  - `docs/RFC_TEMPLATE_DSPX_NEXT.md`
  - `docs/RFC_TEMPLATE_UPSTREAM_MLFLOW.md`
  - `docs/RFC_TEMPLATE_UPSTREAM_DSPY.md`

Current kickoff state:
- Ownership matrix + sequencing map created:
  - `docs/rfc/OBSERVABILITY_KICKOFF_20260207.md`
- RFC drafts instantiated from templates:
  - `docs/rfc/RFC-DSPX-OBS-20260207-mlflow-explain-correlation-v11.md`
  - `docs/rfc/RFC-MLFLOW-OBS-20260207-dspy-tracing-hardening.md`
  - `docs/rfc/RFC-DSPY-CALLBACK-20260207-lifecycle-contract-v1.md`
- Each draft includes A/B/C options + chosen direction + open questions.

Next actions:
1. File upstream umbrella issues from RFC placeholders (MLflow + DSPy).
2. Convert sequencing map into concrete PR checklists with maintainer feedback.
3. Sync packet links in handoff/status docs once issue IDs exist.
4. Keep boundary invariant checks green while implementing DSPx-side PRs.

Acceptance:
- Packet owners and target dates are explicit.
- Draft RFC files exist and are review-ready.
- Upstream-facing RFCs include issue/PR sequencing notes.
- Cross-team questions are tracked explicitly.

---

## 3) MLflow lifecycle follow-through (post-hardening)

Current state:
- Local default backend policy is now deterministic: `sqlite:///mlflow.db`.
- Run start semantics are explicit (bootstrap does not start runs).
- DSPy autolog defaults are tuned to avoid GEPA span-start warning floods.
- URI modes (`file`, `sqlite`, `http`) are covered in regression tests.
- Explain local enrichment resolves sqlite custom artifact roots via MLflow experiment metadata.

Next actions:
1. Add optional trace opt-in recipe examples for CI/local (`DSPX_MLFLOW_DSPY_*`).
2. Split and document ownership explicitly:
   - DSPx: enrichment orchestration + correlation tags/diagnostics
   - MLflow upstream: span no-op safety + callback parallel-state hardening
   - DSPy upstream: callback metadata/lifecycle/context contract (no backend expansion)
3. Decide whether remote MLflow health checks should be added as explicit preflight
   command(s) vs left to user infra.
4. Extend explain enrichment beyond local artifact linkage for remote backends.

Acceptance:
- Default/offline path stays deterministic and quiet.
- Operators have explicit opt-in knobs for richer tracing.
- Ownership split is documented and mapped to issue/PR tracks.
- Remote-mode expectations are documented and test-scoped.

---

## 4) Highest impact now: enforce replay strictness + compatibility policy

Current state:
- `dspx run replay --check-only` and `dspx run explain` are live and tested.
- Drift coverage now includes missing cache file, wrong cache kind folder,
  malformed cache JSON, output drift, and cache provenance drift.
- Replay JSON now emits stable diagnostics (`error_codes`, `error_details`).
- Explain now surfaces replay drift explicitly (`replay_status`,
  `replay_error_codes`, `replay_error_details`) and returns `degraded` on drift.

Next actions:
1. Define strictness policy for replay diagnostics (`warn` vs `error`) and add
   optional strict-mode gate semantics.
2. Add regression coverage that snapshots expected issue-code sets per drift
   class to prevent accidental taxonomy churn.
3. Document compatibility policy for legacy receipt/cache shapes before enabling
   stricter replay enforcement by default.

Acceptance:
- Replay diagnostics remain deterministic/offline and taxonomy-stable.
- Explain continues to classify `ok` vs `degraded` vs `invalid` correctly.
- Strictness behavior is explicit, documented, and test-guarded.

---

## 5) Reconcile legacy/LM cache-key provenance edge cases

Current state:
- Replay recomputes cache key from receipt replay inputs.
- Template paths are deterministic; legacy/LM signatures may have historical
  key-shape drift risk.

Next actions:
1. Audit historical signature receipts + LM cache key payload shapes.
2. Decide policy: normalize writer payloads vs add compatibility fallback map.
3. Add regression tests that pin accepted compatibility behavior.

Acceptance:
- Replay key/provenance checks are consistent across template + LM paths.
- No false drift for known historical receipt shapes.
- Compatibility behavior is documented and test-guarded.

---

## 6) Harden receipt contract coverage/governance

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

## 7) Extend quality contract beyond signatures

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

## 8) Calibrate runtime telemetry thresholds

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

## 9) Keep forge/core compatibility deterministic (`min` track)

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

## 10) Keep docs and operator guidance synchronized

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
