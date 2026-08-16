---
summary: "Offline, non-destructive DSPy 3.3 regeneration canary for the historical simple voice-turn program."
read_when:
  - "Reviewing DSPy 3.1.3 voice-turn artifact compatibility after the typed 3.3 cutover."
  - "Planning the remaining voice-turn regeneration or GEPA materialization work."
type: "evidence"
---

# Simple voice-turn DSPy 3.3 migration canary

This directory is a receipt-backed **offline compatibility canary** created by AK-4789. It regenerates the historical `simple/original` intent as a new DSPy 3.3 candidate without changing or routing away from any DSPy 3.1.3 artifact.

## What this establishes

- The current DSPy/DSPy-AI 3.3.0 program generator materialized the same declared two-`Predict` pipeline into a fresh candidate identity.
- The historical original artifact and the fresh candidate both executed under the same credential-free `stub/echo` typed-LM adapter and frozen input/fixture.
- Candidate and runtime receipts passed integrity checks, and both runtime receipts produced fresh receipt-bound replay output.
- `historical-inventory.json` freezes every file that existed under `examples/voice_turn_brains` before this canary. The regression test checks those 469 path/size/hash identities byte-for-byte.
- `comparison.json` records generated-behavior and same-runtime status evidence without selecting or promoting either candidate.

The authoritative compact map is `canary-index.json`. Generated manifests and receipts retain the canonical local absolute paths observed during execution; they are local evidence, not relocatable release artifacts. The regression test validates their bytes and bindings from a relocated checkout without treating embedded paths as portable authority.

## What this does not establish

The stub emits deterministic placeholders/canned fixture values. Therefore this canary does **not** establish semantic equivalence, answer quality, DSPy-version causality, provider/model quality, production compatibility, winner selection, promotion, publication, or activation. Both candidates' generated example evidence remains failed with `mismatch:response`; the same-runtime executions have no declared quality criteria and keep `quality_approved: false`.

This slice does not cover the historical optimized candidate, GEPA, pickle-backed programs, ReAct/ReActV2, ProgramOfThought, tools, retrievers, streaming, async, credentials, network, Oracle indexing/semantic analysis, or external authority.

## Layout

- `candidate/` — fresh DSPy 3.3.0 candidate with new assembly/candidate/episode/receipt identities.
- `runtime/historical-artifact-under-3.3-stub/` — current-runtime execution and replay evidence for the immutable DSPy 3.1.3 original artifact.
- `runtime/canary-artifact-under-3.3-stub/` — equivalent execution and replay evidence for the fresh candidate.
- `comparison.json` — non-authoritative comparison over generated and same-runtime evidence.
- `*-receipt-check.json`, `*-replay-result.json` — captured local verification reports.
- `historical-inventory.json` — pre-canary byte inventory.

## Reproduction boundary

Do not overwrite this directory or any historical candidate. A future reproduction must use a new absent output root, `DSPX_PROVIDER=stub`, `DSPX_MODEL=stub/echo`, `MLFLOW_ENABLE=0`, `DSPX_CACHE_ENABLE=0`, and the bounded fixture recorded in the runtime replay artifacts. Reproduction evidence gets a new candidate ID, paths, manifests, hashes, receipts, and comparison packet.
