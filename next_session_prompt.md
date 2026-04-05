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
- Objective (one sentence): Close `AK-800` in AK, then claim and execute the next `TG25` ready slice unless the operator explicitly redirects the queue.
- Constraints (hard limits): Keep the completed `TG24` runtime-boundary hardening wave closed unless a surfaced regression or a smaller `TG25` prerequisite explicitly reopens one seam; preserve the `AK-797` trusted-program-root boundary; preserve the `AK-798` narrowed contract-expression boundary; preserve the `AK-799` required-by-default server-auth boundary; preserve the `AK-800` request body size limit boundary; preserve fail-closed SG2 boundary semantics.
- Assumptions (max 3): `AK-800` is in progress and the implementation is complete; the truthful repo-scoped ready queue will show the next `TG25` slice after `AK-800` is closed; `governance/work-items.json` remains a checked-in mirror rather than the live scheduler.
- Blockers (none or list): working-tree scope validation (`just task-scope-check`) is expected to fail in this shared worktree because many pre-existing unrelated tracked/untracked files fall outside the active slice scope; isolate or clean the worktree before expecting working-tree scope validation to pass cleanly.

## READ-FIRST ALLOWLIST (STARTUP BUDGET)
1. `AGENTS.md`
2. `docs/project/vision.md`
3. `docs/project/strategic_goals.md`
4. `docs/project/tactical_goals.md`
5. `docs/project/operational_goals.md`
6. `docs/project/developer_workflow.md`
7. `Justfile`
8. `diary/2026-04-05--add-request-body-size-limit-middleware.md`
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
- Slice executed: `AK-800` — added request body size limits middleware to the DSPx server that rejects requests whose `Content-Length` exceeds a configurable limit (default 10 MiB) before the body is read, with human-friendly size parsing (`DSPX_MAX_BODY_SIZE`), enabled-by-default fail-closed semantics, and 21 new regression tests.
- Outcome: DSPx server now rejects oversized request bodies with `413 Payload Too Large` and invalid `Content-Length` headers with `400 Bad Request`, matching the existing standardized JSON error contract; the stats counter now tracks `status_413`; server docs describe the new body size limit configuration; the checked-in AK projection reflects `AK-800` as in-progress.
- Files changed: `packages/dspx-core/src/dspx/server/security.py`, `packages/dspx-core/src/dspx/server/app.py`, `tests/test_server_body_size.py`, `tests/test_server_metrics.py`, `docs/SERVER.md`, `docs/project/operational_goals.md`, `governance/task-scopes/AK-800.snapshot.json`, `governance/work-items.json`, `diary/2026-04-05--add-request-body-size-limit-middleware.md`, `next_session_prompt.md`.
- Validation commands + results: `uvx ruff format` ✅; `uvx ruff check` ✅; `uvx ty check packages/dspx-core/src/dspx/server/security.py` ✅; `uv run --no-sync -m pytest -q tests/test_server_auth.py tests/test_server_api.py tests/test_server_confirm_mutations.py tests/test_server_global_app.py tests/test_server_metrics.py tests/test_server_metrics_negotiation.py tests/test_server_rate_limit.py tests/test_server_body_size.py` ✅ (55 passed); `./scripts/ci/smoke.sh` ✅; `./scripts/ak.sh work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅.
- Source-of-truth updates: recorded the `AK-800` implementation in `diary/2026-04-05--add-request-body-size-limit-middleware.md`, refreshed `docs/SERVER.md`, `docs/project/operational_goals.md`, and this handoff to point at the remaining truthful `TG25` queue, exported `governance/task-scopes/AK-800.snapshot.json`, and refreshed `governance/work-items.json`.
- Next-session starting point: close `AK-800` in AK and confirm the repo-scoped ready queue for the next `TG25` slice.

## END-OF-SESSION
Run `/commit` and ensure this file reflects the real checkpoint for the next operator/agent.
