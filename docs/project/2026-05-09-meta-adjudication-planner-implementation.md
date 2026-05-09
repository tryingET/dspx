---
summary: "Implementation evidence for Phase 1-6a of the DSPx meta-adjudication orchestration RFC: local planner, target profile, jury requirements, deterministic jury panel, jury verification, program adjudicator formation, program adjudicator verification, program evidence adjudication, adjudication behavior trace sidecars, and adjudication trace Oracle publication preflight/publish commands."
read_when:
  - "You are checking the shipped Phase 1-6a meta-adjudication sidecars."
  - "You need the command shape for `program-promote meta-adjudication-plan`, `target-profile`, `jury-requirements`, `jury-panel`, `verify-jury-panel`, `adjudicator-formation`, `verify-program-adjudicator`, `evidence-adjudication`, `adjudication-behavior-trace`, or `oracle adjudication-trace publish-preflight|publish`."
type: "evidence"
---

# 2026-05-09 Meta-adjudication planner implementation

## Result

Phase 1-6a from `docs/rfc/RFC-DSPX-ADJ-20260509-meta-adjudication-orchestration.md` are implemented as local, non-authoritative sidecars.

Planner command:

```bash
dspx program-promote meta-adjudication-plan \
  --manifest <candidate>/manifest.json \
  --out <candidate>/program_meta_adjudication_plan.json \
  --json
```

The planner command writes:

```text
schema_version=program-meta-adjudication-plan-v1
status=planned_not_executed
lifecycle_state=meta_adjudication_plan_ready
```

First-class target/jury sidecar commands:

```bash
dspx program-promote target-profile \
  --manifest <candidate>/manifest.json \
  --out <candidate>/target_profile.json \
  --json

dspx program-promote jury-requirements \
  --target-profile <candidate>/target_profile.json \
  --out <candidate>/jury_requirements.json \
  --json
```

Those commands write:

```text
schema_version=program-target-profile-v1
schema_version=program-jury-requirements-v1
```

Deterministic jury-panel commands:

```bash
dspx program-promote jury-panel \
  --jury-requirements <candidate>/jury_requirements.json \
  --out <candidate>/meta_jury_selection.json \
  --json

dspx program-promote verify-jury-panel \
  --jury-selection <candidate>/meta_jury_selection.json \
  --out <candidate>/jury_verification.json \
  --json
```

Those commands write:

```text
schema_version=program-meta-jury-selection-v1
schema_version=program-jury-verification-v1
```

Deterministic program-adjudicator commands:

```bash
dspx program-promote adjudicator-formation \
  --jury-verification <candidate>/jury_verification.json \
  --out <candidate>/program_adjudicator_formation.json \
  --json

dspx program-promote verify-program-adjudicator \
  --adjudicator-formation <candidate>/program_adjudicator_formation.json \
  --out <candidate>/program_adjudicator_verification.json \
  --json
```

Those commands write:

```text
schema_version=program-adjudicator-formation-v1
schema_version=program-adjudicator-verification-v1
```

Deterministic evidence-adjudication and behavior-trace commands:

```bash
dspx program-promote evidence-adjudication \
  --manifest <candidate>/manifest.json \
  --adjudicator-verification <candidate>/program_adjudicator_verification.json \
  --out <candidate>/program_evidence_adjudication.json \
  --json

dspx program-promote adjudication-behavior-trace \
  --evidence-adjudication <candidate>/program_evidence_adjudication.json \
  --out <candidate>/adjudication_behavior_trace.json \
  --json
```

Those commands write:

```text
schema_version=program-evidence-adjudication-v1
schema_version=program-adjudication-behavior-trace-v1
```

Explicit adjudication-trace publication commands:

