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
- Latest completed-slice diary: `diary/2026-04-05--land-ak834-tg25-nexus-fixes.md`
- Latest direction refresh diary: `diary/2026-04-05--materialize-next-tg25-hardening-wave.md`
- Latest repo-local learning: `docs/learnings/tg25-adversarial-review-nexus.md`

## SESSION PREFLIGHT (FILL BEFORE EXECUTION)
- Objective (one sentence): Claim `AK-835` and execute the remaining repo-scoped ready `TG25` hardening slice unless AK truth changes first.
- Constraints (hard limits): Keep the completed `AK-797`, `AK-798`, `AK-799`, `AK-800`, and `AK-834` boundaries closed; do not promote `TG26` or widen live policy authority while `AK-835` remains open.
- Assumptions (max 3): the truthful repo-scoped ready queue now contains only `AK-835`; `governance/work-items.json` remains a checked-in mirror; the current branch should carry a clean `AK-834` completion commit before the next slice starts.
- Blockers (none or list): `just verify-full` still fails on repo-wide task-scope resolution tests that align with the remaining `AK-835` slice; isolate any unrelated dirty files before trusting working-tree scope validation.

## READ-FIRST ALLOWLIST (STARTUP BUDGET)
1. `AGENTS.md`
2. `docs/project/vision.md`
3. `docs/project/strategic_goals.md`
4. `docs/project/tactical_goals.md`
5. `docs/project/operational_goals.md`
6. `docs/project/developer_workflow.md`
7. `Justfile`
8. `diary/2026-04-05--land-ak834-tg25-nexus-fixes.md`
9. `diary/2026-04-05--materialize-next-tg25-hardening-wave.md`
10. `docs/learnings/tg25-adversarial-review-nexus.md`
11. `governance/work-items.json`

## EXECUTION MODE (ONE SESSION = ONE SLICE)
1. Choose one highest-leverage actionable slice from `governance/work-items.json` unless operator direction overrides it. In this repo, treat that file as a checked-in projection and confirm the live slice against AK before acting.
2. Confirm the repo-scoped ready queue with `./scripts/ak.sh task ready -F json | jq 'map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx"))'`.
3. Claim the highest-priority ready task before editing.
4. Execute at most one operating slice end-to-end.
5. Validate truthfully with:
   - `./scripts/ci/smoke.sh`
   - `just task-scope-check task_id=<AK-ID> mode=working-tree`
   - `just verify-full`
6. Refresh source-of-truth docs/diary/ADR references before commit.

## SESSION CHECKPOINT (UPDATE BEFORE /commit)
- Slice executed: `AK-834` — landed the adversarial NEXUS hardening slice across Forge sanitize/workorder handling, shared path confinement, replay path resolution, multi-provider `parallel_first` success/readiness semantics, auth-provider structured error signaling, and Oracle frontier/territory correctness.
- Outcome: `AK-834` is complete in AK, the repo-scoped ready queue now contains only `AK-835`, and the checked-in operating-plan/handoff artifacts point at the remaining truthful `TG25` slice instead of the old dual-ready checkpoint.
- Files changed: `apps/forge/src/dspx_forge/sanitize.py`, `apps/forge/src/dspx_forge/workorder.py`, `packages/dspx-core/src/dspx/security.py`, `packages/dspx-core/src/dspx/services/run_replay_service.py`, `packages/dspx-core/src/dspx/multi_provider_lm.py`, `packages/dspx-core/src/dspx/dspy_lm_auth_lm.py`, `packages/dspx-core/src/dspx/coordinates/frontiers.py`, `packages/dspx-core/src/dspx/coordinates/territory.py`, `tests/test_tg25_nexus_fixes.py`, `tests/test_multi_provider_parallel_semantics.py`, `governance/task-scopes/AK-834.snapshot.json`, `docs/project/operational_goals.md`, `governance/work-items.json`, `diary/2026-04-05--materialize-next-tg25-hardening-wave.md`, `diary/2026-04-05--land-ak834-tg25-nexus-fixes.md`, `next_session_prompt.md`.
- Validation commands + results: `uv run --no-sync -m pytest -q tests/test_tg25_nexus_fixes.py tests/test_multi_provider_parallel_semantics.py` ✅; `uv run --no-sync -m pytest -q tests/test_provider_v4.py` ✅; `./scripts/ak.sh work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅; `./scripts/ci/smoke.sh` ✅; `just task-scope-check 834 working-tree` ✅; `just verify-full` ❌ (`tests/test_task_scope.py` still fails because repo-wide task-scope resolution expects the remaining `AK-835` hardening to land).
- Source-of-truth updates: completed `AK-834` in AK with result evidence, exported `governance/task-scopes/AK-834.snapshot.json`, refreshed `docs/project/operational_goals.md`, re-exported `governance/work-items.json`, and replaced the handoff with the post-`AK-834` starting point.
- Next-session starting point: confirm the repo-scoped ready queue still shows only `AK-835`, claim it, and use the remaining `just verify-full` task-scope failures as the first validation target while executing only that one slice unless AK truth changes first.

## END-OF-SESSION
Run `/commit` only if the repo is validation-clean and the handoff reflects the real checkpoint; otherwise preserve the truthful handoff and leave commit/closeout for the isolated slice.
