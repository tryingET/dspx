---
summary: "Current DSPx Oracle backend/storage posture: local SQLite default, explicit shared Postgres publication, MLflow separation, and non-authority boundary."
read_when:
  - "You need the current Oracle DB/storage truth instead of historical RFC/ADR decision-time context."
  - "You are changing Oracle indexing, publication, backend-status, MLflow linkage, or generated-program evidence docs."
  - "You are explaining whether Oracle has one DB or multiple DB surfaces."
type: "reference"
---

# Oracle backend current status

## Purpose

This is the DRY current-status map for DSPx Oracle storage. Historical rationale lives in [[20260505-shared-oracle-coordinate-backend]] and [[20260506-oracle-evidence-publication-boundary]]. Generated-program evidence boundaries live in [[generated-program-evidence-surface-boundaries]].

## Current storage surfaces

| Surface | Backend/storage | Default? | Primary use | Must not become |
|---|---|---:|---|---|
| Candidate-local Oracle index | SQLite `CoordinateIndex`, usually `<candidate>/oracle/coordinates.db` or `generated/oracle/coordinates.db` | Yes | Offline/local indexing, search, reports over `oracle_evidence.json` | Durable source truth, shared publication artifact, activation authority |
| Shared Oracle empirical memory | DS1621 Postgres + pgvector Oracle coordinate backend | No, explicit opt-in only | Curated shared behavioral memory/publication after preflight | MLflow store, AK/governance DB, winner selection, production approval |
| MLflow tracking | DS1621 MLflow Postgres + MinIO or explicit configured MLflow backend | No implicit fallback | Observability runs, metrics, tags, artifacts, UI correlation | Oracle coordinate store, replay source of truth, activation authority |
| AK / `society.v2.db` | Agent Kernel authority substrate | External authority surface | Tasks, decisions, evidence bindings, transitions, activation truth | Oracle cache, MLflow artifact store |

## Current facts

- `program-gen` writes `oracle_evidence.json` as Oracle-readable evidence, but it does **not** index Oracle or write either Oracle DB surface by itself.
- `dspx oracle index --from-program-evidence` writes to the selected local SQLite CoordinateIndex for candidate-local analysis.
- Shared Oracle publication is a separate explicit path over curated/preflighted evidence; it is not automatic and does not copy local `coordinates.db` files wholesale.
- Program-evidence shared-publication preflight validates the `oracle_evidence.json` runtime-trace summary/hash against `program_runtime_traces.json` before the explicit publish command can write shared empirical memory.
- `program-promote status` and activation packets can summarize shared-publication preflight readiness and shared-publication receipt evidence; activation packets validate receipt target/backend posture, secret redaction, idempotency/record/source/non-authority posture, bind receipt source hashes to the supplied preflight when both are present, cross-check candidate-state Oracle publication refs, and expose `evidence_alignment.oracle_publication`, and all remain evidence-only/non-authoritative.
- The DS1621 shared Oracle Postgres/pgvector pilot is live enough for explicit dogfood publication, but remains `production_ready: false`; see [[2026-05-09-oracle-production-readiness-gates-dogfood]].
- DS1621 MLflow Postgres is a different database role from DS1621 Oracle Postgres/pgvector.
- Oracle records may carry authority references as mirrors, but Oracle is empirical memory only. AK/governance/owning-domain surfaces remain canonical authority.

## Executable status check

Use the read-only status command when code or docs need current runtime posture:

```bash
dspx oracle backend-status --json
```

The command must not create `coordinates.db`, connect to Postgres, print secret values, mutate MLflow, mutate AK/governance, or claim activation readiness.

## Config boundary

For shared Oracle publication, prefer Oracle-specific DB URL configuration:

```bash
DSPX_ORACLE_STORE=postgres_pgvector
DSPX_ORACLE_DATABASE_URL=...
# or DSPX_ORACLE_POSTGRES_URL=...
```

An ambient `DATABASE_URL` may be visible to lower-level store diagnostics, but it is not sufficient by itself for the explicit generated-program shared-publication path. Status output should make that distinction visible without printing secrets.

## Related docs

- [[generated-program-evidence-surface-boundaries]] — generated-program evidence surface map.
- [[program-gen-walkthrough]] — local generation/evidence walkthrough.
- [[MLFLOW_OBSERVABILITY_PLAN]] — MLflow tracking/artifact boundary.
- [[20260505-shared-oracle-coordinate-backend]] — accepted shared-backend target decision.
- [[20260506-oracle-evidence-publication-boundary]] — local-to-shared publication boundary.
- [[2026-05-09-oracle-production-readiness-gates-dogfood]] — latest dogfood evidence for backend/backup/authority gates.
