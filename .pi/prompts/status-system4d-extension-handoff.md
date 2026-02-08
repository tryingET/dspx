---
description: capture branch status and draft handoff for System4D extension smoke test
---
Create a ready-to-paste handoff prompt for a fresh session that tests the
System4D intake workflow + extension routing.

Optional focus/context: $@

Execution plan:
1. Read first:
   - `AGENTS.md`
   - `docs/SUBAGENT_WORKFLOW.md`
   - `docs/subagent-runs/schema/system4d-attrs.schema.json`
   - `.pi/extensions/README.md`
   - `.pi/extensions/4d-intake-router.ts`
   - `.pi/prompts/interview-4d-intake.md`
   - `.pi/prompts/subagent-4d-kickoff.md`
2. Inspect current repo state:
   - `git status --short --branch`
   - `git log --oneline -8`
3. Return concise summary + fenced section titled `New context window prompt`
   containing:
   - branch + cleanliness snapshot
   - last 2-3 relevant commits
   - uncommitted workflow files to test
   - startup commands:
     1) ensure interview tool available (if needed): `pi install npm:pi-interview`
     2) start pi with router extension: `pi --extension ./.pi/extensions/4d-intake-router.ts`
   - extension smoke-test checklist:
     1) paste freeform/handoff intent as first message
     2) verify editor prefill `/interview-4d-intake ...`
     3) run interview path (or fallback markdown intake)
     4) verify completed interview proposes `/subagent-4d-kickoff ...`
     5) verify cancel/timeout path proposes recovery `/interview-4d-intake ...`
     6) run debug commands `/s4d-router-status` and `/s4d-router-reset`
   - validation commands to rerun:
     - `pre-commit run --all-files`
     - `just monorepo-check`
     - `just test`
   - boundary reminder: allowed `apps/* -> core`; forbidden `core -> apps/*`
     and never import `dspx_forge.*` from core.

Constraints:
- no destructive git/file operations
- no commits unless asked
- keep output compact and copy-paste ready
