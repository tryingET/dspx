---
summary: "Post-ADR implementation plan for the bounded Decision 105 DSPx execution-attempt machine and immutable evidence projection."
read_when:
  - "Implementing Decision 105 in DSPx after the ADR."
  - "Checking the exact code slice allowed before Decision 106."
type: "implementation_plan"
status: "proposed"
decision_id: 105
---

# Decision 105 implementation plan

## Purpose and authority

Implement the accepted seven-state, ten-transition DSPx-local machine from `semantic-evaluation-execution-custody-v1-machine.json` and produce constructible immutable projection bytes for a later Decision 105 byte-acceptance gate.

This plan does **not** activate the machine in `run_program_runtime_episode`, add a CLI command, invoke a provider/model, use real policy/data, access the network, publish evidence, mutate shared Oracle/AK/governance, or authorize Decision 106 design or consumption. The implementation is a new internal primitive exercised only by synthetic no-network tests. Wiring existing runtime entry points is a later DSPx owner decision.

## Selected slice

### Files

The first implementation slice is limited to:

- new `packages/dspx-core/src/dspx/services/semantic_evaluation_execution_custody.py`;
- new `tests/test_semantic_evaluation_execution_custody.py`;
- `docs/project/semantic-evaluation-execution-custody-v1-projection.schema.json`;
- this plan and its validation/rollout/rollback companion.

No change to `program_runtime_episode.py`, `program_execution_replay.py`, `run_receipts.py`, CLI modules, Oracle publication, provider configuration, or governance is allowed.

### Threat and durability scope

The store defends against other users, unsafe ancestors, symlink/hard-link substitution detectable at open, API misuse, concurrency, and process crash under local POSIX filesystem and SQLite guarantees. It does not claim resistance to a malicious process running as the same UID, root, direct coherent database rewriting, compromised kernel/storage firmware, power-loss behavior beyond SQLite's documented `synchronous=FULL` contract, or remote/network filesystems.

In this plan, **immutable** means append-only/terminal through the reviewed API plus SQLite triggers under that threat model; it is not independently anchored tamper evidence. **Durable** means a successful SQLite FULL transaction on a supported local filesystem; tests prove process-crash recovery, not all hardware failures.

### Race-resistant local store

The caller supplies a trusted parent directory, not a database filename. The module:

1. rejects any symlink ancestor;
2. requires every ancestor from the nearest existing owner root through the parent to be owned by the effective UID and not group/world writable;
3. opens and retains the parent directory descriptor with `O_DIRECTORY|O_NOFOLLOW`, records its device/inode, and rechecks the pathname binding before and after store creation/open;
4. creates a new store directory no-replace with mode `0700` relative to that descriptor, or reopens an existing directory only after owner/mode/device/inode checks;
5. precreates the database via `openat(O_CREAT|O_EXCL|O_NOFOLLOW, 0600)` for a new store;
6. requires database link count one, owner equal to effective UID, regular-file type, and mode `0600` before and after SQLite connect;
7. confines rollback journal/temporary SQLite files to the mode-0700 store directory and uses `journal_mode=DELETE`, `foreign_keys=ON`, and `synchronous=FULL`;
8. rejects network filesystems when reliably detectable and otherwise documents local-filesystem precondition.

All mutations use explicit `BEGIN IMMEDIATE`. A replaced parent/store/database binding, extra hard link, unsafe mode/owner, unexpected SQLite sidecar after clean close, or unknown schema version fails before further mutation.

SQLite is local persistence, not authority. Databases are local runtime evidence and must not be committed.

## Closed stored structures

All stored structures use exact required key sets and reject unknown members recursively.

### Immutable request binding

`AttemptRequest` contains exactly:

- `episode_id`;
- `attempt_kind` (`original|replay`);
- `source_receipt_digest` (null exactly for original, SHA-256 exactly for replay);
- `candidate_coordinate` with exactly `source_manifest_digest` and `candidate_receipt_digest`;
- `input_coordinate` with exactly `normalized_input_digest` and `disclosure_posture=digest_only_no_raw_access_right`;
- `evaluation_request_digest`;
- `effect_inventory_version=dspx-semantic-evaluation-execution-effect-inventory-v1`;
- `configured_runtime_digest`, `configured_provider`, and `configured_model`.

The accepted effect budget is not an open map. It is the single effect-inventory version constant above. Unknown claims or a wider version fail allocation.

### Allocation material and private input snapshot

`AllocationMaterial` is a separate closed, non-projection input containing exactly:

- `candidate_manifest_path` — an existing non-symlink local regular file;
- `candidate_receipt_path` — an existing non-symlink local regular file;
- `input_source_path` — an existing non-symlink local regular file containing canonical UTF-8 JSON object bytes.

The module opens each source descriptor-relative with no-follow checks, verifies stable device/inode/size across the read, and then closes it. It verifies the candidate files' SHA-256 values equal the two `candidate_coordinate` digests and the exact input-source bytes' SHA-256 equals `input_coordinate.normalized_input_digest`. Noncanonical input JSON, a coordinate mismatch, or source replacement fails before allocation.

