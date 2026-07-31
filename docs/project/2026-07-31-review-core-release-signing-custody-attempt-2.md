---
summary: "Second governed many-of-the-greats review of Core signing and CI custody revision 2; outcome revise_rfc."
read_when:
  - "You are tracing review lineage for the Core signing/custody decision."
type: "reference"
---

# Core Signing and CI Custody Review — Attempt 2

## Review identity

- reviewed artifact: `docs/rfc/RFC-DSPX-CORE-20260731-signing-custody.md`, revision 2
- procedure: Prompt Vault `many-of-the-greats` (`text_ok`)
- dispatch: `dispatch-1785510774862`
- reviewer posture: independent, read-only
- outcome: `revise_rfc`
- legal next move: revise the RFC and run a new immutable review attempt

## Closed findings

- The role-based 2-of-3 threshold was decision-complete and fail-closed while exact principals remained unbound.
- The wheel was the sole supported subject; the sdist was auxiliary evidence, leaving AK-4137 untriggered.
- ADR/AK acceptance was placed before implementation and deferral resolution.

## Remaining blockers

1. OIDC fields were still aliases rather than an exact certificate-authenticated verifier contract.
2. The current revocation policy could be selected from more than one owner surface and lacked rollback-safe currentness.
3. Public-repository Actions artifact access/deletion and trusted-evidence recognition were not described in actual provider terms.
4. The post-upload receipt lacked its own retention/effect contract and required authority attachment.

## Adjudication

Keyless exact-workload signing, wheel-only subject scope, separate owner authorization, and bounded CI custody remained contextually dominant, but the verification boundary was under-specified.

## Result

`revise_rfc`

No ADR or implementation was legal from this attempt.
