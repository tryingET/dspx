---
summary: "Freeze the first human-governed promotion-eligibility contract for governance-only policy variants grounded in runtime-spine evidence."
read_when:
  - "You are deciding what comes after governance-only policy-evaluation receipts."
  - "You need the trust boundary for nominating a named governance-only policy variant for explicit human review toward future live authority."
---

ADR 20260409 — Human-Governed Promotion-Eligibility Contract V1
================================================================

Status
------
Accepted

Context
-------
`TG23` / `AK-593` already materialized `synthesis_diagnostics.governed_policy_evaluations`: DSPx can evaluate named governance-only ranking/promotion-policy variants against bounded shadow predictive-ranking evidence plus trusted current metadata and emit receipt-backed judgments without changing live V7 ranking, tie-breaking, pruning, or promotion behavior.

`AK-1085` later closed the missing runtime-spine ambiguity by naming **candidate assembly**, **execution episode**, and **receipt bundle** as first-class bounded runtime objects for the same synthesis run.

That leaves the next SG2 governance question open:
- the repo can now say what a named governance-only policy variant would have concluded on a current run,
- the runtime spine can now identify the exact candidate assembly, execution episode, and receipt bundle that produced the live selected outcome and any bounded governance comparison,
- but DSPx still lacks a dated contract for when those governance-only receipts are strong enough to nominate a policy variant for explicit human review toward future live authority,
- and without that contract repeated governance-only outcomes could drift into de facto authority or ad-hoc human review packages with inconsistent evidence requirements.

The safest next move is therefore still not live policy promotion.
It is a **human-governed promotion-eligibility contract** that decides when a named governance-only policy variant may be nominated for explicit human review using already-emitted governed policy-evaluation receipts plus runtime-spine provenance, while keeping live ranking, tie-breaking, pruning, and promotion authority unchanged.

For V1, **promotion eligibility** means only this:
> whether a named governance-only policy variant is eligible to be reviewed by humans for a later off-run policy/version change.

It does **not** mean reopening or re-promoting the current run's selected candidate.
The current run's live candidate selection and promotion shell stay fixed.

Decision
--------
Adopt **Human-Governed Promotion-Eligibility Contract V1** as the next SG2 contract after governance-only policy-evaluation receipts and the runtime-spine refresh.

## Scope

This contract applies only to the existing multi-candidate `module-gen` synthesis runtime.

It is intentionally:
- post-governed-policy-evaluation,
- governance-only,
- human-reviewed rather than self-promoting,
- current-run bounded,
- runtime-spine-grounded,
- nomination-oriented rather than activation-oriented.

It does **not** authorize live predictive ranking, live tie-break changes, candidate pruning, evaluation reordering, live promotion blocking, automatic policy mutation, or automatic policy promotion from repeated governance receipts.

## Consumer role

The next post-`TG23` consumer is a **promotion-eligibility nomination** for a named governance-only policy variant.

That nomination answers one narrow question:

> Given an already-emitted governed policy-evaluation receipt plus the current run's candidate-assembly / execution-episode / receipt-bundle provenance, is a named governance-only policy variant eligible to be placed in front of explicit human governance for consideration as a future policy change?

An eligibility nomination says only that a variant has enough bounded evidence and provenance to justify explicit human review.
It does not approve the variant, activate it, mutate live policy, rerun candidate selection, or retroactively reinterpret the current run.

## Inputs

The nomination consumes these inputs only:
1. one current-run governed policy-evaluation receipt produced under `20260330.v1`, including:
   - `variant_class`
   - `variant_policy_id`
   - `variant_policy_version`
   - `variant_policy_mode`
   - `outcome`
   - `authority_limit`
   - `live_policy_context`
   - `request_context`
   - `bounded_inputs`
   - `evaluation_result`
2. the current run's live selection / promotion context for attribution only:
   - selection policy id/version
   - promotion policy id/version
   - selected candidate id / variant id / variant origin
   - request tuple identity
3. runtime-spine objects emitted by the same run for the live selected candidate:
   - `candidate_assembly`
   - `execution_episode`
   - `receipt_bundle`
4. when the governed ranking evaluation surfaces a bounded governance candidate, the matching runtime-spine objects for that candidate:
   - `candidate_assembly`
   - `execution_episode`
   - `receipt_bundle`
5. bounded current-run pass/fail metadata proving any surfaced governance candidate already passed the current runtime validation boundary
6. provenance identifiers and timestamps needed to assemble an explicit human review packet.

Authority order remains:
1. live runtime-spine objects and trusted current-run metadata,
2. governed policy-evaluation receipt under `20260330.v1`,
3. human governance outside the run that produced the evidence.

This contract may reuse only already-emitted governed receipts, current-run runtime-spine objects, and trusted current-run metadata.
It must not rescan historical receipts, aggregate cross-run counts, widen Oracle authority, or treat repeated governance-only outcomes as enough to self-promote a policy variant.

