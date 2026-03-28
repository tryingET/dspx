---
summary: "Freeze the next post-divergence SG2 contract for judging whether candidate priors look promising enough to justify later ranking experiments."
read_when:
  - "You are deciding what comes after the read-only candidate-prior divergence explanation."
  - "You need the trust boundary for summarizing prior usefulness before any predictive-ranking contract."
---

ADR 20260328 — Synthesis Evidence Candidate-Prior Readiness Advisory Contract V1
=================================================================================

Status
------
Accepted

Context
-------
`TG15` completed the first bounded explanation layer after candidate-prior divergence: DSPx can now tell, for a single `module-gen` run, whether prior-supported candidates were not selected because they failed current runtime validation, because they still lost under trusted current V7 ranking, because outcomes were mixed, or because trusted comparison context was unavailable.

That closes the first post-audit explanation wave, but it still leaves the next SG2 governance question open:
- the repo now has per-run receipt-backed evidence about how priors relate to current V7 outcomes,
- the tempting next move is to let prior support start influencing ranking or pruning,
- but one explained divergence case is still not enough to justify widening authority,
- and DSPx does not yet have a bounded way to summarize whether priors look consistently helpful, mostly blocked by runtime failures, mostly defeated by current V7 scoring, or simply too sparse to trust.

The safest next move is therefore still not predictive ranking.
It is a **read-only readiness advisory** that rolls up the already-emitted candidate-prior audit and divergence-explanation surfaces across replay-healthy exact-match history, so governance can inspect whether priors look promising enough to merit a later ranking contract.

Decision
--------
Adopt **Synthesis Evidence Candidate-Prior Readiness Advisory Contract V1** as the next SG2 contract after the read-only candidate-prior divergence explanation.

## Scope

This contract applies only to the existing multi-candidate `module-gen` synthesis runtime.

It is intentionally:
- post-divergence,
- retrospective,
- read-only,
- exact-match-history-bounded,
- receipt-backed,
- governance-facing.

It does **not** authorize predictive ranking, candidate pruning, evaluation reordering, promotion blocking, policy mutation, or V9-style strategy evolution.

## Consumer role

The next post-`TG15` consumer is a **candidate-prior readiness advisory**.

That advisory answers one narrow question:

> Across replay-healthy exact-match `module-gen` history already carrying candidate-prior audit and divergence-explanation surfaces, do candidate priors currently look consistently aligned, mostly blocked by runtime failures, mostly defeated by current V7 scoring, too sparse to interpret, or mixed enough that DSPx should stay descriptive only?

The advisory consumes only already-persisted read-only SG2 surfaces.
It does not create a new historical discovery authority, and it does not change current selection behavior.

## Inputs

The advisory consumes these inputs only:
1. replay-healthy exact-match receipt matches already retrieved for the current request,
2. each matched receipt's persisted `candidate_prior_audit` payload,
3. each matched receipt's persisted `candidate_prior_divergence_explanation` payload,
4. bounded receipt identity fields for attribution only (`receipt_path`, `created_at`, selected candidate identity, and request tuple identity).

Authority order remains unchanged:
1. replay-healthy exact-match receipts,
2. degraded exact-match history for diagnostics only,
3. persisted candidate-prior audit and divergence-explanation surfaces for explanation only,
4. Oracle neighbors for context only.

This contract may reuse only persisted surfaces already emitted by earlier SG2 slices.
It must not re-score historical candidates, reconstruct missing divergence classifications, or invent readiness from partial receipt state.

## Status model

The advisory must emit exactly one status from this set:
- `candidate_prior_readiness_unavailable` — the exact-match receipt set cannot support a bounded rollup because exact-match receipt scan errors exist or one or more replay-healthy exact-match receipts are missing, malformed, or unusable for the required persisted audit/explanation surfaces.
- `insufficient_prior_history` — exact-match history exists, but after excluding unusable receipts there are fewer than three usable replay-healthy receipts or fewer than two receipts with positive-prior signal to characterize candidate-prior posture.
- `priors_consistently_convergent` — usable history overwhelmingly shows either selected-prior alignment or no divergence to explain.
- `priors_mostly_blocked_by_runtime_failures` — usable divergence cases predominantly resolve to runtime-failure explanations, suggesting prior-supported alternatives often are not viable current winners.
- `priors_mostly_outscored_under_v7` — usable divergence cases predominantly resolve to lower-ranked-pass / runtime-scoring explanations, suggesting priors may contain signal worth studying later without granting authority yet.
- `priors_mixed_or_inconclusive` — usable history exists, but the rollup splits across unresolved, mixed-runtime, runtime-failure, and runtime-scoring outcomes such that no narrower readiness posture is trustworthy.

For V1, these statuses are descriptive only.
They do **not** imply that priors should already influence ranking, that V7 is wrong, or that a later ranking contract must be approved.

## Rollup rules

V1 computes readiness over replay-healthy exact-match receipts only.
If exact-match receipt scan errors exist, the advisory must fail closed to `candidate_prior_readiness_unavailable` rather than silently rolling up a partial historical set.
For each considered receipt:
- treat `candidate_prior_audit.status == selected_matches_positive_winner_history` as a convergent prior-supported outcome,
- treat `candidate_prior_audit.status == no_positive_prior_candidates` as usable but non-divergent sparse context,
- treat `candidate_prior_divergence_explanation.status == divergence_explained_by_runtime_failures` as a runtime-failure-limited divergence,
- treat `candidate_prior_divergence_explanation.status == divergence_explained_by_runtime_scoring` as a lower-ranked-pass / scoring-limited divergence,
- treat `candidate_prior_divergence_explanation.status == divergence_explained_by_mixed_runtime_outcomes` as mixed divergence,
- treat `candidate_prior_divergence_explanation.status == selected_candidate_prior_unresolved` as usable unresolved caution,
- treat `candidate_prior_divergence_explanation.status == candidate_prior_divergence_unavailable` as unusable for readiness classification.

