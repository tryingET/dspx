---
summary: "Repository-level DSPx operating instructions for agents."
read_when:
  - "You are starting work in the DSPx repo."
  - "You need repo-specific guardrails, read order, and commands."
type: "reference"
---

# AGENTS.md — dspx

## Intent
Provide behavioral intelligence for DSPy programs through Oracle analysis and receipt-based replay.

## Guardrails
- No secrets in git.
- Never push to `main`; MRs only.
- Keep `docs/_core/**` as immutable reference.
- Canonical local workflow: `docs/project/developer_workflow.md`.
- Run `just hooks-install` after cloning.

## Generated DSPy program promotion boundary
- DSPx owns generation, replay, local eval, Oracle evidence, and local jury/adjudication sidecars for generated DSPy programs.
- DSPx artifacts do not by themselves approve production activation.
- For generated-program production activation, use the governance-kernel boundary: `~/ai-society/holdingco/governance-kernel/docs/core/definitions/generated-dspy-program-promotion-governance.md`.
- The owning domain or delegated governing body is the judge; AK/current accepted runtime authority records canonical decision/evidence/transition truth where landed.

## Read Order
1. `docs/system4d/compass.md` — Direction
2. `docs/ARCHITECTURE.md` — System design
3. `docs/project/vision.md` — Canonical long-horizon direction
4. `docs/project/strategic_goals.md` — Current strategic frontier
5. `docs/project/tactical_goals.md` — Current tactical frontier
6. `docs/project/operational_goals.md` — Active operating slices / AK mapping
8. `docs/learnings/` — Crystallized patterns

## Stack
- Python 3.13 + uv + just
- Quality gates: ruff + ty + pytest
- 490+ tests must pass

## Commands
```bash
just install          # Setup
just hooks-install    # Install pre-commit + pre-push hooks
just verify-full      # Workflow + governance + repo validation
just fmt lint typecheck test  # Quality gates
just dspx ...         # Run CLI
just forge ...        # Run Forge pipeline
```

## Shared Tooling (ai-society)
```bash
# Docs discovery
node ~/ai-society/core/agent-scripts/scripts/docs-list.mjs --task "<task>" --top 8

# Tech stack
uv tool run --from ~/ai-society/core/tech-stack-core tech-stack-core show py

# Cognitive triggers
~/steve/prompts/triggers/nexus.md
~/steve/prompts/triggers/inversion.md
~/steve/prompts/triggers/audit.md
```

## Oracle Quick Reference
```bash
dspx oracle index --from-receipts     # Populate
dspx oracle search "<query>"          # Find similar
dspx oracle territory                 # Map regions
dspx oracle contract verify           # Check invariants
dspx oracle attractors --health       # Health report
```

## Cognitive Tools (apply proactively)

| Trigger | When to Use |
|---------|-------------|
| `nexus` | Finding highest-leverage intervention |
| `inversion` | Before solving any problem (shadow analysis) |
| `audit` | Code quality (bugs/debt/smells/gaps) |
| `blast-radius` | Before making changes |
| `escape-hatch` | Before implementing risky changes |

Invoke: "Read `~/steve/prompts/triggers/nexus.md`, apply to [context]"

## KES Integration

DSPx bridges two crystallization systems:

| Oracle (Behavioral) | KES (Process) |
|---------------------|---------------|
| Runs → embeddings → topology | Sessions → patterns → TIPs |
| Attractors ≈ Patterns | Drift ≈ Anti-patterns |
| Causal chains ≈ Propagation | |

- **Diary**: `~/ai-society/AGENTS.md` (workspace-level)
- **Learnings**: `docs/learnings/` (this repo)

## Direction workflow
- When this repo's direction docs under `docs/project/` change, or when current posture needs verification, use `ak direction import|check|export` from the repo root.
- Treat `ak direction check` as the authority-reconciliation gate between repo direction docs and AK's structured direction substrate.
