---
description: update NEXT_STEPS/PROJECT_STATUS and draft handoff prompt
---
Update `NEXT_STEPS.md` and `PROJECT_STATUS.md` for the current state of this branch.
Then provide a ready-to-paste prompt for a new context window.

Optional focus/context: $@

If the focus is System4D extension smoke testing, prefer using:
- `/status-system4d-extension-handoff`

Execution plan:
1. Read first:
   - `AGENTS.md`
   - `PROJECT_STATUS.md`
   - `NEXT_STEPS.md`
   - `docs/MONOREPO_TRANSITION.md`
   - `Justfile`
   - `pyproject.toml`
   - `apps/forge/README.md`
   - `packages/dspx-core/README.md`
2. Inspect current repo state:
   - `git status --short`
   - `git diff HEAD`
   - `git log --oneline -5`
3. Update `PROJECT_STATUS.md`:
   - what is completed now
   - current runtime/packaging behavior
   - latest validation snapshot
   - known gaps and immediate risks
4. Update `NEXT_STEPS.md`:
   - current top priorities in execution order
   - concrete next actions + acceptance criteria
   - keep boundary explicit (`apps/* -> core`; never reverse)
5. Run validation:
   - `pre-commit run --all-files`
   - `just monorepo-check`
   - `just test`
6. Return:
   - concise summary of what changed
   - exact files edited
   - a fenced section titled `New context window prompt` containing:
     - branch + cleanliness snapshot
     - completed work
     - highest-impact next step
     - validation commands to rerun
     - boundary reminder: no core import from `dspx_forge.*`

Constraints:
- no destructive git/file ops
- keep docs synchronized with actual repository behavior
- keep commits reviewable if committing is requested
