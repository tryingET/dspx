---
summary: "Implementation evidence for Phase 1-2 of the DSPx meta-adjudication orchestration RFC: local non-authoritative planner, target profile, and jury requirements sidecars."
read_when:
  - "You are checking the shipped Phase 1-2 meta-adjudication planner sidecars."
  - "You need the command shape for `program-promote meta-adjudication-plan`, `target-profile`, or `jury-requirements`."
type: "evidence"
---

# 2026-05-09 Meta-adjudication planner implementation

## Result

Phase 1-2 from `docs/rfc/RFC-DSPX-ADJ-20260509-meta-adjudication-orchestration.md` are implemented as local, non-authoritative sidecars.

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

The first-class sidecar commands materialize the embedded target profile and jury requirements as standalone JSON artifacts so later phases can consume them without re-running the full planner.

## What it does not do

It does **not**:

- call a model/provider;
- select a model-backed jury;
- verify a jury;
- form or verify a program-specific adjudicator;
- publish to shared Oracle/Postgres;
- mutate AK/governance;
- activate, deploy, promote, rank, or select a winner.

## Implemented files

```text
packages/dspx-core/src/dspx/services/program_meta_adjudication.py
packages/dspx-core/src/dspx/cli/commands/program_promote.py
tests/test_program_meta_adjudication.py
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
missing_count=6
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

Observed sidecar summary:

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

## Validation

Focused checks passed:

```bash
uv run ruff check \
  packages/dspx-core/src/dspx/services/program_meta_adjudication.py \
  packages/dspx-core/src/dspx/cli/commands/program_promote.py \
  tests/test_program_meta_adjudication.py

uv run pytest tests/test_program_meta_adjudication.py -q
uv run ty check packages/dspx-core/src/dspx/services/program_meta_adjudication.py tests/test_program_meta_adjudication.py
```

Observed:

```text
All checks passed!
6 passed
```

## Next phase

The next implementation phase should add deterministic jury-panel selection and DSPx-adjudicator jury verification sidecars, still without model calls, shared Oracle writes, or activation authority.
