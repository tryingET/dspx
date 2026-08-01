---
summary: "Independent exact-byte review accepting owner policy and selector v003 for one authority-false FIDO shadow dogfood."
read_when:
  - "Checking Decision 99 legal review closure or exact v003 policy/selector identities."
  - "Verifying what v003 activation does and does not authorize."
type: "review_memo"
---

# Review — Core owner-policy v003 shadow activation

## Reviewed baseline

- HEAD: `402328b03f16d4c44ab2548315d4e74225683197`
- RFC: `docs/rfc/RFC-DSPX-CORE-20260801-owner-policy-v003-shadow-activation.md`
- Policy v003 commit: `71c3b2ed4cf274cc39ec4d48dda9fe25759a4956`
- Policy path: `governance/release-signing/release-owner-policy-v003.json`
- Policy blob: `7a9214a6ed40c806a532e574a93fc064229bbfe5`
- Policy SHA-256: `f585d4125911a3f5a039739cb36b33d3318c833b710ae5aeea0bd0f9795b3e2c`
- Selector v003 commit: `402328b03f16d4c44ab2548315d4e74225683197`
- Selector blob: `318f86dd5b4f4ce541dd812578ffe4a1e143ed63`
- Selector SHA-256: `d4b169475dae9048cee9aeff047eeb726081b1d44e8c48bd979e8fdaeaf3dc4b`

Computed selector ref:

`dspx-core-owner-policy-selector-v1:git:402328b03f16d4c44ab2548315d4e74225683197:governance/release-signing/release-owner-policy-selector-v003.json:318f86dd5b4f4ce541dd812578ffe4a1e143ed63:d4b169475dae9048cee9aeff047eeb726081b1d44e8c48bd979e8fdaeaf3dc4b`

The reviewer independently recomputed Git object identities and hashes; all inspected files matched HEAD.

## Exact semantic diff

Policy v002 -> v003 changes exactly four fields:

1. `owner_policy_version`: 2 -> 3
2. `effective_at`: `2026-08-01T05:00:00Z` -> `2026-08-01T07:10:00Z`
3. `revocation.authorization_enabled`: false -> true
4. `revocation.disabled_reason`: prior non-empty reason -> null

Selector v002 -> v003 changes exactly the policy version/path/commit/blob/digest locator, accepting decision 96 -> 99, and supersession from nulls to Decision 96 / owner-policy version 2.

## Invariants verified

Unchanged and exact:

- owner `tryingET`, GitHub ID `260287438`;
- one human principal, no independent quorum, concentrated risk accepted;
- pinned ED25519-SK public key and fingerprint `SHA256:OYAnSnMFl+jvWmFJ6TFcHdikBdL7N2MG3k+FIlSqVis`;
- SSHSIG namespace `dspx-core-release-authorization-v1`;
- UP and UV required and parser-enforced;
- maximum lifetime 900 seconds and single-use nonce;
- no revoked fingerprint;
- enabled policy paired with null disabled reason;
- technical controls remain conjunctions, not principals;
- `package_publication=false` and `sdist_supported=false`;
- consumer output remains hard-wired `release_authority=false`.

The selector correctly identifies Decision 99 and supersedes Decision 96 / policy version 2.

## Findings and boundary

Blocker findings: none.

High findings: none.

The reviewed bytes permit only currentness plus one authority-false shadow dogfood. They do not authorize package publication, sdist, registry credentials, an authority-true result, history/checkpoint reset, nonce reuse, or private-key/PIN capture. Authority true remains a separate later decision with fresh bytes, nonce, signature, and review.

Review coverage was limited to the exact policy/selector/RFC and relevant validator/resolver/consumer files. AK Decision 99 runtime state, live ledger state, imported dependencies, and the ceremony were not reviewed by this exact-byte pass and must satisfy their own gates.

## Outcome

**`ready_for_adr`**

## Legal next move

Attach this memo as Decision 99's controlling current-track review closure. Require `ready_for_adr_required.ready=true`, then accept the exact selector evidence and record an ADR. Only after post-ADR plan/rollback artifacts and linked-task reevaluation may Decision 99 unblock for the authority-false ceremony.