## Review-scope constraints

V1 allows exactly two nomination scopes, derived from the governed receipt's variant class:

1. `bounded_current_run_comparison`
   - used only for `ranking_evaluation` variants
   - may reference only the live selected candidate plus the already-bounded governance candidate named by the governed receipt
   - may not add new candidates, expand the comparison set, or recompute ranking from raw history

2. `selected_candidate_only`
   - used only for `promotion_evaluation` variants
   - may reason only about the already-selected live V7 candidate and its bounded runtime-spine provenance
   - may not reopen ranking or name a replacement candidate for promotion

## Eligibility surface constraints

Every V1 promotion-eligibility nomination must declare or inherit all of the following from the governed receipt and nomination layer:
- `promotion_eligibility_contract_version`
- `governed_policy_evaluation_contract_version`
- `variant_class`
- `variant_policy_id`
- `variant_policy_version`
- `variant_policy_mode` (`governance_only`)
- `governed_receipt_ref` — stable reference to the governed evaluation receipt or receipt-bundle attachment
- `review_scope`
- `eligibility_rule_summary`
- `authority_limit` — explicit statement that the nomination cannot change live behavior
- `required_review_artifacts` — explicit list of runtime-spine and governance artifacts that must be present before human review

A nomination that cannot declare these fields must fail closed rather than improvising a human review packet.

## Deterministic eligibility outcomes

Each nomination must emit exactly one eligibility outcome from this set:
- `promotion_eligibility_unavailable` — the governed receipt, runtime-spine provenance, or required review artifacts are missing, malformed, or inconsistent.
- `promotion_eligibility_not_nominated` — the bounded evidence does not nominate the policy variant for explicit human review.
- `promotion_eligibility_nominated_for_human_review` — the bounded evidence and runtime-spine provenance justify explicit human review of the named policy variant, with no live authority change.
- `promotion_eligibility_requires_more_evidence` — bounded evidence exists, but it remains mixed, sparse, or incomplete enough that DSPx should not nominate the policy variant yet.

These outcomes are governance artifacts only.
They do **not** change the selected candidate, live ranking order, tie-break result, current promotion outcome, or active live policy identifiers for the run that produced them.

## Mapping rules

A V1 nomination must fail closed to `promotion_eligibility_unavailable` when any of the following holds:
- the governed policy-evaluation receipt is missing or malformed,
- `variant_policy_mode` is not `governance_only`,
- the governed receipt's selected-candidate identity disagrees with trusted current runtime-spine identity,
- the selected candidate is missing a `candidate_assembly`, `execution_episode`, or `receipt_bundle`,
- `live_policy_context` is incomplete,
- a ranking-evaluation receipt names a governance candidate whose runtime-spine objects are missing or whose current execution episode did not pass,
- required review artifacts cannot be assembled deterministically.

A V1 nomination must emit `promotion_eligibility_not_nominated` when:
- the governed receipt outcome is `policy_evaluation_no_signal`, or
- the governed receipt outcome is `policy_evaluation_affirms_live_policy`.

A V1 nomination must emit `promotion_eligibility_requires_more_evidence` when:
- the governed receipt outcome is `policy_evaluation_mixed_or_inconclusive`, or
- bounded evidence exists but the review packet remains incomplete in a way that should not be silently interpreted as rejection.

A V1 nomination may emit `promotion_eligibility_nominated_for_human_review` only when all of the following hold:
- the governed receipt outcome is `policy_evaluation_surfaces_governance_candidate`,
- the governed receipt stays within the `20260330.v1` authority limit,
- the selected candidate's runtime-spine objects are complete and consistent,
- for `ranking_evaluation`, the surfaced governance candidate is already present in the governed comparison scope, has complete runtime-spine provenance, and passed the current execution boundary,
- for `promotion_evaluation`, the receipt's `promotion_posture` is `promotion_posture_requires_human_review`,
- the nomination can assemble the full human review packet defined below.

## Required human review packet

A V1 nomination is valid only when it can assemble all required review artifacts:
- the governed policy-evaluation receipt itself
- live policy context ids/versions for ranking and promotion
- selected request tuple identity plus selected candidate / variant identity
- selected candidate `assembly_id`, `episode_id`, and `receipt_bundle_id`
- selected candidate `artifact_path` and `content_hash` when present
- selected execution-episode status / score / summary
- selected receipt-bundle evidence / provenance reference
- if a ranking variant surfaced a governance candidate:
  - `candidate_id`
  - `assembly_id`
  - `episode_id`
  - `receipt_bundle_id`
  - proof the candidate passed the current execution boundary
  - the governed receipt's `governance_candidate_reason`
