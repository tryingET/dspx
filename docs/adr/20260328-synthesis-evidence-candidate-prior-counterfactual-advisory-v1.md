---
summary: "Freeze the next post-readiness SG2 contract for surfacing bounded counterfactual prior-supported alternatives before any predictive-ranking authority widens."
read_when:
  - "You are deciding what comes after the read-only candidate-prior readiness advisory."
  - "You need the trust boundary for a pre-ranking counterfactual layer that stays descriptive only."
---

ADR 20260328 — Synthesis Evidence Candidate-Prior Counterfactual Advisory Contract V1
======================================================================================

Status
------
Accepted

Context
-------
`TG17` completed the first bounded governance rollup after the candidate-prior audit and divergence-explanation waves: DSPx now emits a read-only `candidate_prior_readiness_advisory` that summarizes whether replay-healthy exact-match history shows priors as convergent, mostly blocked by runtime failures, mostly outscored under trusted current V7 scoring, too sparse to trust, or mixed.

That closes the first post-divergence readiness question, but it leaves the next SG2 authority question open:
- the repo can now tell when candidate priors look historically promising enough that later ranking experiments are thinkable,
- the tempting next move is to let that posture start influencing live candidate ordering or pruning,
- but readiness alone is still a governance summary rather than a current-run decision surface,
- and DSPx still lacks a bounded way to show, for the current run, which positive-prior-supported candidates remain viable under trusted current V7 facts without silently turning that into ranking authority.

The safest next move is therefore still not predictive ranking.
It is a **read-only counterfactual advisory** that surfaces the current run's passing positive-prior-supported alternatives as a bounded alternative-winner set only when the already-emitted readiness and divergence surfaces say such a comparison is meaningful.

Decision
--------
Adopt **Synthesis Evidence Candidate-Prior Counterfactual Advisory Contract V1** as the next SG2 contract after the read-only candidate-prior readiness advisory.

## Scope

This contract applies only to the existing multi-candidate `module-gen` synthesis runtime.

It is intentionally:
- post-readiness,
- post-selection,
- read-only,
- current-run-truth-bounded,
- exact-match-history-gated,
- counterfactual rather than policy-driving.

It does **not** authorize predictive ranking, candidate pruning, evaluation reordering, promotion blocking, policy mutation, or V9-style strategy evolution.

## Consumer role

The next post-`TG17` consumer is a **candidate-prior counterfactual advisory**.

That advisory answers one narrow question:

> When readiness says candidate priors are historically being outscored under trusted V7 facts, does the current run contain positive-prior-supported candidates that still passed current runtime validation and therefore form a bounded alternative-winner set worth later V8 study?

The advisory reuses already-emitted SG2 surfaces plus trusted current-run metadata.
It does not change selection behavior, and it does not create a hidden second ranking path.

## Inputs

The advisory consumes these inputs only:
1. the current `candidate_prior_readiness_advisory` payload,
2. the current `candidate_prior_divergence_explanation` payload,
3. the current `candidate_prior_audit` payload,
4. trusted current ranked/evaluation metadata for the selected candidate plus every non-selected positive-prior candidate in the audit comparison set,
5. bounded receipt-history summary fields already carried by the readiness advisory for explanation only.

Authority order remains unchanged:
1. replay-healthy exact-match winner history as already summarized by the emitted SG2 surfaces,
2. degraded exact-match history for diagnostics only,
3. trusted current ranked/evaluation metadata for current-run counterfactual explanation only,
4. Oracle neighbors for context only.

This contract may reuse only already-emitted SG2 surfaces plus explicit current-run metadata.
It must not rescan receipts, invent synthetic scores, re-rank candidates under a new policy, or treat adjacent fields as substitutes for missing comparison truth.

## Status model

The advisory must emit exactly one status from this set:
- `candidate_prior_counterfactual_unavailable` — the readiness/advisory inputs or trusted current comparison metadata are missing, malformed, or incomplete for the required comparison set.
- `no_counterfactual_signal` — the current run exposes no bounded prior-supported alternative set worth later ranking study because there is no divergence to explain, all positive-prior alternatives failed current runtime validation, or readiness says priors are historically convergent or mostly blocked by runtime failures.
- `counterfactual_signal_sparse` — readiness remains `insufficient_prior_history`, so DSPx must not over-interpret the current run as meaningful predictive signal yet.
- `counterfactual_positive_prior_alternatives_present` — readiness is `priors_mostly_outscored_under_v7`, the current divergence explanation is `divergence_explained_by_runtime_scoring`, and one or more non-selected positive-prior candidates passed current validation under trusted V7 metadata.
- `counterfactual_signal_mixed_or_inconclusive` — usable current/historical evidence exists, but readiness or divergence remains mixed/unresolved enough that no narrower counterfactual claim is trustworthy.

For V1, these statuses are descriptive only.
They do **not** imply that priors should already influence ranking, that the selected candidate was wrong, or that a later ranking contract must be approved.

## Counterfactual rules

V1 evaluates counterfactual signal only over the audit's `non_selected_positive_prior_candidates` comparison set.
For each compared candidate:
- use explicit current `evaluation_status`, `passed`, `rank`, and `ranking_score` only when trusted metadata fully covers the selected candidate and every compared positive-prior candidate,
- classify a candidate as part of the bounded counterfactual alternative set only when it passed current runtime validation,
- never invent a new ordering among alternative candidates beyond the explicit trusted V7 fields already emitted,
- fail closed to `candidate_prior_counterfactual_unavailable` if the required readiness, divergence, audit, or explicit current comparison metadata is missing or incomplete.

