---
summary: "Freeze the first post-selection audit contract for consuming candidate winner priors before predictive ranking."
read_when:
  - "You are deciding how DSPx may inspect candidate_winner_priors after TG11."
  - "You need the trust boundary for post-selection consumption of candidate priors before V8 ranking."
---

ADR 20260327 — Synthesis Evidence Candidate-Prior Audit Contract V1
===================================================================

Status
------
Accepted

Context
-------
`TG11` proved that DSPx can now materialize a bounded, replay-health-gated candidate-prior payload for the current deterministic `module-gen` variants:
- `candidate_winner_priors` attaches to live `synthesis_diagnostics` metadata and persisted receipts,
- each current candidate reports whether it matches replay-healthy exact-match winner history,
- and the payload is explicitly advisory-only.

That closes the first candidate-prior emission wave, but it leaves the next SG2 question open:
- DSPx now has a per-candidate prior surface,
- the tempting next move is to let that payload steer ranking or pruning,
- but the current authority boundary still only proves replay-healthy exact-match historical winners,
- and the repo has not yet frozen how to inspect whether those priors actually align with present V7 outcomes.

The safest next move is therefore not pre-selection control.
It is a **post-selection audit** that consumes the existing candidate-prior payload after V7 has already selected a winner and records how the selected candidate relates to the positive prior support available in the current fan-out.

Decision
--------
Adopt **Synthesis Evidence Candidate-Prior Audit Contract V1** as the next SG2 contract for consuming `candidate_winner_priors` after `TG11`.

## Scope

This contract applies only to the existing multi-candidate `module-gen` synthesis runtime.

It is intentionally:
- post-selection,
- read-only,
- candidate-prior-aware,
- selected-vs-available,
- replay-health-bounded,
- explanation-first.

It does **not** authorize predictive ranking, candidate pruning, evaluation reordering, promotion blocking, policy mutation, or V9-style strategy evolution.

## Consumer role

The first post-`TG11` consumer is a **candidate-prior audit** for the selected outcome.

That audit answers one narrow question:

> After V7 ranking selected a winner, how did that selected candidate relate to the positive candidate-prior support available in the current fan-out?

The audit consumes the already-emitted per-candidate prior payload plus the selected candidate identity.
It does not create a second evidence-discovery path and it does not modify selection behavior.

## Inputs

The audit consumes these inputs only:
1. the current selected candidate identity:
   - `selected_candidate_id`,
   - `variant_id`,
   - `variant_origin`,
2. the current `candidate_winner_priors` payload defined by ADR 20260327 candidate-prior v1,
3. current ranked-candidate ordering for explanation only.

Authority order remains unchanged:
1. replay-healthy exact-match winner history,
2. degraded exact-match history for diagnostics only,
3. ranked-candidate payloads for explanation only,
4. Oracle neighbors for context only.

## Audit status model

The audit must emit exactly one posture from this set:
- `candidate_priors_unavailable` — the current run cannot provide a usable `candidate_winner_priors` payload or selected candidate identity.
- `selected_matches_positive_winner_history` — the selected candidate has positive winner support under the V1 candidate-prior payload.
- `no_positive_prior_candidates` — no current candidate has positive winner support, so the selected candidate is not diverging from any stronger prior-supported alternative.
- `positive_prior_candidates_present_but_not_selected` — one or more non-selected candidates have positive winner support, but the selected candidate does not.
- `selected_candidate_prior_unsupported` — the selected candidate lacks the stable identity fields the V1 prior contract requires.
- `selected_candidate_prior_degraded` — exact-match history exists, but the selected candidate can only be classified under degraded prior authority.

For V1, `positive_prior_candidates_present_but_not_selected` is an explanation posture, not a policy violation.
It means the V7 winner differed from the subset of candidates that had positive historical winner support.
It does **not** mean the selected candidate is wrong or should have been pruned.

## Minimum audit payload

The V1 candidate-prior audit must contain, at minimum:
- `candidate_prior_audit_version`
- `status`
- `selected_candidate`:
  - `candidate_id`
  - `variant_id`
  - `variant_origin`
  - `prior_status`
- `history_summary`:
  - `exact_match_receipt_count`
  - `positive_evidence_count`
  - `candidate_count`
  - `positive_prior_candidate_count`
- `positive_prior_candidates` — current candidates whose prior status is `matches_positive_winner_history`
- `non_selected_positive_prior_candidates` — subset of positive-prior candidates that are not the selected candidate
- `notes` — bounded explanatory strings

If the audit cannot be computed, it must fail closed into an explicit unavailable payload rather than silently disappearing.

## Attachment surfaces

The V1 candidate-prior audit must attach to the same two runtime surfaces already carrying `synthesis_diagnostics`:
- live `module-gen` artifact metadata,
- persisted `module-gen` receipt metadata.

The implementation may derive the audit entirely from the existing selected candidate metadata plus `candidate_winner_priors`.
It must not create hidden new authority or re-scan receipts through a second undisclosed path.

## Trust and interpretation rules

Interpret the audit as follows:
- `selected_matches_positive_winner_history` means the V7 winner also has replay-healthy exact-match prior winner support.
- `no_positive_prior_candidates` means the current fan-out offers no positive-prior-supported alternative under the frozen V1 prior contract.
- `positive_prior_candidates_present_but_not_selected` means prior-supported alternatives existed, but V7 still selected a different candidate under the existing ranking policy.
- `selected_candidate_prior_unsupported` means the selected candidate cannot be reliably compared under the V1 prior identity key.
- `selected_candidate_prior_degraded` means exact-match history exists, but replay-health or identity resolution prevents the selected candidate from gaining positive authority.

The audit is descriptive only.
It may support later governance decisions about whether predictive ranking should be widened, but it cannot itself change ranking, promotion, or policy outcomes.

## Explicit non-goals

This contract explicitly defers:
- feeding candidate priors into ranking scores,
- tie-break changes when a prior-supported candidate loses,
- pruning candidate fan-out before evaluation,
- penalizing candidates because they lack winner history,
- auto-approving or blocking promotion from audit posture,
- using Oracle similarity as enough to create or deny candidate-prior authority,
- strategy/policy mutation or any V9-style self-evolution.

## First execution slice aligned to this contract

The first AK-backed implementation slice after this ADR is:
- `AK-379` — **Synthesis evidence substrate: emit a post-selection candidate-prior audit for module-gen outcomes**

That slice should materialize the audit payload on live runtime metadata and persisted receipts while keeping V7 ranking, tie-breaking, and promotion behavior unchanged.

Consequences
------------
Positive:
- DSPx gains a bounded consumer of `candidate_winner_priors` before any predictive ranking experiment widens authority.
- The repo can inspect when V7 winners align or diverge from prior-supported candidate identities without pretending that divergence is already a policy failure.
- Later V8 work can evaluate whether candidate priors are useful by reading explicit receipt-backed audit artifacts instead of reverse-engineering runtime history.

Costs / tradeoffs:
- The audit still does not make ranking cheaper or smarter yet; it only explains selected-vs-prior posture.
- Positive prior authority remains asymmetric because replay-healthy historical winners are stronger evidence than historical losers.
- Many runs may continue to report `no_positive_prior_candidates`, especially while exact-match history remains sparse.
