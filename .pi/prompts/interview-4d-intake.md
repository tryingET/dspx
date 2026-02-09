---
description: "Run Stage-0 System4D intake interview and normalize results."
---
Run Stage-0 intake interview for:
- `RUN_ID`: `$1`
- `TASK_TITLE`: `$2`
- `DB_PATH_OR_NONE`: `$3`
- `EXTRA_CONTEXT`: `${@:4}`

Tasks:
1. Ensure run path exists: `docs/subagent-runs/$1/00-intake/`.
2. Treat `docs/subagent-runs/schema/system4d-attrs.schema.json` as canonical contract.
3. Resolve DB path input (canonical semantics):
   - `DB_PATH_OR_NONE` means **Stage-1 DB explorer input path (read-only)**, not where interview answers are stored.
   - if `$3` is `none` or empty, attempt auto-discovery with:
     - `fd -HI -t f -e db -e sqlite -e sqlite3 .`
     - fallback: `find . -type f \( -name "*.db" -o -name "*.sqlite" -o -name "*.sqlite3" \) | head -n 20`
   - if one likely candidate found, set `DB_PATH_OR_NONE` to that path
   - if multiple/unclear candidates, keep `none` and list options in `interview-4d.responses.md`
   - if `$3` is explicit (not `none`), keep it canonical; do not silently override from interview selections.
   - if explicit path is missing at runtime, record availability note in `interview-4d.responses.md` and `brief.md`, and include a DB-clarification rerun command using `DB_PATH_OR_NONE=none`.
4. Prepare/adjust `interview-4d.questions.json` for this task.
   - include explicit context text on DB question: "DB file to inspect in Stage-1 DB explorer (read-only), not answer storage".
   - if question responses suggest a different DB path than canonical `$3`, record mismatch note; keep canonical unless user explicitly overrides.
5. If `interview` tool is available, run it and capture answers.
6. If unavailable, do markdown fallback Q/A with same fields.
7. Write outputs:
   - `docs/subagent-runs/$1/00-intake/interview-4d.responses.md`
   - `docs/subagent-runs/$1/00-intake/brief.md`
8. Update gate file `docs/subagent-runs/$1/00-intake/kickoff-gate-checklist.md`.
9. In `brief.md`, include:
   - hard constraints vs preferences
   - invariants
   - top 3 risks + mitigations
   - success criteria
   - open questions for explorers
10. If interview is incomplete/cancelled:
   - DO NOT propose kickoff command
   - write session recovery steps under `interview-4d.responses.md`
   - include rerun command suggestion for `/interview-4d-intake ...`
