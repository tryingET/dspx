---
summary: "Review memo for the shared Oracle coordinate backend RFC, concluding it is ready for ADR recording with explicit authority and infrastructure boundaries."
read_when:
  - "You are reviewing the shared Oracle coordinate backend RFC or ADR."
  - "You need the review closure rationale for AK decision #29."
  - "You are deciding whether shared Oracle backend implementation may proceed beyond RFC draft."
---

# Review memo — Shared Oracle coordinate backend RFC

- Date: 2026-05-05
- Decision: `#29 Adopt shared Oracle coordinate backend target architecture`
- Reviewed artifact: `docs/rfc/RFC-DSPX-ORACLE-20260505-shared-coordinate-backend.md`
- Review outcome: `ready_for_adr`
- Legal next move: record an ADR accepting the target architecture; implementation remains a separate scoped follow-up.

## Review summary

The RFC is ready for ADR recording as an accepted target architecture. It resolves the session-confusion that mixed three different things:

1. DS1621 MLflow Postgres + MinIO exists for MLflow tracking/artifacts.
2. DSPx Oracle currently uses local SQLite `CoordinateIndex` for explicit local indexing/reporting.
3. The production Oracle target discussed in session is a separate shared, governed behavioral coordinate backend.

The RFC makes the third item explicit without pretending it is already implemented.

## Key tensions reviewed

### Local replayability versus shared production usefulness

The RFC preserves local SQLite and explicit ingestion while naming the production gap. This is the right split: `program-gen` and local replay must not depend on a shared Oracle service, but production workflows need durable behavior memory, team inspection, and cross-program semantic retrieval.

### MLflow backend versus Oracle backend

The RFC rejects reusing MLflow Postgres as Oracle storage. That is the important architectural boundary. MLflow remains run/metric/artifact observability; Oracle is behavioral coordinate/evidence analysis. Sharing the same database/schema would blur ownership, retention, rollback, and authority semantics.

### Empirical interpretation versus promotion authority

The RFC keeps Oracle empirical. It can emit neighborhoods, reports, drift/territory/frontier views, and evidence references. It cannot promote, select winners, block production, mutate AK, mutate governance, or mark activation packets approved. This matches the governance-kernel production-activation boundary.

### DS1621 pilot pressure versus infra ownership

The RFC treats DS1621 as an optional pilot host and assigns DS1621 service deployment/runbook/backup ownership to `softwareco/infra/ds1621-admin`. DSPx owns schemas, CLI/client behavior, and local defaults; infra owns runtime service operations. That split is necessary before implementation.

## Required ADR constraints

The ADR should preserve these constraints:

- Shared Oracle target is a dedicated backend, not the MLflow Postgres database/schema.
- Local SQLite remains the default/offline development store.
- Shared Postgres/pgvector, if implemented, is explicit opt-in and fails closed.
- Oracle ingestion remains explicit; `program-gen` must not auto-index.
- Secret values must not appear in JSON output, logs, docs, or receipts.
- Non-authority flags are validated before shared ingestion.
- Oracle output is evidence/interpretation only; owning domain/governing body decides activation.
- DS1621 runtime deployment, if selected, is an infra-owned follow-up with its own service contract and rollback notes.

## Open questions that do not block ADR

The RFC still leaves valid implementation choices open:

1. DS1621-hosted Postgres + pgvector versus another pilot host.
2. Direct Postgres client from DSPx versus an Oracle HTTP API boundary.
3. Production embedding backend/dimension.
4. Retention policy and quotas.
5. Whether activation packets cite shared Oracle report IDs, local report JSON paths, or both during pilot.

These do not block ADR because the ADR commits only the target boundary and phased path, not the implementation details.

## Review conclusion

Outcome: `ready_for_adr`.

The RFC is specific enough to commit the architecture direction and conservative enough to prevent premature implementation. Record the ADR, then create scoped follow-up work for Phase 1 (`CoordinateStore` abstraction) before any Postgres/pgvector service work.
