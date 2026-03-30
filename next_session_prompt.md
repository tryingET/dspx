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
- Objective (one sentence): Re-run the repo-scoped ready queue after `AK-562`; if it is still empty, do not start a new implementation slice until the next truthful `TG22` contract/materialization step is created.
- Constraints (hard limits): Do not widen evidence authority beyond `docs/adr/20260329-synthesis-evidence-shadow-predictive-ranking-advisory-v1.md`; keep live execution truth in AK; keep `docs/project/operational_goals.md` and this file aligned.
- Assumptions (max 3): `AK-562` is complete and committed; the repo-scoped ready queue is empty again unless a new truthful slice has been materialized; SG3 AK-native scope-snapshot work remains blocked on cross-repo `AK-548` and is not the active wave.
- Blockers (none or list): none.

## READ-FIRST ALLOWLIST (STARTUP BUDGET)
1. `AGENTS.md`
2. `docs/project/vision.md`
3. `docs/project/strategic_goals.md`
4. `docs/project/tactical_goals.md`
5. `docs/project/operational_goals.md`
6. `docs/adr/20260329-synthesis-evidence-shadow-predictive-ranking-advisory-v1.md`
7. `diary/2026-03-29--emit-shadow-predictive-ranking-advisory.md`

## EXECUTION MODE (ONE SESSION = ONE SLICE)
1. Choose one highest-leverage actionable slice from `governance/work-items.json` unless operator direction overrides it. In this repo, treat that file as a checked-in projection and confirm the live slice against AK before acting.
2. Confirm the ready queue with `ak task ready -F json | jq 'map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx"))'`.
3. If the repo-scoped ready queue is empty, do not start a new implementation slice; wait for operator direction or the next truthful decomposition/materialization step.
4. If a repo-scoped ready task exists, claim the current active task before editing docs or code.
5. Implement at most one operating slice end-to-end.
6. Validate the slice with:
   - `./scripts/ci/smoke.sh`
   - `just verify-full`
7. Update source-of-truth docs/diary/ADR references before commit.

## SESSION CHECKPOINT (UPDATE BEFORE /commit)
- Slice executed: `AK-562` — emit the ADR-backed read-only shadow predictive-ranking advisory for `module-gen` outcomes.
- Outcome: DSPx now emits `shadow_predictive_ranking_advisory` on live `module-gen` metadata and persisted receipts, deriving bounded shadow statuses from the existing winner-prior/audit/divergence/readiness/counterfactual surfaces plus trusted current comparison metadata without changing V7 ranking, tie-breaking, pruning, or promotion behavior.
- Files changed: `diary/2026-03-29--emit-shadow-predictive-ranking-advisory.md`, `docs/project/operational_goals.md`, `docs/project/tactical_goals.md`, `governance/task-scopes/AK-562.json`, `governance/work-items.json`, `next_session_prompt.md`, `packages/dspx-core/src/dspx/services/module_service.py`, `packages/dspx-core/src/dspx/services/module_synthesis_evidence.py`, `tests/test_module_service.py`, `tests/test_module_synthesis_evidence.py`, and `tests/test_run_receipts.py`.
- Validation commands + results: `uv run -m pytest -q tests/test_module_synthesis_evidence.py tests/test_module_service.py tests/test_run_receipts.py` ✅; `just task-scope-check task_id=562 mode=working-tree` ✅; `./scripts/ci/smoke.sh` ✅; `just verify-full` ✅; `ak task complete 562 --result '{...}'` ✅; `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅; `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅.
- Source-of-truth updates: refreshed `docs/project/tactical_goals.md`, `docs/project/operational_goals.md`, and `next_session_prompt.md`; recorded the session in `diary/2026-03-29--emit-shadow-predictive-ranking-advisory.md`; refreshed `governance/work-items.json`; added `governance/task-scopes/AK-562.json`; and recorded `AK-562`/`TG21` as complete with the repo-scoped ready queue empty again until the next truthful `TG22` contract/materialization step is created.
- Next-session starting point: re-run the repo-scoped ready queue filter; if it is still empty, do not start a new implementation slice until the next truthful `TG22` contract/materialization step is created, and do not widen SG2 authority beyond the new shadow predictive-ranking advisory.

## END-OF-SESSION
Run `/commit` and ensure this file reflects the real checkpoint for the next operator/agent.
