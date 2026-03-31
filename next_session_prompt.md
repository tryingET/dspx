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
- Objective (one sentence): Claim `AK-615` and audit DSPx's existing `Justfile` against the standardized contract control case.
- Constraints (hard limits): Keep the cleaned-up AK-native task-scope workflow/help contract intact; do not regress snapshot-first authority or reintroduce handoff-based task binding; keep `docs/project/operational_goals.md` and this file aligned.
- Assumptions (max 3): `AK-551` is complete and committed; `AK-615` is the remaining repo-scoped ready slice at `HEAD`; no new SG2 tactical goal has been materialized yet.
- Blockers (none or list): none.

## READ-FIRST ALLOWLIST (STARTUP BUDGET)
1. `AGENTS.md`
2. `docs/project/vision.md`
3. `docs/project/strategic_goals.md`
4. `docs/project/tactical_goals.md`
5. `docs/project/operational_goals.md`
6. `docs/project/developer_workflow.md`
7. `Justfile`
8. `diary/2026-03-31--add-regression-coverage-for-ak-native-task-scope-workflow.md`
9. `governance/task-scopes/AK-551.snapshot.json`

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
- Slice executed: `AK-551` — add regression coverage for the cleaned-up DSPx AK-native task-scope workflow.
- Outcome: broadened the regression surface around claim-based binding, explicit scope-artifact CLI paths, snapshot-over-legacy artifact preference, and real repo workflow-contract alignment so the snapshot-first authority story is covered end to end.
- Files changed: `diary/2026-03-31--add-regression-coverage-for-ak-native-task-scope-workflow.md`, `docs/project/operational_goals.md`, `docs/project/strategic_goals.md`, `docs/project/tactical_goals.md`, `governance/task-scopes/AK-551.snapshot.json`, `governance/work-items.json`, `next_session_prompt.md`, `tests/test_task_scope.py`, and `tests/test_workflow_contracts.py`.
- Validation commands + results: `uv run -m pytest -q tests/test_task_scope.py tests/test_workflow_contracts.py` ✅; `just task-scope-check task_id=551 mode=working-tree` ✅; `./scripts/ci/smoke.sh` ✅; `just verify-full` ✅; `ak task complete 551 --result '{...}'` ✅; `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅; `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅; `ak task ready -F json | jq 'map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx")) | map({id,title})'` ✅ after completion (`AK-615`).
- Source-of-truth updates: recorded the broader regression pass in `diary/2026-03-31--add-regression-coverage-for-ak-native-task-scope-workflow.md`; refreshed `docs/project/strategic_goals.md`, `docs/project/tactical_goals.md`, `docs/project/operational_goals.md`, and this handoff so SG3 is treated as complete and the next ready slice points at `AK-615`; exported `governance/task-scopes/AK-551.snapshot.json`; and refreshed `governance/work-items.json` after the AK completion/export.
- Next-session starting point: claim `AK-615` and audit DSPx's `Justfile` against the standardized contract control case unless operator direction changes.

## END-OF-SESSION
Run `/commit` and ensure this file reflects the real checkpoint for the next operator/agent.
