# NEXT_STEPS.md

> "What would reading this feel like receiving transmission from a higher intelligence?"

---

## TRUE INTENT

This document guides evolution of the DSPx system—its codebase, its upstream dependencies, and its behavioral intelligence capabilities.

**The soul:** Ship reliable ML infrastructure by enforcing quality at every layer, from local hooks to upstream PRs.

---

## What Was Accomplished

### CLI Refactoring — COMPLETE ✅

**Before:** 3,712 lines in `dspx.py`
**After:** 343 lines orchestrator + 14 command modules

| Metric | Change |
|--------|--------|
| Main file | -91% |
| Largest module | 629 lines |
| Total modules | 15 files |

**Quality gates:**
- ✅ `just fmt lint typecheck test` all pass
- ✅ 296 tests passing
- ✅ Documentation updated

**Files:**
```
dspx/cli/
├── dspx.py (343 lines)      # Thin orchestrator
├── utils.py (302 lines)     # Shared utilities
└── commands/                # 13 command modules
```

See `docs/CLI_REFACTORING.md` for full details.

---

## The Nexus Intervention

> What is the ONE change that unlocks everything else?

**The Oracle.**

The Oracle is not a feature. It's a paradigm shift—from reactive debugging to proactive behavioral intelligence. Every other task in this document becomes easier when the Oracle exists:

- **Template adapter bugs** → Oracle detects drift when templates change
- **Upstream MLflow changes** → Oracle shows behavioral regressions
- **Upstream DSPy changes** → Oracle catches propagation failures
- **Dependency upgrades** → Oracle validates replay determinism

**Priority:** All other work is subordinate to Oracle Phase B.

---

## Active Work

### 0) dspy-template-adapter Integration

**Status:** 🟡 BLOCKED on upstream

