---
summary: "Propose immutable enabled owner policy v003 and exact selector currentness solely for one fresh authority-false YubiKey shadow dogfood."
read_when:
  - "Reviewing the exact activation boundary for owner policy v003."
  - "Preparing policy/selector bytes or the authority-false biometric shadow ceremony."
status: revision-under-review
---

# RFC — Owner-policy v003 authority-false shadow activation

## Decision question

Should DSPx make one immutable enabled owner-policy successor current so the accepted Decision 96 architecture can be dogfooded with a fresh real FIDO signature while the consumer remains incapable of granting release authority?

## Goals

- Preserve v002 and selector v002 byte-for-byte as immutable history.
- Create v003 with the same single owner, FIDO key, UP+UV, namespace, lifetime, nonce, revocation, and concentration-risk invariants.
- Enable the policy while retaining false publication/sdist claims.
- Bind v003 through an exact committed selector, accepted AK activation decision, and monotonic checkpoint.
- Display and confirm one full fresh canonical payload before YubiKey Bio signing.
- Consume exactly once through the staged authority-false consumer and prove replay/drift/revocation/currentness failure.
- Prepare forward-only rollback as a higher disabled/revoking generation.

## Non-goals

- No authority-true code or transition.
- No registry credential, package publication, or sdist.
- No v002/v003 rewrite, checkpoint reset, nonce deletion, or tombstone deletion.
- No reuse of the expired historical signature fixture.
- No private FIDO handle, PIN, or biometric recording.
- No GitHub mutation beyond read-only current artifact observations.

## Proposed immutable v003 policy

The policy is a new `dspx-core-release-owner-policy-v2` document with `owner_policy_version: 3`. Relative to v002, only activation-generation fields change:

- `owner_policy_version` becomes `3`;
- `effective_at` becomes the reviewed v003 activation time;
- `revocation.authorization_enabled` becomes `true`;
- `revocation.disabled_reason` becomes `null`.

All other contract fields remain exact unless exact-byte review rejects the proposal:

- repository `tryingET/dspx`, ID `1318473695`;
- one `github-user` principal `tryingET`, ID `260287438`;
- authority model `explicit_single_owner_concentrated_risk`;
- `sk-ssh-ed25519@openssh.com` public key and fingerprint `SHA256:OYAnSnMFl+jvWmFJ6TFcHdikBdL7N2MG3k+FIlSqVis`;
- SSHSIG namespace `dspx-core-release-authorization-v1`;
- UP and UV required;
- purpose `authorize-dspx-core-wheel-release`;
- maximum age 900 seconds and single-use nonce;
- no revoked fingerprint at activation;
- one human principal, no independent quorum, concentrated risk accepted;
- technical controls are conjunctions, not principals;
- package publication and sdist support false.

## Selector and currentness

Policy bytes are committed first. Only then is selector v003 authored with:

- exact version/path/commit/blob/file-SHA-256 for policy v003;
- this activation decision as `accepting_decision_id`;
- `supersedes_decision_id: 96`;
- `supersedes_owner_policy_version: 2`.

Selector bytes are committed and independently verified before review closure. AK may accept/unblock this activation decision only after the exact selector ref is attached as evidence. The live resolver must observe a complete v002 -> v003 chain, select v003, advance the protected checkpoint from 2 to 3, and reject v002 downgrade, forks, gaps, malformed supersession, and unaccepted/unblocked selectors.

## Ceremony and consume

After currentness, the trusted prepare surface derives one fresh payload from current trust policy, owner policy, denylist, source, signed evidence, GitHub artifact observation, and paired custody.

The full canonical JSON bytes and SHA-256 are displayed. Signing is forbidden until the operator explicitly confirms those exact bytes. The signing command runs in a pseudo-terminal so the operator can provide PIN/biometric/touch directly; no secret input is captured.

OpenSSH verification and strict parser verification must prove the pinned ED25519-SK key, exact namespace, signed UP+UV bits, and unexpired payload. The signature counter is telemetry only.

One new owner-only durable ledger consumes the payload. Success is exactly:

```json
{
  "status": "shadow_verified_not_authorized",
  "release_authority": false,
  "package_publication": false,
  "sdist_supported": false
}
```

Replay must fail. Required negative checks cover payload/selector/key/namespace/evidence/source/run/expiry/custody drift, missing UP/UV, disabled/revoked policy, selector fork/gap/downgrade, staged-original substitution, and ledger identity/schema replacement. Tombstones and history remain intact.

## Rollback

Rollback is a later higher immutable generation, never a rewrite or checkpoint reset. If v003 is current and no newer version exists, a v004 policy/selector decision disables authorization, provides a non-empty reason, revokes the fingerprint when appropriate, preserves publication/sdist false, and advances the checkpoint monotonically.

## Decision and rollout boundary

Acceptance of this RFC permits only v003 currentness, one real authority-false shadow dogfood, and its negative evidence. An authority-true result requires a separate fresh decision, implementation diff, review, payload, nonce, signature, and rollback gate.
