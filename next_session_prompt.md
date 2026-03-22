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
- Objective (one sentence): Harden the Oracle Phase C lineage invariants now that the first receipt-backed Time Travel CLI slice is shipped.
- Constraints (hard limits): Keep follow-up work centered on receipt/replay lineage edge cases; preserve the green `just verify-full` baseline and the new `oracle branch|diff|bisect` contract.
- Assumptions (max 3): The Phase C CLI JSON contract is stable enough to build on; receipt v2 lineage metadata will continue to be partially populated in real runs; `DSPX-M2-02` is the highest-leverage next product task.
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
- Slice executed: `DSPX-M2-01` — add a first user-facing Oracle Phase C CLI slice for behavioral branch/diff/bisect workflows.
- Outcome: The repo now ships receipt-backed `dspx oracle branch`, `diff`, and `bisect` commands, plus focused tests/docs, and `just verify-full` is green again.
- Files changed: `packages/dspx-core/src/dspx/cli/commands/oracle.py`, `packages/dspx-core/src/dspx/oracle_time_travel.py`, `tests/test_oracle_time_travel_cli.py`, `docs/ORACLE_TIME_TRAVEL.md`, `governance/work-items.json`, `diary/2026-03-22--oracle-phase-c-cli-slice.md`, `next_session_prompt.md`.
- Validation commands + results: `uv run -m pytest -q tests/test_oracle_time_travel_cli.py` ✅; `uvx ty check packages/dspx-core/src/dspx/oracle_time_travel.py packages/dspx-core/src/dspx/cli/commands/oracle.py` ✅; `./scripts/ci/smoke.sh` ✅; `just verify-full` ✅.
- Deferred tasks updated in `governance/work-items.json`: queued `DSPX-M2-02`, `DSPX-M3-01`; triage `DSPX-M4-01`.
- Next-session starting point: Start `DSPX-M2-02` by adding multi-parent lineage fixtures plus replay/explain fallback assertions so the new Phase C CLI contract is protected by stronger receipt invariants.

## END-OF-SESSION
Run `/commit` and ensure this file reflects the real checkpoint for the next operator/agent.
