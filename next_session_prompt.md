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
- Live execution truth: `ak task ... --repo /home/tryinget/ai-society/softwareco/owned/dspx`
- Planned active/deferred work map: `governance/work-items.json` (legacy checked-in projection/mirror; do not treat as live execution truth)
- Raw session capture: `diary/`

## SESSION PREFLIGHT (FILL BEFORE EXECUTION)
- Objective (one sentence): Claim `AK-263` and define the first SG2 tactical slice plus the receipt/replay/Oracle retrieval contract ranked synthesis should consume first.
- Constraints (hard limits): Keep the repo green under `just verify-full`; preserve the ranked module-synthesis hardening shipped under `AK-260`; do not start predictive ranking implementation before the evidence contract is explicit.
- Assumptions (max 3): `SG1` is materially complete after the module-synthesis hardening pass; `SG2` is now the active strategic goal; the V7/V8/V9 architecture reference remains `docs/adr/20260322-synthesis-architecture-v7-v9.md`.
- Blockers (none or list): None.

## READ-FIRST ALLOWLIST (STARTUP BUDGET)
1. `AGENTS.md`
2. `docs/project/vision.md`
3. `docs/project/strategic_goals.md`
4. `docs/project/tactical_goals.md`
5. `docs/project/operational_goals.md`
6. `docs/adr/20260322-synthesis-architecture-v7-v9.md`
7. `diary/2026-03-23--module-synthesis-regression-corpus.md`

## EXECUTION MODE (ONE SESSION = ONE SLICE)
1. Choose one highest-leverage actionable slice from `governance/work-items.json` unless operator direction overrides it. In this repo, treat that file as a checked-in projection and confirm the live slice against AK before acting.
2. Confirm the ready queue with `ak task ready -F json | jq 'map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx"))'`.
3. Claim the current active task before editing code.
4. Implement one operating slice end-to-end.
5. Validate:
   - `./scripts/ci/smoke.sh`
   - `just verify-full`
6. Update source-of-truth docs/diary/ADR references before commit.

## SESSION CHECKPOINT (UPDATE BEFORE /commit)
- Slice executed: `AK-266` — workflow guardrails: add task-scope attestation and semantic synthesis receipt invariants.
- Outcome: `just verify-full` now enforces an attested scope manifest for the latest claimed task slice, module-synthesis receipt checks validate semantic candidate/workspace/evaluation/ranking consistency, and real `module-gen` runs emit module-quality events instead of relying on CI-only synthetic telemetry.
- Files changed: `packages/dspx-core/src/dspx/task_scope.py`, `packages/dspx-core/src/dspx/services/module_service.py`, `packages/dspx-core/src/dspx/services/module_synthesis_quality.py`, `packages/dspx-core/src/dspx/services/module_synthesis_corpus.py`, `scripts/check_task_scope.py`, `scripts/check_workflow_contracts.py`, `tests/test_task_scope.py`, `tests/test_module_synthesis_quality_runtime.py`, `tests/test_module_synthesis_quality_corpus.py`, `tests/test_repo_hygiene.py`, `governance/task-scopes/AK-266.json`, `Justfile`, `docs/project/developer_workflow.md`, `docs/tech-stack.local.md`, `CONTRIBUTING.md`, `README.md`, `docs/project/operational_goals.md`, `diary/2026-03-23--task-scope-attestation-and-receipt-invariants.md`, `next_session_prompt.md`, and `governance/work-items.json` after AK export.
- Validation commands + results: `uv run -m pytest -q tests/test_task_scope.py tests/test_module_synthesis_quality_runtime.py tests/test_module_synthesis_quality_corpus.py tests/test_module_synthesis_quality_summary.py tests/test_module_synthesis_golden_corpus.py tests/test_module_service.py tests/test_repo_hygiene.py` ✅; `uv run -q python scripts/build_module_synthesis_quality_log.py` ✅; `just task-scope-check` ✅; `./scripts/ci/smoke.sh` ✅; `just verify-full` ✅; `ak evidence record --task 266 --check-type validation:verify-full --result pass --details '{"commands":["./scripts/ci/smoke.sh","just verify-full"]}'` ✅; `ak task complete 266 --result '{"summary":"Added task-scope attestation to verify-full and hardened semantic receipt invariants/runtime module-quality telemetry.","next_task":263}'` ✅; `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅; `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅.
- Source-of-truth updates: `docs/project/operational_goals.md` records `AK-266` as recently completed and notes the new scope-manifest requirement for claimed tasks; the new diary captures the task-scope + receipt-invariant pattern.
- Next-session starting point: claim `AK-263`, freeze the SG2 evidence retrieval contract, and only then decompose the first V8-facing implementation slice.

## END-OF-SESSION
Run `/commit` and ensure this file reflects the real checkpoint for the next operator/agent.
