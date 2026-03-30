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
- Objective (one sentence): Claim `AK-578` and freeze the first governed policy-evaluation contract that consumes shadow predictive-ranking evidence.
- Constraints (hard limits): Keep authority bounded to the already-emitted shadow predictive-ranking evidence surfaces; do not mutate live V7 ranking, tie-breaking, pruning, or promotion behavior; keep `docs/project/strategic_goals.md`, `docs/project/tactical_goals.md`, `docs/project/operational_goals.md`, and this file aligned.
- Assumptions (max 3): `AK-577` is complete and committed; `AK-578` is the only repo-scoped ready task for active `TG22`; SG3 `AK-549`–`AK-551` remain blocked on cross-repo `AK-548` and are not in scope.
- Blockers (none or list): none.

## READ-FIRST ALLOWLIST (STARTUP BUDGET)
1. `AGENTS.md`
2. `docs/project/vision.md`
3. `docs/project/strategic_goals.md`
4. `docs/project/tactical_goals.md`
5. `docs/project/operational_goals.md`
6. `docs/adr/20260329-synthesis-evidence-shadow-predictive-ranking-advisory-v1.md`
7. `diary/2026-03-29--promote-tg22-and-materialize-next-governed-policy-evaluation-contract-slice.md`

## EXECUTION MODE (ONE SESSION = ONE SLICE)
1. Choose one highest-leverage actionable slice from `governance/work-items.json` unless operator direction overrides it. In this repo, treat that file as a checked-in projection and confirm the live slice against AK before acting.
2. Confirm the ready queue with `ak task ready -F json | jq 'map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx"))'`.
3. Claim `AK-578` before editing docs or code.
4. Freeze only the `TG22` contract slice; do not start `TG23` receipt materialization in the same session.
5. Validate the slice with:
   - `./scripts/ci/smoke.sh`
   - `just task-scope-check task_id=576 mode=working-tree`
   - `just verify-full`
6. Update source-of-truth docs/diary/ADR references before commit, then refresh the checked-in projection with `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` and verify it with `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx`.

## SESSION CHECKPOINT (UPDATE BEFORE /commit)
- Slice executed: `AK-577` — promote `TG22` and materialize the next governed policy-evaluation contract slice.
- Outcome: refreshed the SG2 strategic rationale after `AK-562`, promoted `TG22` to the active tactical goal, created `AK-578` as the single next repo-local slice, and converted the repo from an empty-ready-queue decomposition gap into a truthful ready handoff without materializing `TG23` early.
- Files changed: `diary/2026-03-29--promote-tg22-and-materialize-next-governed-policy-evaluation-contract-slice.md`, `docs/project/operational_goals.md`, `docs/project/strategic_goals.md`, `docs/project/tactical_goals.md`, `governance/task-scopes/AK-577.json`, `governance/work-items.json`, and `next_session_prompt.md`.
- Validation commands + results: `ak task ready -F json | jq 'map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx"))'` (empty before materialization) ✅; `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` (preflight) ✅; `just task-scope-check task_id=577 mode=working-tree` ✅; `./scripts/ci/smoke.sh` ✅; `just verify-full` ✅; `ak task complete 577 --result '{...}'` ✅; `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅; `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅.
- Source-of-truth updates: refreshed `docs/project/strategic_goals.md`, `docs/project/tactical_goals.md`, `docs/project/operational_goals.md`, and `next_session_prompt.md`; recorded the session in `diary/2026-03-29--promote-tg22-and-materialize-next-governed-policy-evaluation-contract-slice.md`; added `governance/task-scopes/AK-577.json`; created repo-local task `AK-578`; and refreshed `governance/work-items.json`.
- Next-session starting point: claim `AK-578`, freeze the governed policy-evaluation contract for shadow predictive-ranking evidence, and keep `TG23` unmaterialized until that contract lands.

## END-OF-SESSION
Run `/commit` and ensure this file reflects the real checkpoint for the next operator/agent.
