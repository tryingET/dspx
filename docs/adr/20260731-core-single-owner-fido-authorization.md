---
summary: "Accept explicit concentrated single-owner Core authorization with immutable selector lineage, FIDO UP+UV, coherent staged evidence, and durable nonce consumption."
read_when:
  - "Implementing or reviewing the accepted DSPx Core single-owner FIDO authorization architecture."
  - "Checking what Decision 96 accepted versus what remains separately gated."
status: accepted
---

# ADR — Core single-owner FIDO authorization

## Status and lineage

Accepted by AK Decision 96 after the controlling final review:

- RFC: `docs/rfc/RFC-DSPX-CORE-20260731-single-owner-fido-authorization.md`
- Problem brief: `docs/project/2026-08-01-problem-core-single-owner-fido-authorization.md`
- Legal review closure: `docs/project/2026-08-01-followup-review-final-core-single-owner-fido-authorization.md` (`ready_for_adr`)
- Immutable decision evidence:
  `dspx-core-owner-policy-selector-v1:git:2839e8fcae8191667db5e2dae953af4f8dc4d27a:governance/release-signing/release-owner-policy-selector-v002.json:b733a20ad8c1bce866f35931dcc3a1ab960e5f0f:260e9e3a95bf2366cbb86bd28541d9fc4405b1d7ed775466aa6c5990fa109dba`

## Context

DSPx has one real owner. The historical 2-of-3 policy correctly remains disabled because aliases cannot create independent judgment. Evidence signing and custody are live, but exact-wheel release authority remains separate from evidence authenticity and package publication.

Two review revisions hardened the proposal before acceptance. The first required explicit SSHSIG security-key flags, immutable owner-policy lineage, durable nonce consumption, and an independently deriving consumer. The second required one coherent staged input generation and ledger path/database identity continuity. Commit `2839e8fc` closed those blockers and the final review reported no remaining blocker/high finding in the authorization-false foundation.

## Decision

Adopt an explicit concentrated single-owner model binding `tryingET` / GitHub user ID `260287438` to a dedicated FIDO2 OpenSSH ED25519-SK public key.

The authorization conjunction requires:

- live AK-selected immutable trust- and owner-policy selectors with anti-rollback checkpoints;
- an exact canonical payload SSHSIG under namespace `dspx-core-release-authorization-v1`;
- normal OpenSSH cryptographic verification plus strict signed user-presence and user-verification flag enforcement;
- a maximum 15-minute lifetime and durable single-use nonce tombstone;
- current trust policy, owner policy, denylist, evidence authenticity, clean source, and paired custody before and after reservation;
- one-read staging of every bounded artifact and detached owner signature into a validated owner-only per-run generation used by all downstream parsers, verifiers, authentication, and hashes;
- a FULL-durability SQLite ledger bound to one retained verified connection and exact database/parent identities, with in-transaction schema validation;
- a non-publishing consumer with no registry credential.

Technical controls are conjunctions, not additional principals. The exact-wheel authorization boundary does not grant package publication or sdist authority.

## Consequences and accepted residuals

The model is honest and operational for a solo project, but owner compromise can authorize a release after later activation. PIN/touch does not prove payload inspection, host integrity, device model/non-exportability, GitHub identity, or independent judgment. Recovery credentials remain the same principal.

External policy, revocation, and custody reads cannot be transactionally locked with the local nonce database. The consumer reduces this risk with repeated currentness checks and emits no authoritative result before durable receipt commit, but a narrow documented post-snapshot race remains.

The future true-result linearization point is the durable exact authorization-receipt commit. Any future authority-true implementation must preserve that point and re-enter governance review if it materially changes these boundaries.

## Acceptance boundary and next gates

This ADR records the architecture; it does not activate it.

- `governance/release-signing/release-owner-policy-v002.json` remains immutable and disabled.
- The current shadow consumer remains `release_authority=false`.
- `package_publication=false` and `sdist_supported=false` remain mandatory.
- No fresh owner signature, GitHub mutation, enabled successor policy, or authority-true dogfood is authorized by this ADR.
- Post-ADR implementation and validation/rollout/rollback artifacts remain separate AK lifecycle gates.
- A later owner-authorized task may propose a superseding enabled policy generation and a fresh visible PIN/biometric non-publishing dogfood only after those gates are satisfied.
