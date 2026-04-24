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
- Live execution truth: `ak task ready --repo /home/tryinget/ai-society/softwareco/owned/dspx -F json --json-contract normalized | jq '.tasks | map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx"))'`
- Planned active/deferred work map: `governance/work-items.json` (checked-in projection/mirror; do not treat as live execution truth)
- Latest completed-slice diary: `diary/2026-04-10--freeze-human-review-decision-contract.md`
- Latest contract artifact: `docs/adr/20260410-human-governed-review-decision-contract-v1.md`
- Latest repo-local learning: `docs/learnings/2026-02-28-receipt-v2-phase-c.md`

## SESSION PREFLIGHT (FILL BEFORE EXECUTION)
- Objective (one sentence): Re-run the repo-scoped AK ready queue after `AK-1106`; if it is empty, wait for the next operator-directed or direction-to-execution materialization step before starting new implementation work.
- Constraints (hard limits): Keep the completed `AK-593`, `AK-797`, `AK-798`, `AK-799`, `AK-800`, `AK-834`, `AK-835`, `AK-1047`, `AK-1085`, `AK-1093`, `AK-1094`, `AK-1101`, `AK-1102`, `AK-1105`, and `AK-1106` boundaries closed; keep any follow-on bounded to the `human_review_decisions` contract surface from `docs/adr/20260410-human-governed-review-decision-contract-v1.md`; do not widen live ranking, pruning, promotion, or policy-activation authority.
- Assumptions (max 3): `AK-1106` is complete and committed; no next repo-scoped implementation slice is pinned yet; the repo-scoped ready queue may truthfully be empty.
- Blockers (none or list): none.

## READ-FIRST ALLOWLIST (STARTUP BUDGET)
1. `AGENTS.md`
2. `docs/project/vision.md`
3. `docs/project/strategic_goals.md`
4. `docs/project/tactical_goals.md`
5. `docs/project/operational_goals.md`
6. `docs/adr/README.md`
7. `docs/adr/20260410-human-governed-review-decision-contract-v1.md`
8. `docs/project/program-synthesis-boundary.md`
9. `docs/project/developer_workflow.md`
10. `governance/work-items.json`

## EXECUTION MODE (ONE SESSION = ONE SLICE)
1. Choose one highest-leverage actionable slice from `governance/work-items.json` unless operator direction overrides it. In this repo, treat that file as a checked-in projection and confirm the live slice against AK before acting.
2. Confirm the repo-scoped ready queue with `ak task ready --repo /home/tryinget/ai-society/softwareco/owned/dspx -F json --json-contract normalized | jq '.tasks | map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx"))'`.
3. If the ready queue is empty, do not guess a hidden governance backlog; wait for operator direction or the next explicit direction-to-execution materialization step.
4. If a repo-scoped ready task exists, claim the current active task before editing docs or code.
5. Execute at most one operating slice end-to-end.
6. Validate truthfully with:
   - `./scripts/ci/smoke.sh`
   - `just task-scope-check task_id=<AK-ID> mode=working-tree`
   - `just verify-full`
7. Refresh source-of-truth docs/diary/ADR references before commit.

## SESSION CHECKPOINT (UPDATE BEFORE /commit)
- Slice executed: `AK-1106` — froze the first human-governed review-decision contract for nominated governance-only policy variants, closed `TG28`, and refreshed the bounded handoff/projection stack without guessing the post-contract implementation slice.
- Outcome: `docs/adr/20260410-human-governed-review-decision-contract-v1.md` is now the bounded review-decision contract, `AK-1106` is complete in AK, and the repo-scoped ready queue is now empty instead of being backfilled with a speculative follow-on task.
- Files changed: `diary/2026-04-10--freeze-human-review-decision-contract.md`, `docs/adr/20260410-human-governed-review-decision-contract-v1.md`, `docs/adr/README.md`, `docs/project/operational_goals.md`, `docs/project/tactical_goals.md`, `governance/task-scopes/AK-1106.snapshot.json`, `governance/work-items.json`, `next_session_prompt.md`.
- Validation commands + results: `ak task ready --repo /home/tryinget/ai-society/softwareco/owned/dspx -F json --json-contract normalized | jq '.tasks | map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx"))'` ✅ before completion (`AK-1106` only); `./scripts/ci/smoke.sh` ✅; `just task-scope-check task_id=1106 mode=working-tree` ✅; `just verify-full` ✅; `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅; `ak task scope export 1106 > governance/task-scopes/AK-1106.snapshot.json` ✅; `ak task ready --repo /home/tryinget/ai-society/softwareco/owned/dspx -F json --json-contract normalized | jq '.tasks | map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx"))'` ✅ after completion (`[]`).
- Source-of-truth updates: completed `AK-1106` in AK with result evidence, added the new ADR + diary entry, refreshed `docs/project/tactical_goals.md` and `docs/project/operational_goals.md`, re-exported `governance/work-items.json`, exported `governance/task-scopes/AK-1106.snapshot.json`, and replaced the handoff with the post-contract idle-state checkpoint.
- Next-session starting point: re-run the repo-scoped ready queue; if it is still empty, do not guess the post-`TG28` governance step.

## END-OF-SESSION
Run `/commit` only if the repo is validation-clean and the handoff reflects the real checkpoint; otherwise preserve the truthful handoff and leave commit/closeout for the isolated slice.