V1 maps inputs to statuses deterministically:
- emit `counterfactual_signal_sparse` when readiness is `insufficient_prior_history`,
- emit `no_counterfactual_signal` when readiness is `priors_consistently_convergent` or `priors_mostly_blocked_by_runtime_failures`,
- emit `counterfactual_positive_prior_alternatives_present` only when readiness is `priors_mostly_outscored_under_v7`, divergence is `divergence_explained_by_runtime_scoring`, and at least one compared positive-prior candidate passed current validation,
- emit `counterfactual_signal_mixed_or_inconclusive` when readiness is `priors_mixed_or_inconclusive`, divergence is mixed/unresolved, or the current run exposes both pass-through and unresolved comparison truth that prevents a narrower claim,
- emit `candidate_prior_counterfactual_unavailable` when any required contract surface is unavailable.

V1 must not treat the advisory as a shadow winner selector, a policy override, or a basis for promotion changes.
It surfaces a bounded alternative set for later governance review only.

## Minimum payload

The V1 counterfactual advisory must contain, at minimum:
- `candidate_prior_counterfactual_advisory_version`
- `status`
- `candidate_prior_readiness_status`
- `candidate_prior_divergence_explanation_status`
- `selected_candidate`:
  - `candidate_id`
  - `variant_id`
  - `variant_origin`
  - `rank`
  - `ranking_score`
- `history_summary`:
  - `exact_match_receipt_count`
  - `replay_healthy_receipt_count`
  - `usable_receipt_count`
  - `positive_prior_signal_receipt_count`
  - `passing_positive_prior_candidate_count`
- `counterfactual_positive_prior_candidates` — one entry per passing, non-selected positive-prior candidate in the trusted comparison set, each including:
  - `candidate_id`
  - `variant_id`
  - `variant_origin`
  - `rank`
  - `ranking_score`
  - `evaluation_status`
  - `notes`
- `notes` — bounded explanatory strings

If the advisory cannot be computed, it must fail closed into an explicit unavailable payload rather than silently disappearing or partially filling comparison fields.

## Attachment surfaces

The V1 counterfactual advisory must attach to the same two runtime surfaces already carrying `synthesis_diagnostics`:
- live `module-gen` artifact metadata,
- persisted `module-gen` receipt metadata.

The implementation may derive the advisory only from the current run's trusted metadata plus the SG2 surfaces already emitted for that run.
It must not introduce a hidden second discovery path or silently widen evidence authority beyond the existing candidate-prior payload, audit, divergence-explanation, and readiness-advisory contracts.

## Trust and interpretation rules

Interpret the advisory as follows:
- `no_counterfactual_signal` means the current run does not provide a bounded prior-supported alternative set worth later ranking study under the repo's current trust rules.
- `counterfactual_signal_sparse` means exact-match history is still too sparse to treat the current run as a meaningful predictive signal.
- `counterfactual_positive_prior_alternatives_present` means the current run contains one or more prior-supported candidates that passed current runtime validation but still lost under trusted V7 scoring, making later offline ranking study thinkable but still not authorized.
- `counterfactual_signal_mixed_or_inconclusive` means the current and historical picture is too mixed to support a narrower counterfactual claim.

The advisory is a governance aid, not a ranking override.
It may help decide whether DSPx should later define an offline/shadow predictive-ranking contract, but it cannot itself change ranking, tie-breaking, pruning, or promotion outcomes.

## Explicit non-goals

This contract explicitly defers:
- feeding candidate priors into live ranking scores,
- changing tie-break behavior when prior-supported candidates lose,
- pruning candidate fan-out before evaluation,
- auto-promoting or blocking promotion from counterfactual status,
- inventing synthetic score deltas or alternate winner decisions,
- using Oracle similarity as enough to create or deny counterfactual authority,
- mutating strategy or ranking policy from observed counterfactual patterns.

## First execution slice aligned to this contract

The first AK-backed implementation slice after this ADR is:
- `AK-473` — **Synthesis evidence substrate: emit a read-only candidate-prior counterfactual advisory for module-gen outcomes**

That slice should materialize the counterfactual advisory on live runtime metadata and persisted receipts while keeping V7 ranking, tie-breaking, and promotion behavior unchanged.

Consequences
------------
Positive:
- DSPx gains a bounded bridge from descriptive readiness posture to a concrete current-run counterfactual surface without granting priors ranking authority yet.
- The repo can now distinguish “priors are interesting in theory” from “the current run contained viable prior-supported alternatives under trusted V7 facts.”
- Later V8 governance work can point at explicit receipt-backed counterfactual artifacts instead of jumping directly from readiness posture into live ranking experiments.

Costs / tradeoffs:
- The advisory is still observational only; it does not make ranking cheaper or smarter yet.
- Counterfactual quality depends on both historical readiness posture and complete trusted current-run comparison metadata.
- Many runs may still resolve to `no_counterfactual_signal`, `counterfactual_signal_sparse`, or `counterfactual_signal_mixed_or_inconclusive`.
