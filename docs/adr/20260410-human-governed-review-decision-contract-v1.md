---
summary: "Freeze the first human-governed review-decision contract for nominated governance-only policy variants grounded in nomination receipts and runtime-spine evidence."
read_when:
  - "You are deciding what comes after promotion-eligibility nominations for governance-only policy variants."
  - "You need the trust boundary for how humans resolve a nominated policy variant toward future live authority without changing the generating run."
---

ADR 20260410 — Human-Governed Review-Decision Contract V1
==========================================================

Status
------
Accepted

Context
-------
`TG23` / `AK-593` already materialized `synthesis_diagnostics.governed_policy_evaluations`: DSPx can evaluate named governance-only ranking/promotion-policy variants against bounded shadow predictive-ranking evidence plus trusted current metadata without changing live V7 behavior.

`AK-1085` then closed the runtime-spine ambiguity by naming **candidate assembly**, **execution episode**, and **receipt bundle** as first-class bounded runtime objects for the same synthesis run.

`TG27` / `AK-1102` later materialized `synthesis_diagnostics.promotion_eligibility_nominations`: DSPx can now nominate a named governance-only policy variant for explicit human review when a governed policy-evaluation receipt plus runtime-spine provenance justify it, again without changing live ranking, tie-breaking, pruning, or promotion behavior.

That leaves the next SG2 governance question open:
- the repo can now say that a named governance-only policy variant is eligible for explicit human review,
- the nomination receipt can already bundle the governed receipt, the live policy context, the request context, and the selected/governance-candidate runtime-spine references needed for a bounded review packet,
- but DSPx still lacks a dated contract for how humans resolve that nomination into a durable review decision toward future live authority,
- and without that contract repeated nominations or ad-hoc approvals could drift into de facto authority, inconsistent decision packets, or unnamed policy changes that are hard to audit later.

The safest next move is therefore still not live policy activation.
It is a **human-governed review-decision contract** that decides how one nominated governance-only policy variant may be explicitly resolved by humans for a later off-run policy/version change, while keeping the generating run's live ranking, tie-breaking, pruning, promotion outcome, and active policy identifiers unchanged.

For V1, **review decision** means only this:
> whether a named governance-only policy variant that was already nominated for human review is rejected, deferred, marked as requiring more evidence, or approved for a later explicit off-run policy/version change.

It does **not** mean activating the variant in the run that generated the nomination.
The current run's live candidate selection and promotion shell stay fixed.

Decision
--------
Adopt **Human-Governed Review-Decision Contract V1** as the next SG2 contract after promotion-eligibility nomination receipts.

## Scope

This contract applies only to the existing multi-candidate `module-gen` synthesis runtime.

It is intentionally:
- post-promotion-eligibility-nomination,
- governance-only,
- human-authored rather than self-promoting,
- off-run with respect to the evidence-generating run,
- nomination-bound,
- runtime-spine-grounded,
- decision-oriented rather than activation-oriented.

It does **not** authorize live predictive ranking, live tie-break changes, candidate pruning, evaluation reordering, live promotion blocking, automatic policy mutation, automatic policy promotion, or in-run activation of a nominated policy variant.

## Consumer role

The next post-`TG27` consumer is a **human-governed review decision** for one named governance-only policy variant.

That decision answers one narrow question:

> Given an already-emitted promotion-eligibility nomination receipt plus its governed policy-evaluation receipt and runtime-spine provenance, what explicit human governance decision should be recorded about whether this exact named policy variant may proceed toward a later off-run policy/version change?

A review decision records explicit human judgment about a bounded nominated variant.
It does not approve unnamed bundles of behavior, activate policy in-run, rerun candidate selection, reopen the current promotion result, or reinterpret prior receipts under a broader authority model.

## Inputs

The review decision consumes these inputs only:
1. one current-run promotion-eligibility nomination receipt produced under `20260409.v1`, including:
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
   - `runtime_spine_refs`
   - `review_artifacts`
2. the governed policy-evaluation receipt referenced by that nomination for evidence traceability only
3. the nomination's required human review packet, including the runtime-spine objects and bounded comparison summary already assembled for the nomination
4. explicit human decision metadata:
   - stable reviewer references
   - `reviewed_at`
   - decision rationale
   - the chosen review-decision outcome
   - when approved, the exact future policy/version change target or change record reference outside the generating run
5. provenance identifiers and timestamps needed to bind the decision to the nomination receipt and original runtime-spine evidence.

Authority order remains:
1. the nomination receipt plus its governed receipt and trusted runtime-spine provenance,
2. the explicit bounded human review decision recorded against that packet,
3. a later off-run policy/version change process outside the generating run.

This contract may reuse only already-emitted nomination/governed receipts, trusted current-run runtime-spine objects, and explicit human decision metadata.
It must not rescan historical receipts, aggregate cross-run counts into automatic authority, widen Oracle authority, or treat repeated nominations as enough to self-approve a policy variant.

## Review-scope constraints

A V1 review decision must inherit the nomination's `review_scope` and stay inside it.

V1 allows exactly two review scopes:

