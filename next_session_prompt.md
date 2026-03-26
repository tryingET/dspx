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
- Objective (one sentence): Claim `AK-356` and freeze the first evidence-backed candidate-prior contract for module synthesis before any predictive ranking implementation.
- Constraints (hard limits): Keep the repo green under `./scripts/ci/smoke.sh`; preserve the new `TG9` advisory as advisory-only; do not change V7 ranking/promotion behavior while defining the next contract.
- Assumptions (max 3): `AK-341` is done and committed; `TG9` is complete; the safest next move is a contract-definition slice before any evidence-backed ranking change.
- Blockers (none or list): `just verify-full` remains blocked by pre-existing repo-wide `just typecheck` failures outside the completed SG2 slice.

## READ-FIRST ALLOWLIST (STARTUP BUDGET)
1. `AGENTS.md`
2. `docs/project/vision.md`
3. `docs/project/strategic_goals.md`
4. `docs/project/tactical_goals.md`
5. `docs/project/operational_goals.md`
6. `docs/adr/20260324-synthesis-evidence-history-advisory-v1.md`
7. `diary/2026-03-26--emit-historical-convergence-advisory.md`

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
- Slice executed: `AK-341` — emit a read-only historical convergence advisory for module-gen selections.
- Outcome: `module-gen` now attaches the ADR-backed advisory on live metadata and persisted receipts, exact-match evidence retrieval records bounded degraded states explicitly, and V7 ranking/promotion behavior remains unchanged.
- Files changed: `packages/dspx-core/src/dspx/services/module_service.py`, `packages/dspx-core/src/dspx/services/module_synthesis_evidence.py`, `tests/test_module_service.py`, `tests/test_module_synthesis_evidence.py`, `tests/test_run_receipts.py`, `governance/task-scopes/AK-341.json`, `docs/project/tactical_goals.md`, `docs/project/operational_goals.md`, `diary/2026-03-26--emit-historical-convergence-advisory.md`, `next_session_prompt.md`, and `governance/work-items.json` after AK export/create.
- Validation commands + results: `uv run -m pytest -q tests/test_module_synthesis_evidence.py tests/test_module_service.py tests/test_run_receipts.py` ✅; `./scripts/ci/smoke.sh` ✅; `just verify-full` ⚠️ blocked by pre-existing repo-wide `just typecheck` failures outside the AK-341 slice; targeted AK evidence records ✅; `ak task complete 341 ...` ✅; `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅; `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅.
- Source-of-truth updates: `TG9` is complete, `AK-341` moved to done, and repo docs now point at `TG10` / `AK-356` as the next SG2 planning slice.
- Next-session starting point: inspect the repo-scoped ready queue, claim `AK-356`, and freeze the post-`TG9` candidate-prior contract before any predictive-ranking implementation.

## END-OF-SESSION
Run `/commit` and ensure this file reflects the real checkpoint for the next operator/agent.
