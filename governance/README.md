---
summary: "Governance artifacts index for DSPx."
read_when:
  - "You are looking for DSPx governance artifacts."
  - "You need to understand governance files in this repo."
type: "reference"
---

# Governance Artifacts

AK DB is canonical for live task/work-item truth.

## Purpose

`governance/work-items.json` is a legacy compatibility projection. It is not live execution state, not the planning authority, and not a landing gate for routine validation.

Use Agent Kernel directly for current DSPx work selection and execution state:

```bash
ak task ready --repo /home/tryinget/ai-society/softwareco/owned/dspx
ak task list --repo /home/tryinget/ai-society/softwareco/owned/dspx
ak task show <AK-ID>
```

If a future consumer still needs a checked-in compatibility projection, refresh or verify it only in an explicitly scoped projection-maintenance slice.

Projects may also use:
- Git issues / milestones
- FCOS work-items (for cross-repo work)
- External trackers

## Ontology

```
Milestone > Issue > Task
```

## State Machine

```
triage → queued → doing → review → done
```

| State | Meaning |
|-------|---------|
| triage | Not yet shaped |
| queued | Ready to start |
| doing | In progress |
| review | Awaiting review |
| done | Complete |

## Structure

| Field | Description |
|-------|-------------|
| `id` | Issue ID (e.g., `PROJ-M1-01`) |
| `title` | Short description |
| `state` | `triage` \| `queued` \| `doing` \| `review` \| `done` |
| `tasks` | List of tasks with `text` and `done` |
| `dod` | Definition of done |

## Validation

Routine validation follows the AK-native gates in `docs/project/developer_workflow.md`. The legacy projection is compatibility-only and is not part of the default `just check` landing path.

## Program vs Project

| Type | Location | Scope | Operational? |
|------|----------|-------|--------------|
| **Program** | governance-kernel/governance/programs/ | Cross-company | Yes |
| **Program** | company-templates/governance/programs/ | Company | No |
| **Project** | AK task/work-item state for this repo | This repo | Yes |
| **Legacy projection** | repo/governance/work-items.json | This repo | No |

## When to Use This vs Alternatives

| Use AK When | Use Alternative When |
|---------------|---------------------|
| Work is specific to this repo | Work spans multiple repos (→ FCOS) |
| You need live task authority | Simple bugs (→ git issues) |
| You need claim/scope/evidence lifecycle | Quick notes (→ docs/diary/learnings as appropriate) |

## Related

- L0 Programs: `governance-kernel/governance/programs/`
- L1 Programs: `company-templates/governance/programs/`
- State Machine: `governance-kernel/governance/fcos/state-machine.yaml`
- Glossary: `governance-kernel/docs/core/glossary.md`