1. `bounded_current_run_comparison`
   - used only for `ranking_evaluation` variants
   - may reference only the live selected candidate plus the already-bounded governance candidate named by the nomination/governed receipt chain
   - may not add new candidates, widen the comparison set, or recompute ranking from raw history

2. `selected_candidate_only`
   - used only for `promotion_evaluation` variants
   - may reason only about the already-selected live V7 candidate and its bounded runtime-spine provenance
   - may not reopen ranking or name a replacement candidate for promotion

A V1 review decision may not approve unnamed bundles of policy changes, silently substitute a different variant id/version, aggregate evidence across runs, or bind one human decision to multiple nominations at once.

## Review-decision surface constraints

Every V1 review decision must declare or inherit all of the following:
- `review_decision_contract_version`
- `promotion_eligibility_receipt_version`
- `promotion_eligibility_contract_version`
- `governed_policy_evaluation_receipt_version`
- `governed_policy_evaluation_contract_version`
- `variant_class`
- `variant_policy_id`
- `variant_policy_version`
- `variant_policy_mode` (`governance_only`)
- `nomination_receipt_ref`
- `governed_receipt_ref`
- `review_scope`
- `review_decision_outcome`
- `review_decision_reason`
- `authority_limit` — explicit statement that the decision cannot change live behavior in the generating run
- `reviewer_refs`
- `reviewed_at`
- `required_decision_artifacts` — explicit list of governance/runtime artifacts that had to be present for the decision to be valid

A review decision that cannot declare these fields must fail closed rather than improvising a policy-approval story.

## Deterministic review-decision outcomes

Each review decision must emit exactly one outcome from this set:
- `review_decision_unavailable` — the nomination receipt, governed receipt, runtime-spine provenance, required review artifacts, or explicit human decision metadata are missing, malformed, or inconsistent.
- `review_decision_deferred` — the nomination is valid, but humans intentionally defer the decision pending an explicit later governance step, without interpreting the nomination as approval.
- `review_decision_requires_more_evidence` — the nomination is valid, but humans determine the bounded evidence is still too sparse, mixed, or incomplete to approve or reject the named variant.
- `review_decision_rejected` — humans explicitly reject progressing the named variant toward future live authority under the current bounded evidence packet.
- `review_decision_approved_for_future_policy_change` — humans explicitly approve the exact named policy variant for a later off-run policy/version change, with no in-run authority change.

These outcomes are governance artifacts only.
They do **not** change the selected candidate, live ranking order, tie-break result, current promotion outcome, or active live policy identifiers for the run that produced the nomination.

## Mapping rules

A V1 review decision must fail closed to `review_decision_unavailable` when any of the following holds:
- the promotion-eligibility nomination receipt is missing or malformed,
- the nomination's `eligibility_outcome` is not `promotion_eligibility_nominated_for_human_review`,
- `variant_policy_mode` is not `governance_only`,
- the nomination's `required_artifacts_present` signal is not truthfully present,
- the nomination's `governed_receipt_ref`, `live_policy_context`, `request_context`, or `runtime_spine_refs` are missing or inconsistent,
- the review scope does not match the nomination's declared variant class,
- stable reviewer references, `reviewed_at`, or decision rationale are missing,
- an approval decision cannot name the exact target policy/version change or equivalent off-run change record.

A V1 review decision may emit `review_decision_deferred` only when:
- the nomination is valid for human review,
- the bounded review packet is present,
- and humans intentionally record that the decision is postponed pending an explicit governance precondition outside the generating run.

A V1 review decision may emit `review_decision_requires_more_evidence` only when:
- the nomination is valid for human review,
- the reviewers conclude that the bounded evidence packet is insufficient for approval or rejection,
- and the decision does not silently reinterpret that insufficiency as rejection or approval.

A V1 review decision may emit `review_decision_rejected` only when:
- the nomination is valid for human review,
- humans explicitly decide not to progress the named variant toward future live authority under the current packet,
- and the rejection stays bound to the exact named variant plus bounded review scope.

A V1 review decision may emit `review_decision_approved_for_future_policy_change` only when all of the following hold:
- the nomination outcome is `promotion_eligibility_nominated_for_human_review`,
- the nomination and governed receipts stay within their stated authority limits,
- the selected candidate's runtime-spine provenance remains complete and consistent,
- for `ranking_evaluation`, any bounded governance candidate remains the same candidate already named in the nomination/governed receipt chain,
- for `promotion_evaluation`, the decision stays bound to the already-selected candidate only,
- humans explicitly approve the exact named policy variant id/version,
- the decision records the exact future policy/version change target or bounded change-record reference outside the generating run,
- and the decision packet preserves the explicit statement that later off-run policy mutation is still required.

## Required review-decision packet

A V1 review decision is valid only when it can assemble all required decision artifacts:
- the promotion-eligibility nomination receipt itself
- the governed policy-evaluation receipt itself or a stable reference to it
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
  - the nomination/governed receipt reason that surfaced it
