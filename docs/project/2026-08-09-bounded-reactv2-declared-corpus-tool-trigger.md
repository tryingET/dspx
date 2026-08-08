---
summary: "Trigger for deciding whether generated ReActV2 may execute one hash-bound declared-corpus search tool."
read_when:
  - "Reviewing or implementing generated ReActV2 retrieval in DSPx."
type: "proposal"
---

# Trigger: bounded declared-corpus search for generated ReActV2

## Problem

DSPx can materialize bounded `Retriever` modules from `local_corpus_snapshot`, but generated ReActV2 remains no-tool. A requested six-program batch voice-turn needs the deep-research program to perform iterative retrieval through a real ReActV2 callable while retaining the existing local-only safety boundary.

The current renderer and replay policy intentionally emit and require `tools=[]`, `_TOOL_BINDING_ALLOWED = False`, and descriptor-only tool refs. Treating the requested binding as an ordinary implementation change would contradict the accepted program-gen broadening frame and change a durable generated-code/effect/replay contract.

## Significance

This is architecture-significant because it changes generated executable behavior, tool-effect claims, runtime traces, replay invariants, and the boundary between descriptor-only and executable-local tools. The proposal therefore enters the canonical RFC/review/ADR lifecycle before source implementation.

## Requested decision

Decide whether DSPx may add exactly one fixed, pure, materialization-time corpus-snapshot search binding for explicitly opted-in ReActV2 modules, without creating a generic tool framework or permitting external effects.
