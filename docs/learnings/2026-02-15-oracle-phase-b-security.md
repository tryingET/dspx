# Oracle Phase B Security & Correctness

## Context

Deep review of Oracle Phase B (Behavioral Topology) revealed security and correctness issues in expression evaluation and stability scoring.

## Discovery

### Security Patterns

- Never use `eval()` for user expressions — AST-based validation required
- Block dunder attribute access (`__class__`, `__bases__`) in expression evaluators
- Whitelist allowed AST node types, reject everything else

### Correctness Patterns

- Single data points are "insufficient data" (-1.0), not "stable" (1.0)
- Heuristic metrics should be explicitly documented as such
- Serialization truncation must be tracked (don't silently lose data)

### PII Detection Heuristics

- UUID is NOT PII — it's an anonymized identifier
- API key patterns need prefix matching to avoid false positives
- International phone formats have high false positive rates (use WARNING, not ERROR)

## Evidence

- Found via adversarial review (INVERSION + AUDIT triggers)
- Fixed before Phase B marked complete
- Tests added for edge cases

## Application

Pattern applies to any system that:
- Evaluates user-provided expressions
- Computes stability/quality scores from sparse data
- Detects PII in logs/outputs

## Anti-Patterns

- Returning "stable" for single embeddings (false confidence)
- Flagging UUID as PII (noise drowns out real issues)
- Undocumented heuristic metrics (users trust them too much)

## TIP Candidate

Partial — AST-based expression evaluation pattern could generalize.
Extract to meta TIP if other repos need expression evaluation.
