# Project-local pi extensions

## 4d-intake-router

Path:
- `.pi/extensions/4d-intake-router.ts`

Behavior:
1. On first non-command message after session start, converts freeform intent/handoff text into a proposed:
   - `/interview-4d-intake <RUN_ID> <TASK_TITLE> <DB_PATH_OR_NONE> [EXTRA_CONTEXT...]`
2. Prefills the editor with that command (propose-only, not auto-send).
3. Watches `interview` tool results:
   - if completed + kickoff gate fields present: proposes `/subagent-4d-kickoff ...` with mapped attributes
   - if timed out/cancelled/aborted or required fields missing: proposes session recovery rerun command

Debug commands:
- `/s4d-router-status`
- `/s4d-router-reset`

Notes:
- canonical attribute contract: `docs/subagent-runs/schema/system4d-attrs.schema.json`
- kickoff proposal should only be accepted when `00-intake/kickoff-gate-checklist.md` passes.

Fixture tests:
- TypeScript fixture script: `scripts/test_system4d_intake_router_fixtures.ts`
- pytest wrapper: `tests/test_system4d_intake_router_fixtures.py`
