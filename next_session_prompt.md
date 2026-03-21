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
- Objective (one sentence): Convert the repo's workflow guidance into a real, machine-checked contract so setup, hooks, and validation stop drifting.
- Constraints (hard limits): Keep the slice focused on workflow/governance/tooling surfaces and do not mix in unrelated product behavior changes.
- Assumptions (max 3): Existing roadmap priorities remain valid; fixing the developer workflow contract unblocks future Phase C work; smoke/full validation should be updated to reflect the real repo contract.
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
- Slice executed: `DSPX-M1-02` — enforce the developer workflow contract across docs, hooks, and smoke validation.
- Outcome: The repo now has a canonical workflow contract, a working hook-install path, a root `.gitignore`, a real pre-commit config, and machine-checked workflow/governance validation wired into normal gates.
- Files changed: `docs/project/developer_workflow.md`, `.gitignore`, `.pre-commit-config.yaml`, `scripts/check_workflow_contracts.py`, `tests/test_workflow_contracts.py`, `scripts/ci/smoke.sh`, `Justfile`, `AGENTS.md`, `CONTRIBUTING.md`, `README.md`, `docs/tech-stack.local.md`, `governance/README.md`, `governance/work-items.json`, `diary/2026-03-21--fix-workflow-contract-enforcement.md`, `next_session_prompt.md`.
- Validation commands + results: `python3 scripts/check_workflow_contracts.py` ✅; `cue vet governance/work-items.json governance/work-items.cue` ✅; `./scripts/ci/smoke.sh` ✅; `uv run -m pytest -q tests/test_workflow_contracts.py` ✅; `just verify-full` ⚠️ blocked by pre-existing `uvx ty check packages/dspx-core/src apps/forge/src` failures in untouched files.
- Deferred tasks updated in `governance/work-items.json`: queued `DSPX-M1-03`, `DSPX-M2-01`, `DSPX-M2-02`, `DSPX-M3-01`; triage `DSPX-M4-01`.
- Next-session starting point: Triage `DSPX-M1-03` to restore a green repo-wide typecheck baseline, then resume `DSPX-M2-01` for the first Oracle Phase C CLI slice.

## END-OF-SESSION
Run `/commit` and ensure this file reflects the real checkpoint for the next operator/agent.
