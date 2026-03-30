---
summary: "Freeze the next SG2 contract for a bounded read-only shadow predictive-ranking advisory before any live evidence-aware ranking authority widens."
read_when:
  - "You are deciding what comes after the read-only candidate-prior counterfactual advisory."
  - "You need the trust boundary for a first offline/shadow predictive-ranking surface that stays descriptive only."
---

ADR 20260329 — Synthesis Evidence Shadow Predictive-Ranking Advisory Contract V1
=================================================================================

Status
------
Accepted

Context
-------
`TG19` completed the first read-only current-run counterfactual layer for SG2: DSPx can now surface when replay-healthy exact-match prior-supported alternatives were present, passed current validation, and still lost under trusted V7 scoring.

That closes the first counterfactual question, but it also leaves the next SG2 authority question open:
- the repo can now tell when prior-supported alternatives were viable in the current run,
- the tempting next move is to let that signal directly influence live ranking or pruning,
- but the current SG2 surfaces are still descriptive and governance-bounded,
- and DSPx still lacks a named, receipt-backed way to ask what a bounded prior-aware ranking experiment *would* have done before any live policy changes are allowed.

The safest next move is therefore still not live predictive ranking.
It is a **read-only shadow predictive-ranking advisory** that computes a bounded shadow preference for the current run from already-emitted SG2 surfaces plus trusted current metadata, then records whether that shadow preference matches or diverges from the trusted V7 winner.

Decision
--------
Adopt **Synthesis Evidence Shadow Predictive-Ranking Advisory Contract V1** as the next SG2 contract after the read-only candidate-prior counterfactual advisory.

## Scope

This contract applies only to the existing multi-candidate `module-gen` synthesis runtime.

It is intentionally:
- post-counterfactual,
- read-only,
- current-run bounded,
- exact-match-history-gated,
- shadow/offline rather than live,
- descriptive rather than policy-driving.

It does **not** authorize live predictive ranking, candidate pruning, tie-break changes, promotion blocking, policy mutation, or V9-style self-evolution.

## Consumer role

The next post-`TG19` consumer is a **shadow predictive-ranking advisory**.

That advisory answers one narrow question:

> If DSPx applied a bounded, prior-aware shadow preference to the current run for governance inspection only, would that shadow choice still match the trusted V7 winner, or would it surface a prior-supported passing alternative worth later governed evaluation?

The advisory produces a named shadow result for the current run without changing the live selected artifact.
It exists to create a receipt-backed bridge between descriptive SG2 surfaces and any later governed ranking experiment.

## Inputs

The advisory consumes these inputs only:
1. the current `candidate_winner_priors` payload,
2. the current `candidate_prior_audit` payload,
3. the current `candidate_prior_divergence_explanation` payload,
4. the current `candidate_prior_readiness_advisory` payload,
5. the current `candidate_prior_counterfactual_advisory` payload,
6. trusted current ranked/evaluation metadata for the selected candidate and every current candidate considered by the shadow comparison,
7. bounded request/history summary fields already carried by the SG2 surfaces for explanation only.

Authority order remains unchanged:
1. replay-healthy exact-match winner history,
2. degraded exact-match history for diagnostics only,
3. trusted current ranked/evaluation metadata for current-run comparison only,
4. Oracle neighbors for context only.

This contract may reuse only already-emitted SG2 surfaces plus explicit current-run metadata.
It must not rescan receipts under a new authority model, invent synthetic scores, or silently promote Oracle similarity to ranking authority.

## Shadow comparison set

V1 evaluates shadow signal only over current candidates that satisfy all of the following:
- candidate identity is complete enough for the prior surfaces to reason about it,
- trusted current evaluation metadata is present,
- the candidate passed the current runtime validation/evaluation boundary,
- the candidate appears in the current comparison set already exposed by the SG2 audit/counterfactual surfaces.

Candidates that fail current runtime validation may still explain why the advisory resolved to a non-positive status, but they cannot become the shadow-preferred candidate.

## Shadow preference rule

V1 uses a bounded descriptive shadow preference, not a live ranking policy.

Within the current passing comparison set:
1. prefer candidates with `matches_positive_winner_history`,
2. if multiple passing candidates share that positive prior status, keep their trusted current V7 rank order,
3. if no passing candidate has positive winner history, the shadow advisory cannot surface a positive prior-aware alternative.

The trusted live V7 winner remains the real winner regardless of the shadow result.
The shadow preference is recorded for governance inspection only.

## Status model

The advisory must emit exactly one status from this set:
- `shadow_predictive_ranking_unavailable` — required SG2 surfaces or trusted current comparison metadata are missing, malformed, or incomplete.
- `no_shadow_predictive_signal` — the current run provides no passing positive-prior comparison set that can support a bounded shadow preference.
- `shadow_predictive_ranking_matches_v7` — the bounded shadow preference resolves to the same candidate as the trusted current V7 winner.
- `shadow_predictive_ranking_prefers_positive_prior_alternative` — the bounded shadow preference resolves to a different passing positive-prior candidate than the trusted current V7 winner.
- `shadow_predictive_ranking_mixed_or_inconclusive` — usable evidence exists, but sparse or mixed SG2 posture prevents a narrower shadow claim.

