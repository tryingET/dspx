---
summary: "Freeze the first post-diagnostics SG2 evidence-consuming behavior before predictive ranking."
read_when:
  - "You are wiring SG2 evidence into runtime behavior after TG7 diagnostics."
  - "You need the contract for the first evidence consumer before V8 predictive ranking."
---

ADR 20260324 — Synthesis Evidence History Advisory Contract V1
==============================================================

Status
------
Accepted

Context
-------
`TG6` and `TG7` materially changed the SG2 posture:
- DSPx can now retrieve the V1 module-synthesis evidence bundle from exact-match receipts, replay verification, and constrained Oracle neighbors.
- `module-gen` already surfaces that bundle through bounded `synthesis_diagnostics` metadata and persisted receipts.

That means SG2 is no longer blocked on evidence *retrieval* or evidence *visibility*.
The next risk is different: DSPx could jump straight from raw diagnostics into predictive ranking or policy mutation without first proving that the evidence bundle can support one narrow, auditable runtime behavior.

There is also a contract-shape constraint that matters before V8 work:
- the current evidence bundle is keyed to the **request tuple**,
- healthy exact-match receipts tell us about prior outcomes for the same request,
- that evidence is strong enough to compare the **current selected artifact** against healthy prior winners,
- but it is **not yet a trustworthy per-candidate prior** for the current fan-out before evaluation.

So the first post-diagnostics evidence consumer should operate **after** V7 ranking selects a candidate, not **inside** candidate ranking yet.

Decision
--------
Adopt **Synthesis Evidence History Advisory Contract V1** as the first post-diagnostics SG2 evidence-consuming behavior.

## Scope

This contract applies to the existing `module-gen` synthesis runtime after the normal V7 selection path has already produced a selected artifact.

It is intentionally:
- read-only,
- post-selection,
- module-generation-specific,
- replay-health-aware,
- advisory rather than policy-driving.

It does **not** authorize predictive ranking, candidate pruning, promotion blocking, policy mutation, or V9-style strategy evolution.

## Consumer role

The first evidence consumer is a **historical convergence advisory** for the selected module artifact.

That advisory answers one narrow question:

> Does the selected artifact converge with healthy exact-match history for the same request, diverge from it, or have insufficient healthy history to say?

The advisory consumes the existing evidence bundle plus the current selected artifact identity.
It does not request new remote evidence surfaces and it does not modify selection behavior.

## Inputs

The advisory consumes these inputs only:
1. the current request tuple,
2. the current selected artifact identity:
   - selected candidate id,
   - output hash,
   - cache key when available,
3. the existing V1 evidence bundle from exact-match receipts, replay verification, and constrained Oracle neighbors.

Authority order stays aligned with ADR 20260323:
1. healthy exact-match receipt evidence,
2. degraded exact-match receipt evidence for diagnostics only,
3. Oracle neighbors as contextual hints only.

## Advisory status model

The advisory must emit exactly one posture from this set:
- `no_history` — no exact-match receipts were retrieved.
- `degraded_history_only` — exact-match receipts exist, but none qualify as positive evidence because replay health is degraded or failed.
- `convergent_with_positive_history` — at least one positive-evidence exact-match receipt matches the current selected artifact identity.
- `divergent_from_positive_history` — positive-evidence exact-match receipts exist, but none match the current selected artifact identity.

For V1, artifact-identity matching is anchored first on `output_hash`.
`cache_key` may be carried for explanation, but it is not a substitute for `output_hash` when deciding convergence.

## Minimum advisory payload

The advisory payload must contain, at minimum:
- `advisory_version`
- `status`
- `selected_artifact`:
  - `selected_candidate_id`
  - `output_hash`
  - `cache_key`
- `history_summary`:
  - `exact_match_receipt_count`
  - `positive_evidence_count`
  - `oracle_neighbor_count`
- `matching_positive_receipts` — receipt identities/paths for positive-evidence matches
- `divergent_positive_receipts` — receipt identities/paths for positive-evidence non-matches
- `notes` — bounded explanatory strings

If the advisory cannot be computed, it must fail closed into an explicit unavailable payload rather than silently disappearing.

## Attachment surfaces

The V1 advisory must be attached to the same two runtime surfaces that currently expose `synthesis_diagnostics`:
- module artifact metadata from the live `module-gen` run,
- persisted `module-gen` receipt metadata.

The advisory may reuse the existing evidence bundle already retrieved during the run.
It must not require a second independent evidence-discovery pass by default.

## Trust and interpretation rules

Interpret the advisory as follows:
- `convergent_with_positive_history` means the selected artifact matches at least one healthy exact-match prior winner.
- `divergent_from_positive_history` means the selected artifact is novel relative to healthy exact-match history, not that it is wrong.
- `degraded_history_only` means the repo has historical traces, but replay health prevents them from counting as positive evidence.
- `no_history` means there is no exact-match basis for convergence claims yet.

Oracle neighbors may add context to notes or summary counts, but they do not upgrade a posture to convergence and they do not downgrade a posture to divergence by themselves.

## Explicit non-goals

This contract explicitly defers:
- using evidence as a ranking score input,
- pruning candidate fan-out before evaluation,
- blocking or auto-approving promotion based on advisory posture,
- using Oracle similarity as authority over exact-match replay-healthy receipts,
- mutating strategy or ranking policy from observed history.

## First execution slice aligned to this contract

The first AK-backed implementation slice after this ADR is:
- `AK-341` — **Synthesis evidence substrate: emit a read-only historical convergence advisory for module-gen selections**

That slice should materialize the advisory payload on live runtime metadata and persisted receipts while keeping V7 ranking/promotion semantics unchanged.

Consequences
------------
Positive:
- SG2 gains a real evidence consumer before predictive ranking begins.
- DSPx proves whether the retrieved evidence bundle is useful for explaining runtime outcomes without overstating its authority.
- The repo gets a durable novelty/convergence signal that later V8/V9 work can evaluate against receipts instead of jumping directly to hidden priors.

Costs / tradeoffs:
- The first evidence consumer is deliberately narrower than full predictive ranking.
- Exact-match request history may remain sparse for many modules, so `no_history` will be common at first.
- Novel selections remain advisory-only until a later contract decides whether governance or ranking should respond to them.
