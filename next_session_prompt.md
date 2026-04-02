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
- Objective (one sentence): Claim `AK-708` and land the second `TG24` slice by hardening multi-provider orchestration without widening live policy authority.
- Constraints (hard limits): Keep the `AK-707` server artifact/confirmation behavior unchanged; preserve request/policy isolation and fail-closed capability semantics; do not bundle `AK-709` parser/strictness work into the `AK-708` commit unless strict dependency pressure forces a narrower shared fix.
- Assumptions (max 3): `AK-707` is complete and exported in `governance/work-items.json`; the repo-scoped ready queue now points at `AK-708`; `AK-709` remains staged behind `AK-708`.
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
10. `governance/work-items.json`

## EXECUTION MODE (ONE SESSION = ONE SLICE)
1. Choose one highest-leverage actionable slice from `governance/work-items.json` unless operator direction overrides it. In this repo, treat that file as a checked-in projection and confirm the live slice against AK before acting.
2. Confirm the repo-scoped ready queue with `ak task ready -F json | jq 'map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx"))'` and verify it points at `AK-708`.
3. Claim `AK-708` before editing docs or code.
4. Keep the implementation bounded to multi-provider orchestration, dynamic capability aggregation, request-message preservation, policy override restoration, dirty-worktree-safe isolation, and loser cleanup.
5. If the current working tree still mixes `AK-709` edits into the `AK-708` slice, split or park them before commit so the second `TG24` landing stays sharp.
6. Implement at most one operating slice end-to-end.
7. Validate the slice with:
   - `./scripts/ci/smoke.sh`
   - `just verify-full`
8. Update source-of-truth docs/diary/ADR references before commit.

## SESSION CHECKPOINT (UPDATE BEFORE /commit)
- Slice executed: `AK-707` — persist server-generated artifacts and confirmation boundaries across signature/module/mermaid.
- Outcome: DSPx server mutations now persist stable signature/module artifacts plus mermaid output directories under `generated/server/` (or `DSPX_SERVER_OUTPUT_DIR`), return stable public artifact refs, enforce `X-DSPX-Confirm` across all mutating endpoints when `DSPX_CONFIRM_MUTATIONS=1`, and degrade truthfully when persistence fails.
- Files changed: `docs/SERVER.md`, `docs/project/strategic_goals.md`, `docs/project/tactical_goals.md`, `docs/project/operational_goals.md`, `governance/task-scopes/AK-707.snapshot.json`, `governance/work-items.json`, `next_session_prompt.md`, `packages/dspx-core/src/dspx/cli/utils.py`, `packages/dspx-core/src/dspx/server/app.py`, `tests/test_server_api.py`, `tests/test_server_confirm_mutations.py`, `diary/2026-04-02--materialize-tg24-runtime-boundary-hardening-wave.md`, and `diary/2026-04-02--persist-server-artifacts-and-confirmation-boundaries.md`.
- Validation commands + results: `uv run --no-sync -m pytest -q tests/test_server_api.py tests/test_server_confirm_mutations.py` ✅; `python3 scripts/check_direction_to_execution.py` ✅; `./scripts/ci/smoke.sh` ✅; `just task-scope-check task_id=707 mode=working-tree` ✅ (repo-default snapshot exported); `just verify-full` ✅; `ak task complete 707 --result '{...}'` ✅; `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅; `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅; `ak task ready -F json | jq 'map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx")) | map({id,title})'` ✅ (`AK-708` ready).
- Source-of-truth updates: recorded the `AK-707` implementation in `diary/2026-04-02--persist-server-artifacts-and-confirmation-boundaries.md`, refreshed `docs/SERVER.md` plus the `SG2`/`TG24` operating docs and handoff, exported `governance/task-scopes/AK-707.snapshot.json`, and refreshed `governance/work-items.json` after the AK completion/export.
- Next-session starting point: claim `AK-708`, keep the slice bounded to multi-provider runtime hardening, and leave the parser/strictness follow-on for `AK-709` unless strict dependency pressure forces a smaller shared fix.

## END-OF-SESSION
Run `/commit` and ensure this file reflects the real checkpoint for the next operator/agent.
