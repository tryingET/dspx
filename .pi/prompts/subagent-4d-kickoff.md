---
description: "Kick off interview-first System4D multi-subagent workflow (explorers -> synthesis -> prompt factory)."
---
Start a System4D workflow run with these attributes:

- `RUN_ID`: `$1`
- `TASK_TITLE`: `$2`
- `DRIVER`: `$3`
- `OUTCOME`: `$4`
- `CONSTRAINTS`: `$5`
- `BOUNDARY`: `$6`
- `EDGES_DEPENDENCIES`: `$7`
- `DB_PATH_OR_NONE`: `$8`
- `SUCCESS_CRITERIA`: `$9`
- `EXTRA_CONTEXT`: `${@:10}`

Execution instructions:
1. Create run scaffold from `docs/subagent-runs/_TEMPLATE/` into `docs/subagent-runs/$1/`.
2. Treat `docs/subagent-runs/schema/system4d-attrs.schema.json` as canonical attribute contract.
3. Write `run.manifest.json` and `00-intake/brief.md` using the attributes above.
4. Interview-first intake:
   - If `interview` tool available, run with `00-intake/interview-4d.questions.json` and save responses to `00-intake/interview-4d.responses.md`.
   - Else perform markdown Q/A fallback using the same 4 Dimensions fields.
   - If interview incomplete/cancelled: stop and emit recovery rerun command (no kickoff execution).
5. Evaluate gate checklist `00-intake/kickoff-gate-checklist.md` before proceeding.
6. Launch explorers in parallel:
   - Codebase explorer (cm-first) -> `10-explorers/codebase.md`
   - Docs explorer (qmd-first) -> `10-explorers/docs.md`
   - DB explorer (sqlite3, read-only, if DB path available) -> `10-explorers/database.md`
7. Run technical writer synthesis -> `20-synthesis/technical-writer.md`
8. Run master prompt factory -> `30-prompt-factory/*`
9. Return concise handoff:
   - files created/updated
   - unresolved blockers
   - recommended domain architect execution order

Method constraints:
- Use 4 Dimensions lens in every artifact:
  - Container: Boundary, Constraint, Edge, Dependency, Anti-Goal
  - Compass: Driver, Outcome, Trade-off
  - Engine: Trigger, State, Invariant, Lifecycle
  - Fog: Assumption, Risk, Exception, Debt
- Keep facts vs assumptions explicit.
- No architecture decisions before synthesis stage.
