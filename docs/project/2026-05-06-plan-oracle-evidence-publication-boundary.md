---
summary: "Post-ADR implementation plan for Oracle evidence publication, starting with a no-shared-write publication preflight packet."
read_when:
  - "You are implementing ADR 20260506 Oracle evidence publication boundary."
  - "You need the legal first implementation slice after AK decision #31."
---

# Implementation plan — Oracle evidence publication boundary

- Date: 2026-05-06
- Decision: `#31 Review Oracle evidence publication boundary from initial RFC`
- ADR: `docs/adr/20260506-oracle-evidence-publication-boundary.md`
- RFC: `docs/rfc/RFC-DSPX-ORACLE-20260506-evidence-publication-boundary.md`

## Implementation posture

Proceed in phases. Do not jump directly from ADR to shared Oracle writes.

The first slice must be a local preflight packet that reads candidate artifacts, validates the future publication boundary, and writes no shared records.

Status as of 2026-05-07:

- Phase 1 local preflight packet is implemented by `dspx oracle program-evidence publish-preflight`.
- Phase 2 explicit publish command is implemented by `dspx oracle program-evidence publish`; it is standalone, idempotent, and fails closed without an explicitly configured shared Postgres/pgvector backend.
- Phase 3 evidence-ref surfacing is implemented for `program-promote status` and `program-promote activation-packet` through `--oracle-publication-receipt`; publication refs remain evidence only and cannot approve activation.
- Live shared-backend rollout remains gated by the DS1621/infra contract and optional live tests; no `program-loop` shared-publish convenience is enabled.

## Phase 1 — Publication preflight only

Goal: prove DSPx can decide whether a candidate artifact set is eligible for shared Oracle publication without mutating shared Oracle, AK, governance, MLflow, or generated candidate files.

Scope:

- add a local command such as:

```bash
dspx oracle program-evidence publish-preflight \
  --manifest candidate/manifest.json \
  --target shared-postgres \
  --publication-label retained \
  --publisher-id pi-session-... \
  --publisher-role operator \
  --publisher-assertion "share this synthetic behavior evidence for future Oracle retrieval" \
  --redaction-status checked \
  --retention-class retained_behavior_memory \
  --out candidate/program_oracle_publication_preflight.json \
  --json
```

- read `manifest.json`, `oracle_evidence.json`, receipt metadata, and optional sidecars;
- validate candidate identity and hashes;
- validate non-authority flags;
- require explicit publication label;
- reject unknown labels;
- require authority refs for authority-mirror labels;
- require publisher identity/responsibility fields;
- require legal redaction status and fail closed on missing/unknown/sensitive status;
- require retention class and fail closed on `do_not_publish` for shared-write eligibility;
- compute a stable idempotency key;
- record intended target and backend posture without secret values;
- write a local `program-oracle-shared-publication-preflight-v1` packet.

Required tests:

- rejects missing `oracle_evidence.json`;
- rejects widened non-authority flags;
- rejects missing or unknown publication labels;
- rejects authority-mirror labels without `authority_ref`;
- rejects missing publisher fields;
- rejects missing, `unknown`, or `contains_sensitive_material` redaction status;
- rejects missing or shared-write-ineligible retention class;
- computes stable idempotency keys;
- output contains no DB password / secret-bearing URL;
- packet effect flags prove no shared write, no AK call, no governance mutation.

Exit gate:

- local preflight packet exists;
- candidate-local `program-loop` remains default unchanged;
- no shared database connection is required;
- `just verify-fast` passes.

## Phase 2 — Explicit shared publication command

Goal: write curated publication records to the shared Oracle backend only after preflight is stable.

Scope:

- add explicit publish command, not automatic `program-loop` behavior;
- require explicit shared backend config;
- require preflight pass or equivalent validation;
- upsert idempotently;
- return a publication receipt with redacted backend identity;
- preserve local SQLite and candidate-local workflow behavior.

Exit gate:

- shared writes fail closed on missing/unhealthy backend;
- duplicates are idempotent;
- publication labels are stored and queryable;
- non-authority flags are visible in output;
- optional live test is gated by explicit environment variables.

## Phase 3 — Candidate state and activation evidence refs

Goal: expose shared publication refs as evidence only.

Scope:

- `program-promote status` / candidate state can include shared publication refs;
- activation packets can cite shared Oracle publication/report refs;
- activation remains blocked without owning-domain decision, canonical binding, rollout owner, and rollback plan.

Exit gate:

- negative tests prove publication refs cannot approve activation;
- UI/CLI language says shared Oracle is empirical memory only.

## Phase 4 — `program-loop` convenience opt-in

Goal: optionally connect the local product loop to shared publication after explicit publish semantics are proven.

Scope:

- add a visible flag such as `--publish-to-shared retained`;
- default remains candidate-local only;
- require redaction status and backend posture;
- emit publication receipt/path in `program_loop.json`.

Exit gate:

- no shared mutation happens without explicit flag;
- local dogfood behavior remains service-free by default.

## Next task to create

Recommended next AK task after evidence-ref surfacing:

```text
Add program-loop shared publication opt-in
```

Bound it to DSPx only:

- explicit `program-loop` flag that requires label, redaction status, publisher fields, retention class, and shared backend posture;
- no shared mutation unless the flag is present;
- output publication receipt path in `program_loop.json` as evidence only;
- negative tests proving default `program-loop` remains candidate-local and service-free.

Do not make shared publication the default local smoke path.
