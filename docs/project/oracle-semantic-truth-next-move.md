---
summary: "AK-4659 decision: pursue a provider-free transport-observation prerequisite for a fresh empirical successor, with mandatory pause if no material delta is feasible."
read_when:
  - "Choosing the next Oracle semantic-analysis empirical task after v10."
  - "Deciding whether shared Oracle, ROCS semantics, or another live attempt is the current truth gap."
type: "reference"
status: "selected_no_execution_authority"
task_id: 4659
---

# Oracle semantic truth next move after v10

## Decision

Select the **fresh empirical successor design route**, but do not create or execute v11 yet.

The immediate leaf is provider-free: specify and independently review a typed provider-call outcome receipt that can distinguish a failure proven before transport from an attributable response or a still-open possible external effect. A later empirical successor is admissible only if this work identifies a material observation/custody delta from v10. If it cannot, pause the semantic-analysis live line rather than repeat the same route and membrane under a new task number.

This decision grants zero provider, model, health-probe, network, shared-store, publication, release, activation, or ROCS operation authority.

## Bound facts

- AK-4643 consumed the only v10 corpus process and is non-retryable.
- The first `authority-boundary` case recorded `effect_possible` and then `effect_outcome_unresolved`; no later case ran.
- Result SHA-256 `e8f4de5a…ab49d` is `effect_indeterminate`, not passed or failed.
- Provider-free verification SHA-256 `bd09f20b…a93e` accepted artifact integrity without changing the empirical disposition or terminal bytes.
- V9, code-semantics-v1, and the v10 contract remain immutable evidence. Their complete hashes are recorded in AK-4643 evidence and the v10 learning.
- Provider transport-call cardinality, provider-internal retry behavior, executed provider/model identity, and whether the possible external effect completed remain unproved.
- Decisions 106 and 107 are `unblocked/rejected` with no ADR or accepted semantic-result interface.
- Shared Oracle explicit publication, backup, and fail-closed authority dogfood have succeeded, while the current shared service remains explicit opt-in and `production_ready: false`.

## Proposition and owner classification

| Candidate next route | Proposition | Owner | Current disposition | Selection |
|---|---|---|---|---|
| Fresh empirical successor | Can the exact bounded semantic-analysis corpus produce attributable, scoreable DSPx empirical evidence under a materially stronger effect-observation contract? | DSPx for evaluator/custody; provider adapter owner for transport facts | Unanswered; v10 retained no scoreable response | **Selected for provider-free design only** |
| Semantic-owner interface | Do exact subjects conform to accepted semantic policy? | Named semantic owner, then ROCS | Unconstructible from current inputs; Decisions 106/107 rejected | Not selected |
| Shared-store durability | Can curated empirical memory satisfy current storage-owner production-readiness gates? | DSPx publication contract plus named storage/infra owner | Pilot publication/backup dogfood exists; production readiness remains separate | Valid later leaf, not a semantic-analysis answer |
| Pause | Is another empirical design unjustified because no material observation delta exists? | DSPx task owner | Contingent | Mandatory fallback |

Artifact integrity, empirical quality, semantic conformance, shared publication, and activation answer different propositions. No result in one column can substitute for another.

## V10 observation gap

The exact v10 source and terminal history narrow the local gap without proving provider behavior:

1. DSPx durably marked the possible effect before the generate boundary.
2. The adapter recorded one generate invocation/history entry in the code path that ended with a non-attributable result.
3. The retained packet correctly refused to reinterpret that local bookkeeping as proof that transport did or did not occur.
4. Because no attributable response or provider-confirmed no-effect observation existed, terminal precedence required `effect_indeterminate`.

The missing fact is therefore not another semantic label or scorer threshold. It is a typed, bounded transport/outcome observation owned at the provider-adapter boundary.

## Material successor prerequisite

A provider-free successor design is `successor_designable` only if it can define all of the following without invoking a provider:

- an owner-defined closed outcome vocabulary such as `transport_not_started`, `transport_started`, `response_completed`, `response_failed`, and `transport_outcome_unresolved`;
- a durable pre-transport marker and a terminal adapter receipt whose ordering and cardinality are independently checkable;
- exact rules for when DSPx may close an effect as proven no-transport, attributable response, typed response failure, or indeterminate;
- bounded sanitized error classification and transport metadata with no token, header, credential path, raw response, or unbounded diagnostic retention;
- explicit separation between DSPx generate/history counters and provider transport facts;
- fixture-only positive, negative, malformed, interrupted, duplicate, reordered, and missing-receipt tests;
- exact source/dependency identity for both the provider adapter and DSPx consumer;
- fail-closed behavior when the provider owner cannot supply the required fact.

The `tryinget-dspy-lm-auth` owner controls any new inner transport receipt or callback. DSPx may consume and verify an accepted typed receipt; it must not infer that fact from call counts, exception text, or missing output.

## Mandatory pause gate

Select `pause_unattributable` and create no empirical execution successor if any of these holds:

- no provider-owner mechanism can distinguish pre-transport failure from post-transport uncertainty;
- the proposed change only repeats v10 with another ledger or broader retention;
- feasibility requires a provider, backend, health, or network probe;
- the design depends on raw/unbounded output, secrets, auth-store inspection, or credential paths;
- the proposal changes semantic meanings, labels, subjects, precedence, or claim vocabulary without an accepted semantic owner;
- a fresh unique task/version/ledger, exact review, separate live gate, or independent provider-free verifier cannot be guaranteed;
- the only rationale is that v10 did not pass.

A pause is a truthful result, not a blocker to route around.

## Why the other routes are not first

### Semantic-owner interface

Decision 106 lacks accepted policy bytes, owner-selected subjects, typed joins, access/currentness authority, verdict and abstention vocabulary, precedence, and vectors. Decision 107 cannot manufacture those absent source facts. Only a new accepted owner proposal could justify a fresh ROCS decision; DSPx empirical work cannot supply it.

### Shared-store durability

The current-status owner document records explicit DS1621 publication dogfood, remote backup coverage, and a fail-closed activation boundary. Residual production readiness is real but belongs to a separate storage/publication proposition and owner set. It cannot score the semantic-analysis corpus, prove an executed model, or resolve v10's open effect.

### Immediate unconditional pause

A permanent pause is premature because a bounded provider-free design question remains answerable: whether an owner-supplied transport receipt can create a materially stronger observation boundary. The pause becomes mandatory if that prerequisite fails review.

## Legal next transition

The next execution leaf should be a **no-provider design/review task** for the typed provider-call outcome receipt and DSPx consumption contract. It may produce a cross-repo handoff to the `tryinget-dspy-lm-auth` owner. It must not materialize a v11 benchmark, mutate v10 artifacts, or grant live authority.

Only after that design is accepted as `successor_designable` may a separate task propose v11. Such a task would require a fresh contract, task-fixed ledger and artifact root, exact candidate review, separate operator/live gate, one-process/no-retry custody, and provider-free verification. V10 remains immutable terminal history.

## Maximum claim

AK-4659 selects the next **design question**. It does not establish that a successor is implementable, authorize a provider attempt, prove shared Oracle readiness, reopen Decisions 106/107, establish ROCS conformance, or grant publication, release, or activation authority.
