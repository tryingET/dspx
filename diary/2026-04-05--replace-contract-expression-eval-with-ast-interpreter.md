---
summary: "Diary entry: AK-798 — Replace contract-expression eval() with a tiny AST interpreter."
read_when:
  - "You need the historical implementation context captured in this diary entry."
  - "You are reviewing or extending work related to AK-798 — Replace contract-expression eval() with a tiny AST interpreter."
type: "diary"
---

# AK-798 — Replace contract-expression `eval()` with a tiny AST interpreter

## Summary
Completed `AK-798` by hardening `packages/dspx-core/src/dspx/coordinates/contracts.py` so `python_expr` contract evaluation no longer delegates to Python `eval()`.

## Why
The Oracle contract-expression path still compiled validated ASTs and executed them with `eval()`. Even with restricted globals, that left the security boundary too broad for a `TG25` hardening slice.

## Changes
- added a tiny AST interpreter for the supported expression subset instead of compiling + evaluating Python code
- narrowed the exposed contract namespace to a read-only `_SafeEmbeddingView` plus explicit helper-call allowlists
- rejected arbitrary method calls, non-allowlisted helper calls, and arbitrary attribute traversal during AST validation
- preserved safe compatibility for the existing tested contract patterns, including direct field comparisons and `embedding.output_text`
- added regressions in `tests/test_coordinates_phase_b.py` covering:
  - safe read-only embedding field access
  - rejected method calls like `output_text.strip()`
  - rejected non-allowlisted function calls like `type(output_text)`
- exported `governance/task-scopes/AK-798.snapshot.json`
- refreshed `governance/work-items.json` after marking the AK task done

## Validation
- `uvx ruff format packages/dspx-core/src/dspx/coordinates/contracts.py tests/test_coordinates_phase_b.py` ✅
- `uvx ruff check packages/dspx-core/src/dspx/coordinates/contracts.py tests/test_coordinates_phase_b.py` ✅
- `uvx ty check packages/dspx-core/src/dspx/coordinates/contracts.py` ✅
- `uv run --no-sync -m pytest -q tests/test_coordinates_phase_b.py -k 'SafeExpressionEvaluation'` ✅
- `uv run --no-sync -m pytest -q tests/test_coordinates_phase_b.py` ✅
- `just task-scope-check 798 working-tree` ⚠️ fails in this shared worktree because many pre-existing unrelated tracked/untracked files already fall outside `AK-798` scope
- `./scripts/ak.sh task show 798 -F json` ✅ (`status=done`)
- `./scripts/ak.sh task ready --repo /home/tryinget/ai-society/softwareco/owned/dspx -F json` ✅ (`[799,800]`)
- `./scripts/ak.sh work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅
- `./scripts/ak.sh work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅
- `./scripts/ci/smoke.sh` ✅
- `just verify-full` ⚠️ fails because `verify-fast` binds to the completed `AK-798` slice in the still-dirty shared worktree and the many pre-existing unrelated tracked/untracked files remain outside that task scope

## AK truth after completion
- `AK-798` is `done`
- remaining ready queue: `AK-799`, `AK-800`
