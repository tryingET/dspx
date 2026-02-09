---
summary: "Reusable multi-subagent workflow: parallel explorers -> technical writer synthesis -> prompt-factory -> domain architect execution."
read_when:
  - "You want repeatable multi-agent discovery and architecture drafting with artifact traceability."
  - "You need explorer/writer/architect separation with explicit boundaries and escalation rules."
---

# Subagent Workflow (DSPx)

## Why this is useful here

Yes, this makes sense for this repo.

Benefits:
- avoids one-agent tunnel vision
- separates evidence gathering from design decisions
- creates durable artifacts in `docs/subagent-runs/`
- improves prompt reuse and consistency across RFC cycles
- supports dissent tracking and explicit human escalation

## Tool mapping by explorer role

- Codebase Explorer: `cm` + targeted file reads
- Documentation Explorer: `qmd` (not `qmb` in this environment)
- Database Explorer: `sqlite3` (read-only by default)

## Stage model

### Stage 0 — Interview-first intake + container setup
Inputs:
- task brief
- boundaries/constraints
- optional DB path(s) (auto-discover if missing)

Canonical intake rules:
- `RUN_ID` from command is authoritative for artifact pathing; if additional run IDs appear in handoff text, record as related IDs (do not silently switch).
- `DB_PATH_OR_NONE` means Stage-1 DB explorer input path (read-only), not interview answer storage.
- if command DB path is explicit (not `none`), keep it canonical; interview DB answers can annotate mismatch but must not silently override.
- hard guard: if explicit DB path is missing locally, propose DB-clarification recovery command first; do not propose kickoff until resolved.

Preferred flow:
1. run `pi-interview` with `00-intake/interview-4d.questions.json`
2. capture responses in `00-intake/interview-4d.responses.md`
3. normalize into `00-intake/brief.md`

Fallback flow:
- if `interview` tool unavailable, run markdown Q/A using same 4D schema

Recovery rule:
- if interview is incomplete/cancelled, stop before kickoff proposal and emit a session-recovery rerun command.

Outputs:
- `docs/subagent-runs/<RUN_ID>/run.manifest.json`
- `docs/subagent-runs/<RUN_ID>/00-intake/interview-4d.questions.json`
- `docs/subagent-runs/<RUN_ID>/00-intake/interview-4d.responses.md`
- `docs/subagent-runs/<RUN_ID>/00-intake/brief.md`
- `docs/subagent-runs/<RUN_ID>/00-intake/kickoff-gate-checklist.md`

### Stage 1 — Parallel exploration
Outputs:
- `10-explorers/codebase.md`
- `10-explorers/docs.md`
- `10-explorers/database.md`

Each explorer reports using the 4 Dimensions lens.

### Stage 2 — Technical writer synthesis
Output:
- `20-synthesis/technical-writer.md`

Required synthesis:
1. Needs + Requirements
2. Domain Ontology Summary
3. Capabilities (existing + missing)
4. Contradictions and confidence deltas

### Stage 3 — Master prompt factory
Output:
- `30-prompt-factory/master-prompting.md`
- `30-prompt-factory/system-prompts/*.md`
- `30-prompt-factory/task-prompts/*.md`

Purpose:
- generate domain-architect prompts from synthesis artifacts
- embed boundaries, constraints, invariants, risks

### Stage 4 — Domain architect drafting
Outputs go to:
- `40-domain-drafts/*.md`

Then proceed through consensus/implementation/QA/release/operations folders.

## Canonical schema + gate

- Attribute schema source of truth:
  - `docs/subagent-runs/schema/system4d-attrs.schema.json`
- Kickoff proposal gate:
  - `00-intake/kickoff-gate-checklist.md`
- Rule: do not propose `/subagent-4d-kickoff ...` until gate passes.

## 4 Dimensions integration (required in every stage artifact)

### 1) Container (Structure & Scope)
- Boundary
- Constraint
- Edge
- Dependency
- Anti-Goal

### 2) Compass (Purpose & Value)
- Driver
- Outcome
- Trade-off

### 3) Engine (Dynamics & Behavior)
- Trigger
- State
- Invariant
- Lifecycle

### 4) Fog (Uncertainty & Risk)
- Assumption
- Risk
- Exception
- Debt

## Escalation rule

If domain architects cannot converge after one refinement loop:
- freeze dissent in writing
- escalate to human owner with options + trade-offs

## Prompt assets

Use prompt templates in:
- `.pi/prompts/subagent-workflow/system/`
- `.pi/prompts/subagent-workflow/templates/`
- `.pi/prompts/subagent-4d-kickoff.md` (slash command: `/subagent-4d-kickoff`)
- `.pi/prompts/interview-4d-intake.md` (slash command: `/interview-4d-intake`)

## Optional extension automation

- `.pi/extensions/4d-intake-router.ts`
  - first non-command user message (pass-through mode) -> message still goes to Pi, while extension parses structured intake fields (`RUN_ID`, `TASK_TITLE`, `DB_PATH_OR_NONE`, `EXTRA_CONTEXT`) and prefills `/interview-4d-intake ...`
  - if structured fields are missing, fallback heuristics derive task/run/db inputs
  - completed interview + gate pass -> editor prefill for `/subagent-4d-kickoff ...`
  - incomplete interview or gate fail -> editor prefill for recovery rerun command
  - debug commands: `/s4d-router-status`, `/s4d-router-reset`
