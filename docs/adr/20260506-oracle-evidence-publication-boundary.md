---
summary: "Adopt a curated Oracle evidence publication boundary: shared Oracle Postgres is empirical memory, not a second authority DB, and local coordinates.db files are scratch indexes."
read_when:
  - "You are implementing shared Oracle publication from DSPx candidate artifacts."
  - "You need the accepted boundary between candidate-local Oracle indexes, shared Oracle Postgres, and AK/society.v2.db authority."
  - "You are changing program-loop, Oracle publication, shared ingest, or generated-program activation evidence references."
system4d:
  container:
    boundary: "DSPx Oracle evidence publication from local candidate artifacts into shared empirical memory."
    edges:
      - "docs/rfc/RFC-DSPX-ORACLE-20260506-evidence-publication-boundary.md"
      - "docs/project/2026-05-06-review-oracle-evidence-publication-boundary-many-greats.md"
      - "docs/project/2026-05-06-review-oracle-evidence-publication-boundary-rereview.md"
      - "docs/adr/20260505-shared-oracle-coordinate-backend.md"
      - "docs/project/generated-program-activation-boundary.md"
  compass:
    driver: "Make shared Oracle publication useful without turning Oracle Postgres into authority or copying scratch local indexes as source truth."
    outcome: "Curated artifact re-index publication with provenance, curation labels, publisher custody, redaction status, retention posture, idempotency, and non-authority flags."
  engine:
    invariants:
      - "society.v2.db / AK remains canonical authority for tasks, decisions, evidence bindings, transitions, and activation truth."
      - "Candidate-local coordinates.db files are scratch/cache and must not be migrated wholesale."
      - "Shared Oracle Postgres stores empirical behavioral memory and opaque authority references only."
      - "Shared publication is explicit, idempotent, redaction-aware, and non-authoritative."
      - "The first legal implementation slice is publication preflight only: no shared writes."
      - "Authority-mirror labels require explicit authority refs."
  fog:
    risks:
      - "Shared Oracle reports can become de facto promotion authority."
      - "Winner-only publication can create survivor bias."
      - "Local scratch DB migration can pollute shared memory."
      - "Publication output can leak secret-bearing backend configuration if diagnostics are careless."
      - "Declared redaction can be over-read as deterministic DLP proof."
---

# ADR 20260506 — Oracle Evidence Publication Boundary

## Status

- accepted
- date: 2026-05-06
- owner: DSPx core
- reviewers: DSPx core reviewers, AK/governance liaison, softwareco/infra DS1621 operator
- AK decision: `#31 Review Oracle evidence publication boundary from initial RFC`
- related_docs:
  - `docs/rfc/RFC-DSPX-ORACLE-20260506-evidence-publication-boundary.md`
  - `docs/project/2026-05-06-problem-oracle-evidence-publication-boundary.md`
  - `docs/project/2026-05-06-evidence-oracle-evidence-publication-boundary.md`
  - `docs/project/2026-05-06-review-oracle-evidence-publication-boundary-many-greats.md`
  - `docs/project/2026-05-06-review-oracle-evidence-publication-boundary-rereview.md`
  - `docs/adr/20260505-shared-oracle-coordinate-backend.md`
  - `docs/project/generated-program-activation-boundary.md`
  - `docs/project/program-gen-walkthrough.md`
  - `docs/project/product_posture.md`
  - `~/ai-society/holdingco/governance-kernel/docs/core/definitions/generated-dspy-program-promotion-governance.md`
  - `~/ai-society/holdingco/governance-kernel/docs/core/definitions/transition-passports/generated-cognition-program-production-activation.md`
  - `~/ai-society/softwareco/infra/ds1621-admin/docs/project/ds1621-oracle-coordinate-backend-contract.md`

## Executive summary

DSPx will treat shared Oracle Postgres as curated empirical behavioral memory, not as a second society authority database. `society.v2.db` / Agent Kernel remains canonical authority for tasks, decisions, evidence bindings, transitions, and activation truth where landed.

Future shared Oracle publication must re-index canonical DSPx candidate artifacts into the shared backend with provenance, curation labels, publisher identity/responsibility, redaction status, retention class, retraction posture, idempotency keys, and non-authority flags. It must not copy candidate-local SQLite `coordinates.db` files wholesale.

The first implementation slice authorized by this decision is publication preflight only. Shared writes and `program-loop --publish-to-shared` convenience remain future work after preflight is proven.

## Context

DSPx now has a coherent local product loop:

- `program-loop` materializes a generated DSPy candidate;
- replay-checks its receipt;
- indexes `oracle_evidence.json` into a candidate-local `oracle/coordinates.db`;
- writes `program_oracle_report.json`;
- writes `program_candidate_state.json`.

The candidate-local index is safe by default. It avoids requiring DS1621 availability and avoids polluting shared Oracle memory with every local experiment.

Separately, the shared Oracle coordinate backend ADR accepted a dedicated Postgres/pgvector target for durable shared behavioral evidence. That target is distinct from MLflow Postgres and distinct from AK/governance authority.

The remaining question is how evidence moves from local candidate work into shared Oracle memory.

## Problem statement

Two bad implementation paths are tempting:

1. Treat Oracle Postgres as a second authority database because it is shared, durable, and queryable.
2. Copy a candidate-local `coordinates.db` file into Postgres when a candidate wins.

Both are wrong. Oracle is empirical interpretation. Local coordinate DBs are scratch indexes. Canonical evidence lives in candidate artifacts and authority truth lives in AK/governance/current owner surfaces.

