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
- Live execution truth: `./scripts/ak.sh task ready -F json | jq 'map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx"))'`
- Planned active/deferred work map: `governance/work-items.json` (checked-in projection/mirror; do not treat as live execution truth)
- Latest completed-slice diary: `diary/2026-04-05--land-ak835-tg25-atomic-hardening-cleanup.md`
- Latest direction refresh diary: `diary/2026-04-05--materialize-next-tg25-hardening-wave.md`
- Latest repo-local learning: `docs/learnings/2026-02-28-receipt-v2-phase-c.md`

## SESSION PREFLIGHT (FILL BEFORE EXECUTION)
- Objective (one sentence): Confirm the repo-scoped ready queue is still empty after `AK-835` and only materialize/promote the next truthful `TG26` slice if AK truth names it.
- Constraints (hard limits): Keep the completed `AK-797`, `AK-798`, `AK-799`, `AK-800`, `AK-834`, and `AK-835` boundaries closed; do not reopen the closed `TG25` hardening wave as a generic cleanup queue.
- Assumptions (max 3): the repo is back to a validation-clean baseline; `governance/work-items.json` remains a checked-in mirror; the next truthful move is a bounded `TG26` promotion/materialization step rather than another implicit `TG25` patch.
- Blockers (none or list): none.

## READ-FIRST ALLOWLIST (STARTUP BUDGET)
1. `AGENTS.md`
2. `docs/project/vision.md`
3. `docs/project/strategic_goals.md`
4. `docs/project/tactical_goals.md`
5. `docs/project/operational_goals.md`
6. `docs/project/developer_workflow.md`
7. `Justfile`
8. `diary/2026-04-05--land-ak835-tg25-atomic-hardening-cleanup.md`
9. `diary/2026-04-05--materialize-next-tg25-hardening-wave.md`
10. `governance/work-items.json`

## EXECUTION MODE (ONE SESSION = ONE SLICE)
1. Choose one highest-leverage actionable slice from `governance/work-items.json` unless operator direction overrides it. In this repo, treat that file as a checked-in projection and confirm the live slice against AK before acting.
2. Confirm the repo-scoped ready queue with `./scripts/ak.sh task ready -F json | jq 'map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx"))'`.
3. If the ready queue is empty, do not guess a hidden cleanup backlog; only materialize/promote the next slice when AK truth and the direction stack justify it.
4. Execute at most one operating slice end-to-end.
5. Validate truthfully with:
   - `./scripts/ci/smoke.sh`
   - `just task-scope-check task_id=<AK-ID> mode=working-tree`
   - `just verify-full`
6. Refresh source-of-truth docs/diary/ADR references before commit.

## SESSION CHECKPOINT (UPDATE BEFORE /commit)
- Slice executed: `AK-835` — closed the remaining atomic hardening cleanup across config-managed env refresh, config TOML secret rejection, provider/runtime sanitization, policy bypass audit logging, registry locking, Pi retry boundaries, refine TTY gating, receipt env-hash redaction, bounded previews, generated-code worker fail-closed handling, and task-scope claim fallback.
- Outcome: `AK-835` is complete in AK, the repo-scoped ready queue is empty again, and the repo returns to a truthful validation-clean baseline without reopening the closed `TG25` hardening wave.
- Files changed: `packages/dspx-core/src/dspx/config_loader.py`, `packages/dspx-core/src/dspx/generated_code_guard.py`, `packages/dspx-core/src/dspx/pi_rpc_lm.py`, `packages/dspx-core/src/dspx/policy.py`, `packages/dspx-core/src/dspx/provider_registry.py`, `packages/dspx-core/src/dspx/provider_runtime.py`, `packages/dspx-core/src/dspx/run_receipts.py`, `packages/dspx-core/src/dspx/services/refine_service.py`, `packages/dspx-core/src/dspx/task_scope.py`, `packages/dspx-core/src/dspx/tools/registry.py`, `tests/test_config_loader.py`, `tests/test_provider_runtime.py`, `tests/test_refine_service_memory.py`, `tests/test_run_receipts.py`, `tests/test_tg25_atomic_completion.py`, `governance/task-scopes/AK-835.snapshot.json`, `docs/project/operational_goals.md`, `governance/work-items.json`, `diary/2026-04-05--land-ak835-tg25-atomic-hardening-cleanup.md`, `next_session_prompt.md`.
- Validation commands + results: `uv run --no-sync -m pytest -q tests/test_task_scope.py tests/test_config_loader.py tests/test_provider_runtime.py tests/test_provider_v4.py tests/test_provider_registry.py tests/test_policy_tools_and_providers.py tests/test_refine_service_memory.py tests/test_run_receipts.py tests/test_pi_rpc_provider_unit.py tests/test_policy_capabilities.py tests/test_policy_capabilities_fs.py tests/test_openapi_dry_run_cli.py tests/test_tg25_atomic_completion.py` ✅; `./scripts/ak.sh work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅; `./scripts/ci/smoke.sh` ✅; `just task-scope-check task_id=835 mode=working-tree` ✅; `just verify-full` ✅.
- Source-of-truth updates: completed `AK-835` in AK with result evidence, exported `governance/task-scopes/AK-835.snapshot.json`, re-exported `governance/work-items.json`, refreshed `docs/project/operational_goals.md`, and replaced the handoff with the post-`AK-835` clean-baseline starting point.
- Next-session starting point: confirm the repo-scoped ready queue is still empty, then materialize/promote the next bounded `TG26` slice only when AK truth explicitly names it.

## END-OF-SESSION
Run `/commit` only if the repo is validation-clean and the handoff reflects the real checkpoint; otherwise preserve the truthful handoff and leave commit/closeout for the isolated slice.