```bash
dspx oracle adjudication-trace publish-preflight \
  --trace <candidate>/adjudication_behavior_trace.json \
  --target shared-postgres \
  --publication-label adjudication_behavior_trace \
  --publisher-id <publisher> \
  --publisher-role <role> \
  --publisher-assertion <checked-custody-assertion> \
  --redaction-status checked \
  --retention-class retained_behavior_memory \
  --out <candidate>/adjudication_trace_publication_preflight.json \
  --json

dspx oracle adjudication-trace publish \
  --preflight <candidate>/adjudication_trace_publication_preflight.json \
  --receipt-out <candidate>/adjudication_trace_publication_receipt.json \
  --json
```

Those commands write:

```text
schema_version=program-adjudication-trace-publication-preflight-v1
schema_version=program-adjudication-trace-publication-receipt-v1
```

`publish` performs the shared Oracle/Postgres mutation only when `DSPX_ORACLE_STORE=postgres_pgvector` and `DSPX_ORACLE_DATABASE_URL` or `DSPX_ORACLE_POSTGRES_URL` are configured at runtime.

## What it does

The planner reads an existing generated-program `manifest.json` plus optional sidecars and emits:

- generated candidate identity;
- target profile derived from manifest intent/request data;
- target risks such as source grounding, canonical mutation boundary, review surface boundary, rollout/rollback, and authority boundary;
- jury requirements and required perspectives;
- present/missing local sidecars;
- exact next commands for currently implemented follow-up steps;
- future planned commands for model-backed target/jury/adjudicator phases;
- Oracle/Postgres behavior-memory posture;
- GEPA improvement-lane posture;
- non-authority and no-mutation effect flags.

The first-class sidecar commands materialize the embedded target profile, jury requirements, deterministic meta-jury selection, DSPx adjudicator jury verification, deterministic program-adjudicator formation, DSPx adjudicator program-adjudicator verification, deterministic program evidence adjudication, local adjudication behavior tracing, and explicit adjudication-trace publication preflight/publish as standalone JSON artifacts so later phases can consume them without re-running the full planner.

## What it does not do

It does **not**:

- call a model/provider;
- select a model-backed jury;
- verify a jury with model-backed adjudication;
- publish to shared Oracle/Postgres unless `oracle adjudication-trace publish` is explicitly run with a configured shared backend;
- mutate AK/governance;
- activate, deploy, promote, rank, or select a winner.

## Implemented files

```text
packages/dspx-core/src/dspx/services/program_meta_adjudication.py
packages/dspx-core/src/dspx/services/program_adjudication_publication.py
packages/dspx-core/src/dspx/cli/commands/program_promote.py
packages/dspx-core/src/dspx/cli/commands/oracle.py
tests/test_program_meta_adjudication.py
tests/test_program_adjudication_publication.py
```

## Dogfood

The planner was dogfooded against the live Obsidian/PDF candidate root from the `dspy-lm-auth/codex/gpt-5.5` run:

```bash
uv run --package dspx-core -q python -m dspx.cli.dspx program-promote meta-adjudication-plan \
  --manifest /tmp/dspx-obsidian-pdf-transition-live.9QA9Nv/pdf-transition-program/manifest.json \
  --out /tmp/dspx-obsidian-pdf-transition-live.9QA9Nv/pdf-transition-program/program_meta_adjudication_plan.json \
  --json
```

Observed planner summary:

```text
schema_version=program-meta-adjudication-plan-v1
status=planned_not_executed
risk_ids=behavior_quality,authority_boundary,source_grounding,canonical_mutation_boundary,review_queue_boundary
missing_count=2
evidence_sidecar_commands=adjudicate_program_evidence,write_adjudication_behavior_trace
provider_called=false
activation_authority=false
```

The first-class sidecars were also dogfooded against the same candidate:

