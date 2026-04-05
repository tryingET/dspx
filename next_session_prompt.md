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
- Objective (one sentence): Claim `AK-798`, then execute one remaining `TG25` security slice unless the operator explicitly redirects the queue.
- Constraints (hard limits): Keep the completed `TG24` runtime-boundary hardening wave closed unless a surfaced regression or a smaller `TG25` prerequisite explicitly reopens one seam; preserve the new `AK-797` trusted-program-root boundary; preserve fail-closed SG2 boundary semantics.
- Assumptions (max 3): `AK-797` is closed in AK and reflected in the checked-in projection; the truthful repo-scoped ready queue now begins with `AK-798`/`AK-799`/`AK-800`; `governance/work-items.json` remains a checked-in mirror rather than the live scheduler.
- Blockers (none or list): `just verify-full` is currently blocked by an unrelated `tests/test_task_scope.py` baseline where the global `ak` CLI rejects unregistered temp repos during claimed-task discovery.

## READ-FIRST ALLOWLIST (STARTUP BUDGET)
1. `AGENTS.md`
2. `docs/project/vision.md`
3. `docs/project/strategic_goals.md`
4. `docs/project/tactical_goals.md`
5. `docs/project/operational_goals.md`
6. `docs/project/developer_workflow.md`
7. `Justfile`
8. `diary/2026-04-05--confine-optimize-service-imports-to-trusted-program-roots.md`
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
- Slice executed: `AK-797` — confine `optimize_service._import_program_module()` to trusted program roots.
- Outcome: DSPx now rejects optimize program imports that escape the current working directory, system temp root, and any explicit `DSPX_TRUSTED_PROGRAM_ROOTS` allowlist; direct import regressions cover both rejection and env-based allowlisting; the checked-in AK projection now truthfully shows `AK-798`/`AK-799`/`AK-800` as the remaining ready queue.
- Files changed: `docs/project/operational_goals.md`, `governance/task-scopes/AK-797.snapshot.json`, `governance/work-items.json`, `next_session_prompt.md`, `packages/dspx-core/src/dspx/services/optimize_service.py`, `tests/test_optimize_gepa_stub.py`, and `diary/2026-04-05--confine-optimize-service-imports-to-trusted-program-roots.md`.
- Validation commands + results: `uv run --no-sync -m pytest -q tests/test_optimize_gepa_stub.py` ✅; `uv run --no-sync -m pytest -q tests/test_provider_v4.py -k optimize_manifest_includes_provider_runtime_metadata` ✅; `uvx ruff check packages/dspx-core/src/dspx/services/optimize_service.py tests/test_optimize_gepa_stub.py` ✅; `uvx ty check packages/dspx-core/src/dspx/services/optimize_service.py` ✅; `just task-scope-check task_id=797 mode=working-tree` ✅; `./scripts/ci/smoke.sh` ✅; `just verify-full` ⚠️ fails in the pre-existing `tests/test_task_scope.py` baseline because the global `ak` CLI now rejects unregistered temp repos during claimed-task discovery (unrelated to `AK-797`); `./scripts/ak.sh work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅; `./scripts/ak.sh work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅; `./scripts/ak.sh task show 797 -F json` ✅ (`status=done`); `./scripts/ak.sh task ready --repo /home/tryinget/ai-society/softwareco/owned/dspx -F json` ✅ (`[798,799,800]`).
- Source-of-truth updates: recorded the `AK-797` implementation + closure in `diary/2026-04-05--confine-optimize-service-imports-to-trusted-program-roots.md`, refreshed `docs/project/operational_goals.md` and this handoff to point at the remaining truthful `TG25` queue, kept `governance/task-scopes/AK-797.snapshot.json` as the frozen slice export, and refreshed `governance/work-items.json` after AK completion.
- Next-session starting point: confirm the repo-scoped ready queue and, absent operator override, claim `AK-798` next.

## END-OF-SESSION
Run `/commit` and ensure this file reflects the real checkpoint for the next operator/agent.
