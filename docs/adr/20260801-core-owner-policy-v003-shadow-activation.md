---
summary: "Accept immutable enabled owner policy v003 and selector currentness solely for one fresh authority-false FIDO shadow dogfood."
read_when:
  - "Executing or reviewing Decision 99 owner-policy v003 activation."
  - "Checking whether v003 activation grants release or publication authority."
status: accepted
---

# ADR — Core owner-policy v003 shadow activation

## Status and lineage

Accepted by AK Decision 99.

- RFC: `docs/rfc/RFC-DSPX-CORE-20260801-owner-policy-v003-shadow-activation.md`
- Problem: `docs/project/2026-08-01-problem-core-owner-policy-v003-shadow-activation.md`
- Exact-byte review: `docs/project/2026-08-01-review-core-owner-policy-v003-shadow-activation.md` (`ready_for_adr`)
- Policy v003 commit/blob/SHA-256: `71c3b2ed4cf274cc39ec4d48dda9fe25759a4956` / `7a9214a6ed40c806a532e574a93fc064229bbfe5` / `f585d4125911a3f5a039739cb36b33d3318c833b710ae5aeea0bd0f9795b3e2c`
- Selector evidence:
  `dspx-core-owner-policy-selector-v1:git:402328b03f16d4c44ab2548315d4e74225683197:governance/release-signing/release-owner-policy-selector-v003.json:318f86dd5b4f4ce541dd812578ffe4a1e143ed63:d4b169475dae9048cee9aeff047eeb726081b1d44e8c48bd979e8fdaeaf3dc4b`

## Context

Decision 96 accepted and unblocked the single-owner FIDO architecture while keeping v002 disabled. A real expired signature fixture proved only parser and OpenSSH behavior. The full current-policy/evidence/custody/nonce path still needs one fresh biometric shadow dogfood.

Immutable policy lineage requires a new generation rather than editing v002. Because selecting an enabled generation changes future authorization inputs, exact v003 bytes require their own decision and review even while the consumer remains hard-wired false.

## Decision

Accept owner policy v003 and its exact selector as the current enabled owner-policy generation for one authority-false shadow rollout.

V003 changes exactly policy version, effective time, `authorization_enabled=true`, and `disabled_reason=null`. It preserves the same owner, FIDO public key/fingerprint, namespace, UP+UV requirements, 900-second maximum lifetime, single-use nonce, concentration-risk claims, and false package-publication/sdist claims.

Selector v003 binds the exact policy commit/blob/SHA-256 to Decision 99 and supersedes Decision 96 / policy version 2. Live resolution must select a complete v002 -> v003 chain and advance the protected owner checkpoint monotonically.

## Authorized execution boundary

After Decision 99 completes post-ADR tracking and becomes unblocked, task 4420 may:

1. prove v003 currentness and v002 downgrade/fork/gap rejection;
2. derive one fresh payload from current trust/owner/evidence/custody state;
3. display the complete canonical bytes and SHA-256 and require explicit operator confirmation;
4. obtain one fresh YubiKey Bio PIN/biometric/touch SSHSIG over those exact bytes;
5. verify OpenSSH plus strict pinned ED25519-SK UP+UV details;
6. consume once through a new durable owner-only ledger and staged snapshot;
7. record only `shadow_verified_not_authorized` with authority/publication/sdist false;
8. prove replay and required drift/revocation/currentness failures.

## Non-authorizations

This ADR does not authorize:

- any consumer result with `release_authority=true`;
- package publication, registry credentials, or sdist support;
- reuse of the shadow nonce, payload, or signature for a later transition;
- v002/v003 rewrite, checkpoint reset, tombstone deletion, or force-push;
- private FIDO handle, PIN, or biometric capture;
- GitHub mutation beyond read-only observations.

Authority true remains a separate later decision/task, implementation review, rollback pack, and fresh payload/signature ceremony.

## Rollback

Rollback is forward-only. If the v003 rollout fails or key compromise/loss is suspected, stop ceremonies, preserve evidence, and create a higher immutable disabled/revoking generation with a new selector and accepted AK decision. Never edit v003 or reset the owner checkpoint to v002.