```bash
uv run --package dspx-core -q python -m dspx.cli.dspx program-promote target-profile \
  --manifest /tmp/dspx-obsidian-pdf-transition-live.9QA9Nv/pdf-transition-program/manifest.json \
  --out /tmp/dspx-obsidian-pdf-transition-live.9QA9Nv/pdf-transition-program/target_profile.json \
  --json

uv run --package dspx-core -q python -m dspx.cli.dspx program-promote jury-requirements \
  --target-profile /tmp/dspx-obsidian-pdf-transition-live.9QA9Nv/pdf-transition-program/target_profile.json \
  --out /tmp/dspx-obsidian-pdf-transition-live.9QA9Nv/pdf-transition-program/jury_requirements.json \
  --json
```

Observed target/requirements sidecar summary:

```text
target_profile_schema=program-target-profile-v1
target_profile_status=derived_from_manifest
risk_ids=behavior_quality,authority_boundary,source_grounding,canonical_mutation_boundary,review_queue_boundary
profile_provider_called=false
jury_requirements_schema=program-jury-requirements-v1
required_perspectives=behavior_evidence,target_domain,authority_boundary,source_grounding,canonical_mutation_safety,review_surface,rollout_rollback
requirements_provider_called=false
activation_authority=false
```

The deterministic jury-panel sidecars were also dogfooded against the same candidate:

```bash
uv run --package dspx-core -q python -m dspx.cli.dspx program-promote jury-panel \
  --jury-requirements /tmp/dspx-obsidian-pdf-transition-live.9QA9Nv/pdf-transition-program/jury_requirements.json \
  --out /tmp/dspx-obsidian-pdf-transition-live.9QA9Nv/pdf-transition-program/meta_jury_selection.json \
  --json

uv run --package dspx-core -q python -m dspx.cli.dspx program-promote verify-jury-panel \
  --jury-selection /tmp/dspx-obsidian-pdf-transition-live.9QA9Nv/pdf-transition-program/meta_jury_selection.json \
  --out /tmp/dspx-obsidian-pdf-transition-live.9QA9Nv/pdf-transition-program/jury_verification.json \
  --json
```

Observed jury-panel summary:

```text
jury_selection_schema=program-meta-jury-selection-v1
jury_selection_status=selected
selected_count=7
missing_perspectives=
selection_provider_called=false
jury_verification_schema=program-jury-verification-v1
jury_verification_status=verified
approved_for_program_adjudicator_formation=true
failed_checks=
verification_provider_called=false
activation_authority=false
```

The deterministic program-adjudicator sidecars were also dogfooded against the same candidate:

```bash
uv run --package dspx-core -q python -m dspx.cli.dspx program-promote adjudicator-formation \
  --jury-verification /tmp/dspx-obsidian-pdf-transition-live.9QA9Nv/pdf-transition-program/jury_verification.json \
  --out /tmp/dspx-obsidian-pdf-transition-live.9QA9Nv/pdf-transition-program/program_adjudicator_formation.json \
  --json

uv run --package dspx-core -q python -m dspx.cli.dspx program-promote verify-program-adjudicator \
  --adjudicator-formation /tmp/dspx-obsidian-pdf-transition-live.9QA9Nv/pdf-transition-program/program_adjudicator_formation.json \
  --out /tmp/dspx-obsidian-pdf-transition-live.9QA9Nv/pdf-transition-program/program_adjudicator_verification.json \
  --json
```

Observed program-adjudicator summary:

```text
adjudicator_formation_schema=program-adjudicator-formation-v1
adjudicator_formation_status=formed
role_count=7
formation_provider_called=false
adjudicator_verification_schema=program-adjudicator-verification-v1
adjudicator_verification_status=verified
approved_for_program_evidence_adjudication=true
failed_checks=
verification_provider_called=false
activation_authority=false
```

The deterministic evidence adjudication and trace sidecars were also dogfooded against the same candidate:

