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
- Objective (one sentence): Restock `governance/work-items.json` with the next highest-leverage post-M4 roadmap slice now that the current M1-M4 backlog is complete.
- Constraints (hard limits): Keep the repo green under `just verify-full`; do not reopen completed provider-runtime work unless new evidence requires it; keep the handoff/backlog authoritative and concise.
- Assumptions (max 3): `DSPX-M4-03` is complete and documented; `docs/project/provider-runtime-v4.md` reflects the current verified mixed-provider behavior; the repo is already validated after the latest optimize/default-resolution fix.
- Blockers (none or list): None.

## READ-FIRST ALLOWLIST (STARTUP BUDGET)
1. `AGENTS.md`
2. `README.md`
3. `governance/work-items.json`
4. `docs/project/mission.md`
5. `docs/project/tactical_goals.md`
6. `diary/2026-03-22--mixed-provider-optimize-smoke.md`

## EXECUTION MODE (ONE SESSION = ONE SLICE)
1. Choose one highest-leverage actionable slice from `governance/work-items.json` unless operator direction overrides it.
2. Implement end-to-end on a branch.
3. Validate:
   - `./scripts/ci/smoke.sh`
   - `./scripts/ci/full.sh` (when CI/policy/ontology/contracts changed)
4. Update source-of-truth artifacts before commit.

## SESSION CHECKPOINT (UPDATE BEFORE /commit)
- Slice executed: `DSPX-M4-03` — run one live end-to-end optimize smoke on the mixed-provider defaults.
- Outcome: Re-confirmed provider health for `vllm-local` and `dspy-lm-auth`, ran a live `module-gen` -> `optimize gepa` smoke with `DSPX_CONFIG=config.provider-runtime-v4.example.toml`, fixed a CLI ordering bug so `[optimize]` defaults load before provider resolution, and verified the final manifest captured `student=vllm-local` plus `reflection=dspy-lm-auth`.
- Files changed: `packages/dspx-core/src/dspx/cli/commands/optimize.py`, `tests/test_provider_v4.py`, `docs/project/provider-runtime-v4.md`, `README.md`, `NEXT_STEPS.md`, `governance/work-items.json`, `diary/2026-03-22--mixed-provider-optimize-smoke.md`, and `next_session_prompt.md`.
- Validation commands + results: `DSPX_CONFIG=config.provider-runtime-v4.example.toml MLFLOW_ENABLE=0 just dspx providers health --provider vllm-local --probe --json` ✅; `DSPX_CONFIG=config.provider-runtime-v4.example.toml MLFLOW_ENABLE=0 just dspx providers health --provider dspy-lm-auth --probe --json` ✅; `DSPX_CONFIG=config.provider-runtime-v4.example.toml MLFLOW_ENABLE=0 uv run -q python -m dspx.cli.dspx module-gen ... && DSPX_CONFIG=config.provider-runtime-v4.example.toml MLFLOW_ENABLE=0 uv run -q python -m dspx.cli.dspx optimize gepa --program "$TD/student.py" --train examples/gepa_modulegen_train.csv --out "$TD/optimized" --metric contains --max-metric-calls 2 --nrows 3` ✅; `uv run -q pytest tests/test_provider_v4.py -q` ✅; `./scripts/ci/smoke.sh` ✅; `just verify-full` ✅.
- Deferred tasks updated in `governance/work-items.json`: completed `DSPX-M4-03`; the repo now needs a fresh planned slice rather than another carry-over task.
- Next-session starting point: choose and shape the next roadmap slice in `governance/work-items.json`, then execute it end-to-end from a clean handoff.

## END-OF-SESSION
Run `/commit` and ensure this file reflects the real checkpoint for the next operator/agent.
