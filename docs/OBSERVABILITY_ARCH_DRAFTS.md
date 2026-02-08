---
summary: "Start-here packet for observability architecture drafts across DSPx, MLflow, and DSPy boundaries."
read_when:
  - "You are kicking off architecture drafts with domain experts for MLflow/DSPy follow-ups."
  - "You need ownership boundaries and deliverables for DSPx vs upstream work."
---

# Observability Architecture Drafts (Start Here)

## Purpose

Prepare clean handoff docs so domain experts can draft architecture in a new context window.

## Current baseline (already landed)

- deterministic local MLflow default: `sqlite:///mlflow.db`
- explicit run start semantics (bootstrap does not start runs)
- DSPy autolog trace collection off by default for stability
- explain local enrichment supports sqlite/file modes
- sqlite custom artifact roots now resolved from MLflow experiment metadata

Read baseline docs first:
- `docs/MLFLOW_OBSERVABILITY_PLAN.md`
- `docs/RUN_REPLAY_EXPLAIN.md`

## Non-negotiable boundaries

- monorepo boundary invariant stays strict:
  - allowed: `apps/* -> core`
  - forbidden: `core -> apps/*`
- no `dspx_forge` imports from core
- DSPy scope here is callback/runtime contract only
- no request to add other observability backends in DSPy

## Draft packets by ownership

1) **DSPx next architecture draft**
- `docs/ARCH_DRAFT_DSPX_NEXT.md`

2) **Upstream MLflow architecture draft (DSPy integration + tracing internals)**
- `docs/ARCH_DRAFT_UPSTREAM_MLFLOW.md`

3) **Upstream DSPy architecture draft (callback contract + context propagation)**
- `docs/ARCH_DRAFT_UPSTREAM_DSPY.md`

## RFC templates (fill-in skeletons)

Use matching template per packet:
- DSPx packet -> `docs/RFC_TEMPLATE_DSPX_NEXT.md`
- MLflow packet -> `docs/RFC_TEMPLATE_UPSTREAM_MLFLOW.md`
- DSPy packet -> `docs/RFC_TEMPLATE_UPSTREAM_DSPY.md`

Recommended flow:
1. copy template into a new RFC file (`docs/rfc/` or agreed location)
2. fill sections with concrete options + evidence
3. link upstream issues/PR plan

## Expected output from each domain expert

For each packet, produce:
1. problem statement + constraints
2. architecture options (A/B/C) + tradeoffs
3. proposed target architecture
4. migration/rollout phases
5. acceptance tests
6. risk register + fallback plan

## New-context-window quick prompt

Use this exact structure:

- Read: `docs/OBSERVABILITY_ARCH_DRAFTS.md`
- Then read the assigned packet doc for your domain
- Start from the matching RFC template and create your draft RFC file
- Draft an architecture RFC with:
  - Decision
  - Interfaces/contracts
  - Compatibility
  - Rollout plan
  - Test plan
  - Open questions requiring cross-team alignment
