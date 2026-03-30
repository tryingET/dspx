---
summary: "Freeze the first governance-only policy-evaluation contract that consumes shadow predictive-ranking evidence without mutating live V7 selection or promotion behavior."
read_when:
  - "You are deciding what comes after the read-only shadow predictive-ranking advisory."
  - "You need the trust boundary for governance-only evaluation of ranking or promotion-policy variants before live authority widens."
---

ADR 20260330 — Synthesis Evidence Governed Policy-Evaluation Contract V1
=========================================================================

Status
------
Accepted

Context
-------
`TG21` completed the full read-only SG2 shadow chain for `module-gen`: DSPx can now emit a bounded `shadow_predictive_ranking_advisory` that compares a prior-aware shadow preference against the trusted current V7 winner without changing live ranking, tie-breaking, pruning, or promotion behavior.

That closes the first descriptive shadow-ranking question, but it also creates the next governance pressure:
- the repo now has receipt-backed evidence about when a bounded shadow preference agrees with or diverges from the trusted V7 winner,
- the tempting next move is to let that divergence directly change live ranking, tie-breaking, pruning, or promotion,
- but DSPx still lacks a dated contract for how to evaluate evidence-aware policy variants under governance before granting any live authority,
- and without that contract the repo would either jump too early into live policy mutation or materialize ungoverned evaluation surfaces that later become hard to constrain.

The safest next move is therefore still not live predictive ranking.
It is a **governed policy-evaluation contract** that lets DSPx evaluate named ranking or promotion-policy variants against already-emitted shadow predictive-ranking evidence plus trusted current run metadata, emit governance receipts, and explicitly constrain who may promote those results into future policy authority.

Decision
--------
Adopt **Synthesis Evidence Governed Policy-Evaluation Contract V1** as the next SG2 contract after the read-only shadow predictive-ranking advisory.

## Scope

This contract applies only to the existing multi-candidate `module-gen` synthesis runtime.

It is intentionally:
- post-shadow-advisory,
- governance-only,
- read-only with respect to the live V7 path,
- current-run bounded,
- receipt-backed,
- variant-explicit,
- promotion-authority-limited.

It does **not** authorize live predictive ranking, tie-break changes in the live path, candidate pruning, evaluation reordering, promotion blocking in the live path, automatic policy mutation, or V9-style self-evolution.

## Consumer role

The next post-`TG21` consumer is a **governed policy evaluation**.

That evaluation answers one narrow question:

> Given the already-emitted shadow predictive-ranking advisory and trusted current run metadata, how would a named evidence-aware ranking or promotion-policy variant have evaluated this run for governance purposes, and is the resulting evidence strong enough to justify explicit human-governed follow-up without changing the live V7 outcome?

The governed evaluation produces a receipt-backed judgment about a **named variant under a bounded evidence contract**.
It does not replace the trusted V7 winner, and it does not grant independent promotion authority to the evaluated variant.

## Inputs

The evaluation consumes these inputs only:
1. the current `shadow_predictive_ranking_advisory` payload,
2. the already-emitted current-run SG2 surfaces that the shadow advisory depends on for traceability only:
   - `candidate_winner_priors`
   - `candidate_prior_audit`
   - `candidate_prior_divergence_explanation`
   - `candidate_prior_readiness_advisory`
   - `candidate_prior_counterfactual_advisory`
3. trusted current run metadata for the selected candidate and every candidate explicitly compared by the named evaluation variant:
   - `candidate_id`
   - `variant_id`
   - `variant_origin`
   - `rank`
   - `ranking_score`
   - `evaluation_status`
   - `passed`
   - request tuple identity
   - live ranking/promotion policy identifiers and versions
4. bounded receipt identity and provenance fields for attribution only.

Authority order remains unchanged:
1. already-emitted replay-healthy exact-match SG2 surfaces,
2. trusted current run ranking/evaluation metadata,
3. shadow advisory status and payload,
4. governance variant definition attached to the evaluation request.

This contract may reuse only already-emitted SG2 surfaces and trusted current run metadata.
It must not rescan receipts under a new authority model, synthesize new priors, widen Oracle authority, or invent unbounded alternative comparison sets.

## Allowed evaluation variants

V1 allows exactly two governed variant classes:

1. **Ranking-evaluation variants**
   - Purpose: evaluate whether a bounded evidence-aware ranking rule would have preferred the same candidate as live V7 or a different already-passing candidate.
   - Allowed effect: emit a governance judgment only.
   - Forbidden effect: alter live rank order, tie-breaks, pruning, candidate materialization, evaluation ordering, or promotion outcome.

