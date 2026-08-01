---
summary: "Propose explicit concentrated single-owner Core authorization using an exact-payload hardware-backed SSH/FIDO signature."
status: accepted-for-implementation
---

# RFC — Single-owner FIDO authorization

## Decision question

How can a solo DSPx owner authorize one exact Core wheel without pretending that multiple accounts, roles, or factors are independent principals?

## Proposed model

Use one human principal, `tryingET` (GitHub numeric ID `260287438`). Accept concentration risk explicitly. Authenticate an exact, short-lived, single-use approval payload with a dedicated OpenSSH SSHSIG namespace and a pinned FIDO2 `sk-ssh-ed25519` public key requiring user presence and verification.

Technical controls remain a conjunction: current accepted trust policy, exact workload signature, denylist clearance, current paired evidence/receipt custody, clean source identity, and current owner policy. They are not votes or principals.

The authorization consumer may establish release authority for the exact wheel only. It cannot publish a package, authorize an sdist, or mutate a registry.

## Payload

The canonical payload binds repository name/numeric ID, trust-policy version and immutable selector ref, owner-policy generation and key fingerprint, wheel/manifest/statement digests, source commit, package version, workflow run/attempt, exact purpose, 256-bit nonce, issue/expiry timestamps, and authority ref. Maximum lifetime is 15 minutes.

## Revocation and replay

The current owner policy has an authorization kill switch and revoked-fingerprint list. A consuming runtime must atomically record each nonce before reporting authority and must re-resolve current policy, denylist, owner policy, and custody immediately before consumption. A signature verifier alone is insufficient.

## Security boundary

Three credentials controlled by one operator are not a quorum. GitHub environment review by the same user is deliberate-action friction, not independent approval. Recovery keys are alternate credentials for the same principal. Compromise of the single owner or authenticator remains concentrated risk.

## Rollout

1. Register a dedicated FIDO SSH public key; never commit private key handles.
2. Land immutable owner policy v2 and an accepted Git-bound selector.
3. Land and adversarially test exact SSHSIG authentication.
4. Integrate the adapter with in-process evidence/current-policy/current-custody verification and a durable nonce ledger.
5. Dogfood a non-publishing exact-wheel authorization.

Until steps 4 and 5 pass, the shipped CLI must not grant release authority merely from caller-supplied booleans or JSON receipts.
