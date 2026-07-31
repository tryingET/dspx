---
summary: "First governed many-of-the-greats review of the Core signing and CI custody RFC; outcome revise_rfc."
read_when:
  - "You are tracing review lineage for the Core signing/custody decision."
type: "reference"
---

# Core Signing and CI Custody Review — Attempt 1

## Review identity

- reviewed artifact: `docs/rfc/RFC-DSPX-CORE-20260731-signing-custody.md`, initial revision
- procedure: Prompt Vault `many-of-the-greats` (`text_ok`)
- dispatch: `dispatch-1785509997686`
- reviewer posture: independent, read-only
- outcome: `revise_rfc`
- legal next move: revise the RFC and run a new immutable review attempt

## Adjudication

The keyless-workload school dominated durable-key custody for build-evidence authenticity, while threshold owner governance dominated workload identity for release authorization. Wheel-only subject minimalism dominated atomic wheel+sdist treatment because exact-sdist installation remained unproved. Bounded CI-native custody dominated permanent external custody for the current pre-package-publication posture.

The direction was strong but not decision-complete.

## Blocking findings

1. The signer identity named categories rather than exact OIDC claims and immutable repository/workflow identity.
2. The 2-of-3 threshold lacked roster/version, distinct-principal, payload-binding, expiry, withdrawal, and authority-record semantics.
3. The sdist's non-subject role remained ambiguous.
4. Revocation lacked an authoritative versioned denylist and historical/current verification behavior.
5. The proposed GitHub artifact ACL claimed restrictions the provider could not enforce.
6. No authenticated post-upload receipt bound provider artifact identity back to the signed evidence.
7. The lifecycle did not explicitly require owner acceptance and AK deferral resolution before implementation.

## Result

`revise_rfc`

No ADR or implementation was legal from this attempt.
