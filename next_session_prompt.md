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
- Constraints (hard limits): Keep the repo green under `just verify-full`; preserve the current `module-gen` CLI surface while introducing the synthesis runtime seam; keep the docs/AK/projection coherence checks passing while the new synthesis package skeleton lands.
- Assumptions (max 3): The V7/V8/V9 architecture reference is already captured in `docs/adr/20260322-synthesis-architecture-v7-v9.md`; `AK-249`/`AK-250`/`AK-251` remain the authoritative active operating wave; the checked-in work-items file is now an AK-backed projection rather than a handcrafted backlog authority.
- Blockers (none or list): None.

## READ-FIRST ALLOWLIST (STARTUP BUDGET)
1. `AGENTS.md`
2. `docs/project/vision.md`
3. `docs/project/strategic_goals.md`
4. `docs/project/tactical_goals.md`
5. `docs/project/operational_goals.md`
6. `docs/adr/20260322-synthesis-architecture-v7-v9.md`
7. `diary/2026-03-22--direction-to-execution-v7-v9.md`

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
- Slice executed: NEXUS follow-through — add a machine-checked direction-to-execution coherence contract.
- Outcome: Converted the direction reset from a one-shot docs/AK change into an enforced repo invariant by adding `scripts/check_direction_to_execution.py`, wiring it into smoke/full validation, updating `AGENTS.md` and `NEXT_STEPS.md` to expose the canonical active wave, and exporting `governance/work-items.json` so the checked-in projection matches live AK truth.
- Files changed: `AGENTS.md`, `NEXT_STEPS.md`, `governance/README.md`, `governance/work-items.json`, `scripts/check_direction_to_execution.py`, `scripts/check_workflow_contracts.py`, `scripts/ci/smoke.sh`, `Justfile`, `docs/project/vision.md`, `docs/project/strategic_goals.md`, `docs/project/tactical_goals.md`, `docs/project/operational_goals.md`, `docs/project/purpose.md`, `docs/project/model.md`, `docs/VISION.md`, `docs/adr/20260322-synthesis-architecture-v7-v9.md`, `docs/adr/README.md`, `diary/2026-03-22--direction-to-execution-v7-v9.md`, `diary/2026-03-22--direction-coherence-contract.md`, and `next_session_prompt.md`.
- Validation commands + results: `ak task ready -F json | jq 'map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx"))'` ✅; `python3 scripts/check_workflow_contracts.py` ✅; `python3 scripts/check_direction_to_execution.py` ✅; `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅; `./scripts/ci/smoke.sh` ✅; `just verify-full` ✅; `node ~/ai-society/core/agent-scripts/scripts/docs-list.mjs --docs . --strict` ❌ expected repo-wide pre-existing metadata debt outside this slice (including many historical docs/diary files).
- Source-of-truth updates: active strategic goal is now `SG1`; active tactical goal is `TG2`; active operating slices are `AK-249`/`AK-250`/`AK-251`; `AK-224` and `AK-235` are manually deferred because they are not part of the current active wave; `governance/work-items.json` is now refreshed as an AK-backed checked-in projection and machine-checked for drift.
- Next-session starting point: claim `AK-249` and implement the synthesis contracts/package skeleton described in `docs/project/operational_goals.md`.

## END-OF-SESSION
Run `/commit` and ensure this file reflects the real checkpoint for the next operator/agent.
