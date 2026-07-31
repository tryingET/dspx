---
summary: "Adversarial review of exact Fulcio numeric token-subject policy v2."
read_when:
  - "You are reviewing Core trust policy v2 or the failed live identity canary."
type: "review"
---

# Review — Core Fulcio Token Subject Policy v2

## Evidence

Live run `30658784801` reached Sigstore, created a transparency-log entry, and failed before upload because exact extension `.1.24` drifted. Public Rekor certificate inspection showed the numeric-ID-bound subject while `.1.8`–`.1.23` matched.

## Adversarial alternatives

1. **Accept both forms in v1:** rejected; it mutates immutable policy semantics and broadens identity.
2. **Wildcard the subject:** rejected; it discards exact owner/repository identity.
3. **Ignore `.1.24`:** rejected; policy intentionally requires complete generic-extension coverage.
4. **Advance exact policy v2:** accepted; it preserves history and binds stronger numeric identities.

## Findings

- The provider drift is observed machine evidence, not speculation.
- The new subject is narrower because it includes owner and repository numeric IDs already matched independently by `.1.15` and `.1.17`.
- V2 must preserve every non-authority and wheel-only invariant.
- The failed signature remains non-authoritative historical evidence and must not be retried under v1.

## Outcome

`ready_for_adr`
