---
summary: "Deep implementation review of Oracle publication phases 1-4 and pi-autoresearch adapter preflight."
read_when:
  - "You are deciding whether the Oracle publication phases are ready for live rollout."
  - "You need known review findings before DS1621/shared Oracle production use."
---

# Deep review — Oracle publication implementation phases

- Date: 2026-05-07
- Scope: ADR `docs/adr/20260506-oracle-evidence-publication-boundary.md`
- Implementation plan: `docs/project/2026-05-06-plan-oracle-evidence-publication-boundary.md`
- AK task: `#2589 Deep-review Oracle publication implementation phases`

## Review verdict

All planned implementation phases are present in the codebase:

1. Phase 1: local `program-oracle-shared-publication-preflight-v1` packet.
2. Phase 2: explicit `dspx oracle program-evidence publish` command.
3. Phase 3: publication receipt refs in candidate-state / activation-packet evidence surfaces.
4. Phase 4: explicit `program-loop --publish-to-shared` opt-in.
5. Additional adapter: `dspx oracle autoresearch-evidence publish-preflight` for `pi-autoresearch` packets.

However, the stack is **not review-clean for live/shared rollout**. The default/local behavior is mostly correct, but the deep review found several high-severity hardening gaps before DS1621/shared Oracle production use.

## What passed review

- Default `program-loop` remains candidate-local and service-free.
- `program-loop --skip-oracle-index` avoids local Oracle index/report mutation.
- Phase 1 preflight rejects many bad inputs and redacts configured DB URL posture.
- Phase 2 standalone publish fails closed without a configured backend in CLI tests.
- Phase 3 refs remain evidence-only and do not approve activation.
- Phase 4 opt-in is explicit and not default.
- Optional live Postgres/pgvector tests are gated behind explicit environment variables.
- Targeted validation passed during review:
  - `uv run pytest tests/test_program_workflow.py tests/test_program_oracle_publication.py tests/test_program_candidate_state.py tests/test_program_activation_packet.py -q` => passed before this review artifact.
  - `just verify-fast` passed before this review artifact.
  - subagent targeted validation: 25 tests passed, 1 live test skipped, ruff passed.

## High findings

### H1 — Publish trusts mutable preflight metadata instead of rebuilding the publish contract

Files:

- `packages/dspx-core/src/dspx/services/program_oracle_publication.py:105-126`
- `packages/dspx-core/src/dspx/services/program_oracle_publication.py:234-279`
- `packages/dspx-core/src/dspx/services/program_oracle_publication.py:312-324`

The publish command checks a set of preflight booleans, then copies `publication` and `planned_record` from the preflight into the shared record/receipt. A locally edited preflight can keep `redaction_status_eligible: true` while changing `publication.redaction_status`, removing an authority ref, or widening `planned_record.non_authority`.

Impact: shared publication can bypass the Phase 1 builder's semantic validations if a preflight packet is edited before Phase 2 publish.

Recommended fix: at publish time, recompute/revalidate the preflight-equivalent contract from the manifest/evidence and CLI-accepted preflight, including label class, authority-ref requirement, redaction status, retention class, publisher fields, and `planned_record.non_authority`.

### H2 — Publication id/idempotency key is trusted rather than recomputed

Files:

- `packages/dspx-core/src/dspx/services/program_oracle_publication.py:234-237`
- `packages/dspx-core/src/dspx/services/program_oracle_publication.py:253`
- `packages/dspx-core/src/dspx/services/program_oracle_publication_preflight.py:256-278`

Phase 1 computes a stable publication id, but Phase 2 trusts `preflight["publication_id"]`. Editing this field changes the shared `run_id` and can create duplicate/colliding shared records for unchanged artifacts.

Recommended fix: recompute expected `publication_id` from the actual manifest/evidence hashes and publication fields at publish time, then fail closed if it differs from the preflight value.

### H3 — Explicit shared backend config is weaker than the plan states

Files:

- `packages/dspx-core/src/dspx/services/program_oracle_publication.py:197-206`
- `packages/dspx-core/src/dspx/coordinates/postgres_store.py` env fallback behavior

`_open_configured_shared_store()` allows empty `DSPX_ORACLE_STORE`, then `PostgresPgvectorCoordinateStore` can use ambient `DATABASE_URL`. That is weaker than the plan's explicit shared backend posture and can publish to an unintended Postgres target.

Recommended fix: require `DSPX_ORACLE_STORE=postgres_pgvector` and require an Oracle-specific URL env (`DSPX_ORACLE_DATABASE_URL` or `DSPX_ORACLE_POSTGRES_URL`) for shared publication. Do not use ambient `DATABASE_URL` for publish paths.

### H4 — Candidate-state/status can overwrite candidate artifacts while reporting no program mutation

Files:

- `packages/dspx-core/src/dspx/services/program_candidate_state.py:1213-1225`
- `packages/dspx-core/src/dspx/cli/commands/program_promote.py` `status --out`

`write_program_candidate_state()` writes any `out_path`. A caller can pass a candidate artifact path such as `manifest.json`, while the output reports `program_files_mutated: false`.

