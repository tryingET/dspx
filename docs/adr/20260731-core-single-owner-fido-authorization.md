---
summary: "Proposed explicit concentrated single-owner Core authorization with immutable owner-policy lineage and hardware-backed exact-payload authentication."
status: proposed
---

# Proposed ADR — Core single-owner FIDO authorization

## Context

DSPx has one real owner. The historical 2-of-3 policy correctly remains disabled because aliases cannot create independent judgment. Evidence signing/custody is live, but package release authority remains separate. Independent review required revision before Decision 96 may advance.

## Proposed decision

Adopt a new immutable single-owner policy generation binding `tryingET` / GitHub user ID `260287438` to a dedicated FIDO2 OpenSSH ED25519-SK public key. Require:

- a full Git/AK-bound current owner-policy selector and anti-rollback checkpoint;
- exact canonical payload SSHSIG under namespace `dspx-core-release-authorization-v1`;
- OpenSSH cryptographic verification plus explicit signed UP and UV flag enforcement;
- a 15-minute maximum lifetime and durable single-use nonce tombstone;
- current trust policy, owner policy, denylist, evidence authenticity, clean source, and paired custody before and after nonce reservation;
- a non-publishing consumer with no registry credential.

Technical controls are conjunctions, not additional principals. Package publication and sdist support remain false.

## Consequences

The model is honest and operational for a solo project, but owner compromise can authorize a release. PIN/touch does not prove payload inspection, host integrity, device model/non-exportability, GitHub identity, or independent judgment. Recovery credentials remain the same principal.

A narrow post-snapshot revocation race remains because external currentness reads cannot be transactionally locked with the local nonce database. The future true-result linearization point is the durable exact authorization-receipt commit.

## Current gate

This ADR is not recorded. Decision 96 remains `review_pending` with `review_outcome=revise_rfc`. The owner policy remains disabled. The repair slice may authenticate and durably shadow-consume an approval, but every result remains `release_authority=false` until fresh review, accepted owner-policy lineage, real PIN/touch dogfood, and a separately authorized true-result transition.
