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
- Objective (one sentence): Claim `AK-593` and emit the first governed policy-evaluation receipts for named governance-only ranking/promotion variants from bounded shadow predictive-ranking evidence.
- Constraints (hard limits): Obey `docs/adr/20260330-synthesis-evidence-governed-policy-evaluation-contract-v1.md`; consume only the already-emitted shadow predictive-ranking evidence surfaces plus trusted current run metadata; keep live V7 ranking, tie-breaking, pruning, and promotion unchanged; do not widen into dashboards, registries, or policy switches; keep `docs/project/strategic_goals.md`, `docs/project/tactical_goals.md`, `docs/project/operational_goals.md`, and this file aligned.
- Assumptions (max 3): `AK-578` is complete and committed; `AK-593` is the only repo-scoped ready task for active `TG23`; SG3 `AK-549`–`AK-551` remain blocked on cross-repo `AK-548` and are not in scope.
- Blockers (none or list): none.

## READ-FIRST ALLOWLIST (STARTUP BUDGET)
1. `AGENTS.md`
2. `docs/project/vision.md`
3. `docs/project/strategic_goals.md`
4. `docs/project/tactical_goals.md`
5. `docs/project/operational_goals.md`
6. `docs/adr/20260330-synthesis-evidence-governed-policy-evaluation-contract-v1.md`
7. `diary/2026-03-30--freeze-governed-policy-evaluation-contract.md`

## EXECUTION MODE (ONE SESSION = ONE SLICE)
1. Choose one highest-leverage actionable slice from `governance/work-items.json` unless operator direction overrides it. In this repo, treat that file as a checked-in projection and confirm the live slice against AK before acting.
2. Confirm the ready queue with `ak task ready -F json | jq 'map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx"))'`.
3. Claim `AK-593` before editing docs or code.
4. Materialize only the first governed receipt wave for `TG23`; do not decompose the post-`TG23` tactical wave in the same session.
5. Validate the slice with:
   - `./scripts/ci/smoke.sh`
   - `just task-scope-check task_id=593 mode=working-tree`
   - `just verify-full`
6. Update source-of-truth docs/diary/ADR references before commit, then refresh the checked-in projection with `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` and verify it with `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx`.

## SESSION CHECKPOINT (UPDATE BEFORE /commit)
- Slice executed: `AK-578` — freeze the first governed policy-evaluation contract that consumes shadow predictive-ranking evidence.
- Outcome: authored `docs/adr/20260330-synthesis-evidence-governed-policy-evaluation-contract-v1.md`, promoted `TG23` to the active tactical goal, created `AK-593` as the single next repo-local receipt slice, and refreshed the aligned handoff/projection artifacts without widening live V7 authority.
- Files changed: `diary/2026-03-30--freeze-governed-policy-evaluation-contract.md`, `docs/adr/20260330-synthesis-evidence-governed-policy-evaluation-contract-v1.md`, `docs/adr/README.md`, `docs/project/operational_goals.md`, `docs/project/strategic_goals.md`, `docs/project/tactical_goals.md`, `governance/task-scopes/AK-578.json`, `governance/work-items.json`, and `next_session_prompt.md`.
- Validation commands + results: `ak task ready -F json | jq 'map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx"))'` ✅; `just task-scope-check task_id=578 mode=working-tree` ✅; `./scripts/ci/smoke.sh` ✅; `just verify-full` ✅; `ak task complete 578 --result '{...}'` ✅; `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅; `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅.
- Source-of-truth updates: refreshed `docs/project/strategic_goals.md`, `docs/project/tactical_goals.md`, `docs/project/operational_goals.md`, and `next_session_prompt.md`; recorded the session in `diary/2026-03-30--freeze-governed-policy-evaluation-contract.md`; added `governance/task-scopes/AK-578.json`; created repo-local task `AK-593`; and refreshed `governance/work-items.json`.
- Next-session starting point: claim `AK-593`, materialize the first governed policy-evaluation receipts under ADR 20260330, and keep authority bounded to governance-only evaluation until a later wave explicitly widens it.

## END-OF-SESSION
Run `/commit` and ensure this file reflects the real checkpoint for the next operator/agent.
