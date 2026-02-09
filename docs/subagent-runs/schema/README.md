---
summary: "Canonical System4D attribute schema used by intake/kickoff prompt templates and extension command generation."
read_when:
  - "You are changing `/interview-4d-intake` or `/subagent-4d-kickoff` argument contracts."
  - "You are updating extension-generated slash commands for System4D workflows."
---

# System4D attribute schema

Source of truth:
- `docs/subagent-runs/schema/system4d-attrs.schema.json`

Use it for:
- prompt-template argument expectations
- extension slot extraction and command synthesis
- run manifest validation in QA stage

Canonical semantics:
- `run_id`: authoritative artifact path key for the current run (related handoff run IDs should be annotated, not silently substituted).
- `db_path_or_none`: Stage-1 DB explorer input path (read-only), not an interview answer storage location.
- if `db_path_or_none` is explicit and missing locally, kickoff is blocked until a DB-clarification recovery step resolves the path.

Current workflow version:
- `system4d-v1.0`
