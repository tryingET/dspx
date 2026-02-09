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
- DB precedence rule (canonical):
  - explicit `DB_PATH_OR_NONE` in intake command is authoritative for kickoff
  - interview DB-choice responses are only used when command DB is `none`
  - mismatch is surfaced as warning in UI (no silent override)
  - hard guard: if explicit DB path is missing locally, router prefills a DB-clarification recovery command (`/interview-4d-intake ... "none" ...`) and blocks kickoff proposal until clarified
- RUN_ID disambiguation:
  - router prefers explicit `RUN_ID`
  - warns when multiple run IDs are detected in one message
  - if no explicit `RUN_ID`, first valid run-id mention is used as fallback

Fixture tests:
- TypeScript fixture script: `scripts/test_system4d_intake_router_fixtures.ts`
- pytest wrapper: `tests/test_system4d_intake_router_fixtures.py`
