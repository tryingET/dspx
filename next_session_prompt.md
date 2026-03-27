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
- Objective (one sentence): Claim `AK-378` and define the next dated SG2 contract / execution slice for how DSPx may inspect or consume the new read-only candidate-prior payload without silently widening authority.
- Constraints (hard limits): Keep the repo green under `./scripts/ci/smoke.sh`; do not widen candidate-prior authority beyond advisory-only winner-history payload semantics without a new dated contract; keep live execution truth in AK.
- Assumptions (max 3): `AK-377` is done and committed; `TG11` is complete; `docs/adr/20260327-synthesis-evidence-candidate-prior-v1.md` remains the active authority boundary.
- Blockers (none or list): none.

## READ-FIRST ALLOWLIST (STARTUP BUDGET)
1. `AGENTS.md`
2. `docs/project/vision.md`
3. `docs/project/strategic_goals.md`
4. `docs/project/tactical_goals.md`
5. `docs/project/operational_goals.md`
6. `docs/adr/20260327-synthesis-evidence-candidate-prior-v1.md`
7. `diary/2026-03-27--emit-read-only-candidate-winner-priors.md`
8. `diary/2026-03-27--freeze-evidence-backed-candidate-prior-contract.md`

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
- Slice executed: `AK-377` — emit the read-only candidate winner-prior payload for `module-gen` deterministic variants.
- Outcome: DSPx now emits `candidate_winner_priors` on live `synthesis_diagnostics` metadata and persisted `module-gen` receipts, matching replay-healthy exact-match historical winners by `variant_id` + `variant_origin` while preserving V7 ranking and promotion behavior.
- Files changed: `packages/dspx-core/src/dspx/services/module_synthesis_evidence.py`, `packages/dspx-core/src/dspx/services/module_service.py`, `tests/test_module_synthesis_evidence.py`, `tests/test_module_service.py`, `tests/test_run_receipts.py`, `docs/project/tactical_goals.md`, `docs/project/operational_goals.md`, `diary/2026-03-27--emit-read-only-candidate-winner-priors.md`, `governance/task-scopes/AK-377.json`, `governance/work-items.json`, and `next_session_prompt.md`.
- Validation commands + results: `uv run pytest tests/test_module_synthesis_evidence.py tests/test_module_service.py tests/test_run_receipts.py -q` ✅; `python scripts/check_task_scope.py --task-id 377 --mode working-tree` ✅; `./scripts/ci/smoke.sh` ✅; `just verify-full` ✅; `ak task complete 377 ...` ✅; `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅; `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅.
- Source-of-truth updates: `TG11` / `AK-377` are complete; `AK-378` is the next ready SG2 planning slice to define the post-`TG11` contract/execution wave.
- Next-session starting point: inspect the repo-scoped ready queue, then claim `AK-378` and define the next SG2 contract/slice for how DSPx may inspect or consume candidate priors without silently widening evidence authority.

## END-OF-SESSION
Run `/commit` and ensure this file reflects the real checkpoint for the next operator/agent.
