---
summary: "Independent adversarial review requiring revision of the single-owner FIDO authorization proposal before Decision 96 may advance."
read_when:
  - "Reviewing the original Decision 96 blocker findings and the revision requirements later closed by the accepted design."
type: evidence
---

# Review — Core single-owner FIDO authorization

## Outcome

`revise_rfc`. Decision 96 must remain `review_pending`; no consumer may return `release_authority=true` from the current proposal.

This is not a rejection of explicit concentrated single-owner authority. The direction is honest, and the current implementation fails closed. The proposal is not yet a complete authorization system.

## Blocking findings

1. OpenSSH SSHSIG verification proves a valid namespaced signature but the adapter does not parse and enforce the security-key user-presence and user-verification flags.
2. Owner policy has no accepted immutable Git-bound selector, live AK resolver, anti-rollback checkpoint, or exact selector/hash payload binding.
3. The CLI uses caller time and an in-memory nonce set. Durable crash-safe single-use consumption and an authorization receipt do not exist.
4. No trusted consumer independently derives evidence, policy, denylist, source, run, custody, and authority lineage. Prefix-only selector refs and arbitrary non-empty authority refs are insufficient.
5. Revocation and enabled/disabled-reason invariants are incomplete; current-key revocation must reject through immutable superseding generations.
6. No real PIN/touch signature or integrated non-publishing consumer dogfood exists.

## Required revision

- enforce SSH ED25519-SK UP and UV flags after strict SSHSIG parsing, while retaining `ssh-keygen -Y verify`;
- add immutable owner-policy selector lineage and live anti-rollback resolution;
- derive the exact canonical payload inside a non-publishing shadow consumer from trusted evidence/currentness reads;
- reserve nonces durably before external verification, retain PENDING tombstones on failure/crash, recheck currentness, and durably commit an exact authorization receipt before any future true result;
- preserve `release_authority=false` throughout this repair slice;
- explicitly disclose that PIN/touch does not prove payload inspection, host integrity, device model/non-exportability, GitHub identity, or independent quorum.

## Next legal move

Implement and adversarially test the fail-closed shadow foundation, amend the RFC, then obtain a fresh independent review. Only a later accepted ADR and real interactive signature ceremony may authorize a true-result dogfood.
