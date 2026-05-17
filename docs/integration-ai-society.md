---
summary: "Notes for integrating DSPx with ai-society workflows."
read_when:
  - "You are connecting DSPx to ai-society workflows."
  - "You need integration context across DSPx and ai-society."
type: "reference"
---

# DSPx → ai-society Integration

## Context

DSPx and ai-society KES both implement "knowledge crystallization" but on different substrates:
- **Oracle**: crystallizes behavioral knowledge from executions (runs → embeddings → topology)
- **KES**: crystallizes process knowledge from sessions (diary → learnings → TIPs)

The conceptual parallel suggests these should be unified or at least adjacent.

## The Parallel

| Oracle Concept | KES Concept | Unified Meaning |
|----------------|-------------|-----------------|
| Attractors | Patterns | What converges reliably |
| Drift | Anti-patterns | What changed / went wrong |
| Contracts | Heuristics | Invariants that should hold |
| Causal chains | TIP propagation | Lineage of cause → effect |
| Execution context | TIP provenance | Where did this come from |

Both ask: "What did we learn that we didn't know before?"

## The Opportunity

Integrating DSPx into ai-society's `softwareco/owned/` structure would:

1. **Bring KES infrastructure** — `docs/learnings/`, TIPs, cognitive tools
2. **Enable cross-project propagation** — learnings from DSPx could inform other owned repos
3. **Unify crystallization** — behavioral (Oracle) + process (KES) in one place
4. **Shared tooling** — `docs-list.sh`, `engineering.sh`, cognitive tools in AGENTS.md

## Integration Options

### A) Relocate + Template

Move `~/programming/dspx` → `~/ai-society/softwareco/owned/dspx`

```
~/ai-society/softwareco/owned/dspx/
├── docs/
│   ├── _core/          # From template (immutable)
│   ├── learnings/      # KES: dated learning entries
│   ├── owned/          # DSPx-specific docs
│   ├── org_context/    # From template
│   └── system4d/       # Compass, fog, engine, container
├── packages/dspx-core/ # Existing code
├── apps/forge/         # Existing code
└── AGENTS.md           # Updated with ai-society tooling
```

**Pros:** Full KES integration, clean structure
**Cons:** Repo move, path changes, potential CI disruption

### B) In-Place Overlay

Keep DSPx at `~/programming/dspx`, add KES structure as overlay

```
~/programming/dspx/
├── docs/
│   ├── learnings/      # Add KES structure
│   └── ...existing...
└── AGENTS.md           # Updated with ai-society tooling refs
```

**Pros:** No move, minimal disruption
**Cons:** Partial integration, no template enforcement

### C) Fresh Template + Migrate

Create new repo from template, migrate code + history

**Pros:** Cleanest template application
**Cons:** Most work, migration complexity

## Constraints

- DSPx is active development → minimize disruption
- Git history must be preserved
- Existing CI/docs should continue working
- Should work with ai-society's `docs-list`, `engineering` tooling

## Decision Points

1. **When?** Now, or after specific milestone (e.g., Oracle Phase C)?
2. **Which approach?** A, B, or C?
3. **First step?** Likely: `copier copy ~/ai-society/softwareco/tpl-owned-repo/ ~/ai-society/softwareco/owned/dspx`

## Open Questions

- Does DSPx need the full `docs/system4d/` structure, or subset?
- Should Oracle's "Knowledge Crystallized" section migrate to `docs/learnings/`?
- How to handle existing docs (VISION.md, ARCHITECTURE.md, etc.)?
- TIPs for DSPx: domain-only, or meta escalation too?

---

## Next Actions

- [ ] Decide on approach (A/B/C)
- [ ] Decide on timing (now / after milestone)
- [ ] First integration step
