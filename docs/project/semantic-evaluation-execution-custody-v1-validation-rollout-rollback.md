---
summary: "Synthetic no-network validation, non-activation rollout, and forward-only rollback for Decision 105 implementation."
read_when:
  - "Validating or reviewing the Decision 105 DSPx implementation."
  - "Checking why Decision 106 and runtime activation remain gated."
type: "validation_rollout_rollback"
status: "proposed"
decision_id: 105
---

# Decision 105 validation, rollout, and rollback

## Validation posture

Use only synthetic canonical normalized-input bytes and digest coordinates, in-memory deterministic callables, owner-private temporary local SQLite stores, and subprocess crash harnesses. Do not load real policy/data, configure a provider/model, access the network, invoke the current generated-program runtime, publish, index shared Oracle, call AK from tests, or mutate external authority.

Tests establish only API/transaction behavior on the exercised local filesystem and SQLite runtime. They do not prove same-UID/root tamper resistance, arbitrary power-loss durability, provider behavior, protected-data custody, process/network cleanup, semantic correctness, Decision 106 compatibility, publication/currentness, or production safety.

## Exact identity and schema checks

Before behavior tests:

- bind code, test, plan, machine, ADR, and projection-schema hashes to the reviewed commit/tree;
- validate the projection schema as Draft 2020-12;
- assert the schema's exact fifteen top-level members and every recursive `additionalProperties=false` boundary;
- assert digest grammar, UUID4 grammar, exact enums/constants, nullability conditions, and explicit non-authority false values;
- reject non-NFC strings, unknown nested keys, control characters, numbers, non-finite values, invalid UTF-8, uppercase/short digests, and trailing-newline byte variants;
- prove stored bytes equal hashed bytes exactly and remain stable across process reopen.

## Complete machine and guard proof

Generate all ten canonical transitions and reject every non-edge. Each public mutation must record the exact canonical operation name and a bound operation ID. Prove every terminal has no outgoing mutation.

For **every canonical guard**, include a negative case:

| Operation | Required negative guard cases |
|---|---|
| `reject_request` | validation did not fail; allocation/start already exists |
| `allocate_episode` | invalid request; attempt collision; unsafe/unconfined store; store equal to/inside/ancestor of verified candidate root; store equal to/ancestor/descendant of candidate files or input source; symlink/non-regular/replaced source; manifest or candidate-receipt coordinate mismatch; noncanonical input-source bytes; input digest mismatch; invalid original/replay lineage |
| `cancel_before_attempt` | start exists; wrong terminal reason |
| `recover_unstarted_allocation` | start exists; wrong recovery reason or unequal operation replay |
| `start_attempt` | start exists; candidate/input/request binding drift; effect inventory not exact v1 |
| `observe_return` | start absent; outcome exists; fabricated/public outcome submission attempt |
| `observe_failure` | start absent; outcome exists; fabricated/public outcome submission attempt |
| `recover_unknown_attempt` | start absent; valid outcome exists |
| `recover_unsealed_outcome` | outcome absent/multiple; one valid constructible seal exists |
| `seal_and_close` | outcome absent/multiple; artifact hash mismatch; seal exists; receipt does not describe internally mediated outcome; incomplete trace; pending attempt-owned mutation |

Also prove:

- `cancel_before_attempt` cannot emit `recovered_unstarted`;
- the three recovery operations stay distinct in events and operation bindings;
- no bulk recovery mutation exists;
- `list_incomplete()` is read-only;
- every recovery mutation requires an explicit operation ID;
- equal operation replay adds no event and unequal reuse fails.

For allocation, prove descriptor-read manifest and candidate-receipt hashes equal their request coordinates, exact input-source bytes are canonical and equal their input coordinate, and the candidate root is derived from the verified manifest path. Prove the same transaction makes the attempt row and exact `input_snapshots` BLOB visible together or neither visible. Verify reopening preserves exact bytes, UPDATE/DELETE fails, and no terminal seal/projection contains the snapshot bytes or a raw-data access right. Verify only source-path digests are retained and no source custody/cleanup claim is emitted.