For V1, these statuses are descriptive only.
They do **not** imply that the live winner was wrong, that priors should already influence production ranking, or that a later governed ranking contract must be approved.

## Deterministic mapping rules

V1 maps inputs to statuses deterministically:
- emit `shadow_predictive_ranking_unavailable` when any required SG2 surface or trusted current comparison metadata is unavailable,
- emit `no_shadow_predictive_signal` when no passing candidate in the comparison set has `matches_positive_winner_history`,
- emit `shadow_predictive_ranking_matches_v7` when the shadow-preferred candidate resolves to the same candidate as the trusted V7 winner,
- emit `shadow_predictive_ranking_prefers_positive_prior_alternative` only when a different passing candidate with positive winner history becomes shadow-preferred under the bounded rule,
- emit `shadow_predictive_ranking_mixed_or_inconclusive` when SG2 surfaces remain sparse or mixed enough that V1 cannot make a narrower shadow claim without widening authority.

V1 must fail closed when SG2 surfaces disagree about the comparison set, selected-candidate identity, or prior status of the relevant candidates.

## Minimum payload

The V1 shadow predictive-ranking advisory must contain, at minimum:
- `shadow_predictive_ranking_advisory_version`
- `status`
- `shadow_policy_id`
- `selected_candidate`:
  - `candidate_id`
  - `variant_id`
  - `variant_origin`
  - `rank`
  - `ranking_score`
  - `candidate_prior_status`
- `shadow_preferred_candidate`:
  - `candidate_id`
  - `variant_id`
  - `variant_origin`
  - `rank`
  - `ranking_score`
  - `candidate_prior_status`
  - `match_reason`
- `history_summary`:
  - `exact_match_receipt_count`
  - `replay_healthy_receipt_count`
  - `positive_prior_signal_receipt_count`
  - `passing_positive_prior_candidate_count`
- `notes`

If the advisory cannot be computed, it must fail closed into an explicit unavailable payload rather than silently disappearing or partially filling comparison fields.

## Attachment surfaces

The V1 shadow predictive-ranking advisory must attach to the same two runtime surfaces already carrying `synthesis_diagnostics`:
- live `module-gen` artifact metadata,
- persisted `module-gen` receipt metadata.

The implementation may derive the advisory only from the current run's trusted metadata plus the SG2 surfaces already emitted for that run.
It must not introduce a hidden second discovery path or silently widen evidence authority beyond the existing candidate-prior payload, audit, divergence, readiness, and counterfactual contracts.

## Trust and interpretation rules

Interpret the advisory as follows:
- `no_shadow_predictive_signal` means the current run still lacks a bounded prior-supported passing comparison set worth shadow ranking study.
- `shadow_predictive_ranking_matches_v7` means the bounded prior-aware shadow preference agrees with the trusted current winner, so the current run does not argue for a different governed ranking outcome.
- `shadow_predictive_ranking_prefers_positive_prior_alternative` means the current run contains a passing positive-prior candidate that the bounded shadow rule would have preferred, making later governed ranking evaluation thinkable but still not authorized.
- `shadow_predictive_ranking_mixed_or_inconclusive` means the SG2 surfaces are too sparse or mixed to support a narrower shadow claim.

The advisory is a governance aid, not a live policy override.
It may help decide whether DSPx should later define a governed ranking-evaluation contract, but it cannot itself change ranking, tie-breaking, pruning, promotion, or policy selection.

## Explicit non-goals

This contract explicitly defers:
- feeding the shadow result into live ranking scores,
- pruning candidate fan-out before evaluation,
- blocking promotion when the shadow result disagrees with V7,
- treating degraded history or Oracle similarity as enough to create shadow authority,
- mutating strategy or ranking policy from observed shadow results,
- auto-promoting the shadow-preferred candidate,
- skipping current validation because prior evidence looked strong.

## First execution slice aligned to this contract

The first AK-backed implementation slice after this ADR is:
- `AK-562` — **Synthesis evidence substrate: emit a read-only shadow predictive-ranking advisory for module-gen outcomes**

That slice should materialize the advisory on live runtime metadata and persisted receipts while keeping live V7 ranking, tie-breaking, pruning, and promotion behavior unchanged.

Consequences
------------
Positive:
- DSPx gains a named, receipt-backed bridge from descriptive SG2 evidence into the first shadow predictive-ranking question without granting live ranking authority yet.
- The repo can now distinguish “positive priors existed” from “a bounded prior-aware shadow rule would actually have preferred a different current passing candidate.”
- Later governed ranking-evaluation work can point at explicit shadow receipts instead of jumping directly from counterfactual evidence into live policy changes.

Costs / tradeoffs:
- The advisory is still observational only; it does not make live ranking cheaper or smarter yet.
- Shadow quality depends on complete, trusted current comparison metadata plus the bounded SG2 surfaces already emitted.
- Many runs may still resolve to `no_shadow_predictive_signal` or `shadow_predictive_ranking_mixed_or_inconclusive`.
