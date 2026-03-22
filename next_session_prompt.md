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
- Crystallize durable patterns in `docs/learnings/` and decisions in `docs/decisions/`.
- Track deferred work in `governance/work-items.json` (not in ad-hoc TODO notes).

## SOURCE-OF-TRUTH MAP
- Repo operating contract: `AGENTS.md`
- Mission and goals: `docs/project/`
- Planned active/deferred work map: `governance/work-items.json`
- Prior decisions: `docs/decisions/`
- Crystallized learnings: `docs/learnings/`
- Raw session capture: `diary/`

## SESSION PREFLIGHT (FILL BEFORE EXECUTION)
- Objective (one sentence): Start the first Oracle Phase C vertical slice now that the workflow contract and full validation baseline are green.
- Constraints (hard limits): Keep the next slice centered on receipt-backed Oracle Phase C CLI behavior; preserve the green workflow/typecheck baseline.
- Assumptions (max 3): Receipt v2 metadata is sufficient for the first Time Travel slice; the new workflow contract will catch doc/setup drift; `DSPX-M2-01` remains the highest-leverage product task.
- Blockers (none or list): none

## READ-FIRST ALLOWLIST (STARTUP BUDGET)
1. `AGENTS.md`
2. `README.md`
3. `governance/work-items.json`
4. `docs/project/mission.md`
5. `docs/project/tactical_goals.md`
6. Most recent `diary/YYYY-MM-DD--type-scope-summary.md`

## EXECUTION MODE (ONE SESSION = ONE SLICE)
1. Choose one highest-leverage actionable slice from `governance/work-items.json` unless operator direction overrides it.
2. Implement end-to-end on a branch.
3. Validate:
   - `./scripts/ci/smoke.sh`
   - `./scripts/ci/full.sh` (when CI/policy/ontology/contracts changed)
4. Update source-of-truth artifacts before commit.

## SESSION CHECKPOINT (UPDATE BEFORE /commit)
- Slice executed: `DSPX-M1-03` — restore a green repo-wide typecheck baseline for `just verify-full`.
- Outcome: The remaining forge/core boundary typing issues were fixed, and the full workflow contract now validates end-to-end.
- Files changed: `apps/forge/src/dspx_forge/gitlab_client.py`, `packages/dspx-core/src/dspx/pi_rpc_client.py`, `packages/dspx-core/src/dspx/providers_register_gemini.py`, `packages/dspx-core/src/dspx/services/optimize_service.py`, `packages/dspx-core/src/dspx/services/refine_service.py`, `packages/dspx-core/src/dspx/services/signature_quality.py`, `packages/dspx-core/src/dspx/services/signature_quality_corpus.py`, `governance/work-items.json`, `diary/2026-03-21--fix-typecheck-baseline-restoration.md`, `next_session_prompt.md`.
- Validation commands + results: `uvx ty check packages/dspx-core/src apps/forge/src` ✅; `./scripts/ci/smoke.sh` ✅; `uv run -m pytest -q tests/test_workflow_contracts.py` ✅; `just verify-full` ✅.
- Deferred tasks updated in `governance/work-items.json`: queued `DSPX-M2-01`, `DSPX-M2-02`, `DSPX-M3-01`; triage `DSPX-M4-01`.
- Next-session starting point: Start `DSPX-M2-01` by defining the minimal receipt-backed CLI contract for `dspx oracle branch|diff|bisect`, with the expectation that the full workflow gate stays green throughout the slice.

## END-OF-SESSION
Run `/commit` and ensure this file reflects the real checkpoint for the next operator/agent.
