---
summary: "Freeze the next post-audit SG2 contract for explaining selected-vs-prior divergence before predictive ranking."
read_when:
  - "You are deciding what comes after the read-only candidate-prior audit."
  - "You need the trust boundary for explaining prior-vs-selection divergence before V8 ranking."
---

ADR 20260328 — Synthesis Evidence Candidate-Prior Divergence Explanation Contract V1
====================================================================================

Status
------
Accepted

Context
-------
`TG13` completed the first bounded consumer of `candidate_winner_priors`: DSPx now emits a read-only `candidate_prior_audit` that records whether the V7-selected `module-gen` candidate aligns with the positive prior support available in the current fan-out.

That closes the first post-selection audit wave, but it also reveals the next SG2 question:
- the repo can now tell when the selected candidate differs from the subset of candidates with replay-healthy exact-match winner support,
- the tempting next move is to let that divergence steer ranking, pruning, or promotion,
- but the current authority boundary still does not justify pre-selection control,
- and the audit alone does not yet explain whether divergence arose because prior-supported candidates failed current runtime checks or because V7 still ranked them below the selected winner.

Two same-day guardrail fixes matter before freezing the next contract:
- `AK-388` made candidate-prior audit rank extraction fail closed under metadata drift,
- `AK-431` made the audit omit rank context when ranked metadata only partially covers the audited comparison set.

Those fixes establish a necessary trust boundary: any post-audit explanation that relies on current ranked order must consume only explicit, complete, trusted rank context and must fail closed otherwise.

Decision
--------
Adopt **Synthesis Evidence Candidate-Prior Divergence Explanation Contract V1** as the next SG2 contract after the read-only candidate-prior audit.

## Scope

This contract applies only to the existing multi-candidate `module-gen` synthesis runtime.

It is intentionally:
- post-selection,
- audit-derived,
- read-only,
- current-run-ranking-aware,
- fail-closed on incomplete explanation metadata,
- explanation-first.

It does **not** authorize predictive ranking, candidate pruning, evaluation reordering, promotion blocking, policy mutation, or V9-style strategy evolution.

## Consumer role

The next post-`TG13` consumer is a **candidate-prior divergence explanation**.

That explanation answers one narrow question:

> When the current fan-out contains positive-prior-supported candidates that V7 did not select, did the divergence occur because those candidates failed current runtime validation, because they still lost under trusted current V7 ranking, or because trusted comparison context is unavailable?

The explanation consumes the already-emitted `candidate_prior_audit` plus trusted current-run ranking/evaluation metadata.
It does not open a second receipt-discovery path and it does not modify selection behavior.

## Inputs

The explanation consumes these inputs only:
1. the current `candidate_prior_audit` payload,
2. the current selected candidate identity,
3. trusted current ranked-candidate metadata for the selected candidate plus every compared positive-prior candidate,
4. explicit current evaluation/ranking metadata for those same candidates (`evaluation_status`, `passed`, `ranking_score`, and summary fields when present).

Authority order remains unchanged:
1. replay-healthy exact-match winner history,
2. degraded exact-match history for diagnostics only,
3. current trusted ranked/evaluation metadata for explanation only,
4. Oracle neighbors for context only.

This contract may reuse only metadata already produced by the current synthesis run.
It must not re-scan receipts, invent fallback rank/score values, or treat adjacent fields as substitutes for missing comparison truth.

## Status model

The explanation must emit exactly one status from this set:
- `candidate_prior_divergence_unavailable` — the audit or trusted ranked/evaluation comparison inputs are missing, malformed, or incomplete for the required comparison set.
- `no_divergence_to_explain` — the audit reports either `selected_matches_positive_winner_history` or `no_positive_prior_candidates`, so there is no post-audit divergence to explain.
- `selected_candidate_prior_unresolved` — the audit reports `selected_candidate_prior_unsupported` or `selected_candidate_prior_degraded`, so DSPx must not over-interpret the current outcome as a clean divergence case.
- `divergence_explained_by_runtime_failures` — divergence exists and every non-selected positive-prior candidate failed current runtime validation.
- `divergence_explained_by_runtime_scoring` — divergence exists, at least one non-selected positive-prior candidate passed current validation, and the selected candidate still outranks all of them under trusted current V7 ranking metadata.
- `divergence_explained_by_mixed_runtime_outcomes` — divergence exists and the non-selected positive-prior candidates split across failure and lower-ranked-pass outcomes.

For V1, these statuses are descriptive only.
They do **not** imply that the selected candidate was wrong, that prior-supported candidates should have been preferred, or that ranking should change.

## Comparison rules

