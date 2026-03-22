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
- Objective (one sentence): Triage `DSPX-M4-01` and decide whether DSPx should keep waiting on upstream template-adapter fixes or move to a local patched path.
- Constraints (hard limits): Keep the repo green under `just verify-full`; do not regress the new replay provenance gate; keep scope focused on the unblock decision rather than broad upstream implementation.
- Assumptions (max 3): Replay/cache provenance hardening is now covered by CI; the template-adapter upstream issue set remains the canonical blocker map; `DSPX-M4-01` is now the highest-leverage remaining backlog slice.
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
- Slice executed: `DSPX-M3-01` — tighten CI coverage for cache provenance and replay strictness.
- Outcome: CI/full validation now executes a deterministic replay provenance guard that proves clean replay passes, then injects cache drift and requires a clear `cache_code_hash_mismatch` failure.
- Files changed: `scripts/check_replay_provenance.py`, `scripts/ci/full.sh`, `Justfile`, `docs/project/developer_workflow.md`, `docs/RUN_REPLAY_EXPLAIN.md`, `governance/work-items.json`, `diary/2026-03-22--replay-provenance-ci-hardening.md`, `next_session_prompt.md`.
- Validation commands + results: `uv run -m pytest -q tests/test_run_receipts.py tests/test_workflow_contracts.py` ✅; `./scripts/ci/smoke.sh` ✅; `./scripts/ci/full.sh` ✅; `just verify-full` ✅.
- Deferred tasks updated in `governance/work-items.json`: completed `DSPX-M3-01`; left `DSPX-M4-01` in triage.
- Next-session starting point: Review the upstream template-adapter issue set, then decide whether `DSPX-M4-01` should keep waiting on upstream or move to a local patched integration path.

## END-OF-SESSION
Run `/commit` and ensure this file reflects the real checkpoint for the next operator/agent.
