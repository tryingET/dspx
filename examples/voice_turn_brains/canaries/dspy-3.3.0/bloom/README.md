---
summary: "Offline, non-destructive DSPy 3.3 regeneration canary for the historical bloom voice-turn original."
read_when:
  - "Reviewing bloom voice-turn DSPy 3.3 compatibility evidence."
type: "evidence"
---

# bloom voice-turn DSPy 3.3 canary

AK-4794 regenerated the historical `bloom/original` intent into fresh candidate `prog-cand-1a4f0633acc8` without modifying the DSPy 3.1.3 source candidate, optimized candidate, refinement evidence, intent, or routing.

This directory records a fresh DSPy 3.3.0 candidate, same-input typed-stub executions of the historical and fresh artifacts, receipt checks, executable replay output, a hash-bound local runtime-environment observation, and a non-authoritative comparison. Assembly, candidate, episode, and receipt-bundle identities are fresh; the deterministic request ID is intentionally shared as same-intent lineage. `canary-index.json` is the compact hash and identity map.

The bounded stub fixture and local environment binding are plumbing evidence, not external attestation or OS sandbox proof. They do not establish semantic equivalence, answer quality, DSPy-version causality, live-provider behavior, optimized/GEPA compatibility, winner selection, promotion, publication, routing, or activation. Generated receipts retain local path-bound provenance. Reproduction requires a new absent root and new identities, hashes, receipts, and comparisons.
