---
summary: "Draft RFC for publishing curated DSPx Oracle evidence from local candidate indexes/artifacts into the shared Oracle Postgres backend without creating a second authority database."
read_when:
  - "You are deciding whether Oracle Postgres duplicates society.v2.db / Agent Kernel authority."
  - "You are designing how candidate-local Oracle evidence should enter shared Oracle memory."
  - "You need the boundary between local CoordinateIndex scratch state, shared Oracle Postgres, and AK/governance authority."
type: "rfc"
---

# RFC: Oracle Evidence Publication Boundary

## 0) Metadata

- RFC ID: `RFC-DSPX-ORACLE-20260506-evidence-publication-boundary`
- Status: `draft`
- Owner: `DSPx core`
- Reviewers: `DSPx core reviewers`, `Agent Kernel/governance liaison`, `softwareco/infra DS1621 operator`
- Created: `2026-05-06`
- Target milestone: `shared Oracle production-readiness follow-up`
- Related docs:
  - `docs/rfc/RFC-DSPX-ORACLE-20260505-shared-coordinate-backend.md`
  - `docs/adr/20260505-shared-oracle-coordinate-backend.md`
  - `docs/project/generated-program-activation-boundary.md`
  - `docs/project/program-gen-walkthrough.md`
  - `docs/project/product_posture.md`
  - `~/ai-society/holdingco/governance-kernel/docs/core/definitions/generated-dspy-program-promotion-governance.md`
  - `~/ai-society/holdingco/governance-kernel/docs/core/definitions/transition-passports/generated-cognition-program-production-activation.md`
  - `~/ai-society/softwareco/infra/ds1621-admin/docs/project/ds1621-oracle-coordinate-backend-contract.md`

## 1) Problem statement

DSPx now has three database-like surfaces that can be confused:

1. `society.v2.db` / Agent Kernel, backed by Frankensqlite, is the canonical society authority substrate for tasks, decisions, evidence bindings, transitions, and activation truth.
2. Candidate-local Oracle indexes, currently SQLite `CoordinateIndex` files such as `<candidate>/oracle/coordinates.db`, are scratch/local semantic indexes for interpreting one generated candidate's evidence.
3. The DS1621 Oracle Postgres/pgvector pilot is a proposed shared behavioral memory for curated DSPx Oracle records.

The architectural risk is treating the shared Oracle Postgres DB as a second authority database or treating candidate-local `coordinates.db` as the artifact that should be migrated wholesale after a candidate "wins".

That is wrong. Oracle is empirical memory. AK/governance/current authority remains canonical authority. Candidate-local indexes are implementation caches over canonical candidate artifacts, not durable source truth.

This RFC defines the publication boundary: how curated Oracle-readable evidence should move from local candidate artifacts into shared Oracle Postgres without collapsing evidence, interpretation, and authority.

## 2) Scope / non-goals

### In scope

- Define why a dedicated Oracle Postgres DB is valid alongside `society.v2.db`.
- Define the distinction between:
  - local candidate scratch indexes;
  - shared Oracle empirical memory;
  - AK/governance authority.
- Define the target publication model from canonical candidate artifacts to shared Oracle records.
- Define curation labels for winners, failures, near-misses, and activated candidates.
- Define invariants for future `publish` / shared-index CLI work.

### Out of scope

- Implementing the publication CLI in this RFC.
- Migrating existing local SQLite CoordinateIndex files into Postgres.
- Replacing Agent Kernel, governance-kernel, or `society.v2.db`.
- Making Oracle decide winners, activate candidates, block rollout, or mutate AK/governance.
- Defining the final DS1621 production readiness checklist; infra owns runtime backup/restore/monitoring/rotation truth.

### Invariants