2. **Promotion-evaluation variants**
   - Purpose: evaluate whether a bounded promotion-policy rule would have classified the already-selected live V7 candidate as eligible, cautionary, or ineligible for future governance review.
   - Allowed effect: emit a governance judgment only.
   - Forbidden effect: block live promotion, auto-promote an alternative candidate, or reopen ranking.

V1 does **not** allow hybrid variants that simultaneously redefine candidate generation, candidate pruning, evaluation ordering, ranking, tie-breaking, and promotion as one opaque bundle.
If later work needs that authority, it must freeze a new ADR.

## Variant surface constraints

Every V1 governed variant must declare all of the following:
- `evaluation_contract_version`
- `variant_class` (`ranking_evaluation` or `promotion_evaluation`)
- `variant_policy_id`
- `variant_policy_version`
- `variant_policy_mode` (`governance_only`)
- `input_contracts` — explicit list of SG2/current-run inputs consumed
- `comparison_scope` — explicit bounded candidate set or selected-candidate-only scope
- `decision_rule_summary` — human-readable bounded rule description
- `authority_limit` — explicit statement that the variant cannot mutate live V7 behavior

V1 comparison scopes are deliberately narrow:
- a ranking-evaluation variant may compare only the live selected candidate plus candidates already present in the current shadow advisory comparison set and covered by trusted current metadata,
- a promotion-evaluation variant may reason only about the already-selected live V7 candidate plus the current shadow advisory status and supporting current metadata,
- no variant may add new candidates, recompute the fan-out, or query historical receipts beyond what the current SG2 surfaces already summarize.

## Deterministic evaluation outcomes

Each governed evaluation must emit exactly one outcome from this set:
- `policy_evaluation_unavailable` — required shadow/SG2 inputs, trusted current metadata, or variant definition fields are missing, malformed, or incomplete.
- `policy_evaluation_no_signal` — the bounded inputs do not support a meaningful governance judgment for the named variant.
- `policy_evaluation_affirms_live_policy` — the named variant resolves to the same governance conclusion as the live V7 path for the bounded question it is allowed to ask.
- `policy_evaluation_surfaces_governance_candidate` — the named variant surfaces a bounded alternative governance conclusion worth human review, but with no live authority.
- `policy_evaluation_mixed_or_inconclusive` — bounded evidence exists but remains too sparse, mixed, or internally limited to justify a narrower governance claim.

These outcomes are descriptive governance artifacts only.
They do **not** change the selected candidate, the ranking order, the tie-break result, the promotion decision, or the active policy identifiers for the run that produced them.

## Ranking-evaluation rules

A V1 ranking-evaluation variant may:
- consume the current `shadow_predictive_ranking_advisory`,
- inspect the advisory's `selected_candidate`, `shadow_preferred_candidate`, `status`, and bounded summary fields,
- inspect trusted current rank/score/pass metadata for the same bounded comparison set,
- declare whether the named ranking variant would have affirmed the live winner or surfaced a governance candidate for later study.

A V1 ranking-evaluation variant must:
- fail closed to `policy_evaluation_unavailable` if the shadow comparison set and trusted current metadata disagree,
- emit `policy_evaluation_no_signal` when the shadow advisory status is `no_shadow_predictive_signal`,
- emit `policy_evaluation_affirms_live_policy` when the variant's bounded rule resolves to the live selected candidate,
- emit `policy_evaluation_surfaces_governance_candidate` only when the bounded rule resolves to a different candidate that already passed the current runtime validation boundary,
- emit `policy_evaluation_mixed_or_inconclusive` when sparse or mixed SG2 posture prevents a narrower claim without widening authority.

## Promotion-evaluation rules

A V1 promotion-evaluation variant may:
- consume the current `shadow_predictive_ranking_advisory` and trusted current metadata for the already-selected live V7 candidate,
- classify that live-selected candidate into a governance-only promotion posture,
- state whether the run would warrant future manual review before promoting a comparable policy variant.

A V1 promotion-evaluation variant must:
- keep the live selected candidate fixed,
- keep the live promotion receipt fixed,
- never approve an alternative candidate for promotion,
- never block the already-executed live promotion path,
- emit only governance posture about future policy consideration.

V1 promotion postures may be expressed inside the receipt payload as:
- `promotion_posture_affirms_live_decision`
- `promotion_posture_requires_human_review`
- `promotion_posture_not_assessable`

