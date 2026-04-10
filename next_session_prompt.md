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
- Live execution truth: `./scripts/ak.sh task ready -F json | jq 'map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx"))'`
- Planned active/deferred work map: `governance/work-items.json` (checked-in projection/mirror; do not treat as live execution truth)
- Latest completed-slice diary: `diary/2026-04-05--land-ak835-tg25-atomic-hardening-cleanup.md`
- Latest direction refresh artifact: `docs/project/program-synthesis-boundary.md`
- Latest repo-local learning: `docs/learnings/2026-02-28-receipt-v2-phase-c.md`

## SESSION PREFLIGHT (FILL BEFORE EXECUTION)
- Objective (one sentence): Confirm the repo-scoped ready queue is still empty after the runtime-spine direction refresh and only materialize the next bounded governance slice when AK truth explicitly names it.
- Constraints (hard limits): Keep the completed `AK-797`, `AK-798`, `AK-799`, `AK-800`, `AK-834`, `AK-835`, and `AK-1085` boundaries closed; do not widen governance authority or reopen the runtime-spine slice as a generic cleanup queue.
- Assumptions (max 3): the first runtime spine now exists inside `dspx.synthesis`; `governance/work-items.json` remains a checked-in mirror; the later human-governed review-eligibility / promotion-eligibility contract should stay deferred until AK explicitly materializes it.
- Blockers (none or list): none.

## READ-FIRST ALLOWLIST (STARTUP BUDGET)
1. `AGENTS.md`
2. `docs/project/vision.md`
3. `docs/project/strategic_goals.md`
4. `docs/project/tactical_goals.md`
5. `docs/project/operational_goals.md`
6. `docs/ARCHITECTURE.md`
7. `docs/project/program-synthesis-boundary.md`
8. `docs/project/developer_workflow.md`
9. `governance/work-items.json`
10. `governance/task-scopes/AK-1093.snapshot.json`

## EXECUTION MODE (ONE SESSION = ONE SLICE)
1. Choose one highest-leverage actionable slice from `governance/work-items.json` unless operator direction overrides it. In this repo, treat that file as a checked-in projection and confirm the live slice against AK before acting.
2. Confirm the repo-scoped ready queue with `./scripts/ak.sh task ready --repo /home/tryinget/ai-society/softwareco/owned/dspx -F json --json-contract normalized | jq '.tasks | map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx"))'`.
3. If the ready queue is empty, do not guess a hidden governance backlog; only materialize the next slice when AK truth and the direction stack justify it.
4. Execute at most one operating slice end-to-end.
5. Validate truthfully with:
   - `./scripts/ci/smoke.sh`
   - `just task-scope-check task_id=<AK-ID> mode=working-tree`
   - `just verify-full`
6. Refresh source-of-truth docs/diary/ADR references before commit.

## SESSION CHECKPOINT (UPDATE BEFORE /commit)
- Slice executed: `AK-1093` — refreshed the SG2/TG25 direction stack from the stash into runtime-spine language, added the behavior-first boundary doc, and kept the later governance slice deferred while the ready queue stayed empty.
- Outcome: `AK-1093` is complete in AK, the direction stack now matches the runtime-spine wave backed by `AK-1085`, the repo-scoped ready queue is empty again, and the later human-governed governance contract remains deferred until AK truth explicitly names it.
- Files changed: `docs/project/vision.md`, `docs/project/strategic_goals.md`, `docs/project/tactical_goals.md`, `docs/project/operational_goals.md`, `docs/ARCHITECTURE.md`, `docs/project/program-synthesis-boundary.md`, `governance/task-scopes/AK-1093.snapshot.json`, `governance/work-items.json`, `next_session_prompt.md`.
- Validation commands + results: `./scripts/ak.sh task ready --repo /home/tryinget/ai-society/softwareco/owned/dspx -F json --json-contract normalized | jq '.tasks | map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx"))'` ✅ (`[]`); `./scripts/ak.sh work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅; `./scripts/ci/smoke.sh` ✅; `just task-scope-check task_id=1093 mode=working-tree` ✅; `just verify-full` ✅.
- Source-of-truth updates: completed `AK-1093` in AK with result evidence, exported `governance/task-scopes/AK-1093.snapshot.json`, re-exported `governance/work-items.json`, refreshed `docs/project/vision.md`, `docs/project/strategic_goals.md`, `docs/project/tactical_goals.md`, `docs/project/operational_goals.md`, and `docs/ARCHITECTURE.md`, materialized `docs/project/program-synthesis-boundary.md`, and replaced the handoff with the post-direction-refresh idle starting point.
- Next-session starting point: confirm the repo-scoped ready queue is still empty, and only materialize the deferred governance contract when AK truth or explicit operator direction names the next bounded slice.

## END-OF-SESSION
Run `/commit` only if the repo is validation-clean and the handoff reflects the real checkpoint; otherwise preserve the truthful handoff and leave commit/closeout for the isolated slice.
