---
summary: "Decision 105 RFC for bounded DSPx execution-episode custody and immutable evidence projection."
read_when:
  - "Reviewing or implementing DSPx semantic-evaluation execution episodes."
type: "rfc"
status: "proposed"
decision_id: 105
---
# RFC — DSPx semantic-evaluation execution custody v1

## Status and authority

Proposed for Decision 105 strict convergence. This RFC grants no implementation, provider/model invocation, real-data use, publication, or live-effect authority.

Decision 104 is controlling: DSPx may own evidence only for effects it actually mediates. The semantic owner retains immutable policy meaning; ROCS owns deterministic evaluation; Decision 53 owns publication/currentness; AK owns decision/task/evidence lineage.

## Decision

Adopt **execution-episode custody**, not a generic custody broker.

DSPx custody is limited to:

1. allocation and terminal disposition of one DSPx-local attempt identity;
2. local candidate/input validation DSPx performs;
3. the generated-program invocation path DSPx calls and the value/failure returned to it;
4. DSPx-owned local evidence and receipt bytes;
5. explicit ambiguity when potentially external effects cannot be reconciled.

DSPx does not gain custody over caller-owned raw data, provider infrastructure, network effects, external processes, semantic meaning, ROCS verdicts, publication/currentness, or governance.

## Closed effect inventory

| Class | Decision 105 posture | Permitted claim |
|---|---|---|
| Candidate receipt and declared-surface validation | DSPx-owned current enforcement | DSPx validated the named local bytes under the recorded validation contract. |
| Output-root confinement and disjointness | DSPx-owned current enforcement | DSPx rejected a root that failed its local path boundary. |
| Private normalized input snapshot | DSPx-owned current narrow enforcement | DSPx exclusively wrote its local mode-0600 snapshot; no claim about source custody, secrecy outside that file, or later readers. |
| Generated-surface static membrane | DSPx-owned current narrow enforcement | Named static allow/deny checks passed; no OS sandbox or complete Python effect-isolation claim. |
| Generated-program callable invocation | DSPx-owned invocation and return/exception observation | DSPx called its configured runtime path and observed a return or caught failure. |
| Provider/model/network/subprocess effects behind the call | Observed or indeterminate, not mediated by this contract | No exactly-once, retry-count, executed-model, network-isolation, or external-cleanup claim. |
| DSPx local behavior/trace/episode/receipt files | DSPx-owned current mutation | DSPx wrote and hash-bound the named local evidence bytes. |
| Candidate-local Oracle index/report | Separate optional downstream DSPx-local effect | Only the explicitly named local index/report changed; not shared publication or evaluation authority. |
| Protected semantic-evaluation datasets, leases, read handles, revocation, access history | Unsupported | No claim permitted. A later owner decision is required before such a capability may exist. |
| General child-process supervision and PID-safe cleanup | Unsupported | No process-custody or cleanup claim permitted. |
| Semantic meaning, deterministic evaluation, verdict, publication/currentness, AK governance | Owned elsewhere | No DSPx authority claim permitted. |

An implementation must reject any receipt field that claims an effect outside this inventory.

## Canonical owner-local machine

[`semantic-evaluation-execution-custody-v1-machine.json`](semantic-evaluation-execution-custody-v1-machine.json) is the sole normative lifecycle for one attempt. Prose cannot add states, transitions, retry edges, or stronger authority.

```text
requested → rejected
requested → allocated → closed                 # no attempt started
                       → attempting → indeterminate
                                    → outcome_observed → indeterminate
                                                       → evidence_sealed → closed
```

The machine has eight states and eleven transitions. `rejected`, `indeterminate`, and `closed` are terminal. No terminal state reopens.

### Attempt identity

An `attempt_id` is globally unique within the DSPx owner domain and no-replace. The implementation decision must define its exact generation and durable uniqueness mechanism. Decision 105 requires only these invariants:

- allocation commits the ID and normalized-input binding once;
- no second allocation may reuse it;
- `indeterminate` consumes it permanently;
- execution reproduction uses a distinct attempt ID with explicit lineage and never rewrites the original attempt.

### Start-before-effect rule

`start_attempt` durably commits before DSPx invokes the generated-program runtime path. The marker binds the attempt ID, candidate coordinate, normalized-input digest, accepted effect budget, runtime configuration observation, and evaluation-request digest.

Marker absence permits terminal `cancelled_before_attempt` or `recovered_unstarted` only when the implementation proves that the call site cannot be reached before marker commit. Marker presence without one durable outcome is `indeterminate`, not safe non-start.

### Outcome observation

DSPx may record exactly one:

- `return`: the exact normalized returned-output digest and local status observation; or
- `failure`: the sanitized failure type/message digest and local status observation.

A return is not a semantic pass. A caught failure is not proof that no provider/external effect occurred. Provider configuration is distinct from observed executed-provider/model identity; absent identity remains absent.

### Evidence seal

