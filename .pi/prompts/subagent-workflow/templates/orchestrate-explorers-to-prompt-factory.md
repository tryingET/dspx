---
description: "Orchestrate parallel explorers -> technical writer synthesis -> master prompt factory."
---
Run this workflow for task context: $@

## Inputs required
- RUN_ID (e.g. `20260207-mlflow-observability-rfc`)
- TASK_BRIEF (1-3 paragraphs)
- optional DB_PATH (sqlite file)
- optional INTERVIEW_TOOL_AVAILABLE (`yes|no`)

## Stage 0 — scaffold + interview-first intake
1. copy `docs/subagent-runs/_TEMPLATE` to `docs/subagent-runs/<RUN_ID>/`
2. use canonical contract:
   - `docs/subagent-runs/schema/system4d-attrs.schema.json`
3. initialize `docs/subagent-runs/<RUN_ID>/run.manifest.json` (`run_id`, timestamps, stage status)
4. write task brief to:
   - `docs/subagent-runs/<RUN_ID>/00-intake/brief.md`
5. run interview intake:
   - preferred: use system prompt `.pi/prompts/subagent-workflow/system/interview-facilitator-4d.md`
   - preferred output files:
     - `docs/subagent-runs/<RUN_ID>/00-intake/interview-4d.questions.json`
     - `docs/subagent-runs/<RUN_ID>/00-intake/interview-4d.responses.md`
   - DB path behavior:
     - if not provided, auto-discover sqlite candidates (`fd`/`find`) and record decision
   - fallback: markdown Q/A if `interview` tool unavailable
   - if interview incomplete/cancelled: stop and output recovery rerun command
6. evaluate gate file:
   - `docs/subagent-runs/<RUN_ID>/00-intake/kickoff-gate-checklist.md`
   - proceed only when required attributes are non-empty

## Stage 1 — parallel explorers (write artifacts)
Launch 3 subagents in parallel:

- Codebase Explorer
  - system prompt: `.pi/prompts/subagent-workflow/system/codebase-explorer.md`
  - tools: `read,bash`
  - output: `docs/subagent-runs/<RUN_ID>/10-explorers/codebase.md`

- Documentation Explorer
  - system prompt: `.pi/prompts/subagent-workflow/system/docs-explorer.md`
  - tools: `read,bash`
  - output: `docs/subagent-runs/<RUN_ID>/10-explorers/docs.md`

- Database Explorer (SQLite)
  - system prompt: `.pi/prompts/subagent-workflow/system/db-explorer-sqlite.md`
  - tools: `read,bash`
  - output: `docs/subagent-runs/<RUN_ID>/10-explorers/database.md`
  - if DB_PATH missing: write blocker note + discovery plan

## Stage 2 — technical writer synthesis
- system prompt: `.pi/prompts/subagent-workflow/system/technical-writer-synthesis.md`
- output: `docs/subagent-runs/<RUN_ID>/20-synthesis/technical-writer.md`

## Stage 3 — master prompt factory
- system prompt: `.pi/prompts/subagent-workflow/system/master-prompt-factory.md`
- outputs:
  - `docs/subagent-runs/<RUN_ID>/30-prompt-factory/master-prompting.md`
  - `docs/subagent-runs/<RUN_ID>/30-prompt-factory/system-prompts/*.md`
  - `docs/subagent-runs/<RUN_ID>/30-prompt-factory/task-prompts/*.md`

## Stage 4 — handoff
Return:
- artifact index (all files created)
- unresolved blockers
- recommended domain architect execution order
