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
- Objective (one sentence): Claim `AK-473` and materialize the read-only candidate-prior counterfactual advisory on live metadata and persisted receipts without changing V7 ranking or promotion behavior.
- Constraints (hard limits): Do not widen evidence authority beyond the read-only candidate-prior payload/audit/divergence/readiness/counterfactual layers without a dated contract; keep live execution truth in AK; keep `docs/project/operational_goals.md` and this file aligned.
- Assumptions (max 3): `AK-466` is done and committed; `TG18` is complete; `AK-473` is now the next ready SG2 slice.
- Blockers (none or list): none.

## READ-FIRST ALLOWLIST (STARTUP BUDGET)
1. `AGENTS.md`
2. `docs/project/vision.md`
3. `docs/project/strategic_goals.md`
4. `docs/project/tactical_goals.md`
5. `docs/project/operational_goals.md`
6. `docs/adr/20260328-synthesis-evidence-candidate-prior-counterfactual-advisory-v1.md`
7. `diary/2026-03-28--freeze-candidate-prior-counterfactual-advisory-contract.md`

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
- Slice executed: `AK-477` — lock the deterministic task-binding workflow into contract checks and tests.
- Outcome: DSPx now fails workflow-contract validation if the explicit working-tree task-scope command, the fail-closed wording, or the next-session-checkpoint binding semantics drift out of the repo docs or `Justfile`, so the `AK-474` workflow guardrail is protected by automated contract checks as well as runtime behavior.
- Files changed: `diary/2026-03-28--lock-deterministic-task-binding-into-contract-checks.md`, `governance/task-scopes/AK-477.json`, `governance/work-items.json`, `next_session_prompt.md`, `scripts/check_workflow_contracts.py`, and `tests/test_workflow_contracts.py`.
- Validation commands + results: `python scripts/check_task_scope.py --task-id 477 --mode working-tree` ✅; `uv run -m pytest -q tests/test_workflow_contracts.py` ✅; `python3 scripts/check_workflow_contracts.py` ✅; `./scripts/ci/smoke.sh` ✅; `just verify-full` ✅; `ak task complete 477 ...` ✅; `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅; `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅.
- Source-of-truth updates: `AK-477` is complete; `TG19` remains active with `AK-473` as the next ready SG2 slice.
- Next-session starting point: inspect the repo-scoped ready queue, then claim `AK-473` and materialize the read-only candidate-prior counterfactual advisory on live metadata and persisted receipts without changing V7 ranking or promotion behavior.

## END-OF-SESSION
Run `/commit` and ensure this file reflects the real checkpoint for the next operator/agent.
