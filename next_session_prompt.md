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
- Objective (one sentence): Claim `AK-256` and extend module synthesis from the one-candidate runtime MVP to multi-candidate fan-out with ranked selection receipts.
- Constraints (hard limits): Keep the repo green under `just verify-full`; preserve the existing `module-gen` UX while expanding the runtime under the hood; keep promotion routed through the explicit shell instead of reintroducing direct-path shortcuts.
- Assumptions (max 3): `AK-251` landed runtime static/smoke validation plus receipt-linked synthesis evidence; `TG2` is materially complete and `TG3` is now the active tactical goal; the V7/V8/V9 architecture reference remains `docs/adr/20260322-synthesis-architecture-v7-v9.md`.
- Blockers (none or list): None.

## READ-FIRST ALLOWLIST (STARTUP BUDGET)
1. `AGENTS.md`
2. `docs/project/vision.md`
3. `docs/project/strategic_goals.md`
4. `docs/project/tactical_goals.md`
5. `docs/project/operational_goals.md`
6. `docs/adr/20260322-synthesis-architecture-v7-v9.md`
7. `diary/2026-03-23--route-module-gen-through-synthesis-runtime.md`

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
- Slice executed: `AK-251` — module-gen: route through the synthesis runtime single-candidate path with static/smoke validation and receipts.
- Outcome: `module_service` now executes through the synthesis runtime for cold renders and cache hits, the runtime validates/selects the single candidate and can promote it through the explicit shell, and `module-gen` receipts now carry synthesis IDs/bundles plus run summaries for replay/explain.
- Files changed: `packages/dspx-core/src/dspx/synthesis/runtime.py`, `packages/dspx-core/src/dspx/synthesis/__init__.py`, `packages/dspx-core/src/dspx/synthesis/contracts.py`, `packages/dspx-core/src/dspx/services/module_service.py`, `packages/dspx-core/src/dspx/cli/commands/module.py`, `packages/dspx-core/src/dspx/cli/dspx.py`, `tests/test_synthesis_contracts.py`, `tests/test_module_service.py`, `tests/test_run_receipts.py`, `docs/project/tactical_goals.md`, `docs/project/operational_goals.md`, `diary/2026-03-23--route-module-gen-through-synthesis-runtime.md`, `next_session_prompt.md`, and `governance/work-items.json` after AK export.
- Validation commands + results: `uv run pytest tests/test_synthesis_contracts.py tests/test_module_service.py tests/test_cli_dspx.py tests/test_run_receipts.py -q` ✅; `uv run ruff check packages/dspx-core/src/dspx/synthesis/contracts.py packages/dspx-core/src/dspx/synthesis/runtime.py packages/dspx-core/src/dspx/synthesis/__init__.py packages/dspx-core/src/dspx/services/module_service.py packages/dspx-core/src/dspx/cli/commands/module.py packages/dspx-core/src/dspx/cli/dspx.py tests/test_synthesis_contracts.py tests/test_module_service.py tests/test_run_receipts.py` ✅; `./scripts/ci/smoke.sh` ✅; `just verify-full` ✅; `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅; `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅.
- Source-of-truth updates: `docs/project/tactical_goals.md` now promotes `TG3` to active and marks `TG2` complete; `docs/project/operational_goals.md` now points at `AK-256` as the next ready slice and records `AK-251` as complete; the new diary captures the runtime-validation/promotion-receipt pattern.
- Next-session starting point: claim `AK-256` and add true multi-candidate fan-out plus ranked selection receipts on top of the current runtime shell.

## END-OF-SESSION
Run `/commit` and ensure this file reflects the real checkpoint for the next operator/agent.
