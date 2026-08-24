---
summary: "Non-destructive offline DSPy 3.3 migration canaries for all six historical voice-turn original candidates."
read_when:
  - "Reviewing DSPy 3.1.3 to 3.3 voice-turn compatibility evidence."
  - "Planning optimized-candidate regeneration, GEPA materialization, or voice-turn routing decisions."
type: "evidence"
---

# Voice-turn DSPy 3.3 migration canaries

This namespace contains separately identified, receipt-backed DSPy 3.3 regeneration canaries for the six historical `original` voice-turn candidates. No historical candidate, intent, refinement, optimized artifact, routing index, or AI-control binding is replaced.

- `simple/` was created by AK-4789.
- `elaborate/`, `researched/`, `deep-research/`, `socratic/`, and `bloom/` were created by AK-4794.
- `remaining-originals-index.json` binds the five AK-4794 candidate identities and manifest hashes.
- `successors/AK-4971/` contains the six provider-free DSPy 3.3.1 protected-snapshot successors and their aggregate index.
- `predecessor-contracts/` preserves the consumed evaluation contract byte-for-byte; its terminal evidence is not relabeled or retried.

Each canary contains a newly generated candidate, current-runtime executions of both the historical original artifact and new candidate under the same `stub/echo` typed adapter, receipt checks, executable replay results, a hash-bound local runtime-environment observation, and a non-authoritative comparison. Assembly, candidate, episode, and receipt-bundle identities are fresh; the deterministic request ID is intentionally shared with the historical candidate as same-intent lineage.

These artifacts establish shape-specific DSPy 3.3 materialization plus successful local execution under an observed DSPy 3.3 environment. The environment binding is local evidence, not an external attestation or OS sandbox proof. Stub output does not establish semantic equivalence, answer quality, DSPy-version causality, live-provider behavior, optimized-candidate compatibility, GEPA compatibility, winner selection, promotion, publication, routing, or activation.

Generated receipts retain path-bound local provenance. Reproduction must use a new absent output root and create new identities, manifests, hashes, receipts, runtime evidence, and comparisons; never overwrite this evidence or historical artifacts.

The current execution-unauthorized successor contract remains at `soomfon-evaluation-contract.json`. Its raw digest, exact candidates, and nonclaims are documented in `docs/project/dspy-3-3-soomfon-originals-evaluation-contract.md`. Neither the successor namespace nor its contract grants live-provider, physical-button, routing, promotion, or activation authority.
