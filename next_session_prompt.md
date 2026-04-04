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
- Objective (one sentence): The repo-scoped ready queue is empty after `AK-709`; wait for operator direction or the first truthful `TG25` contract/materialization step before starting a new implementation slice.
- Constraints (hard limits): Keep the completed `TG24` runtime-boundary hardening wave closed unless a surfaced regression or a smaller `TG25` prerequisite explicitly reopens one seam; preserve fail-closed SG2 boundary semantics; use `AK_BIN=ak` for repo-local AK validation in this environment so the wrapper resolves the PATH binary instead of the failing workspace-core cargo path.
- Assumptions (max 3): `AK-709` is complete and exported in `governance/work-items.json`; no repo-scoped ready task currently exists; `TG25` is now the active SG2 tactical wave but its first operating slice has not been materialized yet.
- Blockers (none or list): none.

## READ-FIRST ALLOWLIST (STARTUP BUDGET)
1. `AGENTS.md`
2. `docs/project/vision.md`
3. `docs/project/strategic_goals.md`
4. `docs/project/tactical_goals.md`
5. `docs/project/operational_goals.md`
6. `docs/project/developer_workflow.md`
7. `Justfile`
8. `diary/2026-04-04--tighten-runtime-boundary-parsers-and-mlflow-matching.md`
9. `governance/work-items.json`

## EXECUTION MODE (ONE SESSION = ONE SLICE)
1. Choose one highest-leverage actionable slice from `governance/work-items.json` unless operator direction overrides it. In this repo, treat that file as a checked-in projection and confirm the live slice against AK before acting.
2. Confirm the ready queue with `AK_BIN=ak ./scripts/ak.sh task ready -F json | jq 'map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx"))'`.
3. If the repo-scoped ready queue is empty, do not start a new implementation slice; wait for operator direction or the first truthful `TG25` contract/materialization step.
4. If a repo-scoped ready task exists, claim the current active task before editing docs or code.
5. Implement at most one operating slice end-to-end.
6. Validate the slice with:
   - `AK_BIN=ak ./scripts/ci/smoke.sh`
   - `AK_BIN=ak just verify-full`
7. Update source-of-truth docs/diary/ADR references before commit.

## SESSION CHECKPOINT (UPDATE BEFORE /commit)
- Slice executed: `AK-709` — tighten SG2 receipt parsing, MLflow explain artifact matching, OpenAPI numeric strictness, rate-limit token parsing, and adjacent regression coverage.
- Outcome: DSPx now rejects malformed SG2 historical/governed-policy receipt surfaces during exact-match evidence scans, filters same-artifact local MLflow explain candidates by expected correlation tags, enforces stricter OpenAPI numeric parsing/bounds across query/path/body validation, and fails closed on fractional/zero/negative server rate-limit counts without reopening the landed `AK-707`/`AK-708` boundaries.
- Files changed: `docs/project/operational_goals.md`, `docs/project/strategic_goals.md`, `docs/project/tactical_goals.md`, `governance/task-scopes/AK-709.snapshot.json`, `governance/work-items.json`, `next_session_prompt.md`, `packages/dspx-core/src/dspx/server/security.py`, `packages/dspx-core/src/dspx/services/module_synthesis_evidence.py`, `packages/dspx-core/src/dspx/services/run_explain_service.py`, `packages/dspx-core/src/dspx/tools/openapi/caller.py`, `tests/test_module_synthesis_evidence.py`, `tests/test_openapi_numeric_bounds.py`, `tests/test_run_receipts.py`, `tests/test_server_rate_limit.py`, and `diary/2026-04-04--tighten-runtime-boundary-parsers-and-mlflow-matching.md`.
- Validation commands + results: `uv run --no-sync -m pytest -q tests/test_server_rate_limit.py tests/test_openapi_numeric_bounds.py tests/test_module_synthesis_evidence.py tests/test_run_receipts.py` ✅; `uvx ruff check packages/dspx-core/src/dspx/server/security.py packages/dspx-core/src/dspx/services/module_synthesis_evidence.py packages/dspx-core/src/dspx/services/run_explain_service.py packages/dspx-core/src/dspx/tools/openapi/caller.py tests/test_module_synthesis_evidence.py tests/test_openapi_numeric_bounds.py tests/test_run_receipts.py tests/test_server_rate_limit.py` ✅; `uvx ty check packages/dspx-core/src/dspx/server/security.py packages/dspx-core/src/dspx/services/module_synthesis_evidence.py packages/dspx-core/src/dspx/services/run_explain_service.py packages/dspx-core/src/dspx/tools/openapi/caller.py` ✅; `just task-scope-check 709 working-tree auto` ✅ (repo-default snapshot skip); `AK_BIN=ak ./scripts/ci/smoke.sh` ✅; `AK_BIN=ak just verify-full` ✅; `AK_BIN=ak ./scripts/ak.sh task complete 709 --result '{...}'` ✅; `AK_BIN=ak ./scripts/ak.sh work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅; `AK_BIN=ak ./scripts/ak.sh work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅; `AK_BIN=ak ./scripts/ak.sh task ready -F json | jq 'map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx")) | map({id,title})'` ✅ after completion (empty queue).
- Source-of-truth updates: recorded the `AK-709` implementation in `diary/2026-04-04--tighten-runtime-boundary-parsers-and-mlflow-matching.md`, closed `TG24`, promoted `TG25` to the active tactical wave with an intentionally empty ready queue, exported `governance/task-scopes/AK-709.snapshot.json`, refreshed `governance/work-items.json` after the AK completion/export, and updated the handoff/operating docs to the post-`AK-709` idle-state checkpoint.
- Next-session starting point: re-run the repo-scoped ready-queue check with `AK_BIN=ak ./scripts/ak.sh task ready -F json | jq 'map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx"))'`; if it is still empty, wait for operator direction or the first truthful `TG25` contract/materialization step; otherwise claim the next ready repo-local slice before editing.

## END-OF-SESSION
Run `/commit` and ensure this file reflects the real checkpoint for the next operator/agent.
