---
summary: "Decision to integrate Pi as a first-class provider via persistent RPC mode."
read_when:
  - "You are changing Pi integration strategy or provider runtime boundaries."
  - "You are evaluating one-shot CLI vs persistent provider runtimes."
---

ADR 20260206 — Pi RPC Provider
==============================

Status
------
Accepted

Context
-------
DSPx architecture is provider-first: services (`signature`, `module`, `codegen`, `mermaid`, `optimize`) depend on a common LM provider contract and registry.

Before this ADR, Pi integration options were:
1. One-shot CLI calls (`pi -p ...`) per request.
2. Tool mode (another provider invokes Pi as a tool).
3. Persistent RPC subprocess (`pi --mode rpc`) wrapped as a provider.

We needed a mode that keeps provider interchangeability, reduces repeated startup overhead, and allows explicit timeout/restart handling under policy controls.

Decision
--------
Adopt **Pi as a first-class provider** (`DSPX_PROVIDER=pi-rpc`) implemented via a **persistent RPC subprocess** (`pi --mode rpc`).

Why provider-first:
- Keeps all services on the same LMBase/provider-registry seam.
- Reuses existing policy, tracing, and CLI provider selection flows.
- Avoids service-specific “special path” logic for Pi.

Why RPC (vs `pi -p` one-shot):
- Lower per-call overhead for multi-step workflows.
- Better control over request/response framing, timeout handling, and process restart.
- Cleaner foundation for repeated calls in pipelines (Mermaid, optimize loops, agents).

Why not tool mode:
- Tool mode makes Pi a secondary helper, not a selectable LM runtime.
- Adds prompt/tool orchestration coupling and weaker parity with other providers.
- Harder to reason about provider-level policy/metrics consistency.

Consequences
------------
Positive:
- Faster repeated-call behavior relative to one-shot CLI startup.
- Consistent provider UX (`--provider pi-rpc` / `DSPX_PROVIDER=pi-rpc`).
- Shared policy/tracing hooks across providers.

Costs / tradeoffs:
- More lifecycle complexity (startup handshake, broken pipe, restart behavior).
- Need explicit timeout and crash recovery paths.
- Slightly larger maintenance surface than one-shot mode.

Operational note:
- Keep conservative Pi safety defaults (`DSPX_PI_NO_TOOLS=1`, `DSPX_PI_NO_SESSION=1`, `DSPX_PI_DISABLE_RESOURCES=1`) unless explicitly relaxed.
