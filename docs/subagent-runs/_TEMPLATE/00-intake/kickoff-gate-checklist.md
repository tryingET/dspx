---
summary: "Subagent-run template artifact: Kickoff gate checklist."
read_when:
  - "You are using or updating the subagent-run template structure."
  - "You need the template artifact for Kickoff gate checklist."
type: "reference"
---

# Kickoff gate checklist

Gate intent:
- Only propose `/subagent-4d-kickoff ...` when this checklist passes.

## Required attributes (must be non-empty)

- [ ] `RUN_ID`
- [ ] `TASK_TITLE`
- [ ] `DRIVER`
- [ ] `OUTCOME`
- [ ] `CONSTRAINTS`
- [ ] `BOUNDARY`
- [ ] `EDGES_DEPENDENCIES`
- [ ] `DB_PATH_OR_NONE` (`none` allowed when unresolved; include candidate notes)
- [ ] `SUCCESS_CRITERIA`

## Intake quality

- [ ] Interview completed (not timed out/cancelled), or explicit fallback rationale documented
- [ ] Hard constraints vs preferences separated in `brief.md`
- [ ] Invariants captured in `brief.md`
- [ ] Top risks + mitigations captured in `brief.md`
- [ ] Open questions for explorers captured in `brief.md`

## Decision

- [ ] Gate PASS -> propose kickoff command
- [ ] Gate FAIL -> propose session recovery rerun command

## Reviewer

- Name:
- Timestamp:
- Notes:
