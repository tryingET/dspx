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
- Objective (one sentence): Confirm the repo-scoped ready queue, then either wait in the truthful empty-ready-queue `TG25` state or execute the one highest-leverage ready slice the operator names.
- Constraints (hard limits): Keep the completed `TG24` runtime-boundary hardening wave closed unless a surfaced regression or a smaller `TG25` prerequisite explicitly reopens one seam; preserve fail-closed SG2 boundary semantics; do not invent a `TG25` slice just to keep the queue non-empty.
- Assumptions (max 3): `AK-734` is closed in AK and reflected in the checked-in projection; no repo-scoped task is currently ready; `governance/work-items.json` remains a checked-in mirror rather than the live scheduler.
- Blockers (none or list): none.

## READ-FIRST ALLOWLIST (STARTUP BUDGET)
1. `AGENTS.md`
2. `docs/project/vision.md`
3. `docs/project/strategic_goals.md`
4. `docs/project/tactical_goals.md`
5. `docs/project/operational_goals.md`
6. `docs/project/developer_workflow.md`
7. `Justfile`
8. `diary/2026-04-04--surface-mlflow-tag-contract-drift-and-revalidate-task-scope-contract.md`
9. `governance/work-items.json`

## EXECUTION MODE (ONE SESSION = ONE SLICE)
1. Choose one highest-leverage actionable slice from `governance/work-items.json` unless operator direction overrides it. In this repo, treat that file as a checked-in projection and confirm the live slice against AK before acting.
2. Confirm the ready queue with `./scripts/ak.sh task ready -F json | jq 'map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx"))'`.
3. If the repo-scoped ready queue is empty, stay in the truthful idle `TG25` waiting state unless the operator explicitly redirects the session.
4. If a repo-scoped ready task exists, claim the current active task before editing docs or code.
5. Implement at most one operating slice end-to-end.
6. Validate the slice with:
   - `./scripts/ci/smoke.sh`
   - `just verify-full`
7. Update source-of-truth docs/diary/ADR references before commit.

## SESSION CHECKPOINT (UPDATE BEFORE /commit)
- Slice executed: `AK-734` — surface MLflow tag-contract drift reason codes, reconfirm the assignment-style task-scope invocation contract, and then close the slice after repairing the live AK authority blocker.
- Outcome: DSPx now emits `mlflow_tag_contract_violation` whenever contradictory MLflow correlation tags are dropped during local or remote explain candidate selection, keeps partial/nested historical MLflow matches accepted without false positives, preserved the existing task-scope invocation contract without unnecessary doc churn, and is back to the truthful empty-ready-queue `TG25` waiting state after AK repair + task completion.
- Files changed: `docs/project/operational_goals.md`, `governance/task-scopes/AK-734.snapshot.json`, `governance/work-items.json`, `next_session_prompt.md`, `packages/dspx-core/src/dspx/services/run_explain_service.py`, `tests/test_run_receipts.py`, and `diary/2026-04-04--surface-mlflow-tag-contract-drift-and-revalidate-task-scope-contract.md`.
- Validation commands + results: `uv run --no-sync -m pytest -q tests/test_run_receipts.py` ✅; `uvx ruff check packages/dspx-core/src/dspx/services/run_explain_service.py tests/test_run_receipts.py` ✅; `uvx ty check packages/dspx-core/src/dspx/services/run_explain_service.py` ✅; `just task-scope-check task_id=734 mode=working-tree` ✅ (repo-default snapshot skip, assignment-style contract reconfirmed); `./scripts/ci/smoke.sh` ✅; `just verify-full` ✅; `./scripts/ak.sh work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅; `./scripts/ak.sh work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅; `./scripts/ak.sh task ready -F json | jq 'map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx")) | map({id,title})'` ✅ after implementation (`[]`); post-repair reconfirmation: `./scripts/ak.sh task show 734 -F json` ✅ (`status=done`), `./scripts/ak.sh task ready --repo /home/tryinget/ai-society/softwareco/owned/dspx -F json` ✅ (`[]`).
- Source-of-truth updates: recorded the `AK-734` implementation + closure in `diary/2026-04-04--surface-mlflow-tag-contract-drift-and-revalidate-task-scope-contract.md`, refreshed `docs/project/operational_goals.md` and this handoff back to the idle `TG25` checkpoint, kept `governance/task-scopes/AK-734.snapshot.json` as the frozen slice export, and refreshed `governance/work-items.json` after AK completion.
- Next-session starting point: confirm the repo-scoped ready queue; if it is still empty, stay in the truthful idle `TG25` waiting state until the operator or AK names the next slice.

## END-OF-SESSION
Run `/commit` and ensure this file reflects the real checkpoint for the next operator/agent.