- `society.v2.db` / AK remains canonical authority for tasks, decisions, evidence bindings, transitions, and activation truth where landed.
- Oracle Postgres stores empirical behavioral coordinate memory and may carry authority references, but not authority itself.
- Candidate-local `coordinates.db` files are scratch indexes/caches, not source-of-truth artifacts.
- Shared publication re-indexes canonical artifacts (`oracle_evidence.json`, manifest, receipts, sidecars), not local DB files.
- Shared Oracle publication is explicit, idempotent, provenance-preserving, and non-authoritative.
- No secret values, DB passwords, or full secret-bearing URLs are stored in RFC examples or shared records.

## 3) Current state evidence

- `program-loop` now materializes a candidate, replay-checks its receipt, indexes `oracle_evidence.json` into a candidate-local CoordinateIndex, writes a non-authoritative Oracle report, and writes a candidate-state summary.
- The candidate-local index default is `<candidate>/oracle/coordinates.db`; this prevents accidental pollution of shared memory by every local experiment.
- `dspx oracle index --from-program-evidence` can explicitly index `oracle_evidence.json` files.
- The shared Oracle Postgres/pgvector pilot exists behind explicit opt-in and is tracked by the shared coordinate backend RFC/ADR and DS1621 infra contract.
- Generated-program activation packets remain blocked unless authority fields such as canonical binding ref, rollout owner, and rollback plan exist.

## 4) Option analysis

### Option A: Treat Oracle Postgres as a second authority database

- Design: store promotion/activation truth directly in Oracle Postgres and let Oracle reports influence or represent approval.
- Pros:
  - simple mental model for one Oracle-centric product loop.
- Cons:
  - duplicates and conflicts with AK/governance authority;
  - makes empirical interpretation look normative;
  - creates unclear rollback and jurisdiction semantics;
  - violates existing activation boundaries.
- Risks:
  - Oracle similarity or report output becomes de facto promotion authority.

### Option B: Copy candidate-local `coordinates.db` wholesale into Postgres after a winner is selected

- Design: when a candidate is accepted, migrate or merge its local SQLite CoordinateIndex rows into shared Postgres.
- Pros:
  - appears to reuse local work;
  - might be mechanically easy for a narrow first implementation.
- Cons:
  - treats an implementation cache as source truth;
  - imports scratch/noisy/private records accidentally;
  - loses or weakens publication policy context;
  - complicates idempotency and duplicate detection;
  - couples shared schema to local cache layout.
- Risks:
  - shared Oracle memory becomes polluted by local experiments and cache artifacts.

### Option C: Re-index curated canonical artifacts into shared Oracle Postgres

- Design: future publication commands read canonical candidate artifacts and sidecars, validate non-authority flags and optional authority refs, then upsert curated records into shared Oracle Postgres.
- Pros:
  - preserves source-of-truth lineage;
  - supports winners, failures, near-misses, and activated candidates without survivor bias;
  - keeps Oracle empirical and AK/governance authoritative;
  - allows explicit retention/redaction/publication policy;
  - keeps local scratch indexes disposable.
- Cons:
  - requires a publication contract and idempotency keys;
  - requires operator/product decisions about curation labels and retention;
  - requires backend status checks before shared publication.
- Risks:
  - operators may still over-read shared Oracle records as approval unless labels and non-authority flags are visible.

## 5) Decision

- Chosen target: `Option C`.
- Decision status: `draft; pending review/ADR if accepted`.

A dedicated Oracle Postgres DB makes sense because it is a shared empirical coordinate memory with vector/search workload, not a second society authority database.

Candidate-local indexes remain correct for default product safety. Shared publication should not copy local DBs. It should re-index curated canonical candidate artifacts into shared Oracle Postgres with provenance, curation labels, hashes, and non-authority flags.

## 6) Target architecture

### 6.1 Authority and data-role map