## Effect-mediation proof

Instrument the supplied synthetic callable and private fault barrier:

1. immediately before callable entry, independently read the store from a second connection and prove the durable `start_attempt` event exists and binds the stored snapshot digest;
2. prove the one-argument callable receives an immutable view of the exact stored snapshot bytes/digest; supply conflicting closure data and prove the recorded call-boundary input remains the passed snapshot, while making no claim that arbitrary callable internals used it;
3. prove no public module symbol can record return/failure or accept outcome bytes;
4. return one synthetic value and prove the private `observe_return` digest matches the direct normalized return;
5. raise one synthetic exception and prove the private `observe_failure` digest matches the sanitized caught failure;
6. terminate during the callable and prove recovery yields `indeterminate` without another invocation;
7. attempt `start -> caller-crafted outcome -> seal` through public APIs and prove it is impossible;
8. prove the receipt and projection are created only after the internally mediated outcome commit.

These tests establish mediation through the module API, not resistance to a hostile same-UID process rewriting Python or SQLite directly.

## Crash and durability matrix

Use a fresh subprocess/store for each row. Configure the private barrier at the required phase: `before_commit` for the pre-allocation and failed-seal transaction rows, `after_commit` for committed-state rows, and callable phases for invocation ambiguity. Force process exit or the specified transaction exception, reopen in a new process, and assert:

| Crash point | Required durable result |
|---|---|
| before allocation commit | no attempt exists |
| after allocation commit, before start | explicit `recover_unstarted_allocation` closes recovered-unstarted |
| after start commit, before callable entry | explicit `recover_unknown_attempt` produces `indeterminate`; no invocation/retry |
| during callable / before outcome commit | `indeterminate` |
| after return observation, before seal | explicit `seal_and_close` may use only verified immutable observation; never invoke again |
| after failure observation, before seal | same rule as return |
| during failed seal transaction | no partial terminal seal/projection/closed state visible |
| after seal commit, before result delivery | exact closed record/projection returns read-only; no second write |

After reopen, run SQLite integrity/foreign-key checks, verify directory/database owner/mode/device/inode/link count, verify no unexpected sidecar after clean close, and compare canonical hashes.

## Atomic seal proof

Within one SQLite transaction, `seal_and_close` makes visible together:

- exact closed evidence manifest;
- exact closed downstream receipt;
- full trace through `closed`;
- terminal marker;
- schema-valid exact projection bytes;
- eligible terminal state/reason.

Raise before commit and prove none are visible. After commit, prove all are visible and consistent with the acyclic order `trace -> manifest -> receipt -> projection -> outer seal`. Assert that manifest and receipt contain no projection/seal backlink, the trace contains no artifact-dependent result digest, and the outer seal digest is not embedded in its own preimage. Direct UPDATE/DELETE, trigger removal through the API, and event insertion after terminal must fail. Scope the claim explicitly to API/trigger enforcement; do not label the writable database independently tamper-evident.

Receipt construction before an internally mediated outcome, from unsupported effects, from an unstarted/indeterminate attempt, with unknown nested claim fields, or with an incomplete trace must fail.

## Projection proof

For both eligible terminal reasons:

- validate exact schema bytes and recursive object key sets;
- verify canonical encoding with no newline and stable hash across reopen;
- verify original/replay lineage and nullability;
- verify candidate/input/request/effect inventory coordinates and referenced digests;
- verify configured observation fields and fixed-null executed identities;
- verify digest-only outcome evidence condition and exact equality between `runtime_observation.outcome_kind` and `outcome_evidence.observation_kind`;
- verify all exact non-authority keys are false;
- reject unknown/omitted members at any depth, wrong type/null, mutated digest, noncanonical bytes, or ineligible terminal reason.

Rejected, cancelled, recovered-unstarted, and indeterminate terminals must expose no projection.

Produce one local synthetic projection and verification manifest. The manifest binds exact source commit/tree, schema hash, projection hash, and validation commands. It is implementation evidence only.

## Concurrency and store confinement