Recommended fix: add a forbidden-output guard similar to activation packet output protection, at least for known candidate artifact names.

### H5 — `program-loop` sidecar output paths can overwrite generated artifacts

Files:

- `packages/dspx-core/src/dspx/services/program_workflow.py:145-147`
- `packages/dspx-core/src/dspx/services/program_workflow.py:176-187`
- `packages/dspx-core/src/dspx/services/program_workflow.py:189-199`

`state_out`, `oracle_report_out`, `workflow_out`, publication preflight, and publication receipt paths are caller-controlled and are not guarded against overwriting generated program artifacts.

Recommended fix: centralize sidecar output validation for program-loop and reject known artifact names or paths inside the candidate root that collide with manifest/behavior/receipt/source files.

### H6 — Activation packet does not enforce non-authority constraints on most evidence artifacts

Files:

- `packages/dspx-core/src/dspx/services/program_activation_packet.py:164-177`
- `packages/dspx-core/src/dspx/services/program_activation_packet.py:423-427`
- Candidate-state stricter counterpart: `packages/dspx-core/src/dspx/services/program_candidate_state.py:328-471`

Activation packet schema-checks artifacts and identity-checks some of them, but it does not reject widened non-authority flags for jury results, refined review, decision record, or promotion plan.

Recommended fix: reuse or factor candidate-state non-authority validators in activation packet construction.

## Medium findings

### M1 — Activation artifact identity is fail-open when identity is absent or sparse

Files:

- `packages/dspx-core/src/dspx/services/program_activation_packet.py:194-210`

If an artifact has no `identity`, validation returns success. Missing identity fields are also skipped. Required activation evidence can therefore be unrelated but still count toward gates.

Recommended fix: require identity presence for evidence artifacts that gate activation and require enough exact identity fields to establish candidate/source relation.

### M2 — Activation behavior evidence is checked by filename/existence only

Files:

- `packages/dspx-core/src/dspx/services/program_activation_packet.py:213-221`
- `packages/dspx-core/src/dspx/services/program_activation_packet.py:323-325`

`behavior_results.json` and `behavior_episode.json` refs are not parsed before satisfying the `behavior_evidence` gate.

Recommended fix: parse and schema-check behavior evidence before it can satisfy activation packet gates.

### M3 — Activation `ready_for_rollout_preflight` is advisory but could be overread

Files:

- `packages/dspx-core/src/dspx/services/program_activation_packet.py:339-350`

A string `canonical_binding_ref`, `rollout_owner`, and `rollback_plan` can advance status to `ready_for_rollout_preflight`. The packet notes it is non-authoritative, but this status may be read as stronger than it is.

Recommended fix: rename/qualify the status or verify canonical binding against the owning authority before emitting it.

### M4 — Shared publication metadata/receipt exposes local paths

Files:

- `packages/dspx-core/src/dspx/services/program_oracle_publication.py:271-286`
- `packages/dspx-core/src/dspx/services/program_oracle_publication.py:306-310`

Shared record metadata and receipts include absolute preflight/evidence paths. That can leak workstation/user/workspace structure into shared Oracle records or receipts.

Recommended fix: store relative artifact names plus hashes, or explicitly mark local paths as local-only and exclude them from shared metadata.

### M5 — Preflight backend posture and publish backend selection are inconsistent

Files:

- `packages/dspx-core/src/dspx/services/program_oracle_publication_preflight.py:238-249`
- `packages/dspx-core/src/dspx/coordinates/postgres_store.py` env fallback behavior

Preflight detects `DSPX_ORACLE_DATABASE_URL`; publish may use other env vars. Operator review can see `database_url_present: false` while publish uses a URL.

Recommended fix: make preflight use the same explicit Oracle-specific backend config resolver that publish uses.

### M6 — pi-autoresearch adapter validation is too shallow for the source-owner boundary

Files:

- `packages/dspx-core/src/dspx/services/program_oracle_autoresearch.py:139-198`
- `packages/dspx-core/src/dspx/services/program_oracle_autoresearch.py:327-340`

The adapter validates basic packet/record shape but not all contract-significant fields such as `publicationPreflight.status`, `blockedReasons`, top-level boundaries, top-level source artifacts, or full run-level record fields.

Recommended fix: validate the full pi-autoresearch packet contract before setting `packet_valid: true`.

### M7 — pi-autoresearch duplicate `recordId` values collapse hash evidence

Files:

- `packages/dspx-core/src/dspx/services/program_oracle_autoresearch.py:273-286`

`record_sha256_by_record_id` is keyed by `recordId`; duplicate IDs overwrite earlier hashes.

Recommended fix: reject duplicate record IDs before computing hashes.

### M8 — pi-autoresearch preflight copies source paths/artifacts without a redaction policy

Files:

- `packages/dspx-core/src/dspx/services/program_oracle_autoresearch.py:293-300`

The output copies `packet_path`, `cwd`, and `source_artifacts`. This may be acceptable as a local preflight artifact, but the redaction boundary should be explicit.

Recommended fix: redact or hash source paths, or document them as local-only and prohibit propagation to shared records.

### M9 — `program-loop --publish-to-shared` failure leaves partial local outputs

Files:

