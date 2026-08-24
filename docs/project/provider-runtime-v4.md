---
summary: "Superseded historical provider-runtime-v4 reference; Decision 118 defines the active typed provider architecture."
read_when:
  - "You encounter provider-runtime-v4 history while migrating to the typed hard cutover."
---

# Provider Runtime V4 — superseded

Provider Runtime V4 was the former mixed local/auth-backed architecture. Its
`dspy-lm-auth`, OpenAI-compatible, vLLM, CLI, RPC, registration, health,
benchmark, and `MultiProviderLM` commands are no longer active DSPx surfaces.
Do not follow old V4 command examples or restore its compatibility bridges.

Decision 118 and
[`20260809-dspy-3-3-typed-lm-hard-cutover.md`](../adr/20260809-dspy-3-3-typed-lm-hard-cutover.md)
supersede this runtime with:

- exact DSPy and DSPy-AI 3.3.0;
- DSPx-owned provider/effect/receipt ports;
- exactly one `DSPyTypedLMAdapter` owning DSPy's typed lifecycle;
- a T3 support matrix with the `StubProvider` canary and one separately restored,
  credential-free IP-literal loopback HTTP `OpenAICompatibleProvider`, with explicit
  network policy opt-in and receipt-bound bounded attempt evidence;
- deterministic pre-effect rejection for unsupported or unknown provider names;
- no compatibility registration, response facsimile, fallback, aggregate LM,
  auth checkout, or live-provider command;
- future provider breadth only through separately reviewed additive restoration.

The accepted V4 ADR and repository history remain available solely to explain
the superseded design and migration lineage. They do not authorize current
execution, credentials, provider effects, release, or activation.

For current behavior, read:

- [`../ARCHITECTURE.md`](../ARCHITECTURE.md)
- [`developer_workflow.md`](developer_workflow.md)
- [`2026-08-09-dspy-3-3-typed-lm-hard-cutover-implementation-plan.md`](2026-08-09-dspy-3-3-typed-lm-hard-cutover-implementation-plan.md)
