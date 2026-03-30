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
- Objective (one sentence): Claim `AK-562` and implement the ADR-backed read-only shadow predictive-ranking advisory for `module-gen` outcomes.
- Constraints (hard limits): Do not widen evidence authority beyond `docs/adr/20260329-synthesis-evidence-shadow-predictive-ranking-advisory-v1.md`; keep live execution truth in AK; keep `docs/project/operational_goals.md` and this file aligned.
- Assumptions (max 3): `AK-561` is complete and committed; the repo-scoped ready queue exposes `AK-562`; SG3 AK-native scope-snapshot work remains blocked on cross-repo `AK-548` and is not the active wave.
- Blockers (none or list): none.

## READ-FIRST ALLOWLIST (STARTUP BUDGET)
1. `AGENTS.md`
2. `docs/project/vision.md`
3. `docs/project/strategic_goals.md`
4. `docs/project/tactical_goals.md`
5. `docs/project/operational_goals.md`
6. `docs/adr/20260329-synthesis-evidence-shadow-predictive-ranking-advisory-v1.md`
7. `diary/2026-03-29--refresh-sg2-decomposition-and-materialize-shadow-ranking-wave.md`

## EXECUTION MODE (ONE SESSION = ONE SLICE)
1. Choose one highest-leverage actionable slice from `governance/work-items.json` unless operator direction overrides it. In this repo, treat that file as a checked-in projection and confirm the live slice against AK before acting.
2. Confirm the ready queue with `ak task ready -F json | jq 'map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx"))'`.
3. If the repo-scoped ready queue is empty, do not start a new implementation slice; wait for operator direction or the next truthful decomposition/materialization step.
4. If a repo-scoped ready task exists, claim the current active task before editing docs or code.
5. Implement at most one operating slice end-to-end.
6. Validate the slice with:
   - `./scripts/ci/smoke.sh`
   - `just verify-full`
7. Update source-of-truth docs/diary/ADR references before commit.

## SESSION CHECKPOINT (UPDATE BEFORE /commit)
- Slice executed: `AK-564` — prefer the workspace contrib `dspy-lm-auth` checkout for local editable installs.
- Outcome: Added a repo-local helper that installs and verifies `~/ai-society/softwareco/contrib/dspy-lm-auth`, updated the provider/runtime workflow docs to prefer that contrib checkout, tightened the runtime import guidance, verified the active environment now resolves `dspy_lm_auth` from the contrib repo, and kept `AK-562` as the next ready SG2 implementation slice.
- Files changed: `Justfile`, `README.md`, `diary/2026-03-29--prefer-contrib-dspy-lm-auth-checkout.md`, `docs/UPSTREAM_CONTRIBUTING_WORKFLOW.md`, `docs/project/developer_workflow.md`, `docs/project/operational_goals.md`, `docs/project/provider-runtime-v4.md`, `docs/tech-stack.local.md`, `governance/task-scopes/AK-564.json`, `governance/work-items.json`, `next_session_prompt.md`, `packages/dspx-core/src/dspx/dspy_lm_auth_lm.py`, `tests/test_provider_v4.py`.
- Validation commands + results: `just link-dspy-lm-auth` ✅; `uv run python -c "import dspy_lm_auth; print(dspy_lm_auth.__file__)"` ✅; `uv run -m pytest -q tests/test_provider_v4.py tests/test_workflow_contracts.py` ✅; `just workflow-contract-check` ✅; `just task-scope-check task_id=564 mode=working-tree` ✅; `./scripts/ci/smoke.sh` ✅; `just verify-full` ✅; `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅; `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅.
- Source-of-truth updates: refreshed `README.md`, `docs/UPSTREAM_CONTRIBUTING_WORKFLOW.md`, `docs/project/developer_workflow.md`, `docs/project/provider-runtime-v4.md`, `docs/tech-stack.local.md`, and `docs/project/operational_goals.md`; updated `next_session_prompt.md`; recorded the session in `diary/2026-03-29--prefer-contrib-dspy-lm-auth-checkout.md`; refreshed `governance/work-items.json`; and added `governance/task-scopes/AK-564.json`.
- Next-session starting point: re-run the repo-scoped ready queue filter, then claim `AK-562` if it is still ready; if the local auth-backed provider checkout needs to be reattached first, run `just link-dspy-lm-auth`.

## END-OF-SESSION
Run `/commit` and ensure this file reflects the real checkpoint for the next operator/agent.
