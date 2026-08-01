---
summary: "Decision 99 execution plan for v003 currentness, one confirmed biometric signature, and authority-false shadow consumption."
read_when:
  - "Executing task 4420 after Decision 99 ADR recording."
  - "Checking the exact stop points before payload signing or shadow consumption."
type: "implementation_plan"
---

# Implementation Plan — Owner-policy v003 shadow activation

## Fixed inputs

- Task: AK-4420
- Decision: AK Decision 99
- ADR: `docs/adr/20260801-core-owner-policy-v003-shadow-activation.md`
- Policy v003: commit `71c3b2ed4cf274cc39ec4d48dda9fe25759a4956`, blob `7a9214a6ed40c806a532e574a93fc064229bbfe5`, SHA-256 `f585d4125911a3f5a039739cb36b33d3318c833b710ae5aeea0bd0f9795b3e2c`
- Selector v003: `dspx-core-owner-policy-selector-v1:git:402328b03f16d4c44ab2548315d4e74225683197:governance/release-signing/release-owner-policy-selector-v003.json:318f86dd5b4f4ce541dd812578ffe4a1e143ed63:d4b169475dae9048cee9aeff047eeb726081b1d44e8c48bd979e8fdaeaf3dc4b`
- Owner checkpoint: protected local state, currently v002 before activation
- Trust checkpoint: protected existing local state
- Evidence/custody baseline: fresh read of the accepted 90-day evidence run and paired receipt, subject to current GitHub observation and expiry checks

## Phase sequence

### 0. Preflight

Read back task scope/contracts, Decision 96, Decision 99, policy/selector Git identities, local checkpoint ownership/modes, evidence/custody expiry, current consumer false constants, and clean repository state. Preserve v002/selector bytes exactly.

### 1. Complete Decision 99 currentness gates

Record the ADR plus this plan and the paired validation/rollback artifact. Reevaluate linked task 4420 as still valid for the exact authority-false scope. Require `ready_for_unblocked=true`, then lawfully unblock Decision 99.

Resolve the live owner chain into the protected checkpoint. Require exact v003 selector/policy and checkpoint version 3. Prove v002 downgrade, a synthetic fork, and a synthetic gap fail without changing checkpoint history.

### 2. Materialize fresh trusted inputs

Create a new owner-only run directory under managed disk-backed temporary storage. Use read-only GitHub observations to obtain/confirm current evidence and custody artifacts. Extract the exact signed wheel subject and fetch the pinned trusted root with its configured SHA-256. Verify all bounded inputs before prepare.

### 3. Prepare and display

Run the trusted non-publishing prepare surface once. It derives a fresh 256-bit nonce and at most 10-minute payload from current trust/owner/source/evidence/custody state.

Print the entire canonical JSON file and SHA-256 visibly. Stop. The operator must explicitly confirm those exact bytes before any signing command.

If confirmation is denied, late, ambiguous, or arrives after expiry, do not sign. Preserve the unused payload as non-authoritative evidence and prepare a new payload only under a new explicit operator instruction.

### 4. Biometric signature

After explicit confirmation, invoke `ssh-keygen -Y sign` in a pseudo-terminal against the exact displayed file, dedicated FIDO key, and exact namespace. The operator enters PIN/biometric/touch directly. Do not log secret input.

A command timeout, disconnect, uncertain file creation, or unknown token response is effect-indeterminate: stop and inspect; never retry mechanically or reuse the nonce.

Verify the resulting SSHSIG with OpenSSH and the strict parser. Require the pinned fingerprint, ED25519-SK type, namespace, UP=true, UV=true, and unexpired payload. Record counter only as telemetry.

### 5. Consume exactly once

Create a new owner-only ledger directory/database. Run `consume-shadow` with the same payload/signature and staged trusted inputs. Require a durable receipt with status `shadow_verified_not_authorized` and all authority/publication/sdist flags false.

Stop if output is absent, malformed, ambiguous, or differs in any field. Never rerun the consume command for the same nonce after an indeterminate effect.

### 6. Negative evidence and closure

Immediately rerun the same payload/signature once and require replay rejection. Then run fixture-isolated negative checks for payload drift, expiry, missing UP/UV, disabled/revoked policy, selector downgrade/fork/gap, evidence/custody/currentness drift, staged original replacement, and ledger identity/schema replacement. Do not delete PENDING or committed tombstones.

Record safe telemetry, exact refs/hashes, receipts, ledger identity, negative results, and forward-only rollback procedure in the dogfood evidence artifact. Obtain independent post-run review. Commit/push only safe public docs and evidence.

## Stop boundary

Task 4420 ends at one authority-false shadow receipt and negative proof. It does not implement or authorize authority true. A later transition must use a new payload, nonce, signature, decision, code review, and rollback gate.
