---
summary: "Single-file session handoff to avoid stale status/next-steps docs."
read_when:
  - "At the start of every work session"
  - "When resuming after a pause"
---

# Next Session Prompt

## SESSION TRIGGER (AUTO-START)
Reading this file is authorization to begin immediately.
Do not ask for permission to start.

## ANTI-STALE RULES (HARD)
- Keep this file short and current.
- Keep only the active handoff window (not a history log).
- Move finished session narrative to `diary/`.
- Crystallize durable patterns in `docs/learnings/` and decisions in `docs/adr/` or `docs/decisions/`.
- Keep live execution truth in Agent Kernel; do not treat checked-in backlog mirrors as the live source of truth.
- Keep this file and `docs/project/operational_goals.md` DRY: point at the active slice, do not restate a second roadmap here.

## SOURCE-OF-TRUTH MAP
- Repo operating contract: `AGENTS.md`
- Mission and long-horizon direction: `docs/project/mission.md`, `docs/project/vision.md`
- Strategic/tactical direction: `docs/project/strategic_goals.md`, `docs/project/tactical_goals.md`
- Active operating slices: `docs/project/operational_goals.md`
- Durable architecture decisions: `docs/adr/`
- Live execution truth: `ak task list -F json | jq 'map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx"))'`
- Planned active/deferred work map: `governance/work-items.json` (legacy checked-in projection/mirror; do not treat as live execution truth)
- Raw session capture: `diary/`

## SESSION PREFLIGHT (FILL BEFORE EXECUTION)
- Objective (one sentence): Claim `AK-551` and add the broader regression coverage for DSPx's cleaned-up AK-native task-scope workflow now that `AK-550` removed workflow/handoff coupling to hand-authored manifests.
- Constraints (hard limits): Keep AK-authored task-scope snapshots authoritative for explicit scope; preserve brownfield legacy scope-file validation fallback; do not reintroduce `next_session_prompt.md` as task-binding input; keep `docs/project/operational_goals.md` and this file aligned.
- Assumptions (max 3): `AK-550` is complete and committed; `AK-551` is ready as the selected next FCOS follow-on while `AK-615` remains non-selected; the snapshot-first workflow/help contract landed in the current branch `HEAD`.
- Blockers (none or list): none.

## READ-FIRST ALLOWLIST (STARTUP BUDGET)
1. `AGENTS.md`
2. `docs/project/vision.md`
3. `docs/project/strategic_goals.md`
4. `docs/project/tactical_goals.md`
5. `docs/project/operational_goals.md`
6. `docs/project/developer_workflow.md`
7. `diary/2026-03-31--remove-task-scope-manifest-coupling-from-workflow-and-handoff.md`
8. `diary/2026-03-31--migrate-task-scope-validation-to-ak-native-scope-snapshots.md`
9. `governance/task-scopes/AK-550.snapshot.json`

## EXECUTION MODE (ONE SESSION = ONE SLICE)
1. Choose one highest-leverage actionable slice from `governance/work-items.json` unless operator direction overrides it. In this repo, treat that file as a checked-in projection and confirm the live slice against AK before acting.
2. Confirm the ready queue with `ak task ready -F json | jq 'map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx"))'`.
3. If the repo-scoped ready queue is empty, do not start a new implementation slice; wait for operator direction or the next truthful post-`TG23` contract/materialization step.
4. If a repo-scoped ready task exists, claim the current active task before editing docs or code.
5. Implement at most one operating slice end-to-end.
6. Validate the slice with:
   - `./scripts/ci/smoke.sh`
   - `just verify-full`
7. Update source-of-truth docs/diary/ADR references before commit.

## SESSION CHECKPOINT (UPDATE BEFORE /commit)
- Slice executed: `AK-550` — remove residual workflow and handoff coupling to hand-authored task-scope manifests.
- Outcome: removed the committed `next_session_prompt.md` checkpoint fallback from task-scope binding, refreshed workflow/help/docs/contracts so AK snapshots are the authoritative operator story, kept brownfield legacy scope files as validation-only fallback, and exported `governance/task-scopes/AK-550.snapshot.json`.
- Files changed: `Justfile`, `README.md`, `diary/2026-03-31--remove-task-scope-manifest-coupling-from-workflow-and-handoff.md`, `docs/project/developer_workflow.md`, `docs/project/operational_goals.md`, `docs/project/strategic_goals.md`, `docs/project/tactical_goals.md`, `governance/task-scopes/AK-550.snapshot.json`, `governance/work-items.json`, `next_session_prompt.md`, `packages/dspx-core/src/dspx/task_scope.py`, `scripts/check_task_scope.py`, `scripts/check_workflow_contracts.py`, `tests/test_task_scope.py`, and `tests/test_workflow_contracts.py`.
- Validation commands + results: `uv run -m pytest -q tests/test_task_scope.py tests/test_workflow_contracts.py` ✅; `just task-scope-check task_id=550 mode=working-tree` ✅; `./scripts/ci/smoke.sh` ✅; `just verify-full` ✅; `ak task complete 550 --result '{...}'` ✅; `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅; `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅; `ak task ready -F json | jq 'map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx")) | map({id,title})'` ✅ after completion (`AK-551`, `AK-615`).
- Source-of-truth updates: recorded the cleanup in `diary/2026-03-31--remove-task-scope-manifest-coupling-from-workflow-and-handoff.md`; refreshed `Justfile`, `README.md`, `docs/project/developer_workflow.md`, `docs/project/strategic_goals.md`, `docs/project/tactical_goals.md`, `docs/project/operational_goals.md`, and this handoff so workflow/handoff binding now depends only on explicit task IDs, AK claims, or changed task-scope artifacts; exported `governance/task-scopes/AK-550.snapshot.json`; and refreshed `governance/work-items.json` after the AK completion/export.
- Next-session starting point: claim `AK-551`, add the broader regression coverage for the cleaned-up AK-native task-scope workflow, and keep `AK-615` non-selected unless operator direction changes.

## END-OF-SESSION
Run `/commit` and ensure this file reflects the real checkpoint for the next operator/agent.