| Surface | Role | Owns | Must not own |
|---|---|---|---|
| `society.v2.db` / AK | canonical authority substrate | task truth, decisions, evidence bindings, transition refs, activation truth | vector similarity, empirical neighborhoods |
| governance-kernel | society/domain transition semantics | production activation rules and passports | DSPx local evidence generation |
| candidate artifacts | source evidence | manifest, receipts, behavior results, Oracle-readable evidence, sidecars | shared retention or authority by themselves |
| candidate-local `coordinates.db` | scratch interpretation cache | local semantic index for one candidate/workspace | durable source truth, publication truth |
| shared Oracle Postgres | curated empirical memory | shared coordinate records, vector search, behavioral summaries, provenance refs | winner selection, promotion, deployment, AK/governance mutation |
| MLflow | observability evidence | runs, metrics, artifacts, trace links | Oracle coordinates or activation authority |

### 6.2 Publication source of truth

The publication input is canonical artifacts, not the local index:

```text
manifest.json
manifest.json.meta.json
behavior_results.json / behavior_episode.json
oracle_evidence.json
optional sidecars:
  program_oracle_report.json
  program_candidate_state.json
  program-jury-results-v1
  program-promotion-decision-record-v1
  program-promotion-plan-v1
  generated-cognition-program-production-activation-packet-v1
optional AK/governance refs supplied by operator/current authority
        -> validate hashes, identities, non-authority flags, curation label
        -> upsert shared Oracle record(s)
```

### 6.3 Publication labels

Shared Oracle should not store only winners. Otherwise it learns survivor bias.

Target labels:

| Label | Meaning | Authority implication |
|---|---|---|
| `local_observed` | locally observed candidate evidence worth sharing | none |
| `retained` | useful evidence retained for future search | none |
| `request_more_evidence` | candidate or region needs more evaluation | none |
| `rejected` | useful negative/failed evidence | none |
| `accepted_for_review` | candidate entered a review path | review evidence only |
| `promote_decision_recorded` | local/domain decision sidecar exists | reference only unless AK/governance binding exists |
| `activated` | activation evidence exists with canonical binding ref | Oracle mirrors reference; AK/governance remains truth |
| `rolled_back` | rollback evidence exists | Oracle mirrors reference; AK/governance remains truth |

### 6.4 Idempotency key

Publication should upsert, not append duplicates. A first deterministic key should include:

```text
schema_version=program-oracle-evidence-v1
receipt_bundle_id
assembly_id
candidate_id
oracle_evidence_sha256
publication_label
authority_ref, if supplied
```

If the same evidence is published with a different label later, the record should either:

- add a publication event under the same evidence identity, or
- write a new label-specific record that shares the same evidence hash.

The implementation choice should be explicit before the first shared publication CLI lands.

### 6.5 Minimal CLI target shape

Future commands should make shared publication explicit:

```bash
dspx oracle program-evidence publish \
  --manifest candidate/manifest.json \
  --target shared-postgres \
  --publication-label retained \
  --authority-ref AK-1234 \
  --redaction-status checked \
  --json
```

or, as a convenience after explicit opt-in:

```bash
dspx program-loop \
  --intent intent.yaml \
  --outdir candidate \
  --oracle-scope local \
  --publish-to-shared retained
```

`program-loop` should remain local by default. Any shared publication mode must be visibly opt-in.

### 6.6 Shared record metadata

Each shared Oracle record should carry at least:

```json
{
  "schema_version": "program-oracle-shared-publication-v1",
  "source_schema_version": "program-oracle-evidence-v1",
  "candidate_id": "prog-cand-...",
  "assembly_id": "prog-asm-...",
  "receipt_bundle_id": "prog-rb-...",
  "oracle_evidence_sha256": "...",
  "manifest_sha256": "...",
  "publication_label": "retained",
  "authority_ref": "AK-1234",
  "authority_ref_kind": "opaque_reference_only",
  "redaction_status": "checked",
  "non_authority": {
    "oracle_ranking": false,
    "oracle_pruning": false,
    "oracle_promotion": false,
    "governance_authority": false,
    "external_mutation": false
  }
}
```

## 7) Rollout plan

### Phase 0 — RFC/review alignment

- Land this RFC as draft.
- Review with DSPx core and AK/governance liaison.
- Decide whether this RFC needs a separate ADR or can be folded into the accepted shared coordinate backend ADR as an implementation constraint.

