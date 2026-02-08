---
summary: "Artifact layout for multi-subagent runs (exploration -> synthesis -> prompt factory -> drafting -> delivery)."
read_when:
  - "You are starting a new subagent workflow run and need output locations."
  - "You need traceable artifacts for explorer/synthesis/prompt-factory/domain drafts."
---

# Subagent run artifact layout

Run path:
- `docs/subagent-runs/<RUN_ID>/`

Recommended `RUN_ID` format:
- `<YYYYMMDD>-<slug>`
- example: `20260207-mlflow-observability-rfc`

## Directory contract

- `run.manifest.json`
  - workflow version, stage status, canonical attributes, gate state
- `00-intake/`
  - task brief, constraints, scope
  - interview-first artifacts (`interview-4d.questions.json`, `interview-4d.responses.md`)
  - kickoff gate checklist (`kickoff-gate-checklist.md`)
- `10-explorers/`
  - codebase/docs/database explorer outputs
- `20-synthesis/`
  - technical writer synthesis
- `30-prompt-factory/`
  - master prompting output + generated prompts
- `40-domain-drafts/`
  - architect drafts
- `50-consensus/`
  - dissent + resolution logs
- `60-implementation/`
  - plan, task contracts, evidence
- `70-qa/`
  - verification report
- `80-release/`
  - promotion checklist and release notes
- `90-operations/`
  - telemetry/debt/governance follow-through

## Canonical attribute schema

- `docs/subagent-runs/schema/system4d-attrs.schema.json`

Use this schema for command argument generation and gate checks.

## Template

Copy from:
- `docs/subagent-runs/_TEMPLATE/`

Or scaffold with:
- `scripts/new_subagent_run.sh <slug>`

Then fill in stage artifacts during execution.
