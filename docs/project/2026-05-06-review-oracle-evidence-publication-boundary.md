---
summary: "Review memo for the Oracle evidence publication boundary RFC, concluding it is ready for ADR recording with explicit authority, curation, and publication constraints."
read_when:
  - "You are reviewing the Oracle evidence publication boundary RFC or ADR."
  - "You need the review closure rationale for AK decision #30."
  - "You are deciding whether shared Oracle publication implementation may proceed beyond RFC draft."
---

# Review memo — Oracle evidence publication boundary RFC

- Date: 2026-05-06
- Decision: `#30 Adopt Oracle evidence publication boundary`
- Reviewed artifact: `docs/rfc/RFC-DSPX-ORACLE-20260506-evidence-publication-boundary.md`
- Review outcome: `ready_for_adr`
- Legal next move: record an ADR accepting the publication boundary; implementation remains a separate scoped follow-up.

## Review summary

The RFC is ready for ADR recording. It resolves the confusion introduced by two true but different implementation facts:

1. `program-loop` creates candidate-local Oracle indexes for safe local interpretation.
2. DS1621 has a dedicated Oracle Postgres/pgvector pilot for shared empirical memory.

The RFC correctly refuses to treat either candidate-local `coordinates.db` files or shared Oracle Postgres as authority. It commits to re-indexing curated canonical artifacts into shared Oracle, not migrating local cache files wholesale.

## Key tensions reviewed

### Authority database versus empirical memory

The RFC preserves the central boundary: `society.v2.db` / AK owns canonical task, decision, evidence-binding, transition, and activation truth. Oracle Postgres owns shared empirical coordinate memory. Oracle may carry opaque authority refs and hashes, but those are references only.

This is the right split. It prevents a shared vector/search backend from becoming a second authority database by convenience.

### Local scratch index versus publication source truth

The RFC rejects copying local SQLite `coordinates.db` files into Postgres. That is correct because local indexes are implementation caches derived from artifacts. The publication source of truth should be `oracle_evidence.json`, manifest, receipts, behavior artifacts, and optional review/decision/activation sidecars.

### Winner-only publication versus behavior-space memory

The RFC rejects a winner-only model. That is important because shared Oracle should support learning from failures, rejected candidates, uncertain frontiers, activations, and rollbacks. Winner-only publication would create survivor bias and weaken Oracle's behavioral map.

### Explicit publication versus automatic shared mutation

The RFC keeps `program-loop` local by default and requires visible opt-in for shared publication. This preserves local-first dogfooding and avoids accidental pollution of shared Oracle memory.

### Curation labels and idempotency

The RFC is specific enough for a first implementation direction: publication labels, idempotency keys, redaction status, non-authority flags, and backend health checks are required before shared writes.

## Required ADR constraints

The ADR should preserve these constraints:

- Oracle Postgres is empirical memory, not a second `society.v2.db`.
- Candidate-local `coordinates.db` files are scratch/cache and should not be migrated wholesale.
- Shared publication re-indexes canonical artifacts with hashes/provenance.
- Publication is explicit, idempotent, redaction-aware, and fails closed.
- Publication labels must support useful failures and near-misses, not only winners.
- Shared Oracle records may include AK/governance refs only as opaque references.
- Oracle records/reports cannot approve, promote, deploy, block production, mutate AK, or mutate governance.
- `program-loop` remains local by default; any shared publication convenience path is opt-in.

## Open questions that do not block ADR

1. Whether publication events are separate records or append-only events under one evidence identity.
2. Which publication labels belong in the first implementation slice.
3. Whether all shared publication should require an AK ref or only activation-relevant labels.
4. Whether deterministic redaction checks must precede operator-declared redaction status.
5. Whether the accepted shared coordinate backend ADR should be amended or this boundary should stand as its own ADR.

These do not block ADR because the decision commits the boundary and legal first implementation posture, not the exact schema implementation.

## Review conclusion

Outcome: `ready_for_adr`.

Record an ADR accepting the Oracle evidence publication boundary. Then create scoped follow-up work for Phase 1 publication preflight only. Do not implement shared writes until the preflight packet, labels, idempotency, backend posture checks, redaction posture, and non-authority validation are proven.
