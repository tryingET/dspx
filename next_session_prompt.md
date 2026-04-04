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
- Live execution truth: `ak task list -F json | jq 'map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx"))'`
- Planned active/deferred work map: `governance/work-items.json` (legacy checked-in projection/mirror; do not treat as live execution truth)
- Raw session capture: `diary/`

## SESSION PREFLIGHT (FILL BEFORE EXECUTION)
- Objective (one sentence): The repo-scoped ready queue is empty after `AK-729`; wait for operator direction or the first truthful `TG25` contract/materialization step before starting a new implementation slice.
- Constraints (hard limits): Keep the completed `TG24` runtime-boundary hardening wave closed unless a surfaced regression or a smaller `TG25` prerequisite explicitly reopens one seam; preserve fail-closed SG2 boundary semantics; keep the repaired default repo-local AK validation path working without reintroducing the old `AK_BIN=ak` workaround dependency.
- Assumptions (max 3): `AK-729` is complete and exported in `governance/work-items.json`; no repo-scoped ready task currently exists; `TG25` remains the active SG2 tactical wave but its first operating slice has still not been materialized.
- Blockers (none or list): none.

## READ-FIRST ALLOWLIST (STARTUP BUDGET)
1. `AGENTS.md`
2. `docs/project/vision.md`
3. `docs/project/strategic_goals.md`
4. `docs/project/tactical_goals.md`
5. `docs/project/operational_goals.md`
6. `docs/project/developer_workflow.md`
7. `Justfile`
8. `diary/2026-04-04--land-adversarial-tg24-follow-on-fixes.md`
9. `governance/work-items.json`

## EXECUTION MODE (ONE SESSION = ONE SLICE)
1. Choose one highest-leverage actionable slice from `governance/work-items.json` unless operator direction overrides it. In this repo, treat that file as a checked-in projection and confirm the live slice against AK before acting.
2. Confirm the ready queue with `./scripts/ak.sh task ready -F json | jq 'map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx"))'`.
3. If the repo-scoped ready queue is empty, do not start a new implementation slice; wait for operator direction or the first truthful `TG25` contract/materialization step.
4. If a repo-scoped ready task exists, claim the current active task before editing docs or code.
5. Implement at most one operating slice end-to-end.
6. Validate the slice with:
   - `./scripts/ci/smoke.sh`
   - `just verify-full`
7. Update source-of-truth docs/diary/ADR references before commit.

## SESSION CHECKPOINT (UPDATE BEFORE /commit)
- Slice executed: `AK-729` — land the highest-leverage adversarial TG24 follow-on across SG2 receipt validation, local MLflow linkage, sync-provider isolation, OpenAPI numeric enforcement, and AK wrapper fallback.
- Outcome: DSPx now rejects wrong-type exact-match SG2 receipt fields instead of coercing them, accepts compatible partial/nested local MLflow histories without false negatives, keeps sync-provider `cwd` isolation alive until worker completion, enforces `multipleOf` consistently across OpenAPI params/body/items, and restores truthful default `smoke` / `verify-full` validation without requiring `AK_BIN=ak` on this machine.
- Files changed: `docs/project/operational_goals.md`, `governance/task-scopes/AK-729.snapshot.json`, `governance/work-items.json`, `next_session_prompt.md`, `packages/dspx-core/src/dspx/multi_provider_lm.py`, `packages/dspx-core/src/dspx/services/module_synthesis_evidence.py`, `packages/dspx-core/src/dspx/services/run_explain_service.py`, `packages/dspx-core/src/dspx/tools/openapi/caller.py`, `scripts/ak.sh`, `tests/test_module_synthesis_evidence.py`, `tests/test_multi_provider_parallel_semantics.py`, `tests/test_openapi_numeric_bounds.py`, `tests/test_run_receipts.py`, and `diary/2026-04-04--land-adversarial-tg24-follow-on-fixes.md`.
- Validation commands + results: `uv run --no-sync -m pytest -q tests/test_module_synthesis_evidence.py tests/test_run_receipts.py tests/test_multi_provider_parallel_semantics.py tests/test_openapi_numeric_bounds.py` ✅; `uvx ruff check packages/dspx-core/src/dspx/services/module_synthesis_evidence.py packages/dspx-core/src/dspx/services/run_explain_service.py packages/dspx-core/src/dspx/multi_provider_lm.py packages/dspx-core/src/dspx/tools/openapi/caller.py tests/test_module_synthesis_evidence.py tests/test_run_receipts.py tests/test_multi_provider_parallel_semantics.py tests/test_openapi_numeric_bounds.py` ✅; `uvx ty check packages/dspx-core/src/dspx/services/module_synthesis_evidence.py packages/dspx-core/src/dspx/services/run_explain_service.py packages/dspx-core/src/dspx/multi_provider_lm.py packages/dspx-core/src/dspx/tools/openapi/caller.py` ✅; one-off repro harnesses for wrong-type receipts, partial/nested MLflow histories, sync-provider `cwd` isolation, and query `multipleOf` enforcement ✅; `just task-scope-check 729 working-tree auto` ✅ (repo-default snapshot skip); `./scripts/ci/smoke.sh` ✅; `just verify-full` ✅; `./scripts/ak.sh task complete 729 --result '{...}'` ✅; `./scripts/ak.sh work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅; `./scripts/ak.sh work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅; `./scripts/ak.sh task ready -F json | jq 'map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx")) | map({id,title})'` ✅ after completion (empty queue).
- Source-of-truth updates: recorded the `AK-729` implementation in `diary/2026-04-04--land-adversarial-tg24-follow-on-fixes.md`, refreshed `docs/project/operational_goals.md` and this handoff to the post-`AK-729` idle-state checkpoint, exported `governance/task-scopes/AK-729.snapshot.json`, and refreshed `governance/work-items.json` after the AK completion/export.
- Next-session starting point: re-run the repo-scoped ready-queue check with `./scripts/ak.sh task ready -F json | jq 'map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx"))'`; if it is still empty, wait for operator direction or the first truthful `TG25` contract/materialization step; otherwise claim the next ready repo-local slice before editing.

## END-OF-SESSION
Run `/commit` and ensure this file reflects the real checkpoint for the next operator/agent.
