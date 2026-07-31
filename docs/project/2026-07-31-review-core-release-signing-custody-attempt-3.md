---
summary: "Third governed many-of-the-greats review of Core signing and CI custody revision 3; outcome revise_rfc."
read_when:
  - "You are tracing review lineage for the Core signing/custody decision."
type: "reference"
---

# Core Signing and CI Custody Review — Attempt 3

## Review identity

- reviewed artifact: `docs/rfc/RFC-DSPX-CORE-20260731-signing-custody.md`, revision 3
- procedure: Prompt Vault `many-of-the-greats` (`text_ok`)
- dispatch: `dispatch-1785511142385`
- reviewer posture: independent, read-only
- outcome: `revise_rfc`
- legal next move: revise the RFC and run a new immutable review attempt

## Closed findings

- Public GitHub access and trust-by-signed-receipt were explicit rather than disguised as a private ACL.
- Receipt retention, effect-indeterminate upload handling, and release-task AK attachment were mostly specified.
- The 2-of-3 roster remained fail-closed and AK-4137 remained untriggered.

## Remaining blockers

1. The RFC did not name the exact Fulcio certificate extensions/OIDs that authenticate each security-relevant GitHub claim.
2. A fresh verifier could accept a coherently stale AK policy snapshot because unique-current live resolution was undefined.
3. Confirmed or indeterminate deletion of evidence after receipt creation did not explicitly invalidate current release-use custody.
4. The document revision label did not match the reviewed revision.

## Adjudication

The release-verifier school dominated the historical-evidence-event school: identity, current policy, and current custody must derive unambiguously from authenticated inputs at release-use time.

## Result

`revise_rfc`

No ADR or implementation was legal from this attempt.
