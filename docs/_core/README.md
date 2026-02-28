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

# Tech stack
uv tool run --from ~/ai-society/core/tech-stack-core tech-stack-core show py --prefer-repo
```

## Cognitive Triggers

Available at `~/steve/prompts/triggers/`:

| Trigger | When to Use |
|---------|-------------|
| `nexus` | Finding highest-leverage intervention |
| `inversion` | Before solving any problem (shadow analysis) |
| `audit` | Code quality (bugs/debt/smells/gaps) |
| `blast-radius` | Before making changes |
| `escape-hatch` | Before implementing risky changes |
| `first-principles` | When stuck or constraints feel wrong |

Invoke: "Read `~/steve/prompts/triggers/nexus.md`, apply to [context]"
