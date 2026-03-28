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
- Objective (one sentence): Claim `AK-386` and freeze the next dated SG2 contract after the completed candidate-prior audit without widening evidence authority or changing V7 ranking/promotion behavior.
- Constraints (hard limits): Keep the repo green under `./scripts/ci/smoke.sh`; do not widen candidate-prior authority beyond the read-only audit contract without a new dated ADR; keep live execution truth in AK.
- Assumptions (max 3): `AK-379` is done and committed; `TG13` is complete; `TG14` is the active planning wave after the completed audit implementation.
- Blockers (none or list): none.

## READ-FIRST ALLOWLIST (STARTUP BUDGET)
1. `AGENTS.md`
2. `docs/project/vision.md`
3. `docs/project/strategic_goals.md`
4. `docs/project/tactical_goals.md`
5. `docs/project/operational_goals.md`
6. `docs/adr/20260327-synthesis-evidence-candidate-prior-v1.md`
7. `docs/adr/20260327-synthesis-evidence-candidate-prior-audit-v1.md`
8. `diary/2026-03-27--emit-post-selection-candidate-prior-audit.md`

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
- Slice executed: `AK-431` — fail closed partial candidate-prior audit rank coverage under metadata drift without changing V7 ranking or promotion behavior.
- Outcome: DSPx now omits `candidate_prior_audit` rank context whenever ranked metadata does not fully cover the audited candidate set, preventing receipts from mixing trustworthy and missing order in the same audit.
- Files changed: `diary/2026-03-28--fail-closed-partial-candidate-prior-audit-rank-coverage.md`, `docs/project/operational_goals.md`, `governance/task-scopes/AK-431.json`, `governance/work-items.json`, `next_session_prompt.md`, `packages/dspx-core/src/dspx/services/module_synthesis_evidence.py`, and `tests/test_module_synthesis_evidence.py`.
- Validation commands + results: `uv run pytest tests/test_module_synthesis_evidence.py -q` ✅; `uv run pytest tests/test_module_synthesis_evidence.py tests/test_module_service.py tests/test_run_receipts.py -q` ✅; `python scripts/check_task_scope.py --task-id 431 --mode working-tree` ✅; `./scripts/ci/smoke.sh` ✅; `just verify-full` ✅; `ak task complete 431 ...` ✅; `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅; `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅.
- Source-of-truth updates: `AK-431` is complete as an operator-directed guardrail fix; `TG14` remains active; `AK-386` is still the next ready SG2 planning slice.
- Next-session starting point: inspect the repo-scoped ready queue, then claim `AK-386` and freeze the next dated SG2 contract after the completed candidate-prior audit before editing runtime code again.

## END-OF-SESSION
Run `/commit` and ensure this file reflects the real checkpoint for the next operator/agent.
