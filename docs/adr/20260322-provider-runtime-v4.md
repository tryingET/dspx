---
summary: "Decision to unblock mixed-provider DSPx workflows with a local provider-runtime v4 instead of waiting on dspy-template-adapter fixes."
read_when:
  - "You are changing provider runtime boundaries or mixed-provider workflows."
  - "You need the decision behind `vllm-local`, `openai-compatible`, and `dspy-lm-auth`."
---

ADR 20260322 — Provider Runtime V4
==================================

Status
------
Accepted

Context
-------
`DSPX-M4-01` required an explicit decision on whether DSPx should keep waiting on
upstream `dspy-template-adapter` fixes or move to a local unblock path.

The local blocker map still showed three upstream issues as the practical stop
signals for exact-fidelity adapter integration:
1. XML parsing is brittle for nested tags / CDATA.
2. JSON parsing does not tolerate markdown-wrapped output.
3. Partial demos break optimizer flows.

Vendoring the adapter immediately would pull parser and optimizer-maintenance
risk into DSPx. Waiting on upstream would keep mixed-provider local workflows
stalled even though DSPx already has a provider registry, replay receipts, and a
core-first runtime boundary that can support a local alternative.

Decision
--------
Adopt a **DSPx-local provider-runtime v4** as the unblock path.

That means:
- mixed-provider execution is now modeled explicitly through the provider
  registry rather than through a process-wide adapter monkeypatch,
- `vllm-local` is the supported local student/runtime provider,
- `dspy-lm-auth` is the supported auth-backed remote reflection provider,
- `openai-compatible` remains the generic local/compatible transport,
- provider resolution, health checks, and benchmarks are first-class CLI
  commands,
- optimize flows may take separate student/reflection providers from config, and
- run receipts/manifest metadata capture provider details in a replay-safe,
  redacted form.

We are **not** vendoring `dspy-template-adapter` in this slice.
Exact-fidelity template-adapter support stays optional and upstream-blocked until
those parser/partial-demo issues materially change.

Consequences
------------
Positive:
- DSPx no longer has to wait on adapter fixes to ship a supported mixed-provider
  workflow.
- Provider behavior stays explicit and inspectable via the registry, CLI health
  checks, benchmarks, manifests, and receipts.
- Replay/explain surfaces gain safer provider metadata without leaking secrets.
- GEPA/local workflows can use different student vs reflection providers without
  global `dspy.LM` installation side effects.

Costs / tradeoffs:
- DSPx now owns a larger local provider-runtime surface.
- Live validation of the mixed-provider profile becomes a recurring maintenance
  task as local vLLM and auth-backed routes evolve.
- Template-adapter exact-fidelity work is still deferred; this ADR only removes
  it from the critical path.

Operational note
----------------
Use `docs/project/provider-runtime-v4.md` plus
`config.provider-runtime-v4.example.toml` as the current mixed-provider runtime
reference, then validate with:
- `dspx providers resolve`
- `dspx providers health --probe`
- `dspx providers benchmark`
