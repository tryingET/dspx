---
summary: "Validation, rollout, and rollback notes for ADR 20260506 Oracle evidence publication boundary."
read_when:
  - "You are validating, rolling out, or rolling back Oracle shared publication work."
  - "You need safety gates for publication preflight, shared publish, candidate state refs, or program-loop publish opt-in."
---

# Validation / rollout / rollback — Oracle evidence publication boundary

- Date: 2026-05-06
- Decision: `#31 Review Oracle evidence publication boundary from initial RFC`
- ADR: `docs/adr/20260506-oracle-evidence-publication-boundary.md`
- Implementation plan: `docs/project/2026-05-06-plan-oracle-evidence-publication-boundary.md`

## Global validation invariants

Every implementation slice must preserve:

- `society.v2.db` / AK remains canonical authority;
- shared Oracle Postgres is empirical memory only;
- candidate-local `coordinates.db` files are scratch/cache;
- publication re-indexes canonical artifacts, not local DB files;
- `program-loop` remains local/candidate-local by default;
- publication is explicit and idempotent;
- no secret values in JSON/logs/docs/receipts;
- non-authority flags are validated before publication;
- authority-mirror labels require explicit authority refs;
- missing or unknown redaction status fails closed;
- publisher identity is declared custody context until authenticated binding exists;
- Oracle cannot promote, select winners, deploy, block production, mutate AK, or mutate governance.

## Phase 1 validation — Publication preflight only

Minimum checks:

```bash
uv run pytest tests/test_program_oracle_publication_preflight.py -q
uv run ruff check packages/dspx-core/src/dspx/services packages/dspx-core/src/dspx/cli/commands/oracle.py tests/test_program_oracle_publication_preflight.py
node ~/ai-society/core/agent-scripts/scripts/docs-list.mjs --docs . --strict
just task-scope-check
just verify-fast
```

Required negative checks:

- missing `oracle_evidence.json` fails closed;
- widened `non_authority` flags fail closed;
- unknown publication labels fail closed;
- authority-mirror labels without `authority_ref` fail closed;
- missing publisher fields fail closed;
- shared target without legal redaction status fails closed;
- shared-write eligibility with `do_not_publish` retention class fails closed;
- output redacts backend secrets;
- effect flags prove no shared write, no AK call, no governance mutation.

Rollout:

- ship as local packet only;
- keep shared publication disabled/unimplemented;
- document legal next step as shared publish implementation only after preflight acceptance.

Rollback:

- remove/disable the preflight command;
- local `program-loop` and `oracle index --from-program-evidence` remain unaffected;
- delete only local preflight sidecars if needed.

## Phase 2 validation — Explicit shared publication

Minimum checks:

- all Phase 1 checks;
- idempotent upsert tests;
- fail-closed tests for missing/unhealthy shared backend;
- redaction tests for every JSON/log output path;
- optional live Postgres/pgvector test gated behind explicit env vars and skipped by default.

Rollout:

- require explicit command and shared backend config;
- require publication label, publisher fields, redaction status, and retention class;
- write a publication receipt;
- keep local SQLite/candidate-local defaults unchanged.

Rollback:

- disable shared publish command or unset shared backend config;
- local candidate artifacts and indexes remain valid;
- shared publication records require explicit retraction/delete runbook by idempotency key if rollback must remove them.

## Phase 3 validation — Candidate state / activation refs

Minimum checks:

- candidate-state tests show publication refs as evidence only;
- activation-packet tests prove refs cannot approve activation;
- missing canonical binding / rollout owner / rollback plan still blocks rollout preflight.

Rollout:

- add refs to state/activation packets only as evidence references;
- keep non-authority labels visible.

Rollback:

- stop including shared publication refs in state/activation packet outputs;
- keep local report JSON path support.

## Phase 4 validation — `program-loop` publish opt-in

Minimum checks:

- default `program-loop` writes only candidate-local Oracle index;
- shared publication requires explicit flag;
- missing label/redaction/backend posture fails closed;
- `program_loop.json` records publication as evidence only.

Rollout:

- document the opt-in as advanced/shared-memory behavior;
- never make shared publication the default local smoke path.

Rollback:

- remove the `program-loop` shared publish flag;
- preserve explicit standalone publish command if safe.

## Operator first checks

When debugging publication work, inspect in this order:

1. candidate `manifest.json` and `oracle_evidence.json` hashes;
2. preflight packet status and missing requirements;
3. non-authority flags;
4. publication label and label class;
5. authority ref if the label is authority-mirror;
6. publisher fields;
7. redaction status and retention class;
8. `just dspx oracle backend-status --json` only if shared publication is explicitly requested;
9. DS1621 infra contract if the shared backend is the DS1621 pilot.

## Explicit non-goals for rollout

- Do not migrate local `coordinates.db` files wholesale.
- Do not publish every `program-loop` run by default.
- Do not publish only winners.
- Do not store activation truth in Oracle.
- Do not reuse MLflow Postgres by convenience.
- Do not claim production readiness until DS1621 remote backup and authority gates are proven.