### Phase 1 — Publication preflight only

- Add a local preflight command that reads artifacts and emits a planned publication packet.
- Validate identity, hashes, non-authority flags, label legality, redaction status, backend status, and idempotency key.
- Do not write to shared Oracle yet.

### Phase 2 — Explicit shared publication

- Add an opt-in publish command behind explicit `DSPX_ORACLE_STORE=postgres_pgvector` / secret-ref configuration.
- Upsert publication records idempotently.
- Return a receipt that includes backend identity without secret values.

### Phase 3 — Product-loop integration

- Add an explicit `program-loop --publish-to-shared <label>` convenience path only after Phase 2 has passed.
- Keep local candidate index as default.
- Surface shared publication status in `program_candidate_state.json` and activation packets as evidence references only.

## 8) Compatibility and migration

- Existing local SQLite CoordinateIndex behavior remains supported.
- Existing candidate-local `program-loop` behavior remains default.
- No automatic migration of local `coordinates.db` files.
- Historical local evidence may be published only by re-reading source artifacts where available.
- If source artifacts are missing and only a local SQLite DB remains, publication should fail closed or require a separate recovery RFC.

## 9) Validation plan

Required checks for this RFC slice:

```bash
node ~/ai-society/core/agent-scripts/scripts/docs-list.mjs --docs . --strict --full-list
just task-scope-check task_id=<AK-ID> mode=working-tree
just verify-fast
git diff --check
```

Future implementation tests:

- publish preflight rejects missing `oracle_evidence.json`;
- publish preflight rejects widened non-authority flags;
- publish preflight rejects missing/redaction-unknown status for shared publication;
- publish preflight computes stable idempotency keys;
- shared publish writes only when explicit target/config is present;
- shared publish redacts secret-bearing database URLs from output;
- candidate-state summary reports shared publication refs as evidence only.

## 10) Operational impact

- Shared Oracle publication increases durable storage and backup/retention obligations for DS1621 infra.
- Publication must check backend health and should fail closed when shared backend posture is not acceptable.
- Publication must not require DS1621 availability for local program generation, replay, or candidate-local Oracle analysis.
- Retention labels should support pruning local/noisy records while retaining useful failures and activation-relevant evidence.

## 11) Risk register

| Risk | Trigger | Mitigation | Rollback |
|---|---|---|---|
| Oracle becomes de facto authority | reports shown next to promotion/activation UI | always show non-authority flags and AK/governance refs as references only | hide shared publication refs from activation UI until boundary is fixed |
| Survivor bias | only winners are published | support `rejected`, `request_more_evidence`, and retained failure labels | backfill useful negative evidence from canonical artifacts |
| Shared DB pollution | `program-loop` auto-publishes every scratch run | local default; explicit publish only; redaction/status preflight | delete/retract publication records by idempotency key and label |
| Secret leakage | full DB URL or secret value enters publication output | secret-ref-only config; redacted backend status | revoke/rotate secret and purge leaked records/logs |
| Authority DB duplication | Oracle stores activation truth | store opaque refs/hashes only; AK/governance remains source | remove authority-like fields from Oracle schema |

## 12) Open questions

1. Should publication events be modeled as separate records or as append-only events under one evidence identity?
2. Which labels are mandatory for the first implementation: `retained`, `rejected`, `activated`, or a smaller subset?
3. Should shared publication require an AK evidence/task/decision ref for all records, or only for activation-relevant labels?
4. Should redaction status be operator-declared initially, or should DSPx add deterministic local redaction checks first?
5. Should the accepted shared coordinate backend ADR be amended, or should this RFC get its own ADR?

## 13) Execution checklist

- [x] RFC draft created.
- [ ] RFC reviewed by DSPx core.
- [ ] AK/governance liaison confirms no authority duplication.
- [ ] DS1621 infra owner confirms shared-publication operational assumptions.
- [ ] Decision recorded: amend existing ADR or create a new ADR.
- [ ] Phase 1 publication preflight task scoped.
