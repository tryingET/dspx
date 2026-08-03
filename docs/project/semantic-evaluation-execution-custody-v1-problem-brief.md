---
summary: "Decision 105 problem statement for truthful DSPx execution-episode custody and evidence."
read_when:
  - "Reviewing Decision 105 or any DSPx semantic-evaluation runtime claim."
type: "problem-brief"
status: "proposed"
decision_id: 105
---
# Problem brief — DSPx semantic-evaluation execution custody

## Problem

Decision 104 assigns DSPx only the runtime effects and evidence it actually mediates. The earlier cross-owner design incorrectly assumed a generic protected-data broker with leases, handles, process supervision, and exactly-once external effects.

Current DSPx has bounded generated-program runtime episodes, candidate/receipt verification, local evidence files, replay support, and candidate-local Oracle evidence. It does not currently provide a general protected-data custody service, OS process supervisor, provider-call cardinality proof, network isolation, or external publication authority.

Decision 105 must define the smaller truthful boundary.

## Decision question

What owner-local lifecycle and evidence contract may DSPx use to say:

- one explicit local execution attempt was allocated;
- DSPx observed a return, failure, or ambiguity from the runtime path it invoked;
- local evidence was sealed only after the observed effect;
- replay and retry claims remain no stronger than the recorded mechanics;
- no unsupported protected-data, provider, semantic, publication, or governance authority is implied?

## Acceptance test

Decision 105 is ready for ADR only if independent review agrees that:

1. the effect inventory distinguishes current enforcement, current observation, target mechanics, and unsupported claims;
2. the owner-local machine is closed, bounded, terminal, and contains no retry edge;
3. an attempt-start marker precedes any potentially external provider effect in the target contract;
4. crashes cannot be converted into success, safe non-start, or permission to retry;
5. receipts are downstream of observed effects and an immutable seal commit;
6. Decision 106 receives a bounded immutable evidence projection, not DSPx-private state or a DSPx verdict;
7. semantic meaning, deterministic evaluation, publication/currentness, AK authority, and live rollout stay outside Decision 105.

Any claim that DSPx currently enforces absent custody/process/network mechanics is a blocker.

## Non-goals

This decision does not design a generic broker, protected dataset store, lease/handle protocol, process supervisor, network sandbox, cryptographic authority fabric, ROCS evaluator, Decision 53 adapter, implementation, or live experiment.
