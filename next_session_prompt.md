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
- Objective (one sentence): Claim `AK-377` and emit the read-only candidate winner-prior payload for `module-gen` variants without changing V7 ranking behavior.
- Constraints (hard limits): Keep the repo green under `./scripts/ci/smoke.sh`; preserve the new candidate-prior surface as advisory-only; do not let historical losers, degraded receipts, or Oracle neighbors become pruning authority.
- Assumptions (max 3): `AK-356` is done and committed; `docs/adr/20260327-synthesis-evidence-candidate-prior-v1.md` is the active contract; current deterministic variants continue to expose stable `variant_id` and `variant_origin` metadata.
- Blockers (none or list): none.

## READ-FIRST ALLOWLIST (STARTUP BUDGET)
1. `AGENTS.md`
2. `docs/project/vision.md`
3. `docs/project/strategic_goals.md`
4. `docs/project/tactical_goals.md`
5. `docs/project/operational_goals.md`
6. `docs/adr/20260327-synthesis-evidence-candidate-prior-v1.md`
7. `diary/2026-03-27--freeze-evidence-backed-candidate-prior-contract.md`
8. `docs/adr/20260324-synthesis-evidence-history-advisory-v1.md`

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
- Slice executed: `AK-356` — freeze the first evidence-backed candidate-prior contract for module synthesis.
- Outcome: DSPx now has a dated candidate-prior contract that limits positive authority to replay-healthy exact-match historical winners for the current deterministic variants, keeps candidate priors read-only, and aligns the next implementation slice to `AK-377`.
- Files changed: `docs/adr/20260327-synthesis-evidence-candidate-prior-v1.md`, `docs/adr/README.md`, `docs/project/tactical_goals.md`, `docs/project/operational_goals.md`, `governance/task-scopes/AK-356.json`, `diary/2026-03-27--freeze-evidence-backed-candidate-prior-contract.md`, `next_session_prompt.md`, and `governance/work-items.json` after AK export.
- Validation commands + results: `python scripts/check_task_scope.py --task-id 356 --mode working-tree` ✅; `./scripts/ci/smoke.sh` ✅; `just verify-full` ✅; `ak task complete 356 ...` ✅; `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅; `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅.
- Source-of-truth updates: `TG10` / `AK-356` are complete; `TG11` is active; `AK-377` is the next ready SG2 implementation slice.
- Next-session starting point: inspect the repo-scoped ready queue, then claim `AK-377` and materialize the read-only candidate winner-prior payload on runtime metadata/receipts without changing ranking or promotion behavior.

## END-OF-SESSION
Run `/commit` and ensure this file reflects the real checkpoint for the next operator/agent.
