# CLI Refactoring — 3,712 Lines to 15 Modules

## Context

Single `dspx.py` file grew to 3,712 lines, becoming unmaintainable. Needed to split into modular structure without breaking existing functionality.

## Discovery

### Before
- 3,712 lines in `dspx.py`
- Mixed concerns (commands, callbacks, utilities)
- Hard to navigate and test

### After
- 343 lines orchestrator + 14 command modules
- 91% reduction in main file
- Largest module: 629 lines
- Total: 15 files

### Patterns That Worked

- Each command group → own module (50-630 lines)
- Shared utilities → `utils.py` with decorators
- Typer apps compose via `add_typer()`

### Heuristics

- If a file feels hard to navigate, split it
- If a pattern repeats 3x, extract to utility
- Test file structure mirrors source structure

## Evidence

- 354 tests passing after refactor
- No functionality lost
- Easier to add new commands

## Application

Pattern applies to any CLI that:
- Has >10 command groups
- Mixed orchestration + business logic
- Needs better test isolation

## Anti-Patterns

- Single file > 3000 lines
- Mixing policy callback with commands
- Inline implementations in orchestrator

## TIP Candidate

Yes — CLI module extraction pattern generalizes.
Could become meta TIP for Python CLI projects.
