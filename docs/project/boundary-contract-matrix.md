---
summary: "Executable boundary invariants for DSPx validation-only and preflight surfaces."
read_when:
  - "You change generated-code smoke validation, authority preflight status, SQLite URL parsing, rooted local stores, or agent ReAct wiring."
  - "You add or review a boundary hardening regression test."
type: "reference"
---

# DSPx Boundary Contract Matrix

This matrix records repo-level boundary invariants that must stay executable through tests. It is intentionally narrow: it covers validation-only generated-code execution, local preflight truth, rooted local paths, and SQLite URL discovery.

Run the matrix with:

```bash
just boundary-contract-check
```

## Invariants

| Boundary | Contract | Executable coverage |
|---|---|---|
| Generated-code smoke | Validation-only execution must fail closed on filesystem writes, process execution, network access, forbidden dynamic imports, and dangerous builtin calls. Runtime monkeypatch guards are defense-in-depth; AST validation must reject known escape forms before execution. | `tests/test_synthesis_runtime_smoke.py` |
| Generated-code imports | Top-level imports are restricted to `dspy`, `typing`, `typing_extensions`, and `__future__`; dynamic import of dangerous roots such as `ctypes`, `os`, `subprocess`, `socket`, `pathlib`, `importlib`, and `builtins` is denied during smoke execution. | `tests/test_synthesis_runtime_smoke.py` |
| Authority export preflight | `status == "ready_not_applied"` means local preflight blockers are empty. External apply limitations are represented separately as `external_apply_blocking_reasons` and must not contradict preflight readiness. | `tests/test_authority_adapter_export_preflight.py`, `tests/test_program_candidate_state.py` |
| SQLite URL discovery | Tooling follows storage precedence: `SIXE_DB_URL`, then `DATABASE_URL`, then default `generated/sixe.db`; `sqlite:///relative.db` remains relative and `sqlite:////absolute.db` remains absolute. | `tests/test_tools_registry.py` |
| Rooted local object store | Relative and absolute store roots are accepted; resolved child paths must remain inside the resolved root. | `tests/test_adapters_stores.py` |
| Agent ReAct signature | DSPy `ReAct` is constructed with a concrete `dspy.Signature` type, not a string signature. | `tests/test_agent_service.py` |
| Program execution evidence | `program-gen` execution episodes and Oracle-readable evidence may enrich local behavior evidence summaries, but source-indexed evidence remains non-authoritative: it must not call AK, invoke Oracle/indexing, select winners, promote, mutate governance, mutate external authority, or introduce broad `eval_behavior.py` orchestration. | `tests/test_program_service.py`, `tests/test_program_dataset_splits.py`, `tests/test_program_topology_intent.py`, `tests/test_program_oracle_index.py`, `tests/test_program_oracle_report.py` |

## Change rule

When adding or editing a boundary surface, add or update an adversarial regression that proves the negative case fails closed. Do not expand a blacklist without adding a bypass-oriented test for the failure class that motivated the change.

## Review heuristic

A boundary patch is incomplete if it makes the observed repro fail but leaves an equivalent route through a different import path, status field, parser, or path normalization layer.
