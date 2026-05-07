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
- Status: `draft; revised after review_outcome=revise_rfc`
- Owner: `DSPx core`
- Reviewers: `DSPx core reviewers`, `Agent Kernel/governance liaison`, `softwareco/infra DS1621 operator`
- Created: `2026-05-06`
- Target milestone: `shared Oracle production-readiness follow-up`
- Related docs:
  - `docs/rfc/RFC-DSPX-ORACLE-20260505-shared-coordinate-backend.md`
  - `docs/adr/20260505-shared-oracle-coordinate-backend.md`
  - `docs/project/2026-05-06-review-oracle-evidence-publication-boundary-many-greats.md`
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
- Define publisher identity, publisher responsibility, redaction status, retention class, and retraction posture for shared publication.
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
- The first legal implementation slice is publication preflight only: no shared writes.
- Missing or `unknown` redaction status fails closed for shared publication eligibility.
- Authority-mirror labels require an explicit external authority ref; Oracle stores that ref only as a mirror/reference, never as authority truth.
- No secret values, DB passwords, or full secret-bearing URLs are stored in RFC examples or shared records.

## 3) Current state evidence

- `program-loop` now materializes a candidate, replay-checks its receipt, indexes `oracle_evidence.json` into a candidate-local CoordinateIndex, writes a non-authoritative Oracle report, and writes a candidate-state summary.
- The candidate-local index default is `<candidate>/oracle/coordinates.db`; this prevents accidental pollution of shared memory by every local experiment.
- `dspx oracle index --from-program-evidence` can explicitly index `oracle_evidence.json` files.
- The shared Oracle Postgres/pgvector pilot exists behind explicit opt-in and is tracked by the shared coordinate backend RFC/ADR and DS1621 infra contract.
- Generated-program activation packets remain blocked unless authority fields such as canonical binding ref, rollout owner, and rollback plan exist.
- The first adversarial review attempt, `docs/project/2026-05-06-review-oracle-evidence-publication-boundary-many-greats.md`, returned `revise_rfc`: the central direction is strong, but the RFC needed stricter redaction, publisher responsibility, authority-mirror label, and retention/retraction semantics before ADR.

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

- Design: future publication commands read canonical candidate artifacts and sidecars, validate non-authority flags, publisher identity, redaction status, curation label class, retention class, retraction posture, and optional authority refs, then upsert curated records into shared Oracle Postgres.
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
- Decision status: `draft revised after initial review; requires fresh re-review before ADR`.

A dedicated Oracle Postgres DB makes sense because it is a shared empirical coordinate memory with vector/search workload, not a second society authority database.

Candidate-local indexes remain correct for default product safety. Shared publication should not copy local DBs. It should re-index curated canonical candidate artifacts into shared Oracle Postgres with provenance, curation labels, publisher identity, redaction status, retention class, hashes, and non-authority flags.

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
publication inputs supplied by the publisher:
  publisher_id
  publisher_role
  publication_label
  redaction_status
  retention_class
  optional retraction_ref / replacement_ref
        -> validate hashes, identities, non-authority flags, label class, authority refs, redaction status, and retention posture
        -> Phase 1: write preflight packet only
        -> later phase only: upsert shared Oracle record(s)
