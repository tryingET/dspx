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
- Live execution truth: `ak task ... --repo /home/tryinget/ai-society/softwareco/owned/dspx`
- Planned active/deferred work map: `governance/work-items.json` (legacy checked-in projection/mirror; do not treat as live execution truth)
- Raw session capture: `diary/`

## SESSION PREFLIGHT (FILL BEFORE EXECUTION)
- Objective (one sentence): Claim `AK-249` and start the V9-compatible synthesis core contracts for module generation.
- Constraints (hard limits): Keep the repo green under `just verify-full`; preserve the current `module-gen` CLI surface while introducing the synthesis runtime seam; keep docs/AK/projection coherence checks passing while the synthesis package skeleton lands.
- Assumptions (max 3): The V7/V8/V9 architecture reference is already captured in `docs/adr/20260322-synthesis-architecture-v7-v9.md`; `AK-249`/`AK-250`/`AK-251` remain the authoritative active operating wave; `NEXT_STEPS.md` has been retired in favor of the canonical `docs/project/` direction stack.
- Blockers (none or list): None.

## READ-FIRST ALLOWLIST (STARTUP BUDGET)
1. `AGENTS.md`
2. `docs/project/vision.md`
3. `docs/project/strategic_goals.md`
4. `docs/project/tactical_goals.md`
5. `docs/project/operational_goals.md`
6. `docs/adr/20260322-synthesis-architecture-v7-v9.md`
7. `diary/2026-03-22--retire-next-steps-surface.md`

## EXECUTION MODE (ONE SESSION = ONE SLICE)
1. Choose one highest-leverage actionable slice from `governance/work-items.json` unless operator direction overrides it. In this repo, treat that file as a checked-in projection and confirm the live slice against AK before acting.
2. Confirm the ready queue with `ak task ready -F json | jq 'map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx"))'`.
3. Claim the current active task before editing code.
4. Implement one operating slice end-to-end.
5. Validate:
   - `./scripts/ci/smoke.sh`
   - `just verify-full`
6. Update source-of-truth docs/diary/ADR references before commit.

## SESSION CHECKPOINT (UPDATE BEFORE /commit)
- Slice executed: Direction hygiene — retire `NEXT_STEPS.md` and converge all live references on the canonical `docs/project/` stack.
- Outcome: Salvaged the remaining roadmap truth into canonical project docs, removed `NEXT_STEPS.md`, updated startup/validation/reference surfaces so they no longer depend on it, and kept `next_session_prompt.md` plus `docs/project/operational_goals.md` focused on the active slice instead of duplicating roadmap content.
- Files changed: `AGENTS.md`, `README.md`, `PROJECT_STATUS.md`, `docs/project/strategic_goals.md`, `docs/SIGNATURE_NATIVE_PIPELINE.md`, `docs/UPSTREAM_CONTRIBUTING_WORKFLOW.md`, `docs/MONOREPO_TRANSITION.md`, `docs/RFC_TEMPLATE_DSPX_NEXT.md`, `docs/system4d/fog.md`, `scripts/check_direction_to_execution.py`, `scripts/check_workflow_contracts.py`, `tests/test_workflow_contracts.py`, `diary/2026-03-22--retire-next-steps-surface.md`, `next_session_prompt.md`, and removed `NEXT_STEPS.md`.
- Validation commands + results: `ak task ready -F json | jq 'map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx"))'` ✅; `python3 scripts/check_workflow_contracts.py` ✅; `python3 scripts/check_direction_to_execution.py` ✅; `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅; `./scripts/ci/smoke.sh` ✅; `just verify-full` ✅.
- Source-of-truth updates: canonical direction is now fully under `docs/project/`; `governance/work-items.json` remains an AK-backed checked-in projection; `next_session_prompt.md` and `docs/project/operational_goals.md` stay DRY by pointing only at the active wave.
- Next-session starting point: claim `AK-249` and implement the synthesis contracts/package skeleton described in `docs/project/operational_goals.md`.

## END-OF-SESSION
Run `/commit` and ensure this file reflects the real checkpoint for the next operator/agent.
