---
summary: "Core docs reference for DSPx"
read_when:
  - "When needing governance/ontology context"
  - "When cross-referencing ai-society standards"
---

# Core Docs Reference

DSPx participates in ai-society's Knowledge Evolution System (KES).

## Primary Sources

- Governance: `~/ai-society/holdingco/governance-kernel/`
- Ontology: `~/ai-society/core/ontology-kernel/`
- Templates: `~/ai-society/softwareco/tpl-owned-repo/`

## KES Integration

DSPx has:
- `docs/learnings/` — Crystallized patterns from sessions
- `docs/owned/` — DSPx-specific documentation
- `docs/system4d/` — Compass, fog, engine, container

## Cross-Project Links

- Oracle behavioral crystallization → process crystallization (KES)
- Receipt causal chains → TIP propagation patterns
- Attractors ≈ Patterns, Drift ≈ Anti-patterns

## Tooling Access

```bash
# Docs discovery
node ~/ai-society/core/agent-scripts/scripts/docs-list.mjs --task "<task>" --top 8

# Engineering guidance (immutable, heading-first, and bounded)
python3 scripts/engineering_guidance.py lane headings
python3 scripts/engineering_guidance.py lane range 72 88
```

## Cognitive Prompts

Prompt Vault is canonical for reusable cognitive prompts and procedures.

When applying named prompts such as `nexus`, `inversion`, `audit`, `blast-radius`, `escape-hatch`, or `knowledge-crystallization`:

1. discover or confirm the template with `vault_query` unless the exact vault name is already known;
2. run `vault_dispatch_check` before applying it;
3. retrieve/use template text only when dispatch posture permits text-only use;
4. use the required orchestrator/workflow binding when dispatch check says text-only execution is not lawful.
