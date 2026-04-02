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
- Objective (one sentence): Claim `AK-709` and land the final `TG24` slice by tightening SG2 receipt/explain/openapi/rate-limit boundary parsing without widening live policy authority.
- Constraints (hard limits): Keep the `AK-707` server artifact/confirmation behavior and the `AK-708` multi-provider runtime hardening unchanged; preserve fail-closed boundary semantics; do not bundle the later `TG25` governance-to-live contract into the `AK-709` commit unless a smaller prerequisite doc tweak is strictly required.
- Assumptions (max 3): `AK-708` is complete and exported in `governance/work-items.json`; the repo-scoped ready queue now points at `AK-709`; `TG24` should close once `AK-709` lands.
- Blockers (none or list): none.

## READ-FIRST ALLOWLIST (STARTUP BUDGET)
1. `AGENTS.md`
2. `docs/project/vision.md`
3. `docs/project/strategic_goals.md`
4. `docs/project/tactical_goals.md`
5. `docs/project/operational_goals.md`
6. `docs/project/developer_workflow.md`
7. `Justfile`
8. `diary/2026-04-02--materialize-tg24-runtime-boundary-hardening-wave.md`
9. `diary/2026-04-02--persist-server-artifacts-and-confirmation-boundaries.md`
10. `diary/2026-04-02--harden-multi-provider-runtime-boundaries.md`
11. `governance/work-items.json`

## EXECUTION MODE (ONE SESSION = ONE SLICE)
1. Choose one highest-leverage actionable slice from `governance/work-items.json` unless operator direction overrides it. In this repo, treat that file as a checked-in projection and confirm the live slice against AK before acting.
2. Confirm the repo-scoped ready queue with `ak task ready -F json | jq 'map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx"))'` and verify it points at `AK-709`.
3. Claim `AK-709` before editing docs or code.
4. Keep the implementation bounded to SG2 receipt parsing, MLflow explain artifact matching, OpenAPI numeric strictness, rate-limit token parsing, and only the adjacent regressions needed to fail closed.
5. Do not reopen the landed `AK-707`/`AK-708` runtime boundaries unless `AK-709` exposes a narrower shared fix that cannot stay isolated.
6. Implement at most one operating slice end-to-end.
7. Validate the slice with:
   - `./scripts/ci/smoke.sh`
   - `just verify-full`
8. Update source-of-truth docs/diary/ADR references before commit.

## SESSION CHECKPOINT (UPDATE BEFORE /commit)
- Slice executed: `AK-708` — harden multi-provider orchestration with dynamic capability aggregation, request-message preservation, policy override restoration, dirty-worktree-safe git-worktree isolation, and hung-loser cleanup.
- Outcome: DSPx now derives `providers capabilities` from runtime-resolved provider metadata, materializes message history before fan-out so forward/generate-only providers see the same request payload, restores temporary policy overrides after each multi-provider run, falls back from git worktrees to mirror isolation when dirty repos would hide local edits, and force-cleans hung async losers before isolated workspace cleanup.
- Files changed: `docs/project/tactical_goals.md`, `docs/project/operational_goals.md`, `governance/task-scopes/AK-708.snapshot.json`, `governance/work-items.json`, `next_session_prompt.md`, `packages/dspx-core/src/dspx/cli/commands/providers.py`, `packages/dspx-core/src/dspx/multi_provider_lm.py`, `packages/dspx-core/src/dspx/task_scope.py`, `scripts/ak.sh`, `scripts/check_direction_to_execution.py`, `tests/test_multi_provider_parallel_semantics.py`, `tests/test_provider_v4.py`, and `diary/2026-04-02--harden-multi-provider-runtime-boundaries.md`.
- Validation commands + results: `uv run --no-sync -m pytest -q tests/test_multi_provider_caps.py tests/test_multi_provider_parallel_semantics.py tests/test_provider_registry.py tests/test_provider_v4.py` ✅; `./scripts/ci/smoke.sh` ✅; `just task-scope-check task_id=708 mode=working-tree` ⚠️ skipped (`governance/task-scopes/AK-708.snapshot.json` explicitly says repo-default scope applies); `just verify-full` ✅; `./scripts/ak.sh task complete 708 --result '{...}'` ✅; `./scripts/ak.sh work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅; `./scripts/ak.sh work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅; `./scripts/ak.sh task ready -F json | jq 'map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx")) | map({id,title})'` ✅ (`AK-709` ready).
- Source-of-truth updates: recorded the `AK-708` implementation in `diary/2026-04-02--harden-multi-provider-runtime-boundaries.md`, refreshed the `TG24` operating docs and handoff for `AK-709`, restored the missing repo-local `./scripts/ak.sh` wrapper plus validation-side wrapper preference so repo-scoped AK commands stay deterministic again, exported `governance/task-scopes/AK-708.snapshot.json`, and refreshed `governance/work-items.json` after the AK completion/export.
- Next-session starting point: claim `AK-709`, keep the slice bounded to boundary-parser strictness plus the directly supporting regressions, and close `TG24` without jumping early to the later governance-to-live contract.

## END-OF-SESSION
Run `/commit` and ensure this file reflects the real checkpoint for the next operator/agent.