Upstream issues filed (see `docs/upstream-issues/dspy-template-adapter/`):
1. XML parser fails on nested tags (#1)
2. JSON parser doesn't handle markdown (#2)
3. Partial demos break BootstrapFewShot (#6)

**DSPx-side COMPLETE:**
- ✅ ProviderCapabilities contract
- ✅ All providers expose `.capabilities`
- ✅ CLI fast-fail for missing adapter
- ✅ TemplateAdapterConfig DTO
- ✅ YAML config schema validation
- ✅ `--dry-run` flag for preview

**Unblock condition:** Upstream fixes #1, #2, #6 OR we vendor patched version.

---

### 8) The Oracle: Behavioral Intelligence

**Status:** 🟢 Phase A COMPLETE → Phase B NEXT

#### Phase A: Behavioral Calculus ✅

Every execution is a point in semantic space.

```bash
dspx oracle index --from-receipts    # Ingest executions
dspx oracle search "classify"        # Find similar
dspx oracle drift run-a run-b        # Measure change
dspx oracle cluster -k 5             # Discover groups
```

#### Phase B: Behavioral Topology (CURRENT)

**Map the territory.** Not just points—regions, boundaries, attractors.

```bash
dspx oracle territory --output territory.json
dspx oracle contract add --name "no-pii" --invariant "..."
dspx oracle frontiers --suggest-exploration
dspx oracle attractors --min-stability 0.95
```

**Acceptance criteria:**
- [ ] Territory map shows stable/unstable/unknown regions
- [ ] Behavioral contracts define and verify invariants
- [ ] Frontier detection identifies unexplored inputs
- [ ] Attractor analysis finds naturally stable behaviors
- [ ] Danger zone detection warns of risky regions

#### Phase C-E: Future

- **C: Time Travel** — Behavioral git (branch, diff, bisect)
- **D: Dreaming** — Simulate futures, synthesize tests
- **E: Consciousness** — Self-aware behavioral health

---

## Upstream Work (Parallel Tracks)

### Wave 2: MLflow Upstream

**Goal:** Improve MLflow callback semantics.

**PRs:**
1. Span no-op/warning policy
2. Callback concurrency safety
3. Optional autolog controls

**Status:** Issue/PR prep

### Wave 3: DSPy Upstream

**Goal:** Improve callback metadata and lifecycle hooks.

**PRs:**
1. Callback metadata envelope
2. Compile lifecycle hooks
3. Propagation stress tests

**Status:** Issue/PR prep

### Wave 4: Dependency Reconciliation

**Goal:** Bump dependencies safely.

- Track upstream releases
- Define rollback posture
- Verify replay/explain determinism

---

## Quality Protocol

### Boundary Invariant (Non-Negotiable)

```
Allowed:    apps/* -> core
Forbidden:  core -> apps/*
```

Verify: `just monorepo-check`

### Multi-Perspective Review

For each wave, review from:
- **Framework Architect** — Contracts, lifecycle, thread-safety
- **Provider Engineer** — Capability discovery, failure modes
- **Type Safety Reviewer** — Static analysis, `Any` leaks
- **Test Coverage Reviewer** — Missing tests, edge cases
- **Security Reviewer** — Input validation, resource limits

### Review Output Format

1. **P0 Bugs** — Must fix before continuing
2. **P1 Design questions** — Decisions needed
3. **P1 Test gaps** — Missing coverage
4. **P2 Minor improvements** — Nice-to-haves

### Acceptance Criteria (Per Wave)

- [ ] All P0 bugs fixed
- [ ] Design decisions documented
- [ ] Missing tests added
- [ ] `just fmt && just lint && just typecheck && just test` passes

---

## Invariants

### What MUST Be True (Axioms)

1. **Monorepo boundary** — Core never imports apps
2. **Receipt determinism** — Same input → same receipt hash
3. **Replay fidelity** — Receipt enables exact reproduction
4. **Test green** — All 296+ tests pass

### What's Merely Assumed (Prisoners)

- MLflow is optional (can be disabled)
- Template adapter is optional (has fallback)
- Oracle is additive (doesn't change existing behavior)

### What's "Impossible" (Opportunities)

- Behavioral prediction without execution → Oracle Dreaming
- Self-healing systems → Oracle Consciousness

---

## Residual Limitations

1. **Template adapter upstream** — Blocked on fixes we don't control
2. **Oracle Phase B** — Requires more execution data for territory mapping
3. **Upstream PRs** — Timeline depends on external maintainers

---

## Usage Guide

### For Developers

1. **Before committing:** `just hooks-install` (once), then pre-commit runs automatically
2. **Before pushing:** `just verify-full`
3. **When touching core:** Run `just fmt && just lint`

### For Oracle Development

1. Run `dspx oracle index --from-receipts` to populate
2. Run `dspx oracle search <query>` to find similar executions
3. Run `dspx oracle stats` to see coverage

### For Upstream Work

1. Check `docs/upstream-issues/` for filed issues
2. Prepare PRs as self-contained slices
3. Attach repro scripts to each PR

---

## Evolution Notes

### Next 6 Months

- Oracle Phase B (Topology) → reveals system's behavioral shape
- Template adapter integration (when upstream fixes land)
- MLflow/DSPy upstream PRs merged

### Next 12 Months

- Oracle Phase C (Time Travel) → behavioral git
- Oracle Phase D (Dreaming) → behavioral simulation
- Full behavioral intelligence operational

### Compound Value

Each Oracle phase makes the next easier:
- Topology enables Time Travel (you know where things are)
- Time Travel enables Dreaming (you can explore alternatives)
- Dreaming enables Consciousness (you can predict and prevent)

---

## Knowledge Crystallized

### From CLI Refactoring

**Patterns:**
- Each command group → own module (50-630 lines)
- Shared utilities → `utils.py` with decorators
- Typer apps compose via `add_typer()`

**Anti-patterns:**
- Single file > 3000 lines
- Mixing policy callback with commands
- Inline implementations in orchestrator

**Heuristics:**
- If a file feels hard to navigate, split it
- If a pattern repeats 3x, extract to utility
- Test file structure mirrors source structure

**Added to:**
- `docs/CLI_REFACTORING.md` — Extraction patterns
- `dspx/cli/utils.py` — Shared decorators
- `tests/test_cli_dspx.py` — Patch guidance

---

## Quick Reference

| Command | Purpose |
|---------|---------|
| `just hooks-install` | Install pre-commit hooks |
| `just verify-full` | Full quality gate |
| `just test` | Run test suite |
| `dspx oracle index` | Populate Oracle |
| `dspx oracle search` | Find similar executions |
| `dspx oracle drift` | Measure behavioral change |
