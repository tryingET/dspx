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
- Live execution truth: `ak task ... --repo /home/tryinget/ai-society/softwareco/owned/dspx`
- Planned active/deferred work map: `governance/work-items.json` (legacy checked-in projection/mirror; do not treat as live execution truth)
- Raw session capture: `diary/`

## SESSION PREFLIGHT (FILL BEFORE EXECUTION)
- Objective (one sentence): Claim `AK-251` and route `module-gen` through the new synthesis runtime single-candidate path with static/smoke validation and receipt updates.
- Constraints (hard limits): Keep the repo green under `just verify-full`; preserve the current `module-gen` CLI surface while switching execution through the runtime seam; keep docs/AK/projection coherence checks passing as receipts and validation land.
- Assumptions (max 3): `AK-250` has landed strategy metadata persistence plus candidate workspace/promotion shells; the V7/V8/V9 architecture reference remains `docs/adr/20260322-synthesis-architecture-v7-v9.md`; `AK-251` is now the active operating slice for `TG2`.
- Blockers (none or list): None.

## READ-FIRST ALLOWLIST (STARTUP BUDGET)
1. `AGENTS.md`
2. `docs/project/vision.md`
3. `docs/project/strategic_goals.md`
4. `docs/project/tactical_goals.md`
5. `docs/project/operational_goals.md`
6. `docs/adr/20260322-synthesis-architecture-v7-v9.md`
7. `diary/2026-03-23--add-module-synthesis-runtime-shell.md`

## EXECUTION MODE (ONE SESSION = ONE SLICE)
1. Choose one highest-leverage actionable slice from `governance/work-items.json` unless operator direction overrides it. In this repo, treat that file as a checked-in projection and confirm the live slice against AK before acting.
2. Confirm the ready queue with `ak task ready -F json | jq 'map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx"))'`.
3. Claim the current active task before editing code.
4. Implement one operating slice end-to-end.
5. Validate:
   - `./scripts/ci/smoke.sh`
   - `just verify-full`
6. Update source-of-truth docs/diary/ADR references before commit.

## SESSION CHECKPOINT (UPDATE BEFORE /commit)
- Slice executed: `AK-250` — module synthesis runtime shell: strategy metadata persistence, candidate workspace boundaries, and an explicit promotion shell.
- Outcome: Added runtime contracts and helpers for strategy persistence, candidate scratch workspaces/manifests, and promotion-shell promotion; then wired `module_service` to emit materialized synthesis bundles on fresh renders and cache hits without changing the current `module-gen` CLI surface.
- Files changed: `packages/dspx-core/src/dspx/services/module_service.py`, `packages/dspx-core/src/dspx/synthesis/__init__.py`, `packages/dspx-core/src/dspx/synthesis/contracts.py`, `packages/dspx-core/src/dspx/synthesis/runtime.py`, `tests/test_module_service.py`, `tests/test_synthesis_contracts.py`, `docs/project/operational_goals.md`, `diary/2026-03-23--add-module-synthesis-runtime-shell.md`, `next_session_prompt.md`, and `governance/work-items.json` after AK export.
- Validation commands + results: `ak task ready -F json | jq 'map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx"))'` ✅; `uv run pytest tests/test_synthesis_contracts.py tests/test_module_service.py tests/test_service_caching.py tests/test_cli_dspx.py tests/test_run_receipts.py -q` ✅; `uv run ruff check packages/dspx-core/src/dspx/synthesis/contracts.py packages/dspx-core/src/dspx/synthesis/runtime.py packages/dspx-core/src/dspx/synthesis/__init__.py packages/dspx-core/src/dspx/services/module_service.py tests/test_synthesis_contracts.py tests/test_module_service.py` ✅; `./scripts/ci/smoke.sh` ✅; `just verify-full` ✅; `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅; `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅.
- Source-of-truth updates: `docs/project/operational_goals.md` now promotes `AK-251` to the active slice and records `AK-250` as recently complete; the new diary captures the runtime-shell rationale and promotion-boundary pattern; `next_session_prompt.md` now points directly at the `AK-251` runtime-integration slice.
- Next-session starting point: claim `AK-251` and route `module-gen` through the synthesis runtime with validation/receipt recording while preserving the current CLI UX.

## END-OF-SESSION
Run `/commit` and ensure this file reflects the real checkpoint for the next operator/agent.
