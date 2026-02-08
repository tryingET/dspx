---
summary: "Kickoff ownership matrix and sequencing map for DSPx/MLflow/DSPy observability RFC packet."
read_when:
  - "You need current packet owners, target dates, and draft RFC file locations."
  - "You are coordinating cross-team issue/PR sequencing for observability architecture work."
---

# Observability architecture kickoff (2026-02-07)

## 1) Ownership matrix

| Packet | Owner | Created | Draft review target | RFC file |
|---|---|---|---|---|
| DSPx observability next | `lightningralf (DSPx)` | 2026-02-07 | 2026-02-10 | `docs/rfc/RFC-DSPX-OBS-20260207-mlflow-explain-correlation-v11.md` |
| Upstream MLflow hardening | `lightningralf (DSPx upstream liaison)` | 2026-02-07 | 2026-02-12 | `docs/rfc/RFC-MLFLOW-OBS-20260207-dspy-tracing-hardening.md` |
| Upstream DSPy callback contract | `lightningralf (DSPx upstream liaison)` | 2026-02-07 | 2026-02-12 | `docs/rfc/RFC-DSPY-CALLBACK-20260207-lifecycle-contract-v1.md` |

## 2) Sequencing map (issues/PRs)

1. **DSPx-first contract pinning**
   - finalize DSPx correlation tag/hint schema in RFC
   - open DSPx implementation PR for tags + receipt hints + diagnostics taxonomy

2. **Open upstream issues with concrete reproductions**
   - MLflow issue placeholders:
     - `mlflow/mlflow#TBD-span-noop-safety`
     - `mlflow/mlflow#TBD-dspy-callback-concurrency`
     - `mlflow/mlflow#TBD-dspy-autolog-controls`
   - DSPy issue placeholders:
     - `stanfordnlp/dspy#TBD-callback-metadata-envelope`
     - `stanfordnlp/dspy#TBD-compile-lifecycle-hooks`
     - `stanfordnlp/dspy#TBD-callback-propagation-guarantees`

3. **Upstream PR slicing**
   - MLflow: PR1 warning/no-op safety -> PR2 concurrency state -> PR3 optional controls
   - DSPy: PR1 metadata envelope -> PR2 compile hooks -> PR3 propagation semantics

4. **Downstream reconciliation after upstream releases**
   - bump dependency floors
   - re-run `pre-commit run --all-files`, `just monorepo-check`, `just test`
   - verify no DSPx local workarounds remain in tracing behavior

## 3) Cross-team open questions

- should DSPx remote lookup remain explicit opt-in forever, or conditionally default-on for remote URIs?
- should MLflow no-op span failures be fully silent or debug-level breadcrumbs?
- should DSPy expose callback contract version markers at runtime, or docs/tests only initially?
- what confidence threshold (if any) should promote explain enrichment degradations into strict-mode failures?

## 4) Boundary reminder

- Allowed: `apps/* -> core`
- Forbidden: `core -> apps/*`
- Never import `dspx_forge.*` from core
