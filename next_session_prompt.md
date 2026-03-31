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
- Objective (one sentence): The repo-scoped ready queue is empty after `AK-645`; wait for operator direction or the next truthful post-`TG23` contract/materialization step before starting a new implementation slice.
- Constraints (hard limits): Keep the cleaned-up AK-native task-scope workflow/help contract intact; do not regress snapshot-first authority or reintroduce handoff-based task binding; keep `docs/project/operational_goals.md` and this file aligned.
- Assumptions (max 3): `AK-645` is complete and reflected in `governance/work-items.json`; no new SG2 tactical goal has been materialized yet; no repo-scoped ready task currently exists at `HEAD`.
- Blockers (none or list): none.

## READ-FIRST ALLOWLIST (STARTUP BUDGET)
1. `AGENTS.md`
2. `docs/project/vision.md`
3. `docs/project/strategic_goals.md`
4. `docs/project/tactical_goals.md`
5. `docs/project/operational_goals.md`
6. `docs/project/developer_workflow.md`
7. `Justfile`
8. `diary/2026-03-31--harden-standardized-justfile-surface-with-side-effect-free-probes-and-target-aware-checks.md`
9. `governance/work-items.json`

## EXECUTION MODE (ONE SESSION = ONE SLICE)
1. Choose one highest-leverage actionable slice from `governance/work-items.json` unless operator direction overrides it. In this repo, treat that file as a checked-in projection and confirm the live slice against AK before acting.
2. Confirm the ready queue with `ak task ready -F json | jq 'map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx"))'`.
3. If the repo-scoped ready queue is empty, do not start a new implementation slice; wait for operator direction or the next truthful post-`TG23` contract/materialization step.
4. If a repo-scoped ready task exists, claim the current active task before editing docs or code.
5. Implement at most one operating slice end-to-end.
6. Validate the slice with:
   - `./scripts/ci/smoke.sh`
   - `just verify-full`
7. Update source-of-truth docs/diary/ADR references before commit.

## SESSION CHECKPOINT (UPDATE BEFORE /commit)
- Slice executed: `AK-645` — harden the standardized Justfile surface with side-effect-free probes and target-aware checks.
- Outcome: the public standardized `just doctor` and `just run` targets are now side-effect-free on a clean tree, plain `just run` truthfully falls back to DSPx CLI help, and the workflow-contract checker/tests now validate specific recipe bodies plus adversarial/runtime behavior instead of only raw substring presence.
- Files changed: `Justfile`, `diary/2026-03-31--harden-standardized-justfile-surface-with-side-effect-free-probes-and-target-aware-checks.md`, `docs/project/operational_goals.md`, `docs/tech-stack.local.md`, `governance/task-scopes/AK-645.snapshot.json`, `governance/work-items.json`, `next_session_prompt.md`, `scripts/check_workflow_contracts.py`, and `tests/test_workflow_contracts.py`.
- Validation commands + results: `python3 scripts/check_workflow_contracts.py` ✅; `uv run -m pytest -q tests/test_workflow_contracts.py` ✅; `git checkout -- uv.lock && just doctor` ✅ (`uv.lock` stayed clean); `git checkout -- uv.lock && just run` ✅ (zero-arg help fallback worked and `uv.lock` stayed clean); `just task-scope-check task_id=645 mode=working-tree` ✅; `./scripts/ci/smoke.sh` ✅; `just verify-full` ✅ (then restored incidental pre-existing `uv.lock` drift from other syncful `uv run` validation paths outside the public-target hardening scope); `ak task complete 645 --result '{...}'` ✅; `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅; `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅; `ak task ready -F json | jq 'map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx")) | map({id,title})'` ✅ after completion (empty queue).
- Source-of-truth updates: recorded the Justfile hardening pass in `diary/2026-03-31--harden-standardized-justfile-surface-with-side-effect-free-probes-and-target-aware-checks.md`; refreshed `docs/project/operational_goals.md`, `docs/tech-stack.local.md`, and this handoff to the post-`AK-645` empty-queue state; exported `governance/task-scopes/AK-645.snapshot.json`; and refreshed `governance/work-items.json` after the AK completion/export.
- Next-session starting point: if the repo-scoped AK ready queue is still empty, wait for operator direction or the next truthful post-`TG23` contract/materialization step; otherwise claim the next ready repo-local slice before editing.

## END-OF-SESSION
Run `/commit` and ensure this file reflects the real checkpoint for the next operator/agent.