- the governed receipt's bounded comparison scope summary
- an explicit statement that later human approval is still required outside the generating run.

These artifacts are preconditions for human review, not approval by themselves.

## Minimum nomination receipt payload

Every V1 promotion-eligibility nomination receipt must contain, at minimum:
- `promotion_eligibility_receipt_version`
- `promotion_eligibility_contract_version`
- `governed_policy_evaluation_receipt_version`
- `governed_policy_evaluation_contract_version`
- `variant_class`
- `variant_policy_id`
- `variant_policy_version`
- `variant_policy_mode`
- `review_scope`
- `eligibility_outcome`
- `eligibility_reason`
- `authority_limit`
- `governed_receipt_ref`
- `live_policy_context`
- `request_context`
- `runtime_spine_refs`:
  - `selected_candidate`
    - `candidate_id`
    - `assembly_id`
    - `episode_id`
    - `receipt_bundle_id`
  - `governance_candidate` when present
    - `candidate_id`
    - `assembly_id`
    - `episode_id`
    - `receipt_bundle_id`
- `review_artifacts`:
  - `required_artifacts_present`
  - `selected_candidate_passed_current_boundary`
  - `governance_candidate_passed_current_boundary` when present
  - `shadow_predictive_ranking_status`
  - `consumed_surface_versions`
- `human_governance`:
  - `requires_explicit_human_review` = `true`
  - `can_change_live_policy_in_run` = `false`
  - `can_change_live_ranking` = `false`
  - `can_change_live_tie_breaking` = `false`
  - `can_change_live_pruning` = `false`
  - `can_change_live_promotion` = `false`
- `provenance`:
  - `generated_at`
  - references to the governed receipt plus runtime-spine objects.

If the nomination cannot be computed, DSPx must still emit an explicit unavailable receipt rather than silently omitting the surface.

## Attachment surfaces

The first receipt wave aligned to this contract must attach nomination receipts to persisted `module-gen` receipt metadata.
It may mirror the same payload into live `module-gen` artifact metadata when that reuse stays inside the existing `synthesis_diagnostics` envelope.

The recommended surface name for that first receipt wave is:
- `synthesis_diagnostics.promotion_eligibility_nominations`

V1 does not require a new operator dashboard, experiment registry, or cross-run governance database.
The first truthful slice is the nomination receipt and its bounded human review packet.
Anything larger is deferred.

## Human-governance boundary

Nomination is **not** approval.
A named policy variant becomes eligible only for explicit human review.
Actually promoting a governance-only policy variant into future live authority still requires, at minimum:
1. a later explicit human review decision bound to the nomination receipt,
2. a policy/version change outside the run that generated the evidence,
3. preservation of the original live run receipt trail, the governed policy-evaluation receipt trail, and the nomination receipt trail,
4. no in-run mutation of ranking, tie-breaking, pruning, or promotion behavior,
5. no automatic carry-over from repeated nominations or repeated governance-only outcomes.

If later work wants repeated nominations, cross-run aggregation, or automatic policy release semantics to matter, it must freeze a new ADR.

## Explicit non-goals

This contract explicitly defers:
- cross-run aggregate scoring of governance-only policy variants,
- automatic escalation from repeated governed receipts or repeated nominations,
- live predictive ranking,
- live tie-break mutation,
- candidate pruning from governance evidence,
- evaluation reordering,
- auto-blocking or auto-approving current-run promotion,
- policy self-mutation,
- human-review workflow infrastructure larger than the bounded nomination receipt.

## First execution shape aligned to this contract

The first truthful follow-on after this ADR is a bounded receipt wave that emits `promotion_eligibility_nominations` for named governance-only policy variants by combining:
- governed policy-evaluation receipts,
- current-run runtime-spine references,
- and the required human review packet fields above.

That follow-on must remain governance-only and must not change the active live policy during the run that emitted the nomination.

This ADR does **not** materialize that AK slice by itself.
If the repo-scoped ready queue goes empty after the contract lands, leave it empty rather than guessing the implementation task just to keep the queue non-empty.

Consequences
------------
Positive:
- DSPx gains the first durable seam between governance-only variant evaluation and explicit human review for future policy authority.
- Runtime-spine provenance now anchors human review in the exact candidate assembly, execution episode, and receipt bundle that produced the evidence, instead of ad-hoc metadata scraps.
- Repeated governance-only outcomes no longer have to be interpreted informally; the repo now has a bounded nomination contract that records what is review-eligible and why it still lacks live authority.

Costs / tradeoffs:
- The first slice is intentionally narrow; it defines nomination receipts, not a full human-governance workflow product.
- Many runs may still land in `promotion_eligibility_not_nominated` or `promotion_eligibility_requires_more_evidence`.
- Teams must resist the temptation to treat repeated nominations as de facto policy approval until a later contract explicitly widens authority.
