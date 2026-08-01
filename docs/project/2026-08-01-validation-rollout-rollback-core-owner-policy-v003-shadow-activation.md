---
summary: "Decision 99 validation, one-shot shadow rollout, abort, and forward-only rollback contract for owner policy v003."
read_when:
  - "Validating v003 currentness, the real biometric shadow receipt, or negative-path evidence."
  - "Responding to any indeterminate v003 ceremony or consume result."
type: "validation_rollout_rollback"
---

# Validation, rollout, and rollback — Owner-policy v003 shadow activation

## Invariant

All successful and failed paths in this rollout preserve:

```json
{
  "release_authority": false,
  "package_publication": false,
  "sdist_supported": false
}
```

## Pre-sign gates

- Exact policy/selector commits, blobs, and SHA-256 values recompute.
- Semantic v002 -> v003 diff contains exactly the four reviewed policy changes.
- Independent exact-byte review outcome is `ready_for_adr` with no blocker/high finding.
- Decision 99 is accepted, ADR-recorded, post-ADR tracked, and unblocked.
- Live resolver selects exact v003 and protected checkpoint reports version 3.
- Downgrade/fork/gap tests fail without checkpoint rollback.
- Current trust/evidence/source/custody/GitHub observations all verify and remain unexpired.
- Consumer source still hard-wires authority/publication/sdist false.
- Payload output does not exist before prepare; ledger path does not exist before consume.
- Full canonical payload bytes and SHA-256 have explicit operator confirmation.

## Signing gates

- Signing input inode/bytes/hash equal the confirmed payload.
- Dedicated FIDO public identity and exact namespace are used.
- Pseudo-terminal gives PIN/biometric/touch interaction directly to the operator.
- Detached signature output is newly created.
- OpenSSH verification succeeds.
- Strict parser proves pinned ED25519-SK, UP, UV, exact fingerprint, and valid structure.
- Payload remains inside its policy window.

Any indeterminate signing effect is an immediate stop. Inspect existing files and token response; do not rerun automatically and do not reuse the nonce.

## Consume gates

- New ledger parent is current-owner-only and non-symlink.
- Ledger DB identity/schema/durability validate.
- Consumer reserves before external verification and retains tombstone on failure.
- All artifacts/signature are staged once and originals are never reopened downstream.
- First and second currentness snapshots match.
- Final payload/custody expiry checks pass.
- Durable receipt commit precedes return.
- Result status is exactly `shadow_verified_not_authorized` with all false flags.

An indeterminate consume effect is an immediate stop. Inspect ledger status and receipts; do not run the same nonce again except the single intentional replay proof after a definitely successful committed receipt.

## Required negative results

| Test | Required failure |
|---|---|
| same payload/signature after committed shadow receipt | nonce already reserved/consumed |
| one-byte payload or bound-field drift | canonical payload/signature mismatch |
| expired payload or custody | time/currentness rejection |
| UP or UV absent fixture | strict authentication rejection |
| disabled or revoked synthetic policy | policy validation/authentication rejection |
| v002 after checkpoint v3 | anti-rollback rejection |
| synthetic v003 fork | selector fork rejection |
| synthetic version gap | selector chain gap rejection |
| statement/wheel/manifest/source/run drift | evidence binding rejection |
| GitHub artifact missing/duplicate/expired/digest drift | paired custody rejection |
| original artifact/signature swapped after staging | coherent staged generation or rejection |
| ledger entry/parent/symlink/schema replacement | reserve/finalize rejection |

Synthetic tests use isolated temporary checkpoints/ledgers and generated fixtures. They never mutate the protected live checkpoint, production tombstone, historical Git bytes, or hardware secrets.

## Evidence required

- Decision/task/passport and governance receipt IDs;
- exact policy and selector refs/hashes;
- protected checkpoint before/after version and selector ref;
- displayed canonical bytes and SHA-256 confirmation receipt;
- public signature fingerprint, namespace, UP, UV, flags, counter telemetry, and OpenSSH result;
- payload issue/expiry, consume time, ledger path identity/mode/device/inode, and receipt JSON;
- replay and negative test commands/results;
- current GitHub/custody artifact IDs/digests/expiry;
- explicit no-publication/no-authority statement;
- independent post-run review.

Never record PIN, biometric data, private key handle, registry secrets, or askpass input.

## Rollout

One prepare -> one explicit confirmation -> one signature -> one successful shadow consume -> one replay rejection -> isolated negative matrix -> freeze. There is no authority-true graduation in this rollout.

## Abort and forward-only rollback

Abort on policy/selector mismatch, AK currentness ambiguity, payload confirmation failure, signature uncertainty, currentness/expiry drift, ledger uncertainty, or any true/publication-capable output.

Preserve all evidence and tombstones. Do not edit v003, selector v003, checkpoint, ledger, payload, or signature to make a failure pass.

If v003 must be disabled, create a new scoped rollback task and decision for the next live generation (expected v004 only after checking no newer version). The new immutable policy sets authorization false, supplies a reason, revokes the fingerprint when warranted, preserves publication/sdist false, and advances the checkpoint through a new exact selector. Confirm the live resolver rejects v003 and v002 downgrade after forward rollback.

## Separate authority-true transition

A later authority-true proposal requires a new decision/task, exact code diff, independent review, validation/rollback artifacts, and a fresh payload/nonce/expiry/signature. Neither the v003 policy, its signature, nor its shadow receipt may be reused as release authority.