```

### 6.3 Publication labels

Shared Oracle should not store only winners. Otherwise it learns survivor bias.

Labels are split into two classes so Oracle can remain empirical while still mirroring authority-relevant lifecycle events.

#### Empirical labels

Empirical labels do not require an external authority ref. They describe evidence usefulness, uncertainty, or negative-space behavior.

| Label | Meaning | Authority implication |
|---|---|---|
| `local_observed` | locally observed candidate evidence worth sharing | none |
| `retained` | useful evidence retained for future search | none |
| `request_more_evidence` | candidate or region needs more evaluation | none |
| `rejected` | useful negative/failed evidence | none |

#### Authority-mirror labels

Authority-mirror labels require an explicit `authority_ref`. Oracle does not create, validate as canonical, or own the authority state. It only mirrors the supplied ref for retrieval context.

| Label | Required authority ref | Meaning | Oracle implication |
|---|---|---|---|
| `accepted_for_review` | review/adjudication ref | candidate entered a review path | mirrored reference only |
| `promote_decision_recorded` | decision record / AK / governing-domain ref | local/domain decision sidecar or canonical decision exists | mirrored reference only |
| `activated` | canonical activation binding ref | activation evidence exists with canonical binding ref | mirrored reference only; AK/governance remains truth |
| `rolled_back` | rollback/deactivation ref | rollback evidence exists | mirrored reference only; AK/governance remains truth |

A shared publication request using an authority-mirror label without `authority_ref` must fail closed.

### 6.4 Publisher identity and responsibility

Shared publication is a custody act. A publication request must include:

| Field | Meaning | Requirement |
|---|---|---|
| `publisher_id` | explicit operator/agent/service identity initiating publication | required |
| `publisher_role` | role such as `operator`, `domain_owner_delegate`, `dspx_tooling`, or `governance_delegate` | required |
| `publisher_assertion` | short statement that the publisher is intentionally requesting shared empirical publication | required for shared publication |

The first implementation may treat these as declared fields. Later implementation may validate them against AK/session identity or governing-domain policy. Until that validation exists, outputs must say publisher identity is declared, not authenticated authority.

### 6.5 Redaction status

Shared publication must declare redaction posture. Legal initial values:

| Status | Shared publication eligibility | Meaning |
|---|---|---|
| `checked` | eligible | publisher asserts artifacts were checked for secrets/sensitive data under the current local checklist |
| `not_required` | eligible only for clearly synthetic/non-sensitive fixtures | publisher asserts the evidence contains no sensitive source material by construction |
| `redacted` | eligible | publisher asserts sensitive material was removed or transformed before publication |
| `unknown` | not eligible | redaction posture is unknown |
| `contains_sensitive_material` | not eligible | evidence is known to contain sensitive material and must not be shared |

Missing redaction status must fail closed. `checked`, `not_required`, and `redacted` are not production-grade DLP claims; they are explicit custody assertions until deterministic redaction tooling exists.

### 6.6 Retention and retraction posture

Shared publication must include a retention class:

| Retention class | Meaning |
|---|---|
| `ephemeral_review` | short-lived review support; eligible for early pruning |
| `retained_behavior_memory` | useful behavioral memory retained for future Oracle retrieval |
| `activation_evidence_reference` | activation/rollback-relevant evidence reference; retention follows authority/infra policy |
| `do_not_publish` | preflight-only marker; not eligible for shared write |

Retraction/deletion semantics:

- shared records must be addressable by idempotency key and publication receipt id;
- a later retraction should create an explicit retraction record or tombstone rather than silently deleting provenance;
- physical deletion from Postgres and backups may require infra-owned retention/backup policy and may not be instantaneous;
- retraction of Oracle records does not delete AK/governance authority records or source candidate artifacts.

### 6.7 Idempotency key

Publication should upsert, not append duplicates. A first deterministic key should include:

```text
schema_version=program-oracle-evidence-v1
receipt_bundle_id
assembly_id
candidate_id
oracle_evidence_sha256
publication_label
authority_ref, if supplied
publisher_id
redaction_status
retention_class
```

If the same evidence is published with a different label later, the record should either:

- add a publication event under the same evidence identity, or
- write a new label-specific record that shares the same evidence hash.

The implementation choice should be explicit before the first shared publication CLI lands.

### 6.8 Minimal CLI target shape

The first legal command shape is preflight only:

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

Later shared-write commands should make shared publication explicit:

```bash
dspx oracle program-evidence publish \
  --manifest candidate/manifest.json \
  --target shared-postgres \
  --publication-label retained \
  --publisher-id pi-session-... \
  --publisher-role operator \
  --redaction-status checked \
  --retention-class retained_behavior_memory \
  --authority-ref AK-1234 \
  --json
```

For authority-mirror labels, `--authority-ref` is required. For empirical labels, it is optional.

A future convenience path may exist only after standalone preflight and publish are proven:

```bash
dspx program-loop \
  --intent intent.yaml \
  --outdir candidate \
  --oracle-scope local \
  --publish-to-shared retained