With two independent processes, prove one fresh-start transaction wins and **exactly one callable entry occurs**. The loser—whether using the same equal parent operation ID or a different operation ID—must not receive/reconstruct the private callable capability and must return an in-progress/terminal disposition without invocation. Also prove one operation/attempt/outcome/seal wins, equal replay is read-only, unequal reuse fails, crash-after-start requires recovery rather than another callable entry, and no partial row set appears.

Adversarial store cases must cover:

- symlink in every ancestor position;
- non-owner or group/world-writable ancestor;
- parent/store path replacement detected by device/inode recheck;
- database symlink, non-regular file, hard link count greater than one, wrong owner/mode;
- existing unexpected rollback journal/temporary sidecar after clean close;
- unknown schema version;
- network-filesystem detection when supported.

The module must not import provider configuration, networking clients, subprocess execution, Oracle publication, AK, or governance packages. Test code may use subprocess only for crash proof. Deny socket creation and prove the suite passes.

## Repository validation

Run current `Justfile` equivalents of:

```bash
uv run pytest -q tests/test_semantic_evaluation_execution_custody.py
uv run ruff check packages/dspx-core/src/dspx/services/semantic_evaluation_execution_custody.py tests/test_semantic_evaluation_execution_custody.py
uv run ty check packages/dspx-core/src/dspx/services/semantic_evaluation_execution_custody.py
just task-scope-check <implementation-task-id> working-tree
just check
just verify-full
```

Record exact commands/results. A skipped scope script is not scope proof; independently compare the diff to AK's frozen task scope.

## Independent review and projection-byte acceptance

Before integration, exact commit/tree/schema/code/tests require four unanimous concerns:

1. DSPx boundary and no runtime/CLI activation;
2. lifecycle, SQLite transactionality, crash recovery, idempotency, mediation, and concurrency;
3. complete recursive projection schema, canonical bytes, and ineligible-terminal handling;
4. store security, non-authority claims, and forbidden dependency/effect scan.

Any blocker rejects the slice; corrected bytes require fresh review. Preserve rejection and stop rather than repeatedly widening.

After implementation review and conformance, a **separate Decision 105 projection-byte acceptance gate** must bind and explicitly accept:

- implementation commit/tree;
- projection schema bytes/hash;
- one synthetic projection bytes/hash;
- conformance command evidence;
- four-lane review identities/outcomes;
- explicit statement that acceptance establishes only a prerequisite/readiness signal and does not authorize a successor.

Without that separate acceptance, Decision 106 remains blocked. After acceptance, the ROCS/Decision 106 owner must still separately authorize and initiate its own design work. Acceptance grants no Decision 106 authority, ROCS consumption, DSPx mutation, runtime wiring, provider/network use, publication, or activation.

## Non-activation rollout

1. Integrate the internal module/schema/tests only after exact review.
2. Keep existing runtime, CLI, replay, receipt, Oracle, and publication entry points unchanged.
3. Run one temporary synthetic no-network attempt/projection.
4. Emit the local verification manifest and hand it to the Decision 105 controller.
5. Any AK evidence recording is performed separately through an AK-owner-authorized action; this DSPx plan does not authorize it.
6. Remove temporary stores after required local evidence hashes are handed off unless separately retained outside Git.
7. Do not advertise production capability or allow a consumer.
8. Run the distinct projection-byte acceptance gate before any Decision 106 design.

## Stop and rollback

Stop on partial seal, missing start-before-call, outcome fabrication, same-attempt reinvocation, operation conflation, terminal mutation, projection/schema drift, unsupported claim, unsafe store, network/provider/process activity, scope escape, or inability to preserve `indeterminate`.

Before activation, rollback is forward code removal/revert through review; preserve review/failure evidence. Temporary stores may be removed only after required hashes are handed off, but never rewrite a retained terminal to simulate rollback.

If later activation exists, this plan is insufficient. Its owner must stop admission, preserve terminal evidence, disable forward, and prove attempts remain immutable/readable. Never delete receipts, reopen terminals, relabel `indeterminate`, or revive Decision 98 B0.
