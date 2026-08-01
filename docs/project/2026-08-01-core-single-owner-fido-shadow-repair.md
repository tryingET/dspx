---
summary: "Evidence for repairing Decision 96 into a fail-closed single-owner FIDO shadow authorization foundation."
type: evidence
---

# Core single-owner FIDO shadow repair

## Scope

This slice repairs the rejected Decision 96 proposal without advancing the decision or granting release authority. The owner policy remains disabled. Package publication and sdist support remain false.

## Implemented

- strict OpenSSH SSHSIG envelope and ED25519-SK detail parsing with signed UP and UV flags required;
- normal `ssh-keygen -Y verify` retained as the cryptographic verifier;
- exact public-key fingerprint parsing and immutable revocation/disable invariants;
- full trust-selector, owner-selector, and AK decision authority references in the duplicate-key-free canonical payload;
- proposed Git-bound owner-policy selector plus live AK accepted/unblocked resolver and monotonic checkpoint;
- non-publishing shadow consumer that independently resolves trust/owner policy, verifies statement/Sigstore/denylist/source/receipt/current paired custody, derives payload fields, and repeats currentness checks;
- FULL-durability SQLite nonce ledger with exact schema/application version, no unexpected tables/indexes/views/triggers, unique nonce key, PENDING tombstones retained on failure, and durable exact shadow-receipt commit;
- trusted process clock and immediate pre-commit payload and evidence/receipt expiry checks;
- adversarial concurrent, crash/PENDING, schema-trigger, replay, selector, revocation, duplicate-JSON, UP/UV, namespace, key, payload, TOCTOU, and expiry tests.

Every result remains `release_authority=false` and `package_publication=false`.

## Real authentication-path proof

A previously generated, now-expired canonical payload and YubiKey Bio detached SSHSIG were inspected only as non-authoritative parser/cryptographic fixtures. The strict parser observed:

```json
{"counter": 5, "flags": 5, "user_presence": true, "user_verification": true}
```

The same detached signature passed `ssh-keygen -Y verify` under namespace `dspx-core-release-authorization-v1`. Because the payload is expired and predates the exact owner-selector binding, it proves only the authentication/parser path. It grants no authority and consumed no production nonce.

## Independent code re-review

A focused independent reviewer initially rejected the repair because the ledger accepted unexpected SQLite objects and the shadow consumer exposed a caller clock. The slice then:

- required the entire `sqlite_master` object set and canonical schema to match, including rejection of a replay-enabling trigger;
- moved current time into the trusted consumer and added immediate final custody-expiry validation.

The reviewer then accepted the commit for the authority-false shadow foundation only, with no blocker/high findings in those areas.

## Remaining gates

1. Fresh independent review of the amended RFC/complete repair and legal closure for Decision 96.
2. Record an accepted ADR and immutable selector reference only after legal readiness.
3. Create a superseding enabled owner-policy generation; do not rewrite v002.
4. Prepare a fresh exact payload, visibly display its canonical bytes and SHA-256, then use YubiKey PIN/biometric touch to sign it.
5. Run one non-publishing shadow dogfood first. A separate authorized transition is required before any consumer may return true.
