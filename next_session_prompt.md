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
- Objective (one sentence): Re-run the repo-scoped ready queue after `AK-600`; if it is still empty, do not start a new implementation slice until the next truthful post-`TG23` contract/materialization step is created.
- Constraints (hard limits): Do not widen authority beyond the governance-only receipt boundary frozen in `docs/adr/20260330-synthesis-evidence-governed-policy-evaluation-contract-v1.md`; keep live execution truth in AK; keep `docs/project/operational_goals.md` and this file aligned.
- Assumptions (max 3): `AK-593` and `AK-600` are complete and committed; `TG23` is complete and no next SG2 implementation slice is pinned yet; SG3 `AK-549`–`AK-551` remain blocked on cross-repo `AK-548` and are not the active wave.
- Blockers (none or list): none.

## READ-FIRST ALLOWLIST (STARTUP BUDGET)
1. `AGENTS.md`
2. `docs/project/vision.md`
3. `docs/project/strategic_goals.md`
4. `docs/project/tactical_goals.md`
5. `docs/project/operational_goals.md`
6. `docs/adr/20260330-synthesis-evidence-governed-policy-evaluation-contract-v1.md`
7. `diary/2026-03-30--reconfirm-post-ak-593-empty-ready-queue-and-refresh-handoff-at-current-head.md`
8. `diary/2026-03-30--emit-governed-policy-evaluation-receipts.md`

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
- Slice executed: `AK-600` — reconfirm post-`AK-593` empty ready queue and refresh the idle-state handoff at current `HEAD`.
- Outcome: created an operator-directed workflow-guardrail slice, confirmed the repo-scoped `ak task ready` filter still returned `[]` before and after the slice, refreshed the operating-plan/handoff checkpoint at current `HEAD`, and avoided starting an unpinned SG2 implementation slice.
- Files changed: `diary/2026-03-30--reconfirm-post-ak-593-empty-ready-queue-and-refresh-handoff-at-current-head.md`, `docs/project/operational_goals.md`, `governance/task-scopes/AK-600.json`, `governance/work-items.json`, and `next_session_prompt.md`.
- Validation commands + results: `ak task ready -F json | jq 'map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx"))'` ✅ before `AK-600` (`[]`); `just task-scope-check task_id=600 mode=working-tree` ✅; `./scripts/ci/smoke.sh` ✅; `just verify-full` ✅; `ak task complete 600 --result '{...}'` ✅; `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅; `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅; `ak task ready -F json | jq 'map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx"))'` ✅ after `AK-600` (`[]`).
- Source-of-truth updates: recorded this idle-state confirmation in `diary/2026-03-30--reconfirm-post-ak-593-empty-ready-queue-and-refresh-handoff-at-current-head.md`; refreshed `docs/project/operational_goals.md` and this handoff so they point at the current-`HEAD` empty-queue checkpoint after `AK-593`; added `governance/task-scopes/AK-600.json`; and refreshed `governance/work-items.json` after the AK completion/export.
- Next-session starting point: re-run the repo-scoped ready queue filter; if it is still empty, wait for operator direction or the next truthful post-`TG23` contract/materialization step instead of starting a new implementation slice.

## END-OF-SESSION
Run `/commit` and ensure this file reflects the real checkpoint for the next operator/agent.
