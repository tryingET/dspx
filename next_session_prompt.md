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
- Objective (one sentence): Tighten CI coverage around cache provenance and replay strictness now that the Phase C lineage invariants are pinned.
- Constraints (hard limits): Keep the repo green under `just verify-full`; do not weaken receipt-first replay checks; avoid expanding scope into upstream/template-adapter work.
- Assumptions (max 3): The current replay JSON contract is stable; existing Oracle Phase C tests are sufficient coverage for lineage edge cases; `DSPX-M3-01` is now the highest-leverage next product task.
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
- Slice executed: `DSPX-M2-02` — harden lineage and branch invariants in receipt/replay tests.
- Outcome: Oracle Phase C now has regression coverage for multi-parent lineage overlap, default-branch fallback, branch-timeline bisect fallback, and replay/explain stability when lineage metadata is absent or partial.
- Files changed: `tests/test_oracle_time_travel_cli.py`, `tests/test_run_receipts.py`, `governance/work-items.json`, `diary/2026-03-22--oracle-phase-c-lineage-hardening.md`, `next_session_prompt.md`.
- Validation commands + results: `uv run -m pytest -q tests/test_oracle_time_travel_cli.py tests/test_run_receipts.py` ✅; `./scripts/ci/smoke.sh` ✅; `just verify-full` ✅.
- Deferred tasks updated in `governance/work-items.json`: queued `DSPX-M3-01`; triage `DSPX-M4-01`.
- Next-session starting point: Start `DSPX-M3-01` by reviewing replay/check-only CI coverage gaps and adding one strict provenance-focused signal that fails clearly on drift.

## END-OF-SESSION
Run `/commit` and ensure this file reflects the real checkpoint for the next operator/agent.
