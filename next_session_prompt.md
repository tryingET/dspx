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
- Objective (one sentence): Claim `AK-379` and materialize the ADR-backed post-selection candidate-prior audit on live metadata and persisted receipts without changing V7 ranking or promotion behavior.
- Constraints (hard limits): Keep the repo green under `./scripts/ci/smoke.sh`; do not widen candidate-prior authority beyond the read-only audit contract without a new dated ADR; keep live execution truth in AK.
- Assumptions (max 3): `AK-378` is done and committed; `TG12` is complete and `TG13` is active; `docs/adr/20260327-synthesis-evidence-candidate-prior-audit-v1.md` is the active authority boundary for post-selection prior consumption.
- Blockers (none or list): none.

## READ-FIRST ALLOWLIST (STARTUP BUDGET)
1. `AGENTS.md`
2. `docs/project/vision.md`
3. `docs/project/strategic_goals.md`
4. `docs/project/tactical_goals.md`
5. `docs/project/operational_goals.md`
6. `docs/adr/20260327-synthesis-evidence-candidate-prior-v1.md`
7. `docs/adr/20260327-synthesis-evidence-candidate-prior-audit-v1.md`
8. `diary/2026-03-27--emit-read-only-candidate-winner-priors.md`
9. `diary/2026-03-27--freeze-candidate-prior-audit-contract.md`

## EXECUTION MODE (ONE SESSION = ONE SLICE)
1. Choose one highest-leverage actionable slice from `governance/work-items.json` unless operator direction overrides it. In this repo, treat that file as a checked-in projection and confirm the live slice against AK before acting.
2. Confirm the ready queue with `ak task ready -F json | jq 'map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx"))'`.
3. Claim the current active task before editing docs or code.
4. Implement one operating slice end-to-end.
5. Validate:
   - `./scripts/ci/smoke.sh`
   - `just verify-full`
6. Update source-of-truth docs/diary/ADR references before commit.

## SESSION CHECKPOINT (UPDATE BEFORE /commit)
- Slice executed: `AK-378` — define the next SG2 contract and execution slice for consuming candidate winner priors after `TG11`.
- Outcome: DSPx now has `docs/adr/20260327-synthesis-evidence-candidate-prior-audit-v1.md`, which freezes post-selection candidate-prior consumption as a read-only audit of selected-vs-available positive prior support and aligns the next implementation slice to `AK-379` while preserving V7 ranking and promotion behavior.
- Files changed: `docs/adr/20260327-synthesis-evidence-candidate-prior-audit-v1.md`, `docs/adr/README.md`, `docs/project/tactical_goals.md`, `docs/project/operational_goals.md`, `diary/2026-03-27--freeze-candidate-prior-audit-contract.md`, `governance/task-scopes/AK-378.json`, `governance/work-items.json`, and `next_session_prompt.md`.
- Validation commands + results: `python scripts/check_task_scope.py --task-id 378 --mode working-tree` ✅; `./scripts/ci/smoke.sh` ✅; `just verify-full` ✅; `ak task create --repo /home/tryinget/ai-society/softwareco/owned/dspx "Synthesis evidence substrate: emit a post-selection candidate-prior audit for module-gen outcomes"` ✅ (`AK-379`); `ak task complete 378 ...` ✅; `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅; `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅.
- Source-of-truth updates: `TG12` / `AK-378` are complete; `TG13` is active; `AK-379` is the next ready SG2 implementation slice.
- Next-session starting point: inspect the repo-scoped ready queue, then claim `AK-379` and materialize the ADR-backed post-selection candidate-prior audit on live metadata and persisted receipts without widening evidence authority.

## END-OF-SESSION
Run `/commit` and ensure this file reflects the real checkpoint for the next operator/agent.