`seal_evidence` is downstream of one durable outcome observation. It commits one immutable manifest over all episode-owned evidence artifacts and a receipt that describes that committed manifest. Temporary/incomplete artifacts are not evidence.

The implementation decision must select a no-replace commit mechanism in which the immutable seal is the only success linearization point. Decision 105 does not prescribe a database, filesystem journal, signature system, or multi-owner authority service.

`closed` after `evidence_sealed` means no DSPx episode-owned local mutation remains pending under the attempt ID. It does not mean a provider process, network request, provider-internal retry, or caller-owned resource was cleaned up.

## Crash and recovery

| Last durable state | Lawful recovery |
|---|---|
| no allocation | Return no-attempt evidence; allocate only through a fresh request. |
| `allocated` with no start marker | Verify marker absence and close as unstarted; never claim an invocation occurred. |
| `attempting` with no valid outcome | Commit `indeterminate`; do not invoke again under the attempt ID. |
| `outcome_observed` without a valid seal | Complete the seal only from the immutable observation and verified episode-owned artifacts, otherwise commit `indeterminate`; never re-invoke. |
| `evidence_sealed` without `closed` | Verify the seal and commit `closed` without re-invocation or evidence rewrite. |
| terminal | Return the immutable terminal record for an exactly equal read request; perform no effect. |

Transport timeout, caller cancellation, missing receipt delivery, or process crash does not prove the underlying provider effect did not occur.

## Idempotency and replay

Read-only validation of an existing terminal record is idempotent. Mutation commands use unique operation IDs bound to the complete attempt/request operation; unequal reuse fails closed.

There is no execution retry transition. A replay that re-executes behavior is a new, explicit attempt with:

- a new attempt ID;
- lineage to the source sealed receipt;
- its own start/outcome/seal lifecycle;
- claims limited to the replay mechanism actually used.

An `indeterminate` original cannot be converted to success by a later replay.

## Immutable Decision 106 projection

Decision 106 may consume only a closed, evidence-sealed attempt whose terminal reason is `observed_return` or `observed_failure`. Cancelled/unstarted and indeterminate attempts are ineligible for deterministic evaluation.

The projection contains exactly these top-level members:

1. `schema_version = dspx-semantic-evaluation-evidence-projection-v1`;
2. `episode_id`;
3. `attempt_id`;
4. `candidate_coordinate` — source manifest and candidate-receipt digests;
5. `input_coordinate` — normalized input digest and disclosure posture, never an implied raw-data right;
6. `evaluation_request_digest` — opaque binding to the owner-supplied request bytes;
7. `effect_inventory_version`;
8. `runtime_observation` — configured runtime/provider observations, separately nullable executed identity, start marker, and observed return/failure kind;
9. `outcome_evidence` — returned-output or failure digest with no semantic pass/fail field;
10. `episode_evidence_manifest_digest`;
11. `receipt_digest`;
12. `state_trace_digest` through terminal `closed`;
13. `non_authority` — explicit false semantic-meaning, deterministic-verdict, publication, currentness, promotion, governance, AK-mutation, and external-authority flags.

Every member is mandatory; nullable observations remain explicit nulls. The projection contains no raw provider credential, raw protected dataset, reusable handle, publication state, ROCS verdict, or mutable-latest pointer.

ROCS validates the projection against an accepted Decision 106 contract. Validation cannot mutate the DSPx episode, acquire DSPx authority, or reinterpret absent effect evidence as success.

## Current-to-target gap

Current DSPx source establishes useful primitives but does not implement this canonical machine:

- `runtime_inputs.json` is an exclusive local allocation-like write, but there is no canonical durable attempt-start/outcome/seal/closed record sequence;
- current evidence is written across multiple files without one normative immutable seal commit;
- current runtime catches returns/failures but cannot prove provider transport cardinality, provider retries, executed model identity, network isolation, or external cleanup;
- current replay is bounded and receipt-aware but is not this machine's explicit distinct-attempt lineage protocol.

Therefore acceptance of this RFC would authorize only a later implementation plan, not a claim that the lifecycle exists.

## Validation obligations for a later implementation plan

A later plan must include generated positive/negative traces for every machine transition and at least:

- duplicate attempt allocation;
- call-before-start-marker prevention;
- crash after start and before outcome;
- crash after outcome and before seal;
- seal hash mismatch and partial artifacts;
- receipt-before-effect rejection;
- same-attempt retry rejection;
- replay with distinct lineage;
- provider/model identity absent versus observed;
- unsupported custody/process/network claim rejection;
- Decision 106 projection exact-member and null handling;
- terminal-state reopening rejection.

Green tests are evidence, not architecture or runtime acceptance.

## Explicit non-authorization

Decision 105 does not authorize implementation, live provider/model calls, real policy/data, network access, a protected-data broker, shared Oracle publication, Decision 53 integration, consumer adoption, Pi/prompt projection, automatic preflight, or production activation. Decision 98 B0 and rejected Decision 103 R2 remain excluded from every input, fixture, replay, and evidence claim.
