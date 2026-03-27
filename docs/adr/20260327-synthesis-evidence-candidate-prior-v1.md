---
summary: "Freeze the first evidence-backed candidate-prior contract for module synthesis before predictive ranking."
read_when:
  - "You are planning how SG2 evidence may influence candidate priors or pruning."
  - "You need the trust boundary for pre-evaluation candidate-prior signals after TG9."
---

ADR 20260327 — Synthesis Evidence Candidate-Prior Contract V1
=============================================================

Status
------
Accepted

Context
-------
`TG9` proved that the SG2 evidence bundle can support one narrow runtime behavior without changing V7 selection semantics: DSPx now emits a read-only historical convergence advisory for the selected `module-gen` artifact.

That closes the first post-diagnostics question, but it opens the next risk:
- the repo now has exact-match receipt history, replay-health facts, and Oracle neighbors available during `module-gen`,
- the current runtime also materializes multiple deterministic candidates with stable `variant_id` / `variant_origin` metadata before evaluation,
- and the tempting next move is to treat that history as a pre-evaluation ranking or pruning signal.

The trust boundaries are still narrower than that temptation:
- replay verification only proves the persisted selected artifact/cache linkage for a prior run,
- historical non-winning candidates are visible in ranked payloads, but they are not replay-verified authority in the same way as prior winners,
- Oracle neighbors remain semantic context rather than exact-match proof.

So the first candidate-prior contract must stay explicitly bounded: it should tell DSPx whether a **current candidate identity** has replay-healthy exact-match winner history, but it must not pretend that lack of winner history is already negative evidence or that prior losers are trustworthy pruning authority.

Decision
--------
Adopt **Synthesis Evidence Candidate-Prior Contract V1** as the first SG2 contract for candidate-level priors in `module-gen`.

## Scope

This contract applies only to the existing multi-candidate `module-gen` synthesis runtime.

It is intentionally:
- local-first,
- exact-match-first,
- replay-health-gated,
- candidate-identity-aware,
- read-only,
- winner-history-only.

It does **not** authorize predictive ranking, candidate pruning, promotion blocking, policy mutation, or V9-style strategy evolution.

## Prior consumption phase

The V1 candidate-prior payload is computed **after current candidates are materialized but before any future evidence-aware ranking experiment would consume it**.

That phase boundary matters:
- current candidates already have stable runtime identity (`candidate_id`, `variant_id`, `variant_origin`, ordinal, strategy metadata),
- but V7 evaluation and promotion behavior must remain unchanged while this contract is frozen and first materialized.

V1 therefore defines a read-only payload that later ranking work may inspect, not a score that current selection policy may apply yet.

## Candidate identity key

V1 candidate-prior matching is anchored on a current candidate identity key with these fields:
1. exact request tuple from ADR 20260323,
2. `variant_id` from current candidate metadata,
3. `variant_origin` from current candidate lineage,
4. current synthesis strategy/policy context for explanation only.

For V1, a current candidate is prior-eligible only when `variant_id` and `variant_origin` are both present.
If either field is missing, the payload must report an explicit unsupported status for that candidate instead of silently treating it as zero-history evidence.

## Evidence sources and authority order

V1 candidate-prior evidence is consumed in this order:
1. replay-healthy exact-match `module-gen` receipts whose selected winner can be resolved to a candidate identity key,
2. degraded exact-match receipts for diagnostics only,
3. exact-match ranked-candidate payloads for explanation only,
4. Oracle neighbors as contextual hints only.

Trust remains monotonic:
- exact-match receipt history says what happened,
- replay health proves which historical winner still counts as positive authority,
- ranked candidate payloads explain the prior run shape but do not create negative authority by themselves,
- Oracle adds context but cannot override exact-match replay-healthy winner evidence.

## Winner-history rule

A prior run contributes **positive candidate-prior evidence** only when all of the following hold:
- the receipt is an eligible exact-match `module-gen` synthesis receipt,
- replay status is healthy under ADR 20260323,
- the historical selected winner can be resolved to `variant_id` and `variant_origin`,
- that historical winner identity matches the current candidate identity key.

This means V1 authorizes only **winner-history matches** as positive authority.

V1 explicitly does **not** treat the following as negative evidence:
- a current candidate lacking any historical winner match,
- a current candidate appearing as a non-selected ranked candidate in prior receipts,
- Oracle similarity without exact-match replay-healthy winner evidence,
- replay-degraded or malformed exact-match history.

## Candidate prior status model

Each current candidate must emit exactly one V1 status from this set:
- `unsupported_candidate_identity` — the current candidate lacks the stable identity fields V1 requires.
- `no_positive_winner_history` — no replay-healthy exact-match prior winner matches the current candidate identity.
- `degraded_history_only` — exact-match history exists, but no replay-healthy winner evidence qualifies as positive authority.
- `matches_positive_winner_history` — at least one replay-healthy exact-match prior winner matches the current candidate identity.

For V1, `no_positive_winner_history` means only that DSPx lacks positive winner authority for the current candidate.
It is not a penalty verdict and it is not pruning authority.

## Minimum payload

The V1 candidate-prior payload must contain, at minimum:
- `candidate_prior_version`
- `mode` (`winner_history_only`)
- `history_summary`:
  - `exact_match_receipt_count`
  - `positive_evidence_count`
  - `oracle_neighbor_count`
  - `candidate_count`
- `candidate_priors` — one entry per current candidate, each including:
  - `candidate_id`
  - `variant_id`
  - `variant_origin`
  - `status`
  - `positive_winner_match_count`
  - `matching_positive_receipts`
  - `notes`
- `notes` — bounded bundle-level explanatory strings

If the payload cannot be computed, it must fail closed into an explicit unavailable structure rather than silently disappearing.

## Attachment surfaces

The V1 candidate-prior payload must attach to the same two runtime surfaces already carrying `synthesis_diagnostics`:
- live `module-gen` artifact metadata,
- persisted `module-gen` receipt metadata.

The implementation may reuse the existing SG2 evidence bundle already retrieved for the run.
It must not create a second hidden discovery path or silently widen authority beyond replay-healthy exact-match winner history.

## Explicit non-goals

This contract explicitly defers:
- feeding the payload into the ranking score,
- pruning candidate fan-out before evaluation,
- penalizing candidates because they historically lost,
- treating ranked-candidate presence as negative authority,
- treating Oracle similarity as enough to create or deny a prior,
- auto-approving or blocking promotion from prior status,
- strategy/policy mutation or any V9-style self-evolution.

## First execution slice aligned to this contract

The first AK-backed implementation slice after this ADR is:
- `AK-377` — **Synthesis evidence substrate: emit read-only candidate winner priors for module-gen variants**

That slice should materialize the V1 payload on live metadata and persisted receipts while leaving V7 ranking, tie-breaking, and promotion behavior unchanged.

Consequences
------------
Positive:
- DSPx now has a dated contract for the first candidate-level prior surface instead of jumping directly from post-selection advisory to hidden pre-evaluation scoring.
- Replay-healthy exact-match winner history becomes usable without overstating what the repo can prove about historical losers.
- A later V8 ranking experiment can consume a durable, receipt-backed payload instead of rediscovering trust boundaries ad hoc.

Costs / tradeoffs:
- V1 priors are intentionally asymmetric: they can recognize prior winners but not safely penalize prior losers.
- Candidate-prior usefulness will initially depend on stable variant identity and repeated exact-match runs.
- Predictive ranking remains deferred until the repo proves that the read-only payload is useful and governance decides how much authority it should gain.
