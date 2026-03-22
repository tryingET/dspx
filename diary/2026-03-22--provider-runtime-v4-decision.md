# 2026-03-22 — Provider Runtime V4 Decision

## What I Did
- Reviewed the existing `dspy-template-adapter` blocker map and treated issues #1, #2, and #6 as still-good reasons not to vendor the adapter into DSPx's critical path.
- Shipped a DSPx-local mixed-provider runtime path instead:
  - added explicit `openai-compatible`, `vllm-local`, and `dspy-lm-auth` providers,
  - added provider resolve / health / benchmark CLI commands,
  - added config-loader support for mixed-provider runtime sections and optimize defaults,
  - captured redacted provider/runtime metadata in run receipts and GEPA manifests.
- Documented the decision in `docs/adr/20260322-provider-runtime-v4.md` and updated the roadmap/source-of-truth docs.
- Marked `DSPX-M4-01` done and queued `DSPX-M4-02` for live environment verification.

## What Surprised Me
- The provider-registry seam was already strong enough that the real unblock was not a template-adapter fork; it was making the mixed-provider runtime explicit and observable.
- Receipt-safe provider metadata turned out to be part of the decision quality, because it lets replay/explain and optimize outputs stay auditable once multiple providers are involved.

## Patterns
- When an upstream optional dependency is still unstable, unblock the product by strengthening the local seam you already own instead of pulling the upstream maintenance burden into the repo prematurely.
- Mixed-provider workflows need three things together to feel real: config defaults, operator-facing health/benchmark commands, and redacted runtime metadata in artifacts.

## Crystallization Candidates
- If DSPx adds more provider families, keep the runtime provider-registry-first and require each provider to supply both health semantics and replay-safe metadata instead of hiding transport details in service-specific code.
