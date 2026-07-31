---
summary: "Adopt exact numeric-ID-bound Fulcio token subject in immutable Core trust policy v2."
read_when:
  - "You are implementing or verifying Core trust policy v2."
type: "decision"
---

# ADR 20260731 — Core Fulcio Token Subject Policy v2

## Status

- accepted
- date: 2026-07-31
- AK decision: `#92 Accept exact Fulcio numeric token subject policy v2`

## Context

Live canary run `30658784801` observed Fulcio extension `.1.24` as `repo:tryingET@260287438/dspx@1318473695:environment:core-release-evidence`. Exact policy v1 correctly rejected it because v1 records the former subject format.

## Decision

Adopt immutable trust policy v2 with the exact observed numeric-ID-bound subject. Preserve v1 for historical verification. Select v2 through a monotonic selector that supersedes policy v1 and Decision 90. Keep every other workload matcher, root, subject, roster, deny, and non-authority rule unchanged.

## Consequences

- Current GitHub/Fulcio workload identity can verify exactly.
- Numeric owner/repository identity is present in both dedicated OIDs and token subject.
- No wildcard or dual-form acceptance is introduced.
- Evidence signatures, including the failed canary signature, grant no release authority.

## Rollback

Delete the enable variable and accept a higher deny/policy version if new drift or compromise is observed. Never rewrite v1 or v2.