- `packages/dspx-core/src/dspx/services/program_workflow.py:135-187`

On backend failure, program generation, local index/report, and preflight may already exist. This is acceptable if fail-closed means "no shared publication/receipt", but it should be documented/tested as partial local side effects rather than atomic rollback.

Recommended fix: document this semantics and add tests asserting the intended partial local outputs.

## Low findings

### L1 — Writer functions trust arbitrary mappings

Files:

- `packages/dspx-core/src/dspx/services/program_oracle_autoresearch.py:402-414`
- Similar writer pattern exists elsewhere.

Normal CLI paths use builders first, but imported writer functions can write contradictory packets.

Recommended fix: validate schema/effect/non-authority fields inside writer functions or keep them private by convention.

### L2 — Publisher assertions can contain secrets

The initial model treated redaction status as a declared custody assertion, not DLP, and persisted `publisher_assertion` as-is.

Resolution: AK task `#2607` adds a light fail-closed guard for obvious secret-shaped publisher assertions and separates secret custody into explicit 1Password `op://` refs. DSPx validates URI-safe refs, stores only redacted descriptors plus stable hashes, does not resolve refs via SDK/CLI during publication, and revalidates descriptors before shared publication so resolved secret values cannot be smuggled into receipts or shared metadata.

## Recommended remediation order

1. **Block live rollout until H1-H3 are fixed.** These directly affect shared publication safety.
2. Fix H4-H6 before treating activation/candidate-state packets as robust evidence surfaces.
3. Tighten pi-autoresearch adapter validation before relying on it as a source-owner membrane.
4. Document `program-loop --publish-to-shared` partial-local-output semantics.
5. Only then run/live-gate DS1621 shared backend publication smoke with secret refs and explicit env gates.

## Review conclusion

The implementation phases are complete as product slices, but the review outcome is **hardening required before production/shared rollout**. The safest next AK work is not DS1621 live rollout; it is a bounded hardening task for Phase 2 publish revalidation/idempotency/backend explicitness, followed by activation-output guardrails.

## Hardening pass resolution — 2026-05-07

AK task `#2599 Fix Oracle publication hardening findings` resolved the review blockers that were in scope for this pass:

- H1/H2/H3: Phase 2 publish now recomputes/revalidates publication semantics, idempotency key, planned-record non-authority flags, and requires explicit Oracle-specific Postgres/pgvector configuration for real shared publication.
- H4/H5: candidate-state and program-loop sidecar writers reject output paths that would overwrite known generated program artifacts.
- H6/M1/M2: activation packets now reject missing evidence identity, widened non-authority flags on gating evidence, and corrupt behavior evidence schemas.
- M4/M5: shared publication metadata omits local absolute source paths from the shared coordinate record, and preflight backend posture uses Oracle-specific URL keys consistently.
- M6/M7: pi-autoresearch adapter preflight validates more of the source packet contract and rejects duplicate record ids.
- M9: program-loop failure semantics are now tested: missing backend fails closed before receipt/workflow output; local generation/preflight side effects remain local-only and non-authoritative.
- L2: publisher-assertion secret handling is resolved by AK task `#2607`: publisher assertions reject obvious secret-shaped content, and secret custody uses URI-safe redacted 1Password `op://` reference descriptors whose values are never resolved or persisted. Phase 2 publish also rejects tampered descriptors that add resolved values or extra fields.

Validation for the hardening pass:

```bash
uv run pytest tests/test_program_oracle_publication.py tests/test_program_oracle_publication_preflight.py tests/test_program_oracle_autoresearch.py tests/test_program_activation_packet.py tests/test_program_candidate_state.py tests/test_program_workflow.py -q
uv run ruff check packages/dspx-core/src/dspx/services/program_oracle_publication.py packages/dspx-core/src/dspx/services/program_oracle_publication_preflight.py packages/dspx-core/src/dspx/services/program_oracle_autoresearch.py packages/dspx-core/src/dspx/services/program_activation_packet.py packages/dspx-core/src/dspx/services/program_candidate_state.py packages/dspx-core/src/dspx/services/program_workflow.py tests/test_program_oracle_publication.py tests/test_program_oracle_autoresearch.py tests/test_program_activation_packet.py tests/test_program_candidate_state.py tests/test_program_workflow.py
uv run ty check packages/dspx-core/src/dspx/services/program_oracle_publication.py packages/dspx-core/src/dspx/services/program_oracle_publication_preflight.py packages/dspx-core/src/dspx/services/program_oracle_autoresearch.py packages/dspx-core/src/dspx/services/program_activation_packet.py packages/dspx-core/src/dspx/services/program_candidate_state.py packages/dspx-core/src/dspx/services/program_workflow.py tests/test_program_oracle_publication.py tests/test_program_oracle_autoresearch.py tests/test_program_activation_packet.py tests/test_program_candidate_state.py tests/test_program_workflow.py
```

Observed results:

- `62 passed`
- `ruff`: passed
- `ty`: passed

Remaining live-readiness boundary: this hardening does not claim DS1621/shared Oracle production readiness. Live rollout still requires explicit DS1621 backend/backup evidence and live-gated publication smoke.
