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
- Objective (one sentence): Claim `AK-317` and remove the repo-local `rocs_cli` GitLab baseline-resolution compatibility path now that `AK-473`/`TG19` are complete.
- Constraints (hard limits): Do not widen evidence authority beyond the read-only candidate-prior payload/audit/divergence/readiness/counterfactual layers without a dated contract; keep live execution truth in AK; keep `docs/project/operational_goals.md` and this file aligned.
- Assumptions (max 3): `AK-473` is done and committed; `TG19` is complete; the repo-scoped ready queue now falls back to `AK-317` until a later SG2 contract is frozen.
- Blockers (none or list): none.

## READ-FIRST ALLOWLIST (STARTUP BUDGET)
1. `AGENTS.md`
2. `docs/project/vision.md`
3. `docs/project/strategic_goals.md`
4. `docs/project/tactical_goals.md`
5. `docs/project/operational_goals.md`
6. `docs/adr/20260328-synthesis-evidence-candidate-prior-counterfactual-advisory-v1.md`
7. `diary/2026-03-28--emit-candidate-prior-counterfactual-advisory.md`

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
- Slice executed: `AK-473` — emit a read-only candidate-prior counterfactual advisory for `module-gen` outcomes.
- Outcome: DSPx now emits `candidate_prior_counterfactual_advisory` on live `module-gen` metadata and persisted receipts, deriving bounded counterfactual statuses and passing positive-prior-supported alternatives from the existing audit/divergence/readiness surfaces plus trusted current comparison metadata without changing V7 ranking or promotion behavior.
- Files changed: `diary/2026-03-28--emit-candidate-prior-counterfactual-advisory.md`, `docs/project/operational_goals.md`, `docs/project/tactical_goals.md`, `governance/task-scopes/AK-473.json`, `governance/work-items.json`, `next_session_prompt.md`, `packages/dspx-core/src/dspx/services/module_service.py`, `packages/dspx-core/src/dspx/services/module_synthesis_evidence.py`, `tests/test_module_service.py`, `tests/test_module_synthesis_evidence.py`, and `tests/test_run_receipts.py`.
- Validation commands + results: `uv run -m pytest -q tests/test_module_synthesis_evidence.py tests/test_module_service.py tests/test_run_receipts.py` ✅; `uv run -q python scripts/check_task_scope.py --task-id 473 --mode working-tree` ✅; `./scripts/ci/smoke.sh` ✅; `just verify-full` ✅; `ak task complete 473 ...` ✅; `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅; `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅.
- Source-of-truth updates: `AK-473` is complete; `TG19` is complete; no next SG2 implementation slice is pinned yet, so the repo-scoped ready queue currently points at `AK-317`.
- Next-session starting point: confirm the repo-scoped ready queue still points at `AK-317`, then claim it and remove the repo-local `rocs_cli` GitLab baseline-resolution compatibility path unless the operator redirects the repo back to a new SG2 contract slice.

## END-OF-SESSION
Run `/commit` and ensure this file reflects the real checkpoint for the next operator/agent.