The initial RFC had the right central direction, but adversarial review found it under-specified on redaction status, publisher responsibility, authority-shaped labels, and retraction/retention posture. The revised RFC closed those gaps and passed re-review.

## Decision drivers

- Preserve AK / `society.v2.db` as canonical authority.
- Preserve local-first `program-loop` safety.
- Make shared Oracle useful for retained behavior memory and cross-program retrieval.
- Avoid survivor bias by retaining useful failures and near-misses, not only winners.
- Keep publication explicit and auditable.
- Preserve provenance, hashes, redaction posture, labels, publisher responsibility, and non-authority flags.
- Keep secrets out of JSON, logs, docs, receipts, and publication records.
- Start with preflight-only implementation before shared writes.

## Decision

Adopt Option C from the revised RFC: shared Oracle publication must use curated artifact re-indexing, not local DB migration.

The accepted model is:

```text
canonical candidate artifacts + publisher custody fields + optional authority refs
  -> publication preflight
  -> validate identity, hashes, labels, authority-ref requirements, redaction posture, retention class, non-authority flags
  -> Phase 1: local preflight packet only
  -> later phase only: explicit shared Oracle upsert
  -> shared empirical memory record / receipt
```

Publication input should be canonical artifacts such as:

- `manifest.json`;
- `manifest.json.meta.json`;
- `behavior_results.json` / `behavior_episode.json`;
- `oracle_evidence.json`;
- `program_oracle_report.json`;
- `program_candidate_state.json`;
- optional jury/review/decision/promotion/activation sidecars;
- optional AK/governance refs supplied explicitly.

Publication requests must include publisher identity/responsibility fields, publication label, redaction status, and retention class.

Labels are accepted in two classes:

- empirical labels: `local_observed`, `retained`, `request_more_evidence`, `rejected`;
- authority-mirror labels: `accepted_for_review`, `promote_decision_recorded`, `activated`, `rolled_back`.

Authority-mirror labels require an explicit `authority_ref`. Oracle does not create or own the authority state; it mirrors the supplied ref for retrieval context only.

`program-loop` remains local by default. Any future shared publication convenience mode must be explicit opt-in and must come after standalone preflight and shared publish semantics are proven.

## Alternatives considered

### Option A — Oracle Postgres as authority database

Rejected. It duplicates AK/governance authority and makes empirical reports look normative.

### Option B — Copy candidate-local `coordinates.db` wholesale into Postgres

Rejected. It treats an implementation cache as source truth, risks importing noisy/private scratch records, weakens curation policy, and couples shared schema to local cache layout.

### Option C — Re-index curated canonical artifacts into shared Oracle Postgres

Accepted. It preserves provenance, supports labels/retention/redaction/idempotency, avoids survivor bias, and keeps Oracle empirical.

## Consequences

Positive:

- The shared Oracle publication path has a clear source-of-truth boundary.
- Local candidate indexes remain disposable.
- Shared Oracle can learn from winners, failures, near-misses, activations, and rollbacks.
- AK/governance authority remains unambiguous.
- Future implementation can begin with publication preflight before any shared writes.

Costs / tradeoffs:

- A publication preflight packet/schema is required before shared writes.
- Operators need explicit publisher fields, labels, redaction status, and retention class.
- Idempotency and duplicate handling must be designed before shared-write implementation.
- Shared Oracle records need retention and deletion/retraction semantics.
- Initial redaction status is declared custody context, not deterministic DLP proof.

Risks:

- Shared Oracle reports may become de facto promotion pressure.
- Winner-only operator habits may still create survivor bias.
- Shared publication could leak secrets if backend status is not redacted.
- Publication labels could be over-read as approval unless UI/CLI wording stays explicit.
- Authority-mirror labels could be misused if later implementation allows them without real refs.

## Follow-through obligations

Before any shared publication implementation:

1. create a Phase 1 publication preflight task;
2. define a `program-oracle-shared-publication-preflight-v1` or equivalent packet;
3. validate source artifact hashes and identities;
4. validate non-authority flags;
5. require explicit publication label and label class;
6. require publisher identity/responsibility fields;
7. require legal redaction status;
8. require retention class;
9. require authority refs for authority-mirror labels;
10. compute stable idempotency key;
11. report backend status without exposing secrets;
12. write no shared records.

Before shared writes:

1. prove preflight tests;
2. prove secret redaction tests;
3. prove fail-closed behavior for missing/unhealthy shared backend;
4. decide publication event versus label-specific record semantics;
5. decide first shared-write label subset;
6. ensure DS1621 backup/retention/monitoring posture is acceptable for shared publication;
7. keep activation truth in AK/governance/current authority.

Before `program-loop` shared publication convenience:

1. ship explicit publish command first;
2. keep local candidate index as default;
3. require visible operator opt-in and label;
4. surface shared publication refs as evidence only in candidate state and activation packets.

## Validation expectations

For this ADR recording:

- docs strict validation;
- task-scope validation;
- `git diff --check`;
- `just verify-fast`.

For implementation tasks:

- focused preflight tests;
- non-authority negative tests;
- authority-mirror-label-without-ref negative tests;
- publisher-field validation tests;
- redaction-status validation tests;
- retention-class validation tests;
- idempotency tests;
- local default `program-loop` regression tests;
- optional live shared-backend tests gated behind explicit service env vars only.

## Current implementation status

Accepted architecture. No shared-publication implementation is approved by this ADR alone.

Current truth:

```text
program-loop default: candidate-local Oracle index
shared Oracle Postgres: empirical memory target / pilot only
publication model: accepted boundary, not yet implemented
authority truth: AK / governance / owning domain, not Oracle
legal next implementation slice: publication preflight only
```