These are explanatory subfields, not live outcomes.

## Minimum receipt payload

Every V1 governed policy-evaluation receipt must contain, at minimum:
- `policy_evaluation_receipt_version`
- `evaluation_contract_version`
- `variant_class`
- `variant_policy_id`
- `variant_policy_version`
- `variant_policy_mode`
- `outcome`
- `authority_limit`
- `live_policy_context`:
  - `ranking_policy_id`
  - `ranking_policy_version`
  - `promotion_policy_id`
  - `promotion_policy_version`
- `request_context`:
  - request tuple identity
  - `selected_candidate_id`
  - `selected_variant_id`
  - `selected_variant_origin`
- `bounded_inputs`:
  - `shadow_predictive_ranking_status`
  - identifiers/versions for each SG2 surface consumed
  - candidate-count summary for the bounded comparison set
- `evaluation_result`:
  - `evaluated_candidate_ids`
  - `governance_candidate_id` when present
  - `governance_candidate_reason` when present
  - `promotion_posture` when variant class is `promotion_evaluation`
  - `notes`
- `promotion_authority`:
  - `can_change_live_ranking` = `false`
  - `can_change_live_tie_breaking` = `false`
  - `can_change_live_pruning` = `false`
  - `can_change_live_promotion` = `false`
  - `requires_explicit_human_governance` = `true`
- `provenance`:
  - `generated_at`
  - bounded source references to current metadata and attached SG2 surfaces

If the governed evaluation cannot be computed, it must still emit an explicit unavailable receipt rather than silently omitting the evaluation.

## Attachment surfaces

The first receipt wave must attach the governed policy-evaluation receipt to persisted `module-gen` receipt metadata.
It may also mirror the same payload into live `module-gen` artifact metadata when that reuse stays inside the existing `synthesis_diagnostics` envelope.

V1 does not require a new operator dashboard, standalone registry, or cross-run governance database.
The first truthful slice is the receipt itself.
Anything larger is deferred until later governance waves prove necessary.

## Promotion-authority limits

Promotion authority is the hard boundary for this ADR.

V1 explicitly requires that:
- live V7 ranking remains authoritative for candidate selection,
- live V7 tie-breaking remains unchanged,
- live V7 pruning remains unchanged,
- live V7 promotion execution remains unchanged,
- governed policy-evaluation receipts may recommend only **human review of future policy changes**,
- no evaluation variant may become self-promoting,
- no evaluation receipt may be treated as an automatic migration trigger for ranking or promotion policy.

A future promotion of a policy variant from governance-only to live-authorized requires, at minimum:
1. a later ADR that widens authority explicitly,
2. explicit human approval of the named variant,
3. a policy/version change outside the run that generated the evaluation receipt,
4. preservation of the original live V7 receipt trail and the governance-evaluation receipt trail.

## Explicit non-goals

This contract explicitly defers:
- live evidence-aware ranking,
- live tie-break mutation from shadow signals,
- candidate pruning from priors or shadow outcomes,
- evaluation reordering,
- auto-blocking or auto-approving promotion from governance receipts,
- cross-run aggregate governance scoring beyond the first receipt wave,
- broad experiment orchestration infrastructure,
- policy self-mutation or any V9-style autonomous strategy evolution.

## First execution slice aligned to this contract

The first AK-backed implementation slice after this ADR is:
- `AK-593` — **Synthesis evidence substrate: emit first governed policy-evaluation receipts for named governance-only ranking/promotion variants from shadow predictive-ranking evidence**

That slice should materialize the first receipt wave on persisted runtime metadata while keeping live V7 ranking, tie-breaking, pruning, and promotion behavior unchanged.

Consequences
------------
Positive:
- DSPx gains the first durable seam between evidence-aware experimentation and live policy authority.
- The repo can evaluate named ranking or promotion-policy variants against real SG2 evidence without pretending those variants already govern production behavior.
- Later `TG23` work can materialize receipts against a frozen contract instead of rediscovering variant boundaries ad hoc.
- Human promotion authority becomes more explicit because the receipt now records both what a variant would have said and why it still lacked live power.

Costs / tradeoffs:
- The first slice is intentionally narrow; it creates governance receipts, not a full experiment platform.
- Many runs may still evaluate to `policy_evaluation_no_signal` or `policy_evaluation_mixed_or_inconclusive`.
- Operators must resist the temptation to treat repeated governance outcomes as de facto live policy until a later ADR explicitly widens authority.
