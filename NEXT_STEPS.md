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
- ✅ 354 tests passing
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

### 0) Provider Runtime V4 / Template-Adapter Unblock Decision

**Status:** 🟢 local patched path accepted; mixed-provider profile live-verified end-to-end; exact-fidelity adapter remains optional/upstream-blocked

Upstream adapter blockers still tracked in `docs/upstream-issues/dspy-template-adapter/`:
1. XML parser fails on nested tags (#1)
2. JSON parser doesn't handle markdown (#2)
3. Partial demos break BootstrapFewShot / GEPA (#6)

**Decision:**
- Do **not** vendor `dspy-template-adapter` in the critical path yet.
- Use DSPx-local provider runtime v4 as the supported unblock path for mixed-provider workflows.
- Keep exact-fidelity template-adapter integration optional until the upstream parser/demo blockers materially change.

**Shipped in the local path:**
- ✅ explicit `vllm-local`, `openai-compatible`, and `dspy-lm-auth` providers
- ✅ provider resolve / health / benchmark CLI commands
- ✅ config-driven student/reflection provider defaults for GEPA
- ✅ receipt-safe provider metadata for replay/explain and optimize manifests
- ✅ mixed-provider runtime reference: `docs/project/provider-runtime-v4.md`

**Live validation complete (`DSPX-M4-02` + `DSPX-M4-03`):**
- ✅ `vllm-local` probe passed against `http://127.0.0.1:1234/v1` with `Qwen/Qwen3.5-27B`
- ✅ `dspy-lm-auth` probe passed against `codex/gpt-5.4`
- ✅ mixed-provider benchmark completed successfully for both providers
- ✅ known-bad route confirmed: `codex/gpt-5.4-nano` is rejected on the active ChatGPT/Codex account route
- ✅ one live `module-gen` → `optimize gepa` smoke completed with config-driven defaults and wrote a manifest showing `student=vllm-local` + `reflection=dspy-lm-auth`
- ✅ CLI regression fixed: `optimize gepa` now loads `DSPX_CONFIG` before resolving `[optimize]` provider defaults
- ⚠️ end-to-end caveats on the verified local setup: the hello-style smoke should use `contains` rather than `exact`, the tiny proof reuses train-as-val when `--val` is omitted, and the current `Qwen/Qwen3.5-27B` student took ~61s wall-clock for a 3-row / 2-metric-call run

**Next execution step:**
- Restock `governance/work-items.json` with the next roadmap slice; the current M1-M4 backlog is now complete.

---

### 8) The Oracle: Behavioral Intelligence

**Status:** 🟢 Phase A COMPLETE → Phase B COMPLETE → Receipt v2 ready for Phase C

#### Phase A: Behavioral Calculus ✅

Every execution is a point in semantic space.

```bash
dspx oracle index --from-receipts    # Ingest executions
dspx oracle search "classify"        # Find similar
dspx oracle drift run-a run-b        # Measure change
dspx oracle cluster -k 5             # Discover groups
```

#### Phase B: Behavioral Topology ✅

**Map the territory.** Not just points—regions, boundaries, attractors.

```bash
dspx oracle territory --output territory.json
dspx oracle contract list
dspx oracle contract verify --limit 100
dspx oracle frontiers --suggest
dspx oracle attractors --health
```

**Acceptance criteria:**
- [x] Territory map shows stable/unstable/unknown regions
- [x] Behavioral contracts define and verify invariants
- [x] Frontier detection identifies unexplored inputs
- [x] Attractor analysis finds naturally stable behaviors
- [x] Danger zone detection warns of risky regions
- [x] Security hardened: AST-based expression evaluation (no eval())
- [x] Correctness: single embeddings return "insufficient data" not "stable"
- [x] PII patterns refined: UUID not flagged, API keys require prefix

**Known limitations:**
- Coverage estimates are heuristics (documented in output)
- Requires embedding backend for full functionality

#### Phase C: Time Travel (NEXT)

**Behavioral git.** Branch, diff, bisect across behavioral history.

```bash
dspx oracle branch feature-x         # Create behavioral branch
dspx oracle diff main feature-x      # Compare behaviors
dspx oracle bisect --find regression # Find when behavior changed
```

**Receipt v2 enhancements (ready):**
- `causal_chain`: List of parent run_ids for behavioral lineage
- `parent_run_id`: Immediate parent for single-hop queries
- `branch`: Named branch for grouping (defaults to git branch)
- `outcome`: success/failure/partial/cached/unknown for Dreaming
- `latency_ms`: Execution duration for simulation
- `tokens_*`: Token counts for cost modeling
- `execution_context`: git commit, python version, env hash

#### Phase D-E: Future

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
4. **Test green** — All 354+ tests pass

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
2. **Oracle Phase B** — Requires embedding backend for full functionality; coverage estimates are heuristic
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
4. Run `dspx oracle territory` to map behavioral regions
5. Run `dspx oracle contract verify` to check invariants
6. Run `dspx oracle attractors --health` for health report

### For Upstream Work

1. Check `docs/upstream-issues/` for filed issues
2. Prepare PRs as self-contained slices
3. Attach repro scripts to each PR

---

## Evolution Notes

### Next 6 Months

- Oracle Phase C (Time Travel) → behavioral git for change tracking
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

> **Crystallized learnings now live in `docs/learnings/`.**
> This section provides index; detailed entries are dated files.

### Index of Learnings

| Date | Topic | Key Insight |
|------|-------|-------------|
| 2026-02-28 | [Receipt v2 Phase C+](docs/learnings/2026-02-28-receipt-v2-phase-c.md) | Causal chains, outcome signals, execution context |
| 2026-02-15 | [Oracle Phase B Security](docs/learnings/2026-02-15-oracle-phase-b-security.md) | AST-based eval, single-point stability, PII heuristics |
| 2026-01-15 | [CLI Refactoring](docs/learnings/2026-01-15-cli-refactoring.md) | 3,712 → 15 modules, 91% reduction |

### Quick Patterns (Reference)

**Receipt v2 patterns:**
- Omit empty fields, capture context by default, bound chains at 50

**Security patterns:**
- Never `eval()`, block dunders, whitelist AST nodes

**Correctness patterns:**
- Single points = "insufficient data", not "stable"

### KES Integration

DSPx participates in ai-society's Knowledge Evolution System:
- **Diary**: `~/ai-society/AGENTS.md` (workspace-level)
- **Learnings**: `docs/learnings/` (this repo)
- **Cognitive tools**: `~/steve/prompts/triggers/`

Oracle crystallizes **behavioral** knowledge (runs → embeddings → topology).
KES crystallizes **process** knowledge (sessions → patterns → TIPs).

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
| `dspx oracle territory` | Map behavioral regions |
| `dspx oracle contract` | Verify behavioral invariants |
| `dspx oracle frontiers` | Detect unexplored inputs |
| `dspx oracle attractors` | Find stable behaviors |
| `dspx oracle predict` | Predict behavioral convergence |

**Receipt v2 fields (Phase C+):**

| Field | Purpose | Phase |
|-------|---------|-------|
| `causal_chain` | Behavioral lineage | C (Time Travel) |
| `parent_run_id` | Single-hop parent | C (Time Travel) |
| `branch` | Behavioral grouping | C (Time Travel) |
| `outcome` | Success/failure signal | D (Dreaming) |
| `latency_ms` | Execution duration | D (Dreaming) |
| `tokens_*` | Token counts | D (Dreaming) |
| `execution_context` | System state snapshot | E (Consciousness) |
