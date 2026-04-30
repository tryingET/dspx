---
summary: "Crystallized learning note: Receipt v2 for Oracle Phase C+."
read_when:
  - "You are looking for prior DSPx implementation learnings."
  - "You need the learning note for Receipt v2 for Oracle Phase C+."
type: "reference"
---

# Receipt v2 for Oracle Phase C+

## Context

Preparing Oracle for Phase C (Time Travel) required richer receipt metadata to enable behavioral lineage tracking, outcome signals for Dreaming, and execution context for Consciousness.

## Discovery

Added new optional fields to `build_run_receipt()`:
- `causal_chain` + `parent_run_id` — behavioral lineage
- `branch` — grouping for Time Travel operations
- `outcome` — success/failure signal for simulation learning
- `latency_ms` + `tokens_*` — cost/latency modeling
- `execution_context` — git commit, python version, env hash

## Evidence

- 358 tests pass including new Phase C+ tests
- Backwards compatible (v1 receipts still work)
- Empty/default fields omitted (keeps receipts small)

## Application

Pattern applies to any system that:
- Needs to track causal relationships between executions
- Wants to learn from outcomes (success/failure)
- Requires environment correlation for debugging

## Design Patterns

- Omit empty/default fields (keeps receipts small)
- `capture_context=True` by default (can disable for privacy)
- Causal chains bounded at 50 depth (prevent unbounded growth)
- All new fields backwards compatible

## Anti-Patterns

- Storing raw env values (use hash instead)
- Unbounded causal chains (memory/perf issues)
- Returning "stable" for single embeddings (false confidence)

## TIP Candidate

No — DSPx-specific, doesn't generalize to other repos.