V1 must fail closed when the persisted audit/explanation surfaces needed for rollup are absent or malformed.
A replay-healthy exact-match receipt missing those persisted surfaces makes the overall advisory unavailable rather than merely skipped.
It must not infer a readiness posture from raw ranked candidates, candidate priors alone, or adjacent fields when the explanatory surfaces are missing.

V1 uses these deterministic rollup thresholds:
- require at least **three** usable replay-healthy exact-match receipts before any non-sparse readiness posture may be emitted,
- require at least **two** usable receipts with positive-prior signal (`selected_matches_positive_winner_history`, runtime-failure divergence, runtime-scoring divergence, mixed divergence, or unresolved divergence) before any non-sparse readiness posture may be emitted,
- emit `priors_consistently_convergent` only when usable positive-prior signal remains convergent and no usable divergence/unresolved outcomes remain,
- emit `priors_mostly_blocked_by_runtime_failures` or `priors_mostly_outscored_under_v7` only when that posture covers at least two-thirds of usable divergence receipts and is a strict majority over the competing divergence posture,
- otherwise emit `priors_mixed_or_inconclusive`.

## Minimum payload

The V1 readiness advisory must contain, at minimum:
- `candidate_prior_readiness_advisory_version`
- `status`
- `history_summary`:
  - `exact_match_receipt_count`
  - `replay_healthy_receipt_count`
  - `usable_receipt_count`
  - `convergent_receipt_count`
  - `no_positive_prior_receipt_count`
  - `runtime_failure_divergence_count`
  - `runtime_scoring_divergence_count`
  - `mixed_divergence_count`
  - `unresolved_receipt_count`
  - `unusable_receipt_count`
- `considered_receipts` — one entry per replay-healthy exact-match receipt considered for readiness, each including:
  - `receipt_path`
  - `created_at`
  - `candidate_prior_audit_status`
  - `candidate_prior_divergence_explanation_status`
  - `usable_for_readiness`
  - `notes`
- `notes` — bounded explanatory strings

If the advisory cannot be computed, it must fail closed into an explicit unavailable payload rather than silently disappearing or inventing a readiness posture from sparse evidence.

## Attachment surfaces

The V1 readiness advisory must attach to the same two runtime surfaces already carrying `synthesis_diagnostics`:
- live `module-gen` artifact metadata,
- persisted `module-gen` receipt metadata.

The implementation may derive the advisory only from the current retrieval bundle plus persisted audit/explanation payloads already present on matched receipts.
It must not introduce a hidden second discovery path or silently widen evidence authority beyond earlier SG2 contracts.

## Trust and interpretation rules

Interpret the advisory as follows:
- `insufficient_prior_history` means exact-match history is still too sparse or too malformed to support a stable governance judgment about priors.
- `priors_consistently_convergent` means usable history rarely shows a meaningful mismatch between prior support and selected current winners.
- `priors_mostly_blocked_by_runtime_failures` means prior-supported alternatives often fail current runtime validation, so priors do not yet look like strong candidates for ranking authority.
- `priors_mostly_outscored_under_v7` means prior-supported alternatives often remain viable current candidates but still lose under trusted V7 scoring, making later ranking experiments thinkable but still not authorized.
- `priors_mixed_or_inconclusive` means the current historical picture is too split to support a narrower readiness claim.

The advisory is a governance aid, not a policy override.
It may help decide whether candidate priors deserve a future predictive-ranking contract, but it cannot itself change ranking, tie-breaking, pruning, or promotion outcomes.

## Explicit non-goals

This contract explicitly defers:
- feeding candidate priors into ranking scores,
- changing tie-break behavior when prior-supported candidates lose,
- pruning candidate fan-out before evaluation,
- using readiness posture to block or auto-approve promotion,
- inventing synthetic readiness labels from raw score deltas,
- using Oracle similarity as enough to create or deny candidate-prior authority,
- mutating strategy or ranking policy from observed readiness posture.

## First execution slice aligned to this contract

The first AK-backed implementation slice after this ADR is:
- `AK-462` — **Synthesis evidence substrate: emit a read-only candidate-prior readiness advisory for module-gen outcomes**

That slice should materialize the readiness advisory on live runtime metadata and persisted receipts while keeping V7 ranking, tie-breaking, and promotion behavior unchanged.

Consequences
------------
Positive:
- DSPx gains a bounded historical summary of whether candidate priors look promising enough to study further without granting them ranking authority yet.
- The repo can distinguish priors that are usually blocked by current runtime failures from priors that often remain viable but still lose under V7 scoring.
- Later V8 governance work can point at explicit receipt-backed readiness artifacts instead of anecdotes about a few memorable divergence cases.

Costs / tradeoffs:
- The advisory is still observational only; it does not make ranking cheaper or smarter yet.
- Readiness quality depends on persisted receipt surfaces staying well-formed and exact-match history becoming rich enough to summarize.
- Many requests may still resolve to `insufficient_prior_history` or `priors_mixed_or_inconclusive` for some time.
