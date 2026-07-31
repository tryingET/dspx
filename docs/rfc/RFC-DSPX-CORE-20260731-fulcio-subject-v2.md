---
summary: "Advance Core trust policy after live Fulcio token-subject schema drift."
read_when:
  - "You are changing Core trust policy after live certificate identity drift."
type: "rfc"
---

# RFC — Core Fulcio Token Subject Policy v2

## Trigger

Evidence-only canary run `30658784801` produced a real keyless signature and Rekor entry but failed exact offline identity verification before artifact upload. The certificate's generic Fulcio extension `1.3.6.1.4.1.57264.1.24` was:

`repo:tryingET@260287438/dspx@1318473695:environment:core-release-evidence`

Policy v1 expected the historical value:

`repo:tryingET/dspx:environment:core-release-evidence`

All other required SAN/OID facts `.1.8` through `.1.23` matched the exact repository, owner, workflow, ref, source/workflow commit, run, event, visibility, environment, and GitHub-hosted runner.

## Decision proposal

Create immutable trust policy v2 with:

- `policy_version: 2`;
- the observed numeric-ID-bound `.1.24` subject;
- unchanged repository, workflow, Sigstore root, wheel-only subject, deny, roster, and non-authority claims;
- a v2 selector superseding policy v1 and Decision 90;
- workflow creation/verification against policy/selector v2.

Preserve policy v1 and selector v1 bytes for historical verification. Do not weaken exact matching, accept both subject forms in one policy, or use a wildcard. Future drift requires another monotonic policy and owner decision.

## Safety

The failed canary uploaded no evidence or receipt artifacts. The enable variable was deleted before this proposal. The Rekor signature is historical evidence only and grants no release authority.

## Validation

- v1 and v2 policies validate only their exact subject forms;
- v2 selector verifies exact policy Git blob and supersedes v1/Decision 90;
- selector-chain tests prove a gapless 1→2 chain;
- workflow uses only v2 after selector acceptance;
- release authority, package publication, and sdist support remain false.
