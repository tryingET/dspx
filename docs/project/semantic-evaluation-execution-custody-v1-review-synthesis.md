---
summary: "Controlling Decision 105 synthesis accepting bounded DSPx execution-episode custody for ADR consideration."
read_when:
  - "Determining the legal next move after Decision 105 review."
type: "review_synthesis"
status: "accepted"
decision_id: 105
review_outcome: "ready_for_adr"
---
# Decision 105 controlling review synthesis

## Controlling input

This synthesis controls only the exact packet recorded in [`semantic-evaluation-execution-custody-v1-review-memo.md`](semantic-evaluation-execution-custody-v1-review-memo.md): commit `63aaa6430defc3d596f7866e2860710f75eea842`, tree `dfe8f76afe9cf6d104a3345e359401fd59d45fee`, and the five listed document hashes.

The predecessor at `2aa41a9d4d3e64364a488707e1e5721965e5d7c1` remains rejected review history.

## Synthesis

The exact packet is coherent for ADR consideration because it selects the smallest authority DSPx can truthfully own:

1. DSPx allocates and terminally disposes one local attempt identity.
2. DSPx may claim only validation, invocation observation, local evidence, receipt, replay-output, and candidate-local Oracle effects it directly performs.
3. A durable attempt-start marker precedes the potentially external generated-program invocation.
4. Missing or ambiguous outcome after start consumes the attempt as `indeterminate`; there is no same-attempt retry.
5. One atomic `seal_and_close` commit binds the outcome, complete evidence manifest, downstream receipt, full state trace, and terminal marker.
6. Replay is a distinct attempt with mandatory source-receipt lineage and cannot rehabilitate an indeterminate original.
7. The Decision 106 projection has exact mandatory members, fixed-null executed identity, no semantic pass/fail, no raw authority, and no mutable pointer.
8. Protected-data custody, provider cardinality/retries, OS process cleanup, network isolation, executed identity, semantic truth, publication/currentness, and governance remain outside DSPx's claim.

## Decision recommendation

`ready_for_adr`

A Decision 105 ADR may accept only this execution-episode/evidence boundary and canonical seven-state machine. It must state that current DSPx does not implement the machine and that a later independently reviewed implementation plan is required before code.

## Legal next sequence

```text
Decision 105 boundary ADR
→ separately reviewed implementation plan
→ explicitly scoped DSPx-only implementation task
→ synthetic no-network conformance and crash/replay proof
→ later Decision 106 interface work only after accepted immutable projection bytes exist
```

No arrow authorizes the next. No real policy/data, provider/model call, network, protected-data broker, shared publication, consumer, Pi, prompt projection, preflight, or production activation is authorized.
