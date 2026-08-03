---
summary: "Accept a bounded DSPx execution-attempt lifecycle and receipt-backed evidence contract only for effects DSPx directly mediates."
read_when:
  - "Implementing or reviewing Decision 105 execution-episode custody in DSPx."
  - "Checking which semantic-evaluation effects DSPx may attest."
status: accepted
---

# ADR — Bounded semantic-evaluation execution custody v1

## Status and lineage

Accepted by AK Decision 105 after strict exact-byte review.

- Problem brief: `docs/project/semantic-evaluation-execution-custody-v1-problem-brief.md`
- Evidence note: `docs/project/semantic-evaluation-execution-custody-v1-evidence-note.md`
- RFC: `docs/project/semantic-evaluation-execution-custody-v1-rfc.md`
- Canonical machine: `docs/project/semantic-evaluation-execution-custody-v1-machine.json`
- Review memo: `docs/project/semantic-evaluation-execution-custody-v1-review-memo.md`
- Controlling synthesis: `docs/project/semantic-evaluation-execution-custody-v1-review-synthesis.md` (`ready_for_adr`)
- Reviewed commit/tree: `63aaa6430defc3d596f7866e2860710f75eea842` / `dfe8f76afe9cf6d104a3345e359401fd59d45fee`

The reviewed packet distinguishes current DSPx primitives from this target contract. This ADR accepts the target boundary; it does not claim that DSPx currently implements it.

## Context

DSPx already has local validation, attempt-like artifact allocation, generated-program invocation observation, receipt bundles, bounded replay, and candidate-local Oracle evidence. Those primitives do not establish a generic protected-data broker, OS process supervisor, network-isolation boundary, provider-call cardinality controller, executed provider/model identity authority, or terminal cleanup proof.

Decision 104 rejected a global cross-owner custody machine. It assigns immutable policy meaning to its semantic owner, deterministic evaluation to ROCS, publication/currentness to Decision 53, and governance truth to AK. Decision 105 therefore needs the smallest DSPx-local contract that can produce truthful evidence without absorbing those owners or attesting effects DSPx does not mediate.

## Decision

DSPx will own one bounded local execution-attempt lifecycle and may attest only effects it directly performs or observes at a defined mediation point.

The canonical v1 machine is the reviewed seven-state, ten-transition machine in `semantic-evaluation-execution-custody-v1-machine.json`. Its core rules are:

1. A durable attempt-start marker precedes any potentially external generated-program invocation.
2. An attempt has one immutable identity and cannot be reopened after a terminal transition.
3. Unknown outcome after durable start is terminal `indeterminate`; the same attempt is never retried.
4. Replay is a distinct attempt whose immutable projection identifies its source receipt. Replay cannot repair or relabel an indeterminate original.
5. A successful outcome becomes `closed` only through one atomic `seal_and_close` commit binding the outcome, complete evidence manifest, downstream receipt, terminal state trace, and closed marker.
6. Failure and indeterminate branches preserve their truthful terminal evidence and never manufacture a success receipt.
7. Idempotent recovery may repeat only operations whose durable effect identity proves that repetition cannot duplicate the mediated effect.

### Closed effect inventory

DSPx may claim only the reviewed inventory:

- validation it executes;
- local attempt/evidence writes it owns;
- durable invocation-start observation at its call boundary;
- invocation return/error observation available at that boundary;
- receipt and manifest sealing it performs;
- distinct replay output linked to a source receipt;
- candidate-local Oracle indexing it performs after closure.

An absent observation point produces an explicit nonclaim. Signatures or hashes bind intent and bytes; they do not prove runtime behavior.

### Immutable Decision 106 projection

Only an attempt whose atomic seal-and-terminal commit produced `closed` with terminal reason `observed_return` or `observed_failure` may expose the reviewed immutable non-semantic projection. Cancelled/unstarted and `indeterminate` attempts are ineligible for deterministic evaluation and expose no Decision 106 projection. An eligible projection binds attempt and replay lineage, contract and input identities, observed execution outcome, complete evidence/receipt identities, and fixed-null executed provider/model identity. It contains no semantic pass/fail, policy meaning, raw authority object, mutable pointer, publication status, or governance decision.

ROCS may consume an eligible projection under Decision 106, but DSPx does not compute or endorse the ROCS verdict.

## Consequences

### Benefits

- DSPx evidence is limited to observable effects at DSPx-owned boundaries.
- Crash ambiguity is preserved instead of being silently retried or converted to success.
- Receipt sealing covers the complete terminal trace.
- Replay lineage is explicit and cannot rehabilitate an original attempt.
- The ROCS interface is immutable, non-semantic, and independent of mutable currentness pointers.
- Owner-local lifecycle rigor replaces a global machine without weakening source-owner boundaries.

### Costs and residual risk

- Current DSPx source does not yet implement the accepted machine or atomic seal.
- The contract cannot prove provider-side call cardinality, provider retries, OS process cleanup, network isolation, protected-data custody, or executed provider/model identity.
- Local persistence and atomicity choices remain implementation work and require crash/concurrency proof.
- A receipt proves recorded observations and bound bytes, not complete external behavior.
- Decision 106 compatibility is unproven until ROCS independently accepts its consumer contract.

## Exclusions and non-authorizations

This ADR does not authorize or claim:

- a generic broker, global cross-owner state graph, supervisor/read spool, or sparse-Merkle protocol;
- protected-data custody, process containment, network containment, provider-call cardinality, or provider cleanup;
- semantic policy meaning, ROCS evaluation logic or verdict, Decision 53 publication/currentness, or AK authority;
- executed provider/model identity in v1;
- live policy, protected datasets, provider/model calls, network access, publication, adoption, Pi integration, prompt projection, automatic preflight, or production activation;
- reuse, rerun, relabeling, tuning, or revival of Decision 98 B0.

## Next gates

This ADR records architecture only. Before code, Decision 105 requires a separately reviewed implementation plan and validation/rollout/rollback companion. Any implementation task must remain DSPx-local and prove the machine with synthetic no-network fixtures, crash/restart ambiguity, atomic closure, replay lineage, idempotency, and forbidden-effect nonclaims.

The legal sequence is: separately reviewed implementation plan; explicitly scoped DSPx-only implementation; synthetic no-network conformance and crash/replay proof; acceptance of immutable projection bytes; only then Decision 106 interface work. Decision 107 remains blocked until Decisions 105 and 106 both have accepted interfaces. No gate authorizes its successor automatically, and this ADR alone does not establish accepted projection bytes.

## Rollback

Before implementation, rollback is documentary: supersede this ADR and keep existing DSPx runtime behavior unchanged. After implementation, rollback must stop new attempt admission, preserve all existing receipts and terminal evidence, prevent receipt rewriting or indeterminate rehabilitation, and disable the new path through an owner-reviewed forward change. Never delete evidence or reinterpret a terminal attempt to simulate rollback.
