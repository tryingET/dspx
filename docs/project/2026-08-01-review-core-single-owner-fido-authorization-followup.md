---
summary: "Fresh follow-up review rejecting mutable artifact snapshots and replaceable nonce-ledger path identity at commit 5f03e1b4."
read_when:
  - "Reviewing the post-5f03e1b4 snapshot and nonce-ledger rejection or its required repair."
type: evidence
---

# Follow-up review — Core single-owner FIDO authorization

## Reviewed baseline

Commit `5f03e1b4c3191930762d9851f4fd9d48bbbcdc44`.

## Outcome

`revise_rfc`. Decision 96 remains `review_pending`; this review does not accept the proposed ADR or authorize an enabled owner policy, a live signature ceremony, a true-result consumer, or package publication.

## Blocking findings

1. `_derive_snapshot` reopened mutable caller-owned artifact paths across parsing, bundle validation, Sigstore/cosign, receipt verification, and hashing. A replacement could make one authorization attempt observe bytes from different generations.
2. `NonceLedger` validated its pathname once, then opened that replaceable pathname separately for reserve, finalize, and status. It did not validate parent ownership/mode or preserve the identity of the database selected at construction, so entry, parent, or symlink replacement could redirect a later operation.

## Required repair

- Copy each bounded artifact and detached owner signature exactly once into a newly created owner-only per-run directory; pass only those staged paths to parsers, bundle validators, cryptographic verifiers, receipt validation, and hashes for the entire attempt.
- Keep live AK/GitHub currentness reads and monotonic checkpoint state distinct from immutable staged artifact bytes.
- Require a non-symlink, owner-only immediate ledger parent with safe non-symlink ancestors, retain one verified SQLite connection/database identity for the ledger lifecycle, and fail closed if the database entry or any parent identity changes.
- Add deterministic tests that replace every artifact original after staging, replace the signature original before authentication, and replace the ledger entry/parent with regular files or symlinks before reserve/finalize.

## Authority boundary

The repair may only strengthen the non-publishing shadow foundation. It must retain:

```json
{
  "release_authority": false,
  "package_publication": false,
  "sdist_supported": false
}
```

A fresh post-repair review is still required before Decision 96 may advance.
