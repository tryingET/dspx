---
summary: "Long-horizon product and architecture vision for DSPx."
read_when:
  - "When aligning long-term direction"
  - "When choosing which architecture wave to invest in next"
---

# Vision

DSPx should become the local-first engineering runtime for DSPy systems: a toolkit that can **safely synthesize, optimize, replay, explain, and eventually improve LM-driven programs** without hiding the evidence trail.

## What success looks like

A DSPx user can:
- describe a signature, module, or program intent,
- generate a deterministic artifact from a structured spec,
- validate and optimize it against real provider/runtime constraints,
- replay and explain the result from receipts/manifests, and
- trust that every important decision is inspectable, reproducible, and governable.

## Scope boundaries

DSPx is:
- a local-first DSPy toolkit,
- a provider-agnostic runtime with explicit capability contracts,
- a reproducibility and behavioral-intelligence layer around LM programming.

DSPx is not:
- a hosted SaaS control plane,
- an app-first monolith where core depends on Forge or other apps,
- an uncontrolled self-modifying agent runtime.

## Durable product principles

1. **Core-first architecture** — `packages/dspx-core` is the product; apps remain optional consumers.
2. **Specs before code** — structured intermediate representations should drive rendering, validation, and replay whenever possible.
3. **Receipts before anecdotes** — generated artifacts, evaluations, and promotion decisions must leave durable evidence.
4. **Provider/runtime explicitness** — provider differences stay visible through capability contracts, health checks, manifests, and policy.
5. **Governed autonomy** — higher-order automation is allowed only when its strategy, policy, evidence, and promotion boundaries are explicit.

## Architecture horizon (dated references)

The current architecture direction is recorded in:
- [ADR 20260322 — Provider Runtime V4](../adr/20260322-provider-runtime-v4.md)
- [ADR 20260322 — Synthesis Architecture V7-V9](../adr/20260322-synthesis-architecture-v7-v9.md)

Those ADRs define the long-horizon synthesis stack:

- **V7** — a synthesis runtime that can generate candidate artifacts, evaluate them, select the best passing candidate, and promote it through an explicit policy boundary.
- **V8** — a predictive/evidence-aware layer that uses receipts, Oracle history, and priors to rank or prune candidates before expensive execution.
- **V9** — a governed self-evolution layer where synthesis strategies and policies can be proposed, evaluated, and promoted under explicit controls instead of hidden prompt drift.

## What this implies right now

The next active wave is not "add more surface area"; it is to make `module-gen` the first serious consumer of a **V9-compatible synthesis core while shipping only V7 behavior first**.

That means near-term work should favor:
- synthesis contracts and intermediate representations,
- candidate/evaluation/promotion receipts,
- deterministic rendering + validation,
- module-generation integration through the synthesis runtime,
- clear separation between strategy, evidence, policy, and promotion.

It should defer, until the foundation exists:
- speculative app expansion,
- broad new provider families without evidence needs,
- uncontrolled self-improvement loops,
- exact-fidelity template-adapter work in the critical path.
