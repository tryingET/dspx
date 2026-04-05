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
- Objective (one sentence): Claim `AK-799`, then execute one remaining `TG25` security slice unless the operator explicitly redirects the queue.
- Constraints (hard limits): Keep the completed `TG24` runtime-boundary hardening wave closed unless a surfaced regression or a smaller `TG25` prerequisite explicitly reopens one seam; preserve the `AK-797` trusted-program-root boundary; preserve the `AK-798` narrowed contract-expression boundary; preserve fail-closed SG2 boundary semantics.
- Assumptions (max 3): `AK-798` is closed in AK and reflected in the checked-in projection; the truthful repo-scoped ready queue now begins with `AK-799`/`AK-800`; `governance/work-items.json` remains a checked-in mirror rather than the live scheduler.
- Blockers (none or list): `just task-scope-check 798 working-tree` currently fails in this shared worktree because many pre-existing unrelated tracked/untracked files already fall outside `AK-798` scope; isolate or clean the worktree before expecting working-tree scope validation to pass for the next slice.

## READ-FIRST ALLOWLIST (STARTUP BUDGET)
1. `AGENTS.md`
2. `docs/project/vision.md`
3. `docs/project/strategic_goals.md`
4. `docs/project/tactical_goals.md`
5. `docs/project/operational_goals.md`
6. `docs/project/developer_workflow.md`
7. `Justfile`
8. `diary/2026-04-05--replace-contract-expression-eval-with-ast-interpreter.md`
9. `governance/work-items.json`

## EXECUTION MODE (ONE SESSION = ONE SLICE)
1. Choose one highest-leverage actionable slice from `governance/work-items.json` unless operator direction overrides it. In this repo, treat that file as a checked-in projection and confirm the live slice against AK before acting.
2. Confirm the ready queue with `./scripts/ak.sh task ready -F json | jq 'map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx"))'`.
3. If the repo-scoped ready queue is empty, stay in the truthful idle `TG25` waiting state unless the operator explicitly redirects the session.
4. If a repo-scoped ready task exists, claim the current active task before editing docs or code.
5. Implement at most one operating slice end-to-end.
6. Validate the slice with:
   - `./scripts/ci/smoke.sh`
   - `just verify-full`
7. Update source-of-truth docs/diary/ADR references before commit.

## SESSION CHECKPOINT (UPDATE BEFORE /commit)
- Slice executed: `AK-798` — replace contract-expression `eval()` with a tiny AST interpreter and tighter helper/attribute allowlists.
- Outcome: DSPx contract expressions now run through a tiny AST interpreter instead of Python `eval()`, only expose a read-only embedding view plus explicit helper calls, reject arbitrary method calls / non-allowlisted functions / arbitrary attribute traversal, and keep compatibility for safe field and comparison usage; the checked-in AK projection now truthfully shows `AK-799`/`AK-800` as the remaining ready queue.
- Files changed: `diary/2026-04-05--replace-contract-expression-eval-with-ast-interpreter.md`, `docs/project/operational_goals.md`, `governance/task-scopes/AK-798.snapshot.json`, `governance/work-items.json`, `next_session_prompt.md`, `packages/dspx-core/src/dspx/coordinates/contracts.py`, and `tests/test_coordinates_phase_b.py`.
- Validation commands + results: `uvx ruff format packages/dspx-core/src/dspx/coordinates/contracts.py tests/test_coordinates_phase_b.py` ✅; `uvx ruff check packages/dspx-core/src/dspx/coordinates/contracts.py tests/test_coordinates_phase_b.py` ✅; `uvx ty check packages/dspx-core/src/dspx/coordinates/contracts.py` ✅; `uv run --no-sync -m pytest -q tests/test_coordinates_phase_b.py -k 'SafeExpressionEvaluation'` ✅; `uv run --no-sync -m pytest -q tests/test_coordinates_phase_b.py` ✅; `just task-scope-check 798 working-tree` ⚠️ fails in this shared worktree because many pre-existing unrelated tracked/untracked files already fall outside `AK-798` scope; `./scripts/ak.sh task show 798 -F json` ✅ (`status=done`); `./scripts/ak.sh task ready --repo /home/tryinget/ai-society/softwareco/owned/dspx -F json` ✅ (`[799,800]`); `./scripts/ak.sh work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅; `./scripts/ak.sh work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅; `./scripts/ci/smoke.sh` ✅; `just verify-full` ⚠️ fails because `verify-fast` binds to the completed `AK-798` slice in the still-dirty shared worktree and the many pre-existing unrelated tracked/untracked files remain outside that task scope.
- Source-of-truth updates: recorded the `AK-798` implementation + closure in `diary/2026-04-05--replace-contract-expression-eval-with-ast-interpreter.md`, refreshed `docs/project/operational_goals.md` and this handoff to point at the remaining truthful `TG25` queue, kept `governance/task-scopes/AK-798.snapshot.json` as the frozen slice export, and refreshed `governance/work-items.json` after AK completion.
- Next-session starting point: confirm the repo-scoped ready queue and, absent operator override, claim `AK-799` next.

## END-OF-SESSION
Run `/commit` and ensure this file reflects the real checkpoint for the next operator/agent.
