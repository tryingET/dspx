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
- Objective (one sentence): Re-run the repo-scoped DSPx AK ready queue filter after `AK-559`; if the queue is still empty, wait for the next operator-directed slice or newly frozen SG2 contract before starting new implementation work.
- Constraints (hard limits): Do not widen evidence authority beyond the read-only candidate-prior payload/audit/divergence/readiness/counterfactual layers without a dated contract; keep live execution truth in AK; keep `docs/project/operational_goals.md` and this file aligned.
- Assumptions (max 3): `AK-559` is complete and committed; no next SG2 implementation slice is pinned yet; any new implementation work still requires either operator direction or a repo-scoped ready AK task.
- Blockers (none or list): none.

## READ-FIRST ALLOWLIST (STARTUP BUDGET)
1. `AGENTS.md`
2. `docs/project/vision.md`
3. `docs/project/strategic_goals.md`
4. `docs/project/tactical_goals.md`
5. `docs/project/operational_goals.md`
6. `docs/adr/20260328-synthesis-evidence-candidate-prior-counterfactual-advisory-v1.md`
7. `diary/2026-03-29--fix-repeated-openapi-local-ref-resolution-across-sibling-branches.md`

## EXECUTION MODE (ONE SESSION = ONE SLICE)
1. Choose one highest-leverage actionable slice from `governance/work-items.json` unless operator direction overrides it. In this repo, treat that file as a checked-in projection and confirm the live slice against AK before acting.
2. Confirm the ready queue with `ak task ready -F json | jq 'map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx"))'`.
3. If the repo-scoped ready queue is empty, do not start a new implementation slice; wait for operator direction or a newly ready AK slice.
4. If a repo-scoped ready task exists, claim the current active task before editing docs or code.
5. Implement at most one operating slice end-to-end.
6. Validate the slice with:
   - `./scripts/ci/smoke.sh`
   - `just verify-full`
7. Update source-of-truth docs/diary/ADR references before commit.

## SESSION CHECKPOINT (UPDATE BEFORE /commit)
- Slice executed: `AK-559` — fix repeated OpenAPI local ref resolution across sibling branches.
- Outcome: Fixed repeated local OpenAPI schema ref resolution so reused sibling properties and combinator branches no longer collapse into unconstrained schemas, added regressions for the surfaced false-pass cases, refreshed the aligned docs/handoff artifacts, and returned the repo to a no-ready-slice state after the operator-directed follow-on validation slice.
- Files changed: `diary/2026-03-29--fix-repeated-openapi-local-ref-resolution-across-sibling-branches.md`, `docs/OPENAPI_TOOLING.md`, `docs/project/operational_goals.md`, `governance/task-scopes/AK-559.json`, `governance/work-items.json`, `next_session_prompt.md`, `packages/dspx-core/src/dspx/tools/openapi/caller.py`, `tests/test_openapi_schema_combinators.py`.
- Validation commands + results: `uv run -m pytest -q tests/test_openapi_schema_combinators.py tests/test_openapi_schema_refs_allof.py tests/test_openapi_numeric_bounds.py tests/test_openapi_url_loading.py` ✅; `uvx ty check packages/dspx-core/src apps/forge/src` ✅; `just task-scope-check task_id=559 mode=working-tree` ✅; `./scripts/ci/smoke.sh` ✅; `just verify-full` ✅; `ak task complete 559 ...` ✅; `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅; `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅; `ak task ready -F json | jq 'map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx"))'` ✅ after completion (`[]`).
- Source-of-truth updates: refreshed `docs/OPENAPI_TOOLING.md` for the repeated-ref behavior, updated `docs/project/operational_goals.md` and `next_session_prompt.md` to the latest current-HEAD checkpoint, recorded the slice in `diary/2026-03-29--fix-repeated-openapi-local-ref-resolution-across-sibling-branches.md`, and added `governance/task-scopes/AK-559.json` for the attested workflow slice.
- Next-session starting point: re-run the repo-scoped `ak task ready` filter; if it is still empty, wait for operator direction or a newly frozen SG2 contract before starting another slice.

## END-OF-SESSION
Run `/commit` and ensure this file reflects the real checkpoint for the next operator/agent.
