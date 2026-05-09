---
summary: "Implementation evidence for Phase 1 of the DSPx meta-adjudication orchestration RFC: a local non-authoritative planner sidecar."
read_when:
  - "You are checking the shipped Phase 1 meta-adjudication planner."
  - "You need the command shape for `program-promote meta-adjudication-plan`."
type: "evidence"
---

# 2026-05-09 Meta-adjudication planner implementation

## Result

Phase 1 from `docs/rfc/RFC-DSPX-ADJ-20260509-meta-adjudication-orchestration.md` is implemented as a local, non-authoritative planning sidecar.

Command:

```bash
dspx program-promote meta-adjudication-plan \
  --manifest <candidate>/manifest.json \
  --out <candidate>/program_meta_adjudication_plan.json \
  --json
```

The command writes:

```text
schema_version=program-meta-adjudication-plan-v1
status=planned_not_executed
lifecycle_state=meta_adjudication_plan_ready
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

Observed summary:

```text
schema_version=program-meta-adjudication-plan-v1
status=planned_not_executed
risk_ids=behavior_quality,authority_boundary,source_grounding,canonical_mutation_boundary,review_queue_boundary
missing_count=6
provider_called=false
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
```

Observed:

```text
All checks passed!
4 passed
```

## Next phase

The next implementation phase should build deterministic `program-target-profile-v1` and `program-jury-requirements-v1` sidecars as first-class files, then dogfood them on the Obsidian/PDF transition candidate before introducing any model-backed juror/adjudicator proposal behavior.
