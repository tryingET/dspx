---
summary: "CLI refactoring plan and progress for dspx.py extraction"
read_when:
  - "Continuing dspx.py refactoring"
  - "Adding new CLI commands"
  - "Understanding CLI module organization"
---

# CLI Refactoring - COMPLETE ✅

## Summary

Successfully refactored `dspx.py` from **3,712 lines** to **343 lines** (91% reduction).

The original monolithic CLI file has been split into 14 clean modules.

## Final Structure

```
packages/dspx-core/src/dspx/cli/
├── dspx.py              # 343 lines - thin orchestrator
├── dspx.py.backup       # 3,712 lines - original (kept for reference)
├── utils.py             # 302 lines - shared decorators and helpers
└── commands/
    ├── __init__.py      #  51 lines - exports + status
    ├── cache.py         # 244 lines - cache info/list/show/clear/prune
    ├── run.py           # 182 lines - run replay/explain
    ├── optimize.py      # 154 lines - optimize gepa
    ├── providers.py     # 171 lines - providers list/capabilities/smoke
    ├── oracle.py        # 498 lines - oracle index/search/neighbors/stats/cluster/drift
    ├── signature.py     # 535 lines - sig gen/refine/quality-summary
    ├── mermaid.py       #  89 lines - mermaid gen/sig
    ├── openapi.py       # 405 lines - openapi ops/call/describe/load/env
    ├── web.py           #  62 lines - web fetch/scrape
    ├── tools.py         # 362 lines - tools list/describe/run/search
    ├── adapters.py      # 629 lines - adapters list/dataset/split/eval
    ├── codegen.py       # 214 lines - codegen helpers
    └── module.py        # 249 lines - module-gen helpers
```

## Extraction Summary

| Command Group | Lines | Status |
|---------------|-------|--------|
| cache | 244 | ✅ Complete |
| run | 182 | ✅ Complete |
| optimize | 154 | ✅ Complete |
| providers | 171 | ✅ Complete |
| oracle | 498 | ✅ Complete |
| signature | 535 | ✅ Complete |
| mermaid | 89 | ✅ Complete |
| openapi | 405 | ✅ Complete |
| web | 62 | ✅ Complete |
| tools | 362 | ✅ Complete |
| adapters | 629 | ✅ Complete |
| codegen | 214 | ✅ Helpers inline |
| module | 249 | ✅ Helpers inline |
| **Total** | **4,017** | **✅ Complete** |

## Benefits Achieved

1. **Navigability**: Each command module is 50-630 lines (vs 3,700 in one file)
2. **Testability**: Command modules can be tested in isolation
3. **Consistency**: Shared patterns in `utils.py` ensure uniform behavior
4. **Maintainability**: Adding new commands doesn't touch core CLI wiring
5. **Discoverability**: `cli/commands/` directory shows all command groups

## Quality Gates

All gates pass:
- ✅ `just fmt` - Formatting clean
- ✅ `just lint` - All checks passed
- ✅ `just typecheck` - All checks passed
- ✅ `just test` - 296 passed, 4 skipped

## Adding New Commands

1. Create module in `cli/commands/<name>.py`:

```python
"""Brief description of command group."""

from __future__ import annotations

import typer

app = typer.Typer(no_args_is_help=True)

@app.command("name")
def command_name(...) -> None:
    """Command help text."""
    # implementation
```

2. Export in `cli/commands/__init__.py`:

```python
from dspx.cli.commands.<name> import app as <name>_app
```

3. Register in `cli/dspx.py`:

```python
from dspx.cli.commands import <name>_app
app.add_typer(<name>_app, name="<name>", help="...")
```

4. Run gates: `just fmt && just lint && just typecheck && just test`