When the audit status is `positive_prior_candidates_present_but_not_selected`, V1 compares the selected candidate against `non_selected_positive_prior_candidates` only.

For each compared candidate:
- use explicit `rank` only when trusted ranked metadata fully covers the selected candidate and every compared positive-prior candidate,
- use explicit `ranking_score` / evaluation status from current-run metadata only,
- classify the candidate as `failed_runtime_validation` when it did not pass the current V7 runtime checks,
- classify the candidate as `lower_ranked_pass` when it passed current checks but still ranked below the selected candidate,
- fail closed to `candidate_prior_divergence_unavailable` if the comparison set lacks complete trusted rank context or the required explicit pass/score fields.

V1 must not derive rank from `ordinal`, infer score from position, or substitute partial ordering for complete comparison truth.

## Minimum payload

The V1 divergence explanation must contain, at minimum:
- `candidate_prior_divergence_explanation_version`
- `status`
- `candidate_prior_audit_status`
- `selected_candidate`:
  - `candidate_id`
  - `variant_id`
  - `variant_origin`
  - `prior_status`
  - `rank`
  - `ranking_score`
- `history_summary`:
  - `exact_match_receipt_count`
  - `positive_evidence_count`
  - `positive_prior_candidate_count`
  - `compared_candidate_count`
- `compared_positive_prior_candidates` — one entry per non-selected positive-prior candidate, each including:
  - `candidate_id`
  - `variant_id`
  - `variant_origin`
  - `rank`
  - `ranking_score`
  - `evaluation_status`
  - `comparison_status`
  - `notes`
- `notes` — bounded explanatory strings

If the explanation cannot be computed, it must fail closed into an explicit unavailable payload rather than silently disappearing or partially filling comparison fields.

## Attachment surfaces

The V1 divergence explanation must attach to the same two runtime surfaces already carrying `synthesis_diagnostics`:
- live `module-gen` artifact metadata,
- persisted `module-gen` receipt metadata.

The implementation may derive the explanation entirely from the current synthesis payload plus `candidate_prior_audit`.
It must not create a hidden second discovery path or silently widen evidence authority beyond the existing candidate-prior payload and audit contracts.

## Trust and interpretation rules

Interpret the explanation as follows:
- `no_divergence_to_explain` means the current run either aligned with positive prior support or had no positive-prior-supported alternative to compare.
- `selected_candidate_prior_unresolved` means current prior authority is too degraded or identity-incomplete to support a clean divergence interpretation.
- `divergence_explained_by_runtime_failures` means prior-supported alternatives existed, but they failed the current runtime gate and therefore were not viable V7 winners.
- `divergence_explained_by_runtime_scoring` means one or more prior-supported alternatives passed, but trusted current V7 scoring/ranking still preferred the selected candidate.
- `divergence_explained_by_mixed_runtime_outcomes` means the positive-prior alternatives split across rejected and lower-ranked-pass outcomes.

The explanation is an observational layer for later governance, not a ranking override.
It may inform whether priors look promising enough to justify a later V8 contract, but it cannot itself change ranking, tie-breaking, pruning, or promotion outcomes.

## Explicit non-goals

This contract explicitly defers:
- feeding candidate priors into ranking scores,
- changing tie-break behavior when a prior-supported candidate loses,
- pruning candidate fan-out before evaluation,
- penalizing candidates because they lack prior support,
- blocking or auto-approving promotion from divergence status,
- using Oracle similarity as enough to create or deny candidate-prior authority,
- mutating strategy or ranking policy from observed divergence patterns.

## First execution slice aligned to this contract

The first AK-backed implementation slice after this ADR is:
- `AK-441` — **Synthesis evidence substrate: emit a read-only candidate-prior divergence explanation for module-gen outcomes**

That slice should materialize the explanation payload on live runtime metadata and persisted receipts while keeping V7 ranking, tie-breaking, and promotion behavior unchanged.

Consequences
------------
Positive:
- DSPx gains a bounded way to inspect *why* prior-supported alternatives lost before governance considers any predictive-ranking authority.
- The repo can now separate divergence caused by current runtime failures from divergence caused by lower current V7 ranking.
- Later V8 work can evaluate candidate-prior usefulness against explicit receipt-backed explanation artifacts instead of anecdotal intuition.

Costs / tradeoffs:
- The new surface is still explanatory only; it makes ranking no cheaper or smarter yet.
- Trust remains deliberately narrow because explanation quality depends on complete current-run metadata.
- Many runs may still resolve to `no_divergence_to_explain` or `candidate_prior_divergence_unavailable`, especially while prior-supported alternatives remain sparse.
