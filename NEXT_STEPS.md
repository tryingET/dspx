# Next Steps

Current branch context: `main`.
Execution mode reference: full-sweep (DSPx + upstream MLflow + upstream DSPy), ordered waves.

---

## Multi-Perspective Review Protocol

**Apply this protocol to all waves before marking work complete.**

For each wave, review from multiple expert perspectives and fix bugs systematically:

### Expert Perspectives (use relevant subset)

| Expert | Focus | Key Questions |
|--------|-------|---------------|
| **Framework Architect** | Internal contracts, lifecycle, thread-safety | Does this honor existing protocols? Edge cases in async/concurrent flows? |
| **Provider/Backend Engineer** | Capability discovery, failure modes, heterogeneity | What happens when backends differ? Degradation paths? |
| **API/DX Specialist** | Library ergonomics, config patterns, error messages | Is this debuggable? Are errors actionable? |
| **Type Safety Reviewer** | Static analysis, type completeness, `Any` leaks | Does `ty`/`ruff` report clean? Are `# type: ignore` justified? |
| **Test Coverage Reviewer** | Missing tests, edge cases, regression risk | What scenarios are untested? What would break silently? |
| **Security/Hardening Reviewer** | Input validation, resource limits, injection vectors | What happens with malformed input? Are there DoS vectors? |

### Review Output Format (per wave)

1. **Bugs found** — Must fix before continuing (P0)
2. **Design questions** — Decisions needed (P1)
3. **Test gaps** — Missing coverage (P1)
4. **Minor improvements** — Nice-to-haves (P2)

### Acceptance Criteria (per wave)

- [ ] All P0 bugs fixed and committed
- [ ] Design decisions documented in relevant `docs/` file
- [ ] Missing tests added for touched behavior
- [ ] `just fmt && just lint && just typecheck && just test` passes

---

## 0) dspy-template-adapter Integration

**Status:** 🟡 BLOCKED on upstream fixes — Critique complete, issues filed.

