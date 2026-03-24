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
- Objective (one sentence): Claim `AK-337` and define the first post-diagnostics SG2 contract/next execution slice before starting more implementation.
- Constraints (hard limits): Keep the repo green under `just verify-full`; do not start predictive ranking or policy mutation without an explicit contract/AK slice; preserve the read-only evidence posture where the current diagnostics seam depends on it.
- Assumptions (max 3): `AK-278` is complete; `TG7` is complete and `TG8` is now active; the next step is contract-setting/planning rather than more ad-hoc coding.
- Blockers (none or list): None.

## READ-FIRST ALLOWLIST (STARTUP BUDGET)
1. `AGENTS.md`
2. `docs/project/vision.md`
3. `docs/project/strategic_goals.md`
4. `docs/project/tactical_goals.md`
5. `docs/project/operational_goals.md`
6. `docs/adr/20260322-synthesis-architecture-v7-v9.md`
7. `docs/adr/20260323-synthesis-evidence-retrieval-v1.md`
8. `diary/2026-03-24--implement-module-synthesis-evidence-bundle.md`
9. `diary/2026-03-24--surface-synthesis-evidence-diagnostics.md`

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
- Slice executed: `AK-278` — synthesis evidence substrate: thread the v1 evidence bundle into `module-gen` diagnostics without changing ranking.
- Outcome: `module-gen` now surfaces the v1 evidence bundle through bounded `synthesis_diagnostics` metadata and persisted receipts, so later SG2/V8 work can consume explicit evidence artifacts instead of rediscovering history ad hoc.
- Files changed: `packages/dspx-core/src/dspx/services/module_service.py`, `packages/dspx-core/src/dspx/cli/commands/module.py`, `tests/test_module_service.py`, `tests/test_run_receipts.py`, `docs/project/tactical_goals.md`, `docs/project/operational_goals.md`, `diary/2026-03-24--surface-synthesis-evidence-diagnostics.md`, `governance/task-scopes/AK-278.json`, `next_session_prompt.md`, and `governance/work-items.json` after AK export.
- Validation commands + results: `uv run -m pytest -q tests/test_module_service.py tests/test_run_receipts.py -k 'module_service_simple or cli_meta_receipts_are_versioned'` ✅; `./scripts/ci/smoke.sh` ✅; `just verify-full` ✅; `ak evidence record --task 278 --check-type validation:verify-full --result pass --details '{"commands":["uv run -m pytest -q tests/test_module_service.py tests/test_run_receipts.py -k \"module_service_simple or cli_meta_receipts_are_versioned\"","./scripts/ci/smoke.sh","just verify-full"]}'` ✅; `ak task complete 278 --result '{"summary":"Surfaced the v1 module-synthesis evidence bundle in runtime diagnostics and module-gen receipts without changing ranking behavior.","next_task":337}'` ✅; `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅; `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅.
- Source-of-truth updates: `TG7`/`AK-278` are marked complete; `TG8`/`AK-337` now point at the next contract-setting SG2 slice.
- Next-session starting point: inspect the ready queue, claim `AK-337`, and keep predictive ranking/policy mutation out of scope until that contract-backed task is complete.

## END-OF-SESSION
Run `/commit` and ensure this file reflects the real checkpoint for the next operator/agent.
