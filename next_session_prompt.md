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
- Active/deferred work contract: `governance/work-items.json`
- Prior decisions: `docs/decisions/`
- Crystallized learnings: `docs/learnings/`
- Raw session capture: `diary/`

## SESSION PREFLIGHT (FILL BEFORE EXECUTION)
- Objective (one sentence): Establish a usable source-of-truth baseline so the next session can start directly on a shaped Oracle Phase C slice.
- Constraints (hard limits): Keep the slice docs/governance-only; do not fold in unrelated local changes already present in the worktree.
- Assumptions (max 3): Roadmap docs are still authoritative; receipt v2 groundwork means Phase C is the highest-leverage next implementation area; smoke validation is sufficient for this non-code slice.
- Blockers (none or list): none

## READ-FIRST ALLOWLIST (STARTUP BUDGET)
1. `AGENTS.md`
2. `README.md`
3. `governance/work-items.json`
4. `docs/project/mission.md`
5. `docs/project/tactical_goals.md`
6. Most recent `diary/YYYY-MM-DD--type-scope-summary.md`

## EXECUTION MODE (ONE SESSION = ONE SLICE)
1. Pick one highest-leverage actionable slice from `governance/work-items.json`.
2. Implement end-to-end on a branch.
3. Validate:
   - `./scripts/ci/smoke.sh`
   - `./scripts/ci/full.sh` (when CI/policy/ontology/contracts changed)
4. Update source-of-truth artifacts before commit.

## SESSION CHECKPOINT (UPDATE BEFORE /commit)
- Slice executed: `DSPX-M1-01` — refresh mission, tactical goals, backlog, and session handoff.
- Outcome: Repo source-of-truth docs now reflect the Oracle-first roadmap, and the next session can start on a queued Phase C issue instead of rebuilding context.
- Files changed: `docs/project/mission.md`, `docs/project/tactical_goals.md`, `governance/work-items.json`, `diary/2026-03-21--chore-governance-baseline-refresh.md`, `next_session_prompt.md`.
- Validation commands + results: `cue vet governance/work-items.json governance/work-items.cue` ✅; `./scripts/ci/smoke.sh` ✅.
- Deferred tasks updated in `governance/work-items.json`: queued `DSPX-M2-01`, `DSPX-M2-02`, `DSPX-M3-01`; triage `DSPX-M4-01`.
- Next-session starting point: Start `DSPX-M2-01` by defining the minimal receipt-backed CLI contract for `dspx oracle branch|diff|bisect`, then implement the first end-to-end vertical slice.

## END-OF-SESSION
Run `/commit` and ensure this file reflects the real checkpoint for the next operator/agent.