- the nomination's `eligibility_reason` plus required-review-artifacts summary
- stable reviewer references
- `reviewed_at`
- explicit decision rationale
- when approved, the exact future policy/version change target or bounded change-record reference plus responsible owner reference
- an explicit statement that later off-run policy/version mutation is still required and that the generating run remains unchanged.

These artifacts are preconditions for a valid human decision, not policy activation by themselves.

## Minimum review-decision receipt payload

Every V1 review-decision receipt must contain, at minimum:
- `review_decision_receipt_version`
- `review_decision_contract_version`
- `promotion_eligibility_receipt_version`
- `promotion_eligibility_contract_version`
- `governed_policy_evaluation_receipt_version`
- `governed_policy_evaluation_contract_version`
- `variant_class`
- `variant_policy_id`
- `variant_policy_version`
- `variant_policy_mode`
- `review_scope`
- `nomination_receipt_ref`
- `governed_receipt_ref`
- `eligibility_outcome`
- `review_decision_outcome`
- `review_decision_reason`
- `authority_limit`
- `live_policy_context`
- `request_context`
- `runtime_spine_refs`
- `review_artifacts`:
  - `required_artifacts_present`
  - `selected_candidate_passed_current_boundary`
  - `governance_candidate_passed_current_boundary` when present
  - `consumed_surface_versions`
- `human_review`:
  - `reviewer_refs`
  - `reviewed_at`
  - `decision_rationale`
  - `future_policy_change_ref` when approved
  - `requires_explicit_human_review` = `true`
  - `requires_off_run_policy_change` = `true`
  - `can_change_live_policy_in_run` = `false`
  - `can_change_live_ranking` = `false`
  - `can_change_live_tie_breaking` = `false`
  - `can_change_live_pruning` = `false`
  - `can_change_live_promotion` = `false`
- `provenance`:
  - `generated_at`
  - references to the nomination receipt, governed receipt, and runtime-spine objects.

If the review decision cannot be computed or recorded, DSPx must still emit an explicit unavailable receipt rather than silently omitting the surface.

## Attachment surfaces

The first receipt wave aligned to this contract may attach review-decision receipts to persisted `module-gen` receipt metadata when that write stays append-only and remains clearly bound to the originating nomination receipt.
It may mirror the same payload into local governance artifact metadata when that mirror preserves the original run's evidence trail rather than rewriting it.

The recommended surface name for that first receipt wave is:
- `synthesis_diagnostics.human_review_decisions`

V1 does not require a new operator dashboard, workflow engine, or cross-run governance database.
The first truthful slice is the decision receipt and its bounded decision packet.
Anything larger is deferred.

## Human-governance boundary

Review decision is **not** activation.
A named policy variant becomes approved only for a later explicit off-run policy/version change.
Actually promoting a governance-only policy variant into future live authority still requires, at minimum:
1. a recorded review decision bound to the nomination receipt,
2. a later policy/version change outside the run that generated the evidence,
3. preservation of the original live run receipt trail, the governed policy-evaluation receipt trail, the nomination receipt trail, and the review-decision receipt trail,
4. no in-run mutation of ranking, tie-breaking, pruning, or promotion behavior,
5. no automatic carry-over from repeated nominations or repeated review decisions.

If later work wants automatic activation, cross-run aggregation of review outcomes, or repeated approvals to matter by themselves, it must freeze a new ADR.

## Explicit non-goals

This contract explicitly defers:
- automatic live activation of a governance-only policy variant,
- cross-run aggregate scoring of nominations or review decisions,
- batching multiple nominations into one opaque approval,
- approving unnamed strategy bundles instead of one named policy variant,
- live predictive ranking,
- live tie-break mutation,
- candidate pruning from governance evidence,
- evaluation reordering,
- auto-blocking or auto-approving current-run promotion,
- policy self-mutation,
- human-review workflow infrastructure larger than the bounded decision receipt.

## First execution shape aligned to this contract

The first truthful follow-on after this ADR is a bounded receipt wave that emits `human_review_decisions` for nominated governance-only policy variants by combining:
- promotion-eligibility nomination receipts,
- governed policy-evaluation receipts,
- current-run runtime-spine references,
- and explicit human decision metadata.

That follow-on must remain governance-only and off-run with respect to the evidence-generating run.

This ADR does **not** materialize that AK slice by itself.
If the repo-scoped ready queue goes empty after the contract lands, leave it empty rather than guessing the implementation task just to keep the queue non-empty.

Consequences
------------
Positive:
- DSPx gains the first durable seam between promotion-eligibility nomination and explicit human review decision for named governance-only policy variants.
- Human review now stays bound to the exact nomination receipt, governed receipt, and candidate-assembly / execution-episode / receipt-bundle provenance that justified the review in the first place.
- Approval, rejection, deferment, and evidence insufficiency become explicit inspectable governance artifacts instead of informal operator lore.

Costs / tradeoffs:
- The first slice is intentionally narrow; it defines review-decision receipts, not a full human-governance workflow product.
- Many nominations may still land in `review_decision_deferred`, `review_decision_requires_more_evidence`, or `review_decision_rejected`.
- Teams must resist the temptation to treat repeated review decisions as de facto live policy authority until a later contract explicitly widens authority.