```

`program-loop` must remain local by default. Any shared publication mode must be visibly opt-in.

### 6.9 Shared record metadata

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
  "publication_label_class": "empirical",
  "publisher_id": "pi-session-...",
  "publisher_role": "operator",
  "publisher_identity_kind": "declared_not_authenticated",
  "authority_ref": "AK-1234",
  "authority_ref_kind": "opaque_reference_only",
  "redaction_status": "checked",
  "retention_class": "retained_behavior_memory",
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

This is the only legal first implementation slice.

- Add a local preflight command that reads artifacts and emits a planned publication packet.
- Validate identity, hashes, non-authority flags, label legality, authority-ref requirements, publisher fields, redaction status, retention class, backend status, and idempotency key.
- Do not write to shared Oracle yet.
- Do not add `program-loop --publish-to-shared` yet.

### Phase 2 — Explicit shared publication

- Add an opt-in publish command behind explicit `DSPX_ORACLE_STORE=postgres_pgvector` / secret-ref configuration.
- Require a passing preflight packet or equivalent validations.
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
- publish preflight rejects missing or unknown publication labels;
- publish preflight rejects authority-mirror labels without `authority_ref`;
- publish preflight rejects missing publisher identity/responsibility fields;
- publish preflight rejects missing, `unknown`, or `contains_sensitive_material` redaction status for shared publication;
- publish preflight rejects missing or `do_not_publish` retention class for shared writes;
- publish preflight computes stable idempotency keys;
- shared publish writes only when explicit target/config is present;
- shared publish redacts secret-bearing database URLs from output;
- candidate-state summary reports shared publication refs as evidence only.

## 10) Operational impact

- Shared Oracle publication increases durable storage and backup/retention obligations for DS1621 infra.
- Publication must check backend health and should fail closed when shared backend posture is not acceptable.
- Publication must not require DS1621 availability for local program generation, replay, or candidate-local Oracle analysis.
- Retention labels should support pruning local/noisy records while retaining useful failures and activation-relevant evidence.
- Retraction should be modeled as explicit tombstone/retraction evidence; physical deletion from Postgres and backups is infra-governed and may lag logical retraction.
- Publisher identity in the first implementation is declared custody context, not authenticated authority.

## 11) Risk register

| Risk | Trigger | Mitigation | Rollback |
|---|---|---|---|
| Oracle becomes de facto authority | reports shown next to promotion/activation UI | always show non-authority flags and AK/governance refs as references only | hide shared publication refs from activation UI until boundary is fixed |
| Survivor bias | only winners are published | support `rejected`, `request_more_evidence`, and retained failure labels | backfill useful negative evidence from canonical artifacts |
| Shared DB pollution | `program-loop` auto-publishes every scratch run | local default; explicit publish only; redaction/status preflight | delete/retract publication records by idempotency key and label |
| Secret leakage | full DB URL or secret value enters publication output | secret-ref-only config; redacted backend status | revoke/rotate secret and purge leaked records/logs |
| Authority DB duplication | Oracle stores activation truth | store opaque refs/hashes only; AK/governance remains source | remove authority-like fields from Oracle schema |
| Ambiguous redaction posture | publication proceeds with unknown or informal redaction status | legal redaction values; fail closed on missing/unknown/sensitive | retract record and rotate/purge if secrets leaked |
| Authority-mirror label without authority ref | `activated`/rollback-like labels are published from Oracle-only claims | require authority refs for mirror labels | retract/tombstone mislabeled records |

## 12) Open questions

1. Should publication events be modeled as separate records or as append-only events under one evidence identity?
2. Which empirical labels are mandatory for the first implementation: `retained`, `rejected`, `request_more_evidence`, or a smaller subset?
3. Should publisher identity remain declared-only for the first implementation, or must it bind to Pi/AK/session identity before shared writes?
4. What deterministic redaction checks can DSPx add after the initial declared redaction-status model?
5. Should the accepted shared coordinate backend ADR be amended, or should this RFC get its own ADR?

## 13) Execution checklist

- [x] RFC draft created.
- [x] Initial adversarial review completed with outcome `revise_rfc`.
- [x] RFC revised for redaction status, publisher responsibility, authority-mirror labels, retention/retraction, and preflight-only first implementation.
- [ ] Fresh review attempt completed against the revised RFC.
- [ ] AK/governance liaison confirms no authority duplication.
- [ ] DS1621 infra owner confirms shared-publication operational assumptions.
- [ ] Decision recorded: amend existing ADR or create a new ADR.
- [ ] Phase 1 publication preflight task scoped.