**Context:** Optional integration of [dspy-template-adapter](https://github.com/MaximeRivest/dspy-template-adapter) into DSPx for exact-fidelity prompt templates.

### Artifacts

- **Critique:** `docs/TEMPLATE_ADAPTER_CRITIQUE.md`
- **Integration spec:** `docs/TEMPLATE_ADAPTER_INTEGRATION.md` (needs revision post-upstream-fixes)
- **Upstream issues:** `docs/upstream-issues/dspy-template-adapter/`

### Upstream Issues Filed

| # | Issue | Priority | URL | Blocks DSPx? |
|---|-------|----------|-----|--------------|
| 1 | XML parser fails on nested tags and CDATA | High | [#1](https://github.com/MaximeRivest/dspy-template-adapter/issues/1) | Yes — XML mode unusable |
| 2 | JSON parser doesn't handle markdown-wrapped output | High | [#2](https://github.com/MaximeRivest/dspy-template-adapter/issues/2) | Yes — JSON mode fragile |
| 3 | Clarify `parse_mode='chat'` limitations | Medium | [#3](https://github.com/MaximeRivest/dspy-template-adapter/issues/3) | No — Doc only |
| 4 | Add `__repr__` for debugging | Low | [#4](https://github.com/MaximeRivest/dspy-template-adapter/issues/4) | No — DX improvement |
| 5 | Document thread-safety guarantees | Medium | [#5](https://github.com/MaximeRivest/dspy-template-adapter/issues/5) | Partial — Need clarity for async |
| 6 | Handle partial demos from optimizers | Medium | [#6](https://github.com/MaximeRivest/dspy-template-adapter/issues/6) | Yes — Breaks BootstrapFewShot/GEPA |

### DSPx-Side Work (can proceed in parallel)

These tasks don't require upstream fixes and unblock implementation once upstream resolves:

1. ~~**ProviderCapabilities contract** — Define `dspx/capabilities.py` with explicit fields~~ ✅ DONE (`11dd6ee`)

2. ~~**Capability discovery interface** — Add `capabilities` property to all `*LM` classes~~ ✅ DONE (`11dd6ee`)
   - `ClaudeHeadlessLM.capabilities` — structured_output_format: json|xml based on output_format
   - `CodexExecLM.capabilities` — json_mode=True, structured_output_format="json"
   - `GeminiCLILM.capabilities` — structured_output_format="none"
   - `OpenRouterLM.capabilities` — structured_output_format="none" (model-dependent)
   - `PiRpcLM.capabilities` — structured_output_format="none"
   - `DSpyStubLM.capabilities` — structured_output_format="none"
   - `MultiProviderLM.capabilities` — uses `all()` for json_mode, most restrictive format

3. ~~**CLI fast-fail for missing dep** — When `--template-config` passed, check adapter availability at entrypoint~~ ✅ DONE (`a191016`)

4. ~~**TemplateAdapterConfig DTO** — Add to `dspx/dtos.py`:~~ ✅ DONE (`220e0ae`)
   - `TemplateMessage`
   - `TemplateAdapterConfig`
   - Extend `SignatureGenRequest.template_adapter: Optional[TemplateAdapterConfig]`
   - Extend `CodegenRequest.template_adapter: Optional[TemplateAdapterConfig]`
   - Tests in `tests/test_dtos.py` (21 tests)

5. ~~**YAML config schema** — Add JSON Schema for template config validation:~~ ✅ DONE (`f4e1408`)
   - `docs/schemas/template-adapter-config.schema.json`
   - `dspx/schema_validation.py` — validation with line-number error messages
   - Tests in `tests/test_schema_validation.py` (14 tests)

6. ~~**`--dry-run` flag** — Add to `dspx signature gen --template-config ... --dry-run` to preview rendered messages without LM call~~ ✅ DONE (`aca0912`)
   - Added `--dry-run` flag to `signature gen` command
   - Validates config, shows rendered messages (if adapter available) or summary
   - Tests in `tests/test_cli_dspx.py` (3 tests)

### Acceptance Criteria for Implementation

Proceed with `DSPxTemplateAdapter` implementation when:

- [ ] Upstream #1 (XML parser) fixed OR we vendor a patched version
- [ ] Upstream #2 (JSON markdown) fixed OR we pre-process in wrapper
- [ ] Upstream #6 (partial demos) fixed OR we filter demos in wrapper
- [x] DSPx-side ProviderCapabilities contract merged
- [x] All providers expose `.capabilities` property
- [x] CLI fast-fail implemented
- [x] TemplateAdapterConfig DTO added

### Implementation Review (multi-perspective)

Before proceeding to DTOs and remaining work, review completed implementation from these perspectives:

#### Expert 1: Capabilities Contract Reviewer

**Files to review:**
- `packages/dspx-core/src/dspx/capabilities.py`
- `packages/dspx-core/src/dspx/lm_base.py`

**Review lenses:**
- [ ] Is `ProviderCapabilities` frozen/immutable? (Should use `frozen=True` or `@dataclass(frozen=True)`)
- [ ] Are defaults sensible for unknown providers? (Current: `json_mode=False`, `structured_output_format="none"`)
- [ ] Is the `Literal["json", "xml", "none"]` type complete, or should it include `"yaml"`, `"markdown"`?
- [ ] Are Field descriptions accurate for all fields?
- [ ] Should `supports_vision` and `supports_audio` be in the base contract or optional extensions?

#### Expert 2: Provider Implementation Reviewer

**Files to review:**
- `packages/dspx-core/src/dspx/claude_cli_lm.py` (capabilities section)
- `packages/dspx-core/src/dspx/codex_exec_lm.py` (capabilities section)
- `packages/dspx-core/src/dspx/gemini_cli_lm.py` (capabilities section)
- `packages/dspx-core/src/dspx/openrouter_lm.py` (capabilities section)
- `packages/dspx-core/src/dspx/pi_rpc_lm.py` (capabilities section)
- `packages/dspx-core/src/dspx/multi_provider_lm.py` (`_combine_caps` function)

**Review lenses:**
- [ ] Is `ClaudeHeadlessLM.structured_output_format` correct? (Currently: `json` for json mode, else `xml`)
- [ ] Is `CodexExecLM.json_mode=True` correct? Does Codex actually guarantee valid JSON?
- [ ] Is `GeminiCLILM.structured_output_format="none"` correct, or does Gemini CLI support JSON?
- [ ] Is `OpenRouterLM.structured_output_format="none"` too conservative? Should it vary by model?
- [ ] Does `_combine_caps()` handle edge cases? (empty provider list, None capabilities, missing fields)
- [ ] Is the `all()` logic for `json_mode` correct in MultiProviderLM?
- [ ] Is the "most restrictive" logic for `structured_output_format` correct?

#### Expert 3: CLI Integration Reviewer

**Files to review:**
- `packages/dspx-core/src/dspx/cli/dspx.py` (`_check_template_adapter_available`, `_require_template_adapter`, command options)
- `tests/test_cli_dspx.py` (fast-fail tests)

**Review lenses:**
- [ ] Is the availability check cached correctly? (Module-level global, not re-checked per-call)
- [ ] Does the error message include all install options? (`pip install dspx-core[templates]` vs `pip install dspy-template-adapter`)
- [ ] Is `--template-config` added to all relevant commands? (Missing: `mermaid sig`, `mermaid gen`?)
- [ ] Do tests cover all commands with `--template-config`?
- [ ] Is the exit code consistent (2) across all fast-fail cases?
- [ ] Should `--template-config` imply `--template-adapter` flag, or are they separate concerns?
- [ ] What happens if config file doesn't exist? (Should fail before adapter check)

#### Expert 4: Type Safety Reviewer

**Files to review:**
- All files with `# type: ignore` comments
- `packages/dspx-core/src/dspx/capabilities.py` (Pydantic model)

**Review lenses:**
- [ ] Does `ty` report any diagnostics on capabilities code?
- [ ] Is the `Literal` type for `structured_output_format` properly exported for type checkers?
- [ ] Are there any `Any` types that should be more specific?
- [ ] Is the `# type: ignore[import-untyped]` on dspy_template_adapter import justified?

#### Review Output Format

For each expert, produce:
1. **Bugs found** — Must fix before continuing
2. **Design questions** — Decisions needed
3. **Test gaps** — Missing test coverage
4. **Minor improvements** — Nice-to-haves

**After review:** Fix all bugs, document design decisions, add missing tests before proceeding to DTOs.

### Review Status

✅ **COMPLETE** — Review conducted and bugs fixed (`docs/TEMPLATE_ADAPTER_IMPLEMENTATION_REVIEW.md`)

**Bugs fixed:**
1. ProviderCapabilities now frozen (immutable) — `5419957`
2. Empty provider list returns safe defaults (not json_mode=True) — `5419957`
3. Added supports_vision/supports_audio aggregation — `5419957`
4. --template-config validates file exists before adapter check — `5824660`

**Tests added:**
- `tests/test_multi_provider_caps.py` — 9 tests for `_combine_caps()` edge cases
- `tests/test_cli_dspx.py` — 3 tests for missing file scenario

### Critique Reference (preserved)

<details>
<summary>Expert critique lenses (click to expand)</summary>

#### Expert 1: DSPy Framework Architect

**Domain:** DSPy internals, adapter lifecycle, optimizer integration, signature/module contracts.

**Critique lenses:**
- Does the proposed `DSPxTemplateAdapter` wrapper correctly honor DSPy's adapter protocol (`format()`, `parse()`, callbacks)?
- Will `{instruction}` slot actually be optimizable by MIPROv2/COPRO given the wrapper layer?
- Does per-module adapter binding via `dspy_template_adapter.Predict` conflict with `dspy.configure(adapter=...)` global state?
- Are there edge cases in optimizer flows (BootstrapFewShot, GEPA) where demo injection or history expansion breaks?
- Does the integration respect DSPy's `settings.context()` thread-safety for async/concurrent calls?
- Is the `parse_mode="chat"` fallback to `ChatAdapter.parse()` correct, or will it produce format mismatches?

**Key files to cross-reference:**
- `~/programming/upstream/dspy-template-adapter/dspy_template_adapter/template_adapter.py`
- DSPy source: `dspy/adapters/`, `dspy/teleprompt/`

### Expert 2: Provider Abstraction Engineer

**Domain:** Multi-provider systems, capability discovery, heterogeneous LLM backends, failure modes.

**Critique lenses:**
- Is the capability → parse_mode mapping (`json_mode` → `json`, Claude → `xml`) accurate and complete?
- What happens when `MultiProviderLM` fans out to children with different capabilities? Single adapter or per-child?
- How does the wrapper handle providers that don't report capabilities cleanly?
- Is `json_repair` robust enough for all CLI-provider output quirks, or are there failure classes it misses?
- Does XML parse mode handle nested tags, CDATA, or malformed responses gracefully enough for production?
- What's the degradation path when a provider claims `json_mode` but emits invalid JSON?

**Key files to cross-reference:**
- `packages/dspx-core/src/dspx/multi_provider_lm.py`
- `packages/dspx-core/src/dspx/claude_cli_lm.py`, `codex_exec_lm.py`, `gemini_cli_lm.py`
- `packages/dspx-core/src/dspx/openrouter_lm.py`

### Expert 3: Python API Design & DX Specialist

**Domain:** Library ergonomics, optional dependencies, configuration patterns, developer experience, type safety.

**Critique lenses:**
- Is `TemplateAdapterConfig` expressive enough for real-world customization, or will users need escape hatches?
- Does the YAML config file format (`--template-config ./templates/triage.yaml`) have good DX (editor support, validation, errors)?
- Is the `parse_mode: "auto"` behavior predictable and debuggable, or will it surprise users?
- Are error messages actionable when `dspy-template-adapter` is not installed but config is provided?
- Does the `register_helpers: {name: "import.path.fn"}` pattern have security/ergonomics issues?
- Is the DTO hierarchy (`TemplateMessage`, `TemplateAdapterConfig`, extended `SignatureGenRequest`) clean or over-engineered?
- Should generated programs embed `_TEMPLATE_CONFIG` as a mutable global, or is there a better pattern?

**Key files to cross-reference:**
- `packages/dspx-core/src/dspx/dtos.py`
- `docs/TEMPLATE_ADAPTER_INTEGRATION.md` (DTOs section, CLI integration section)

### Expected Output

For each expert, produce:
1. **Fatal flaws** — Must-fix before implementation
2. **Significant risks** — Address with mitigation or design change
3. **Minor improvements** — Nice-to-haves
4. **Open questions** — Require clarification or decision

After critique: Synthesize into a prioritized revision list for `docs/TEMPLATE_ADAPTER_INTEGRATION.md`.

</details>

---

## Boundary invariant (non-negotiable)

- Allowed: `apps/* -> core`
- Forbidden: `core -> apps/*`
- Never import `dspx_forge.*` from core code.

Acceptance:
- `just monorepo-check` stays green.
- No reverse imports introduced in diffs.

---

## 1) Keep baseline stable on every iteration

Actions:
1. Keep hooks installed (once per clone):
   - `just hooks-install`
2. Use tiered validation:
   - per commit: pre-commit hook (fast staged checks)
   - per batch/before push: `just verify-full`
3. Run extra quality gates when touching core runtime contracts:
   - `just fmt && just lint`

### Multi-Perspective Review (when modifying baseline/tooling)

| Perspective | Review Focus |
|-------------|--------------|
| **Framework Architect** | Do hook changes affect CI parity? Local vs CI drift? |
| **Test Coverage Reviewer** | Are new lint/type rules covered by failing test fixtures? |
| **DX Specialist** | Are error messages from hooks actionable? |

Acceptance:
- Fast local commit loop stays low-latency.
- Full gate passes at least once per commit batch before push.

---

## 2) Package and land Wave-1 DSPx observability changes cleanly

Actions:
1. Slice reviewable commits for:
   - `dspx.*` MLflow correlation tags
   - receipt `mlflow_hints`
   - explain diagnostics + `--mlflow-remote-lookup`
   - tests/docs synchronization
2. Ensure commit messages map to one concern each.
3. Keep remote lookup bounded in explain path (HTTP timeout budget + retries `0`) and retain regression coverage for remote-unreachable URIs.

### Multi-Perspective Review

| Perspective | Files to Review | Key Questions |
|-------------|-----------------|---------------|
| **Framework Architect** | `packages/dspx-core/src/dspx/mlflow_*` | Are MLflow callbacks thread-safe? Proper span lifecycle? |
| **Provider Engineer** | `packages/dspx-core/src/dspx/receipts.py` | Do hints handle missing MLflow gracefully? Remote fallback? |
| **Type Safety Reviewer** | All modified files | Any new `# type: ignore`? Are MLflow imports guarded? |
| **Test Coverage Reviewer** | `tests/test_run_receipts.py`, `tests/test_mlflow_*.py` | Timeout tests cover all edge cases? Mock vs real MLflow? |
| **Security Reviewer** | Remote lookup code | Is remote URL validated? Timeout bounds enforced? |

### Bugs to Check

- [ ] Remote lookup doesn't hang on unreachable URIs (timeout budget enforced)
- [ ] MLflow import failures don't crash receipt generation
- [ ] Correlation tags don't leak secrets
- [ ] Explain path handles both local and remote runs

Acceptance:
- No mixed concerns per commit.
- Tests covering receipt hints + explain diagnostics remain green.
- `tests/test_run_receipts.py::test_run_explain_remote_lookup_flag_graceful` stays fast/no-hang.
- Docs reflect actual CLI flags and runtime behavior.

---

## 3) Wave-2 upstream MLflow execution (issue/PR prep)

Actions:
1. Open/update MLflow umbrella issue from RFC packet.
2. Prepare PR slicing artifacts:
   - PR1 span no-op/warning policy
   - PR2 callback concurrency state safety
   - PR3 optional autolog controls
3. Attach concrete repro notes and downstream impact.

### Multi-Perspective Review

| Perspective | Review Focus |
|-------------|--------------|
| **Framework Architect** | Do upstream changes break DSPy callback contract? Span nesting correct? |
| **Provider Engineer** | Multi-process MLflow scenarios? Distributed tracing? |
| **Test Coverage Reviewer** | Are there repro scripts for each PR? Stress tests for concurrency? |
| **Security Reviewer** | Do autolog controls prevent credential leakage? |

### Bugs to Check (upstream integration)

- [ ] Span no-op doesn't break parent span linkage
- [ ] Callback concurrency doesn't cause race conditions in metrics
- [ ] Autolog disable actually disables all side effects
- [ ] Backward compatibility with older MLflow versions

Acceptance:
- Umbrella + slice checklists exist and are linkable.
- Scope remains additive/backward compatible by default.

---

## 4) Wave-3 upstream DSPy execution (issue/PR prep)

Actions:
1. Open/update DSPy umbrella issue from RFC packet.
2. Prepare PR slicing artifacts:
   - PR1 callback metadata envelope
   - PR2 compile lifecycle hooks
   - PR3 propagation guarantees/stress tests
3. Keep compatibility semantics explicit (missing vs null, marker rollout).

### Multi-Perspective Review

| Perspective | Review Focus |
|-------------|--------------|
| **Framework Architect** | Do compile hooks integrate with optimizer lifecycle? Metadata envelope extensible? |
| **Provider Engineer** | Propagation works across MultiProviderLM fan-out? |
| **Type Safety Reviewer** | Are new DSPy types properly re-exported? Breaking changes for downstream? |
| **Test Coverage Reviewer** | Stress tests cover concurrent optimization? Large program graphs? |

### Bugs to Check (upstream integration)

- [ ] Metadata envelope doesn't break existing callbacks
- [ ] Compile hooks fire at correct lifecycle points
- [ ] Propagation guarantees hold under concurrent execution
- [ ] Legacy callbacks still work (backward compatibility)

Acceptance:
- Issue/PR decomposition is concrete and test-gated.
- Legacy callback compatibility is preserved.

---

## 5) Wave-4 downstream reconciliation plan

Actions:
1. Track upstream release readiness checkpoints.
2. Define dependency floor bump steps + rollback posture.
3. Re-verify replay/explain behavior after dependency updates.

### Multi-Perspective Review

| Perspective | Review Focus |
|-------------|--------------|
| **Framework Architect** | Do upstream releases break DSPx adapter contract? Receipt format compatibility? |
| **Provider Engineer** | All providers work with new dependency versions? |
| **Test Coverage Reviewer** | Full test suite passes with new deps? Integration tests? |
| **Security Reviewer** | Dependency bumps don't introduce vulnerabilities? `pip audit` clean? |

### Bugs to Check (dependency upgrades)

- [ ] Replay determinism preserved with new MLflow/DSPy versions
- [ ] Explain output format stable across versions
- [ ] No new transitive dependency conflicts
- [ ] Rollback procedure tested and documented

Acceptance:
- Upgrade path and rollback path both documented.
- Replay/explain determinism remains intact post-upgrade.

---

## 6) System4D extension smoke-testing track (optional focus)

If current focus is System4D extension smoke testing, prefer:
- `/status-system4d-extension-handoff`

Actions:
1. Re-run router fixture/tests and workflow gate checks.
2. Verify authoritative semantics remain intact:
   - explicit command `RUN_ID` is canonical
   - `DB_PATH_OR_NONE` semantics unchanged
3. Keep run artifacts under `docs/subagent-runs/<RUN_ID>/` synchronized.

### Multi-Perspective Review

| Perspective | Files to Review | Key Questions |
|-------------|-----------------|---------------|
| **Framework Architect** | Router, extension glue code | Is RUN_ID resolution deterministic? Priority order correct? |
| **Provider Engineer** | DB path handling | Does DB_PATH_OR_NONE handle missing/invalid paths correctly? |
| **Type Safety Reviewer** | Extension type stubs | Are extension types properly exported for consumers? |
| **Test Coverage Reviewer** | Router fixtures, workflow gates | Are all RUN_ID sources tested? Edge cases? |
| **Security Reviewer** | Extension IPC | Is input sanitized? No injection vectors? |

### Bugs to Check

- [ ] Router behavior deterministic under fixture coverage
- [ ] Explicit RUN_ID always wins over environment/defaults
- [ ] DB_PATH_OR_NONE returns None for invalid paths (doesn't crash)
- [ ] Run artifacts stay synchronized with actual behavior

Acceptance:
- Router behavior deterministic under fixture coverage.
- No drift between extension behavior and schema/docs.

---

## 8) Behavioral Oracle: Semantic Regression & Topological Assurance

**Status:** 🔵 READY TO START — Builds on existing receipts/cache/MLflow infrastructure.

**Vision:** Transform passive execution traces into active behavioral assurance. Don't just run programs—navigate a space where all possible behaviors can be mapped, predicted, and guaranteed.

### The Paradigm Shift

| Current World | Oracle World |
|---------------|--------------|
| Run program → Get output | Query behavioral space → See all reachable outputs |
| Detect bugs after change | Prove correctness before change |
| Compare providers empirically | See provider fingerprints in semantic space |
| Test sampled inputs | Map entire behavioral territory |
| Time passes linearly | Traverse behavioral history at will |

### Layered Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│  LAYER 5: ORACLE INTERFACE (dspx oracle ...)                            │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ Commands: navigate, prove, synthesize, travel, fingerprint      │  │
│  │ "dspx oracle prove --invariant 'no-pii-in-output'"              │  │
│  │ "dspx oracle travel --to 2024-01-15 --against current-code"     │  │
│  └──────────────────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────────────┤
│  LAYER 4: BEHAVIORAL DYNAMICS (dspx/dynamics/)                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ • Simulator: Predict outcomes without running                    │  │
│  │ • Predictor: Forecast drift trajectory                           │  │
│  │ • Counterfactual: "What if I had used Claude instead?"          │  │
│  │ • Synthesizer: Generate test cases at territory boundaries      │  │
│  └──────────────────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────────────┤
│  LAYER 3: BEHAVIORAL TOPOLOGY (dspx/topology/)                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ • Territory Map: All observed behaviors in semantic space       │  │
│  │ • Invariants: Regions that must never be violated               │  │
│  │ • Attractors: Where outputs tend to cluster                     │  │
│  │ • Forbidden Zones: Semantic regions that indicate failure       │  │
│  │ • Boundaries: Edges of tested behavior                          │  │
│  └──────────────────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────────────┤
│  LAYER 2: SEMANTIC COORDINATES (dspx/coordinates/)                     │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ • Embedding Engine: Map (input, output, config) → vector        │  │
│  │ • Distance Metrics: Semantic similarity, behavioral drift       │  │
│  │ • Coordinate System: Latent space for all DSPx executions       │  │
│  │ • Clustering: Group similar behaviors automatically             │  │
│  └──────────────────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────────────┤
│  LAYER 1: EXECUTION CAPTURE (✅ ALREADY EXISTS)                        │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ • Receipts: Every run produces structured record                │  │
│  │ • MLflow: Correlation tags, hints, artifacts                    │  │
│  │ • Cache: Deterministic replay capability                        │  │
│  │ • Replay/Explain: Full provenance chain                         │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

### Phase A: Semantic Coordinates & Capture (Foundation)

**Goal:** Every execution receipt becomes a point in navigable semantic space.

**Implementation:**

```bash
# packages/dspx-core/src/dspx/coordinates/
├── __init__.py
├── embeddings.py      # Embed (input, output, config) → vector
├── metrics.py         # Semantic distance, drift scoring
├── clustering.py      # Group similar executions
└── storage.py         # Persist coordinate index
```

**CLI Commands:**

```bash
# Index existing runs into semantic space
dspx oracle index --from-mlflow --since 30d

# Find similar past executions
dspx oracle search --input "classify this ticket" --top 5

# Show semantic neighbors of a run
dspx oracle neighbors --run-id abc123
```

**Acceptance Criteria:**
- [ ] Every receipt can be embedded into semantic coordinates
- [ ] Similar executions cluster together (visualizable)
- [ ] Search by semantic similarity returns relevant results
- [ ] Coordinate index persists and updates incrementally

### Phase B: Behavioral Topology (Territory Mapping)

**Goal:** Build a map of your system's behavioral territory—not just points, but regions and boundaries.

**Implementation:**

```bash
# packages/dspx-core/src/dspx/topology/
├── __init__.py
├── territory.py       # Map of observed behaviors
├── invariants.py      # Define and check constraints
├── boundaries.py      # Find edges of tested space
├── attractors.py      # Identify stable regions
└── visualization.py   # ASCII/JSON territory maps
```

**CLI Commands:**

```bash
# Visualize behavioral territory
dspx oracle territory --output territory.json

# Define an invariant (semantic constraint)
dspx oracle invariant add --name "no-pii" \
    --description "Outputs must not contain PII patterns"

# Check if recent runs violate invariants
dspx oracle check --against invariants.yaml

# Find boundary cases (edge of tested territory)
dspx oracle boundaries --suggest-tests
```

**Territory Visualization (ASCII):**

```
                    ┌─────────────────────────────────────────┐
                    │     BEHAVIORAL TERRITORY MAP            │
                    │                                         │
         Unstable   │    ○──○──○                    ○──○      │
         Region     │   /      \\                  /    \     │
                    │  ○   🔴   ○   ←── drift     ○  ✓  ○     │
                    │   \      /     detected      \    /     │
                    │    ○──○──○                    ○──○      │
                    │           │                             │
                    │           ▼                             │
                    │    ═══════════════                       │
                    │    STABLE PLATEAU      ○ ←─ unexplored  │
                    │    ═══════════════     /                │
                    │                       ○                 │
                    └─────────────────────────────────────────┘

Invariant Status:
  ✓ no-pii:        847 runs verified, 0 violations
  ✓ json-valid:    847 runs verified, 0 violations
  ⚠ no-hallucination: 847 runs, 3 boundary approaches detected

Suggested Boundary Tests:
  1. Input with ambiguous pronoun references
  2. Very long context (>8000 tokens)
  3. Non-English input with English instructions
```

**Acceptance Criteria:**
- [ ] Territory map shows stable vs unstable regions
- [ ] Invariants can be defined and checked against runs
- [ ] Boundary detection identifies untested input space
- [ ] Drift from stable region is quantified (not just "changed")

### Phase C: Regression Engine (Automated Assurance)

**Goal:** Every execution becomes an automatic regression test. Changes are validated against behavioral history.

**Implementation:**

```bash
# packages/dspx-core/src/dspx/regression/
├── __init__.py
├── capture.py         # Harvest test cases from runs
├── runner.py          # Replay against new config
├── drift.py           # Semantic drift detection
├── report.py          # Diff and explanation generation
└── ci.py              # CI integration helpers
```

**CLI Commands:**

```bash
# Capture high-quality runs as test cases
dspx regression capture --from-mlflow --min-quality 0.8 --since 7d

# Run regression suite
dspx regression run --against claude-3.5-sonnet --fail-threshold 0.15

# Compare behavioral diff between branches
dspx regression diff --baseline main --compare feature-branch

# Generate CI configuration
dspx regression ci --output .github/workflows/behavioral-regression.yml
```

**Regression Report:**

```
╔═══════════════════════════════════════════════════════════════════════════╗
║                     BEHAVIORAL REGRESSION REPORT                          ║
╠═══════════════════════════════════════════════════════════════════════════╣
║ Baseline: main @ a1b2c3d   Compare: feature-prompt-tweak @ x9y8z7w       ║
║ Test Cases: 127                                                            ║
╠═══════════════════════════════════════════════════════════════════════════╣
║                                                                           ║
║  ✓ Passed:     119 (93.7%)                                                ║
║  ⚠ Drifted:      5 ( 3.9%)  — semantic change, within tolerance          ║
║  ✗ Regressed:    3 ( 2.4%)  — exceeded drift threshold                   ║
║                                                                           ║
╠═══════════════════════════════════════════════════════════════════════════╣
║ REGRESSED CASES:                                                          ║
║                                                                           ║
║ 1. signature/classify-ticket (drift: 0.42)                               ║
║    Input: "The login page is broken, urgent!"                            ║
║    Baseline output: {category: bug, priority: high, ...}                 ║
║    New output:      {category: incident, priority: critical, ...}        ║
║    Semantic diff: category shifted from bug→incident                     ║
║                                                                           ║
║ 2. signature/extract-entities (drift: 0.38)                              ║
║    Input: "Contact John at john@example.com for details"                 ║
║    Baseline: entities=[name: John, email: john@example.com]              ║
║    New:      entities=[name: John]  ← EMAIL DROPPED                      ║
║    ⚠ Potential invariant violation: no-pii (PII not detected)            ║
║                                                                           ║
╚═══════════════════════════════════════════════════════════════════════════╝

Recommendation: DO NOT MERGE
  - 3 behavioral regressions detected
  - 1 potential invariant violation
  - Review changed prompts in signatures/classify.py
```

**Acceptance Criteria:**
- [ ] Runs automatically harvested as regression tests
- [ ] Semantic drift quantified with threshold-based failure
- [ ] Before/after diffs show *why* change occurred
- [ ] CI integration fails builds on unacceptable drift

### Phase D: Predictive Dynamics (The Oracle Awakens)

**Goal:** Don't just detect drift—predict it. Simulate behavioral changes before committing code.

**Implementation:**

```bash
# packages/dspx-core/src/dspx/dynamics/
├── __init__.py
├── simulator.py       # Predict outcomes without running
├── predictor.py       # Forecast drift trajectory
├── counterfactual.py  # "What if" analysis
└── synthesizer.py     # Generate boundary test cases
```

**CLI Commands:**

```bash
# Simulate change before committing
dspx oracle simulate --change prompt.yaml --against baseline

# Predict drift trajectory
dspx oracle forecast --horizon 30d --confidence 0.95

# Counterfactual: what if I had used different provider?
dspx oracle counterfactual --run-id abc123 --provider claude

# Synthesize edge case tests
dspx oracle synthesize --boundary-coverage 0.95
```

**Simulation Output:**

```
╔═══════════════════════════════════════════════════════════════════════════╗
║                     BEHAVIORAL SIMULATION RESULT                          ║
╠═══════════════════════════════════════════════════════════════════════════╣
║                                                                           ║
║  Change: prompt.yaml (instruction template modified)                      ║
║  Simulated against: 127 historical test cases                             ║
║                                                                           ║
║  ┌─────────────────────────────────────────────────────────────────────┐ ║
║  │  Predicted Behavioral Impact:                                        │ ║
║  │                                                                      │ ║
║  │    112 cases (88%) → No significant change                          │ ║
║  │     11 cases ( 9%) → Minor drift (semantic_distance < 0.1)          │ ║
║  │      4 cases ( 3%) → Moderate drift (semantic_distance 0.1-0.3)     │ ║
║  │      0 cases ( 0%) → Severe drift (semantic_distance > 0.3)         │ ║
║  │                                                                      │ ║
║  │  Invariant Projections:                                              │ ║
║  │    ✓ no-pii:         100% compliant (predicted)                     │ ║
║  │    ✓ json-valid:     100% compliant (predicted)                     │ ║
║  │    ⚠ no-hallucination: 2 cases approaching boundary                 │ ║
║  └─────────────────────────────────────────────────────────────────────┘ ║
║                                                                           ║
║  RECOMMENDATION: SAFE TO COMMIT                                          ║
║    All invariants preserved, drift within acceptable bounds.             ║
║                                                                           ║
╚═══════════════════════════════════════════════════════════════════════════╝
```

**Acceptance Criteria:**
- [ ] Changes can be simulated before execution
- [ ] Drift trajectory predictable from historical patterns
- [ ] Counterfactual analysis shows provider alternatives
- [ ] Edge case synthesis improves boundary coverage

### Phase E: Oracle Interface (Full Vision)

**Goal:** The complete interface for behavioral navigation.

**CLI Commands (Full Set):**

```bash
# === NAVIGATION ===
dspx oracle navigate --to "stable classification region"
dspx oracle path --from current --to optimal --show-steps

# === PROOF ===
dspx oracle prove --invariant no-pii --exhaustive
dspx oracle prove --equivalence sig-a sig-b --threshold 0.95

# === SYNTHESIS ===
dspx oracle synthesize --find-failure-modes
dspx oracle synthesize --cover-boundary 0.99

# === TIME TRAVEL ===
dspx oracle travel --to 2024-01-15 --query "classify this"
dspx oracle history --run-id abc123 --show-evolution

# === FINGERPRINTING ===
dspx oracle fingerprint --provider claude-3.5-sonnet
dspx oracle compare-providers --for "sentiment analysis"

# === CONVERGENCE ===
dspx oracle convergence --optimizer-iterations 50 --toward ground-truth
dspx oracle divergence --detect --threshold 0.1
```

### Multi-Perspective Review

| Perspective | Files to Review | Key Questions |
|-------------|-----------------|---------------|
| **ML Systems Engineer** | `coordinates/`, `topology/` | Embedding model choice? Latency of coordinate computation? |
| **Data Engineer** | `coordinates/storage.py` | Index scaling? Incremental updates? Query patterns? |
| **QA Engineer** | `regression/` | Test case selection bias? False positive/negative rates? |
| **Security Reviewer** | All modules | Embedding model data handling? PII in coordinates? |
| **DX Specialist** | CLI commands | Are commands intuitive? Error messages actionable? |

### Dependencies

- **Required:** `sentence-transformers` or similar embedding library
- **Optional:** `umap-learn` for territory visualization, `scikit-learn` for clustering
- **Infrastructure:** Vector index (SQLite with sqlite-vss, or external like Chroma/Qdrant)

### Implementation Order

```
Week 1-2: Phase A (Semantic Coordinates)
  └── Foundation layer, enables everything else

Week 3-4: Phase B (Behavioral Topology)
  └── Territory mapping, invariant definition

Week 5-6: Phase C (Regression Engine)
  └── Immediate practical value, CI integration

Week 7-8: Phase D (Predictive Dynamics)
  └── Advanced simulation, forecasting

Week 9+: Phase E (Oracle Interface)
  └── Full vision, advanced commands
```

### Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Drift detection accuracy | >95% | Manual validation of flagged regressions |
| False positive rate | <5% | Regressions that weren't actually regressions |
| Test case synthesis quality | >80% useful | Human evaluation of suggested edge cases |
| Simulation accuracy | >90% | Simulated predictions match actual runs |
| CI integration adoption | All PRs | Behavioral regression runs on every PR |

---

## 9) Keep docs synchronized with branch reality

Actions:
1. Update together when behavior changes:
   - `README.md`
   - `PROJECT_STATUS.md`
   - `NEXT_STEPS.md`
   - `docs/MLFLOW_OBSERVABILITY_PLAN.md`
   - `docs/RUN_REPLAY_EXPLAIN.md`
2. Ensure status/roadmap language matches actual tested behavior.

### Multi-Perspective Review

| Perspective | Review Focus |
|-------------|--------------|
| **DX Specialist** | Are CLI examples copy-pasteable? Error messages match docs? |
| **Test Coverage Reviewer** | Do docs describe tested behavior? Any doc/test drift? |
| **Framework Architect** | Are architecture claims accurate? Diagrams current? |

### Bugs to Check

- [ ] No contradictory command/flag guidance across canonical docs
- [ ] New context handoff can be copied directly from docs
- [ ] Examples in docs match actual CLI output
- [ ] Version numbers/dependencies in docs are current

Acceptance:
- No contradictory command/flag guidance across canonical docs.
- New context handoff can be copied directly from docs.
