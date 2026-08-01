---
summary: "Revise the explicit concentrated single-owner Core authorization design around immutable policy lineage, UP/UV-enforced FIDO SSHSIG, and durable shadow consumption."
status: revision-under-review
---

# RFC — Single-owner FIDO authorization

## Decision question

How can the solo DSPx owner authorize one exact Core wheel without pretending that multiple accounts, roles, credentials, or technical factors are independent principals?

## Proposed model

Use one human principal, `tryingET` (GitHub numeric ID `260287438`). Accept concentration risk explicitly. Authenticate one exact, short-lived, single-use approval payload with a dedicated OpenSSH SSHSIG namespace and pinned `sk-ssh-ed25519@openssh.com` public key.

The verifier must require both the normal OpenSSH cryptographic verification and strict parsing of the signed security-key detail flags. User presence (UP) and user verification (UV) must both be set. The counter is telemetry, not replay protection.

Technical controls remain a conjunction: live AK-selected immutable trust and owner policies, exact workload signature, current denylist and owner kill switch, current paired evidence/receipt custody, clean source identity, trusted time, and durable nonce consumption. They are not votes or principals.

The later authorization consumer may establish release authority for the exact wheel only. It has no registry/package-write credential and cannot publish a package, authorize an sdist, or mutate a registry.

## Immutable authority lineage

Historical trust and owner policy bytes are never rewritten. An owner-policy selector binds the exact policy Git commit, blob, and SHA-256 to an accepted AK decision. Live resolution requires a complete AK decision list, repo scope, accepted/unblocked state, exact selector reference, and a monotonic local checkpoint. The approval payload binds the full trust-selector and owner-selector references plus `ak-decision:<id>` authority lineage.

The proposed selector names Decision 96 but is not current while Decision 96 remains `review_pending`. Working-tree JSON and a public-key fingerprint are never authority.

## Exact payload

The duplicate-key-free canonical payload binds repository name/numeric ID, trust-policy version and full immutable selector ref, owner-policy generation and full immutable selector ref, key fingerprint, wheel/manifest/statement digests, source commit, package version, workflow run/attempt, exact purpose, 256-bit nonce, issue/expiry timestamps, and exact AK decision authority ref. Maximum lifetime is 15 minutes.

The trusted consumer derives these fields from independently verified artifacts and live owner surfaces. It does not accept caller booleans, digests, currentness JSON, or a caller clock.

## Revocation and replay

Immutable owner-policy generations define an authorization kill switch, disabled-reason invariant, and revoked fingerprints. An enabled generation has `disabled_reason: null`; a disabled generation has a non-empty reason. A policy listing its current key as revoked is invalid. Disablement, revocation, replacement, or recovery uses a superseding immutable generation.

The nonce ledger uses FULL-durability SQLite and a unique `(owner-selector-ref, fingerprint, nonce)` key. Before signature/external verification, the consumer commits a PENDING reservation. Failure or crash leaves that tombstone consumed. After a second currentness read, it transactionally commits the exact shadow authorization receipt. Only a later accepted implementation may emit true after that durable commit.

## Linearization and TOCTOU

The future true-result linearization point is the durable authorization-receipt commit. External policy, revocation, and custody reads cannot be atomically locked with a local database. The consumer therefore resolves and verifies before and after nonce reservation, documents the narrow post-snapshot revocation race, and emits nothing authoritative before commit.

## Security boundary and nonclaims

Three credentials controlled by one operator are not a quorum. GitHub environment review by the same user is deliberate-action friction, not independent approval. Recovery keys are the same principal.

A valid SSHSIG with UP+UV does **not** prove:

- that the human inspected the exact bytes or understood the decision;
- host integrity or absence of payload substitution before signing;
- YubiKey model, genuine hardware, or non-exportability;
- GitHub account/numeric-ID control;
- current policy, denylist, custody, source, or nonce state;
- independent judgment or package-publication authority.

Owner loss, coercion, host compromise, and authenticator compromise remain concentrated risks.

## Revised rollout

1. Register the dedicated FIDO public key; never commit its private handle or PIN.
2. Land the proposed immutable owner policy and selector, while authorization stays disabled and Decision 96 stays under review.
3. Enforce strict SSHSIG ED25519-SK UP+UV detail parsing in addition to OpenSSH verification.
4. Land and adversarially test the owner-policy live resolver, durable nonce ledger, and non-publishing shadow consumer with `release_authority=false` hard-wired.
5. Obtain fresh independent review and only then advance Decision 96/record an ADR.
6. Accept a superseding enabled owner-policy generation after a real terminal ceremony proves the shadow path.
7. Use a fresh nonce and signature for one non-publishing exact-wheel true-result dogfood, then prove replay, expiry, policy, denylist, custody, and revocation drift fail closed.

Until steps 5–7 pass, no shipped surface may return release authority true.
