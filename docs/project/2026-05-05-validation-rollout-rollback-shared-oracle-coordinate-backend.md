---
summary: "Validation, rollout, and rollback notes for ADR 20260505 shared Oracle coordinate backend."
read_when:
  - "You are validating, rolling out, or rolling back shared Oracle backend work."
  - "You need the safety gates for CoordinateStore, Postgres/pgvector, or DS1621 Oracle pilot slices."
---

# Validation / rollout / rollback — Shared Oracle coordinate backend

- Date: 2026-05-05
- Decision: `#29 Adopt shared Oracle coordinate backend target architecture`
- ADR: `docs/adr/20260505-shared-oracle-coordinate-backend.md`
- Implementation plan: `docs/project/2026-05-05-plan-shared-oracle-coordinate-backend.md`

## Global validation invariants

Every implementation slice must preserve:

- local SQLite default behavior;
- no implicit Postgres/shared-service connection;
- explicit Oracle ingestion only;
- `program-gen` does not auto-index;
- no secret values in JSON/logs/docs/receipts;
- non-authority flags validated before shared ingestion;
- Oracle does not promote, select winners, deploy, block production, mutate AK, or mutate governance.

## Phase 1 validation — CoordinateStore abstraction

Minimum checks:

```bash
uv run pytest tests/test_coordinates.py tests/test_program_oracle_index.py tests/test_program_oracle_report.py -q
uv run pytest tests/test_oracle_backend_status.py -q
uv run ruff check packages/dspx-core/src/dspx/coordinates packages/dspx-core/src/dspx/services packages/dspx-core/src/dspx/cli/commands/oracle.py tests/test_coordinates.py tests/test_program_oracle_index.py tests/test_program_oracle_report.py tests/test_oracle_backend_status.py
node ~/ai-society/core/agent-scripts/scripts/docs-list.mjs --docs . --strict
just task-scope-check
just verify-fast
```

Escalate to `just verify-full` if the slice changes embedding semantics, generated-program evidence contracts, CLI dispatch structure broadly, or shared runtime behavior.

Rollout:

- land behind no behavior change;
- keep existing CLI examples valid;
- update docs only if public command output changes.

Rollback:

- revert abstraction layer to direct `CoordinateIndex` calls;
- keep local SQLite index files untouched;
- do not attempt data migration.

## Phase 2 validation — Postgres + pgvector adapter

Minimum checks:

- all Phase 1 checks;
- store contract tests for both SQLite and Postgres adapter code paths;
- config redaction tests proving database URLs/passwords never appear in JSON/logs;
- fail-closed tests for missing config, unreachable backend, missing pgvector extension, migration mismatch, and authority-claiming evidence;
- optional live integration smoke only when explicit service env vars are present.

Live-gated smoke command shape:

```bash
DSPX_ORACLE_LIVE_POSTGRES=1 \
DSPX_ORACLE_STORE=postgres_pgvector \
DSPX_ORACLE_DATABASE_URL='<operator-injected secret URL>' \
uv run --extra oracle-postgres pytest tests/test_postgres_store_live.py -q
```

This test must skip by default in local/CI service-free runs.

Rollout:

- keep `sqlite` as default;
- require explicit `DSPX_ORACLE_STORE=postgres_pgvector` or equivalent;
- require explicit operator-provided database URL/secret ref;
- ship `backend-status` updates before recommending the shared backend.

Rollback:

- unset shared-store config;
- return to SQLite `CoordinateIndex`;
- leave shared DB records intact unless an infra-owned cleanup/runbook says otherwise;
- document any failed migration or partial ingest receipt.

## Phase 3 validation — DS1621 pilot service

Current status: DS1621 live pilot deployed, pgvector health passed, DSPx live-gated smoke passed, first disposable restore proof passed, 14-day retention/quota helpers exist, and latest dump is exported to the operator-confirmed `DspxOracleBackups` Hyper Backup share; production-readiness gates remain open.

Minimum checks:

- infra repo docs strict for the DS1621 service contract/runbook;
- DSPx `backend-status --json` links the infra contract and reports the live pilot while preserving local SQLite default truth;
- DS1621 health check from workstation;
- non-secret generated-program ingest/report smoke;
- backup/restore posture documented;
- off-NAS backup boundary documented and latest dump exported to a Hyper Backup selected share;
- rollback to local SQLite demonstrated or documented.

Rollout:

- infra owner lands service contract in `softwareco/infra/ds1621-admin`;
- DSPx status/docs link the contract as contract-only until live deployment evidence exists;
- deploy separate Oracle backend, not MLflow database/schema;
- publish non-secret connection/health contract;
- keep secrets in 1Password/env injection, never repo docs.

Rollback:

- stop Oracle pilot service without stopping MLflow;
- unset DSPx shared Oracle config;
- verify `just dspx oracle backend-status --json` reports local SQLite or shared-unavailable truth;
- retain service data until infra owner approves cleanup.

## Phase 4 validation — Reports/API/UI and activation evidence

Minimum checks:

- report/search API contract tests;
- activation packet evidence-reference tests;
- UI/API label checks for non-authority wording;
- negative tests proving Oracle report outcomes cannot approve activation.

Rollout:

- expose shared Oracle reports as evidence references only;
- activation packet status remains blocked unless owning-domain/governing-body decision, canonical binding, rollout owner, and rollback plan are present;
- update README/backend-status only after implementation truth changes.

Rollback:

- remove shared Oracle report refs from activation packets;
- keep local report JSON path support;
- disable UI/API route if labels or authority checks are wrong.

## Operator first checks

When debugging shared Oracle backend work, inspect in this order:

1. `just dspx oracle backend-status --json`
2. local SQLite index/report behavior
3. shared store health only if explicitly configured
4. ingest receipt errors
5. non-authority validation errors
6. DS1621 contract/runbook, noting that the current contract status is not deployed unless infra evidence says otherwise

## Explicit non-goals for rollout

- Do not migrate historical local SQLite indexes automatically.
- Do not run `program-gen` as an implicit ingestion job.
- Do not reuse MLflow Postgres by convenience.
- Do not run `cg-sync` or governance generated-artifact mutation for DSPx implementation slices.
- Do not touch unrelated DS1621 dirty files during DSPx work.
