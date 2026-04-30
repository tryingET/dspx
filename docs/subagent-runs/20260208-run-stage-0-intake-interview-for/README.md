---
summary: "Archived subagent-run artifact: Subagent run template."
read_when:
  - "You are auditing the archived subagent-run workflow output."
  - "You need the recorded artifact for Subagent run template."
type: "reference"
---

# Subagent run template

Copy this folder to `docs/subagent-runs/<RUN_ID>/`.

Initialize run metadata first:
- `run.manifest.json` (set `run_id`, timestamps, initial attributes)

Stage 0 intake supports interview-first:
- `00-intake/interview-4d.questions.json`
- `00-intake/interview-4d.responses.md`
- `00-intake/brief.md`
- `00-intake/kickoff-gate-checklist.md`

Canonical attribute contract:
- `docs/subagent-runs/schema/system4d-attrs.schema.json`

Fill artifacts in stage order:
1. `00-intake`
2. `10-explorers`
3. `20-synthesis`
4. `30-prompt-factory`
5. `40-domain-drafts`
6. `50-consensus`
7. `60-implementation`
8. `70-qa`
9. `80-release`
10. `90-operations`