In the same allocation transaction, the module stores the exact verified input-source bytes in an immutable `input_snapshots` BLOB row keyed by attempt ID. The mode-0600 database inside the mode-0700 store is the private normalized-input snapshot boundary; neither terminal seal nor projection exposes the bytes or grants a source-data access right.

The candidate root is derived from the verified manifest's parent rather than caller assertion. Before allocation, the module proves the store directory is not equal to, inside, or an ancestor of that candidate root and is not equal to or an ancestor/descendant of either candidate file or the input source. Every path component is checked under the store threat model. Only canonical source-path digests are retained with the request binding. This slice claims no custody, secrecy, lease, revocation, or cleanup for the source paths or for readers outside the private store.

### Exact projection schema

`semantic-evaluation-execution-custody-v1-projection.schema.json` freezes the complete recursive projection contract: exact keys, scalar types, nullability, lowercase SHA-256 grammar, configured-label grammar, original/replay condition, outcome condition, and recursive unknown-member rejection.

Projection values contain no JSON numbers. Strings must be valid UTF-8 and Unicode NFC; control characters outside JSON escapes are rejected. Stored and hashed projection bytes use one encoding only: UTF-8, NFC strings, sorted keys, separators `,` and `:`, `ensure_ascii=False`, `allow_nan=False`, and **no trailing newline**. There is no distinct display-byte encoding.

The schema itself is loaded from package/repo bytes only during tests; production code carries the same closed validators/constants so schema validation is not a mutable runtime dependency. Schema hash drift fails the exact fixture test.

### Atomic seal envelope

The internal terminal seal uses this acyclic construction order:

1. Build canonical `state_trace` bytes containing only canonical operation name, from/to state, caller/derived operation digest, sequence, and event digest. The terminal `seal_and_close` transition fact is independent of every artifact it commits.
2. Build and hash `evidence_manifest` with exactly the immutable request digest, start-event digest, outcome-event digest, state-trace digest, and effect-inventory version. It contains no receipt, projection, or seal backlink.
3. Build and hash `receipt` with exactly receipt schema version, attempt ID/kind, source-receipt digest, terminal reason, evidence-manifest digest, state-trace digest, and explicit non-authority object identical to the projection schema. It contains no projection or seal backlink.
4. Build and hash the schema-valid `projection`, which references the already-fixed manifest, receipt, and trace digests.
5. Build the closed outer seal containing exactly `seal_schema_version`, attempt ID, terminal reason, embedded manifest, receipt, trace, terminal marker, projection, and projection digest. Hash the outer seal only after construction; its digest is stored beside it and is not embedded in its own preimage.

The terminal marker contains exactly state `closed` and terminal reason. No manifest, receipt, trace, event, projection, terminal marker, or outer seal includes a digest that depends on itself or on a later node in the DAG.

The seal cannot contain raw input/output/failure/provider credentials or free-form effect claims. Return/failure evidence is digest-only. Sanitized failure text is canonicalized and hashed before sealing; the seal stores the digest, not message text.

### Database records

Store:

1. `attempts` — immutable request bytes/digest, retained source-path digests, current state, terminal reason;
2. `input_snapshots` — exact private normalized-input bytes/digest inserted atomically with allocation and never projected;
3. `operations` — unique operation ID, canonical machine operation, request digest, committed result digest;
4. `events` — monotonic per-attempt canonical transition bytes;
5. `terminal_seals` — the complete seal bytes/digest and exact projection bytes/digest for eligible observed-outcome closure;
6. `terminal_nonseals` — rejected, cancelled/recovered-unstarted, and indeterminate terminal bytes that expose no projection.

Schema triggers prohibit UPDATE/DELETE of input snapshots, operations, events, and terminal rows; prohibit transition insert after terminal; and allow attempt state change only with the corresponding event/terminal record in the same transaction. Once terminal, only exactly equal reads are lawful.

## Canonical operations and API

Every mutation maps one-to-one to a canonical machine operation and binds a non-empty caller operation ID, canonical operation name, attempt/request identity, and complete request digest. Equal replay returns the stored result without a new event; unequal reuse fails.

Public methods:

- `reject_request(operation_id, rejection_request)` → `reject_request`;
- `allocate_attempt(operation_id, request, allocation_material)` → `allocate_episode`, atomically stores the private normalized-input snapshot, and returns an internal UUID4 attempt ID;
- `cancel_before_attempt(operation_id, attempt_id)` → `cancel_before_attempt` only;
- `run_attempt(operation_id, attempt_id, allocation_material, callable(snapshot))` owns the full mediated call path: verifies the supplied source-path digests equal those retained at allocation, reopens and rehashes all three source files, rehashes the stored snapshot, privately commits `start_attempt`, passes an immutable snapshot view containing the exact stored bytes/digest to the supplied one-argument callable only after commit returns, privately commits exactly one `observe_return` or `observe_failure`, then privately commits `seal_and_close`;
- `recover_unstarted_allocation(operation_id, attempt_id)` → `recover_unstarted_allocation` only;
- `recover_unknown_attempt(operation_id, attempt_id)` → `recover_unknown_attempt` only;
- `recover_unsealed_outcome(operation_id, attempt_id)` → `recover_unsealed_outcome` only when verified immutable seal inputs cannot produce one valid seal;
- `seal_and_close(operation_id, attempt_id)` → `seal_and_close` from a previously durable immutable outcome without invoking again;
- `read_terminal(attempt_id)` and `read_projection(attempt_id)` are read-only.

