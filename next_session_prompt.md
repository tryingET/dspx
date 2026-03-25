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
- Objective (one sentence): Claim `AK-341` and emit the read-only historical convergence advisory defined in `docs/adr/20260324-synthesis-evidence-history-advisory-v1.md` on live runtime metadata/receipts.
- Constraints (hard limits): Keep the repo green under `just verify-full`; preserve V7 ranking/promotion behavior; do not turn advisory posture into predictive scoring, pruning, or policy mutation.
- Assumptions (max 3): `AK-337` and `AK-346` are complete; `TG8` is complete and `TG9` is now active; the advisory should reuse the existing evidence bundle instead of re-running independent evidence discovery by default.
- Blockers (none or list): None.

## READ-FIRST ALLOWLIST (STARTUP BUDGET)
1. `AGENTS.md`
2. `docs/project/vision.md`
3. `docs/project/strategic_goals.md`
4. `docs/project/tactical_goals.md`
5. `docs/project/operational_goals.md`
6. `docs/adr/20260323-synthesis-evidence-retrieval-v1.md`
7. `docs/adr/20260324-synthesis-evidence-history-advisory-v1.md`
8. `diary/2026-03-24--freeze-post-diagnostics-sg2-contract.md`
9. `diary/2026-03-24--fail-closed-task-scope-validation.md`

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
- Slice executed: `AK-346` — fail closed task-scope verification across multi-commit slices.
- Outcome: `just task-scope-check` now fails closed when it cannot resolve task binding, validates the full attested task slice from manifest introduction through `HEAD` in head mode, and the handoff doc no longer points at invalid `ak task ... --repo` syntax.
- Files changed: `packages/dspx-core/src/dspx/task_scope.py`, `scripts/check_task_scope.py`, `Justfile`, `tests/test_task_scope.py`, `tests/test_workflow_contracts.py`, `docs/project/developer_workflow.md`, `docs/tech-stack.local.md`, `diary/2026-03-24--fail-closed-task-scope-validation.md`, `governance/task-scopes/AK-346.json`, `next_session_prompt.md`, and `governance/work-items.json` after AK export.
- Validation commands + results: `uv run -m pytest -q tests/test_task_scope.py tests/test_workflow_contracts.py` ✅; `uvx ty check packages/dspx-core/src/dspx/task_scope.py scripts/check_task_scope.py` ✅; `./scripts/ci/smoke.sh` ✅; `just verify-full` ⚠️ blocked by pre-existing repo-wide `just typecheck` failures outside the AK-346 slice; `ak evidence record --task 346 --check-type validation:targeted-slice --result pass --details '{"commands":["uv run -m pytest -q tests/test_task_scope.py tests/test_workflow_contracts.py","uvx ty check packages/dspx-core/src/dspx/task_scope.py scripts/check_task_scope.py","./scripts/ci/smoke.sh"],"blocked_commands":["just verify-full"]}'` ✅; `ak evidence record --task 346 --check-type validation:verify-full --result fail --details '{"command":"just verify-full","blocked_by":["packages/dspx-core/src/dspx/cli/commands/providers.py","packages/dspx-core/src/dspx/cli/dspx_mermaid2dspy.py","packages/dspx-core/src/dspx/tools/registry.py"]}'` ✅; `ak task complete 346 --result '{"summary":"Made task-scope validation fail closed and validate full multi-commit task slices instead of skipping on missing task binding or checking only HEAD^..HEAD.","next_task":341}'` ✅; `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅; `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅.
- Source-of-truth updates: workflow docs now describe fail-closed/full-slice task-scope validation; `AK-341` remains the next SG2 implementation slice.
- Next-session starting point: inspect the ready queue, claim `AK-341`, and emit the advisory on runtime metadata/receipts without changing ranking or promotion semantics.

## END-OF-SESSION
Run `/commit` and ensure this file reflects the real checkpoint for the next operator/agent.
