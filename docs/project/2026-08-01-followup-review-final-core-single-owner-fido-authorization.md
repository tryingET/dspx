---
summary: "Final structured re-review accepting the revised single-owner FIDO authorization RFC for ADR recording after snapshot and ledger identity repair."
read_when:
  - "Checking the controlling legal review closure for Decision 96."
  - "Confirming whether the revised Core single-owner FIDO authorization RFC is ready for ADR."
type: "review_memo"
---

# FOLLOWUP_REVIEW_FINAL — Core single-owner FIDO authorization

## Reviewed artifact and baseline

- RFC: `docs/rfc/RFC-DSPX-CORE-20260731-single-owner-fido-authorization.md`
- Reviewed Git baseline: `2839e8fcae8191667db5e2dae953af4f8dc4d27a`
- Repair evidence: `docs/project/2026-08-01-core-single-owner-fido-shadow-repair.md`
- Rejection being closed: `docs/project/2026-08-01-review-core-single-owner-fido-authorization-followup.md`

This is a new immutable review attempt. It does not overwrite the two historical `revise_rfc` attempts.

## Review conclusion

The revised RFC and commit `2839e8fc` close the two remaining blocking findings from the post-`5f03e1b4` review:

1. **Artifact-generation coherence — closed.** Every bounded release artifact and the detached owner signature is read once from its caller-owned original and copied into a validated current-owner `0700` per-run directory. Downstream JSON parsing, bundle validation, Sigstore/cosign and receipt verification, owner authentication, and hashes use only `0600` staged files. Both currentness derivations reuse the same staged generation.
2. **Nonce-ledger path/identity continuity — closed.** The ledger requires a current-owner-only immediate parent and safe non-symlink ancestors, retains one verified SQLite connection, binds database and parent device/inode/owner/mode identities, validates exact schema inside reserve/finalize transactions, and fails closed on entry, parent, mode, or symlink replacement.

Deterministic tests exercise swaps of all eight bounded artifact roles after staging, detached-signature replacement before authentication, database-entry replacement before reserve and finalize, parent replacement, unsafe parent mode, and symlink replacement. The focused consumer suite passed 26 tests; the broader release authorization/signing/custody/workflow set passed 94 tests. Ruff, workflow-contract, commit-hook, pre-push, and push validation passed.

No blocker or high-severity finding remains in the reviewed authorization-false foundation.

## Residual risks accepted for ADR

The RFC explicitly preserves the material residuals:

- one human principal remains a concentration risk;
- PIN/touch does not prove payload inspection, host integrity, device model/non-exportability, GitHub identity, or independent judgment;
- external policy/revocation/custody state cannot be transactionally locked with the local ledger, leaving a narrow documented post-snapshot race;
- future activation still requires post-ADR planning, a superseding enabled policy generation, and a fresh visible signing/dogfood ceremony.

These are disclosed tradeoffs and follow-through obligations, not hidden claims of independent quorum or publication authority.

## Authority boundary

This review accepts the architecture for ADR recording only. It does not:

- enable `governance/release-signing/release-owner-policy-v002.json`;
- authorize an enabled successor generation;
- perform or authorize a fresh signature;
- authorize GitHub mutation;
- make the current shadow consumer return `release_authority=true`;
- authorize package publication or sdist support;
- unblock post-ADR execution without its separate AK lifecycle gates.

## Outcome

**`ready_for_adr`**

## Legal next move

1. Attach this memo as the latest `current_track` review attempt with `review_outcome=ready_for_adr`.
2. Attach the dedicated problem brief.
3. Require `ak decision passport 96 -F json` to report `ready_for_adr_required.ready=true`.
4. Only then move Decision 96 through `decision_pending -> adr_required` with outcome `accepted`, record the ADR, and bind decision evidence to the exact immutable owner-policy selector reference.

No authority-true or publication transition is part of that move.