`run_attempt` derives unique transition operation IDs from the caller operation ID plus canonical operation name and binds all derived IDs in `operations`. The start marker binds the verified candidate, input, and snapshot digests. Its `start_attempt` transaction has exactly one fresh-start winner: only the process that revalidates the supplied material against retained path digests and immutable content coordinates, rehashes the stored snapshot, proves all still match the immutable request, and changes `allocated -> attempting` receives an unpersisted private callable-entry capability carrying that exact immutable snapshot view. Any concurrent call—whether it reuses the equal parent operation ID or supplies a different one—observing `attempting`, an outcome, or a terminal state must not enter the callable; it returns the stored in-progress/terminal disposition and requires canonical recovery after ambiguity. The private capability is consumed before callable entry and cannot be reconstructed from database bytes. Start/outcome methods and mediation capabilities are private and absent from the module's declared public surface. No public method accepts a caller-supplied outcome observation.

A private test fault barrier supports named `before_commit` and `after_commit` phases for each canonical operation plus `before_callable` and `during_callable`. A `before_commit` barrier runs only after all guards and transaction writes are staged but before COMMIT, allowing process termination or an injected transaction exception to prove rollback. An `after_commit` barrier runs only after COMMIT returns. The barrier cannot alter request/evidence bytes, bypass a guard, fabricate an outcome, or appear in the public API.

There is no bulk mutating recovery scan. A read-only `list_incomplete()` may report candidates; the caller must invoke exactly one canonical recovery operation with its own operation ID for each attempt.

## Mandatory guards

Each operation enforces every guard from the canonical machine, including:

- validation failed / request valid;
- no allocation or start where required;
- output/store root confined to the new private store and path-disjoint from the resolved candidate root and input source supplied in allocation material;
- normalized input snapshot bytes canonical, digest-matched, and atomically committed with allocation;
- original/replay lineage validity;
- verified candidate manifest/receipt files match their coordinate digests, stored snapshot matches the input coordinate, and all candidate/input/request bindings remain unchanged;
- exact accepted effect-inventory version;
- exactly one allowed outcome kind;
- valid start/outcome/seal absence or presence for recovery;
- all seal artifacts hash-verified;
- receipt describes only the internally mediated observation;
- full terminal trace bound;
- no pending attempt-owned mutation.

Every guard gets at least one negative test; passing state-edge tests alone is insufficient.

## Effect mediation, identity, and replay

`run_attempt` is the only API that can create an observed return/failure. It commits start before entering the callable and creates outcome evidence only from the direct return or caught exception. A caller cannot submit outcome bytes. A caught failure does not imply effect-free failure. Missing post-start outcome becomes `indeterminate` through explicit recovery.

Attempt IDs are internal UUID4 values enforced by a primary key; tests inject a deterministic factory only to prove collisions. Replay always allocates a new attempt and requires a non-null source receipt. No method changes an original attempt or converts `indeterminate` to success.

The primitive claims only its validation, local SQLite commits, callable entry, and direct return/failure observation. It rejects protected-data custody, provider cardinality/retries, executed identity, network/process isolation or cleanup, semantic truth, publication/currentness, promotion, governance, AK mutation, or external authority. Candidate-local Oracle indexing is excluded.

## Implementation sequence

1. Freeze and validate the projection schema bytes.
2. Add canonicalization, closed validators, typed inputs, and exact claim schemas.
3. Add safe private-store creation/open, schema/triggers, and transactions.
4. Implement idempotency and each canonical operation separately.
5. Implement mediated `run_attempt`, private fault barriers, recovery, and atomic seal.
6. Add all synthetic tests from the companion plan.
7. Run focused and full gates plus four-concern exact-source review.
8. Emit a local verification manifest containing commit/tree, schema hash, test commands, and one synthetic projection hash.
9. Submit that manifest to the Decision 105 controller. Any AK recording is a separate AK-owner action, not an effect authorized by this DSPx plan.
10. Run a distinct Decision 105 exact projection-byte acceptance review. Its acceptance establishes only that a prerequisite is ready; the ROCS/Decision 106 owner must separately authorize and initiate Decision 106 design. It never permits consumption or activation.

## Stop conditions and completion

Stop on any new state/transition/retry, outcome submission API, non-atomic seal, terminal mutation, unsupported claim, unsafe store construction, runtime/CLI wiring, provider/network/process/protected-data effect, shared service, global broker, publication, ROCS verdict, Decision 53 currentness, or AK mutation.

The slice is complete only when exact code/schema/tests are independently accepted, synthetic no-network checks pass, and a projection is produced and hash-bound. Decision 105 remains blocked until the separate projection-byte acceptance gate and lifecycle closure. Green tests are evidence, not architecture, cross-owner consumption, or production acceptance.
