---
summary: "Evidence note for the shared Oracle coordinate backend decision, separating current SQLite Oracle, DS1621 MLflow Postgres, and session-captured production Oracle target."
read_when:
  - "You need evidence for AK decision #29."
  - "You are checking whether Oracle Postgres was implemented or only proposed."
---

# Evidence note — Shared Oracle coordinate backend

- Date: 2026-05-05
- Decision: `#29 Adopt shared Oracle coordinate backend target architecture`
- Problem brief: `docs/project/2026-05-05-problem-shared-oracle-coordinate-backend.md`
- RFC: `docs/rfc/RFC-DSPX-ORACLE-20260505-shared-coordinate-backend.md`

## Evidence surface 1 — Current DSPx Oracle implementation

Current DSPx Oracle storage is local SQLite:

- `packages/dspx-core/src/dspx/coordinates/storage.py` defines SQLite-backed `CoordinateIndex`.
- Default index path is `generated/oracle/coordinates.db` unless `DSPX_ORACLE_INDEX_PATH` is set.
- `packages/dspx-core/src/dspx/services/program_oracle_index.py` explicitly ingests `program-oracle-evidence-v1` into `CoordinateIndex`.
- `dspx oracle backend-status --json` reports the local SQLite default and any explicitly configured shared-store scaffold state without creating indexes or exposing secrets.

## Evidence surface 2 — DS1621 MLflow is separate

DS1621 currently hosts the shared MLflow target at `http://ds1621:50000`.

The DS1621 MLflow stack uses:

- Postgres for MLflow metadata;
- MinIO for MLflow artifacts;
- DS1621 runbook/diary material in `softwareco/infra/ds1621-admin`.

This is not an Oracle coordinate store. It should not be reused by convenience as the Oracle database/schema without an explicit architecture decision.

## Evidence surface 3 — Session-captured production Oracle target

The relevant Pi session JSONL was inspected using the `pi-session-jsonl` skill and `jq` only:

```text
~/.pi/agent/sessions/--home-tryinget-ai-society-softwareco-owned-dspx--/2026-05-04T02-01-00-544Z_3a398eb6-68f8-4571-86f8-ffdee6307e3b.jsonl
```

Relevant timestamp:

```text
2026-05-05T17:37:00.456Z
```

The session conclusion was that production Oracle should be:

```text
shared, governed behavioral evidence service
not MLflow replacement
not promotion engine
```

The target flow was:

```text
generated DSPy program
  -> manifest.json / manifest.json.meta.json
  -> behavior_results.json / behavior_episode.json
  -> oracle_evidence.json
  -> explicit ingestion job
  -> shared Oracle CoordinateIndex
  -> report/search/territory/drift APIs
  -> UI / CLI analysis
  -> optional AK/decision handoff, never automatic authority
```

## Evidence surface 4 — DS1621 Oracle pilot is live but not production-ready

The infra-owned DS1621 pilot target is published in:

- `~/ai-society/softwareco/infra/ds1621-admin/docs/project/ds1621-oracle-coordinate-backend-contract.md`
- `~/ai-society/softwareco/infra/ds1621-admin/contracts/ds1621-oracle-coordinate-backend.env`

Its deployment status is:

```text
pilot_deployed_health_ok_live_smoke_passed_not_production_ready
```

This proves the owner boundary, non-secret target contract, live DS1621 pgvector health, DSPx live-gated smoke, first disposable restore proof, 14-day pilot retention/quota helpers, and latest-dump export to the operator-confirmed `DspxOracleBackups` Hyper Backup share exist. It does **not** prove a completed remote Hyper Backup run after export, monitoring/rotation readiness, production readiness, or activation authority.

## Evidence surface 5 — DSPx live-gated integration smoke exists but is skipped by default

DSPx now declares optional Postgres driver support as `dspx-core[oracle-postgres]` and includes `tests/test_postgres_store_live.py` for an explicit live round-trip smoke.

The smoke requires:

```text
DSPX_ORACLE_LIVE_POSTGRES=1
DSPX_ORACLE_DATABASE_URL=<operator-injected secret URL>
psycopg installed through the oracle-postgres extra
```

Default local/CI runs remain service-free and skip this test unless those opt-in gates are present.

## Evidence surface 6 — Governance boundary already exists

The generated cognition-program production-activation boundary lives outside DSPx local sidecars:

- governance-kernel defines the reusable production-activation semantics;
- owning domain/governing body judges concrete activation;
- AK/current authority records canonical decision/evidence/transition truth where landed;
- Oracle/MLflow/DSPx sidecars are evidence only.

## Conclusion

The evidence supports a dedicated shared Oracle backend target, not reusing the MLflow Postgres database and not staying local-only as the production architecture. RFC review, ADR recording, storage seams, DS1621 pilot provisioning, optional driver declaration, a passed live-gated DSPx integration smoke, backup/restore proof, retention/quota helpers, and latest-dump export into `DspxOracleBackups` now exist. Hyper Backup run evidence, monitoring/rotation, and production-readiness gates remain undone.
