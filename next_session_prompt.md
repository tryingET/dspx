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
- Objective (one sentence): Confirm the repo-scoped ready queue is still empty after `AK-317` and wait for the next operator-directed slice or a newly frozen SG2 contract before editing code.
- Constraints (hard limits): Do not widen evidence authority beyond the read-only candidate-prior payload/audit/divergence/readiness/counterfactual layers without a dated contract; keep live execution truth in AK; keep `docs/project/operational_goals.md` and this file aligned.
- Assumptions (max 3): `AK-317` is complete and committed; `TG19` remains complete; no next SG2 implementation slice is pinned yet, so the repo-scoped ready queue stays empty unless the operator or AK changes it.
- Blockers (none or list): none.

## READ-FIRST ALLOWLIST (STARTUP BUDGET)
1. `AGENTS.md`
2. `docs/project/vision.md`
3. `docs/project/strategic_goals.md`
4. `docs/project/tactical_goals.md`
5. `docs/project/operational_goals.md`
6. `docs/adr/20260328-synthesis-evidence-candidate-prior-counterfactual-advisory-v1.md`
7. `diary/2026-03-28--remove-rocs-cli-gitlab-baseline-compatibility-path.md`

## EXECUTION MODE (ONE SESSION = ONE SLICE)
1. Choose one highest-leverage actionable slice from `governance/work-items.json` unless operator direction overrides it. In this repo, treat that file as a checked-in projection and confirm the live slice against AK before acting.
2. Confirm the ready queue with `ak task ready -F json | jq 'map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx"))'`.
3. Claim the current active task before editing docs or code.
4. Implement one operating slice end-to-end.
5. Validate:
   - `./scripts/ci/smoke.sh`
   - `just verify-full`
6. Update source-of-truth docs/diary/ADR references before commit.

## SESSION CHECKPOINT (UPDATE BEFORE /commit)
- Slice executed: `AK-317` — remove the repo-local `rocs_cli` GitLab baseline-resolution compatibility path.
- Outcome: DSPx now points its ontology manifest at workspace-only `repo:` locators, no longer vendors `tools/rocs-cli`, and resolves ROCS through workspace core or `PATH` instead of the repo-local compatibility copy.
- Files changed: `diary/2026-03-28--remove-rocs-cli-gitlab-baseline-compatibility-path.md`, `docs/project/operational_goals.md`, `governance/task-scopes/AK-317.json`, `governance/work-items.json`, `next_session_prompt.md`, `ontology/index.md`, `ontology/manifest.yaml`, `scripts/check_direction_to_execution.py`, `scripts/rocs.sh`, and deleted `tools/rocs-cli/**`.
- Validation commands + results: `./scripts/rocs.sh --doctor` ✅; `./scripts/rocs.sh --which` ✅; `uv run -q python scripts/check_task_scope.py --task-id 317 --mode working-tree` ✅; `./scripts/ci/smoke.sh` ✅; `just verify-full` ✅; `ak task complete 317 ...` ✅; `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅; `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅.
- Source-of-truth updates: `AK-317` is complete; `TG19` remains complete; no next SG2 implementation slice is pinned; the repo-scoped ready queue is empty.
- Next-session starting point: confirm the repo-scoped ready queue is still empty, then wait for operator direction or a newly frozen SG2 contract before starting another slice.

## END-OF-SESSION
Run `/commit` and ensure this file reflects the real checkpoint for the next operator/agent.