```bash
uv run --package dspx-core -q python -m dspx.cli.dspx program-promote evidence-adjudication \
  --manifest /tmp/dspx-obsidian-pdf-transition-live.9QA9Nv/pdf-transition-program/manifest.json \
  --adjudicator-verification /tmp/dspx-obsidian-pdf-transition-live.9QA9Nv/pdf-transition-program/program_adjudicator_verification.json \
  --out /tmp/dspx-obsidian-pdf-transition-live.9QA9Nv/pdf-transition-program/program_evidence_adjudication.json \
  --json

uv run --package dspx-core -q python -m dspx.cli.dspx program-promote adjudication-behavior-trace \
  --evidence-adjudication /tmp/dspx-obsidian-pdf-transition-live.9QA9Nv/pdf-transition-program/program_evidence_adjudication.json \
  --out /tmp/dspx-obsidian-pdf-transition-live.9QA9Nv/pdf-transition-program/adjudication_behavior_trace.json \
  --json
```

Observed evidence-adjudication and trace summary:

```text
evidence_adjudication_schema=program-evidence-adjudication-v1
evidence_adjudication_status=evidence_adjudicated
ready_for_domain_decision=true
activation_approved=false
evidence_provider_called=false
trace_schema=program-adjudication-behavior-trace-v1
trace_status=trace_ready_for_publication_preflight
shared_oracle_write_performed=false
trace_activation_authority=false
```

The adjudication-trace publication preflight was dogfooded against the same candidate:

```bash
uv run --package dspx-core -q python -m dspx.cli.dspx oracle adjudication-trace publish-preflight \
  --trace /tmp/dspx-obsidian-pdf-transition-live.9QA9Nv/pdf-transition-program/adjudication_behavior_trace.json \
  --target shared-postgres \
  --publication-label adjudication_behavior_trace \
  --publisher-id pi-session \
  --publisher-role operator \
  --publisher-assertion 'share checked adjudication trace for future Oracle retrieval and GEPA analysis; no activation authority is granted' \
  --redaction-status checked \
  --retention-class retained_behavior_memory \
  --out /tmp/dspx-obsidian-pdf-transition-live.9QA9Nv/pdf-transition-program/adjudication_trace_publication_preflight.json \
  --json
```

Observed publication-preflight summary:

```text
trace_publication_preflight_schema=program-adjudication-trace-publication-preflight-v1
trace_publication_preflight_status=ready_not_published
publication_label=adjudication_behavior_trace
ready_for_shared_publication=true
blocking_reasons=
shared_oracle_mutated=false
activation_authority=false
database_url_present=false
```

A live publish attempt correctly failed closed in this shell because no shared Oracle backend env was present:

```text
publish_exit_code=2
Error: explicit adjudication trace publication requires a configured and available Postgres/pgvector Oracle backend: set DSPX_ORACLE_STORE=postgres_pgvector
receipt_written=false
```

The publish path itself is covered by tests using an injected fake shared Oracle store, proving one shared coordinate record and a local receipt without requiring secrets in the test environment.

## Validation

Focused checks passed:

```bash
uv run ruff check \
  packages/dspx-core/src/dspx/services/program_meta_adjudication.py \
  packages/dspx-core/src/dspx/services/program_adjudication_publication.py \
  packages/dspx-core/src/dspx/cli/commands/program_promote.py \
  packages/dspx-core/src/dspx/cli/commands/oracle.py \
  tests/test_program_meta_adjudication.py \
  tests/test_program_adjudication_publication.py

uv run pytest tests/test_program_meta_adjudication.py tests/test_program_candidate_state.py tests/test_program_adjudication_publication.py -q
uv run ty check packages/dspx-core/src/dspx/services/program_meta_adjudication.py packages/dspx-core/src/dspx/services/program_adjudication_publication.py tests/test_program_meta_adjudication.py tests/test_program_adjudication_publication.py
```

Observed:

```text
All checks passed!
32 passed
```

## Next phase

The next phase is a live configured publication run once the operator supplies a runtime shared-Oracle environment/secret reference, followed by GEPA example curation from published traces plus later domain outcomes.
