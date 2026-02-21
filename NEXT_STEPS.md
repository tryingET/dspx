# Next Steps

Current branch context: `main`.
Execution mode reference: full-sweep (DSPx + upstream MLflow + upstream DSPy), ordered waves.

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

1. **ProviderCapabilities contract** — Define `dspx/capabilities.py` with explicit fields:
   ```python
   @dataclass(frozen=True)
   class ProviderCapabilities:
       json_mode: bool
       structured_output_format: Literal["json", "xml", "none"]
       supports_tools: bool
   ```

2. **Capability discovery interface** — Add `capabilities` property to all `*LM` classes:
   - `ClaudeHeadlessLM.capabilities`
   - `CodexExecLM.capabilities`
   - `GeminiCLILM.capabilities`
   - `OpenRouterLM.capabilities` (query `/models` or static mapping)
   - `MultiProviderLM.capabilities` — use `all()` for json_mode, not `any()`

3. **CLI fast-fail for missing dep** — When `--template-config` passed, check adapter availability at entrypoint:
   ```python
   if template_config and not _adapter_available():
       sys.exit("dspy-template-adapter not installed. Run: pip install dspx-core[templates]")
   ```

4. **TemplateAdapterConfig DTO** — Add to `dspx/dtos.py`:
   - `TemplateMessage`
   - `TemplateAdapterConfig`
   - Extend `SignatureGenRequest.template_adapter: Optional[TemplateAdapterConfig]`

5. **YAML config schema** — Add JSON Schema for template config validation:
   - `docs/schemas/template-adapter-config.schema.json`
   - Validate at load with line-number error messages

6. **`--dry-run` flag** — Add to `dspx signature gen --template-config ... --dry-run` to preview rendered messages without LM call

### Acceptance Criteria for Implementation

Proceed with `DSPxTemplateAdapter` implementation when:

- [ ] Upstream #1 (XML parser) fixed OR we vendor a patched version
- [ ] Upstream #2 (JSON markdown) fixed OR we pre-process in wrapper
- [ ] Upstream #6 (partial demos) fixed OR we filter demos in wrapper
- [ ] DSPx-side ProviderCapabilities contract merged
- [ ] All providers expose `.capabilities` property
- [ ] CLI fast-fail implemented
- [ ] TemplateAdapterConfig DTO added

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

Acceptance:
- Issue/PR decomposition is concrete and test-gated.
- Legacy callback compatibility is preserved.

---

## 5) Wave-4 downstream reconciliation plan

Actions:
1. Track upstream release readiness checkpoints.
2. Define dependency floor bump steps + rollback posture.
3. Re-verify replay/explain behavior after dependency updates.

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

Acceptance:
- Router behavior deterministic under fixture coverage.
- No drift between extension behavior and schema/docs.

---

## 7) Keep docs synchronized with branch reality

Actions:
1. Update together when behavior changes:
   - `README.md`
   - `PROJECT_STATUS.md`
   - `NEXT_STEPS.md`
   - `docs/MLFLOW_OBSERVABILITY_PLAN.md`
   - `docs/RUN_REPLAY_EXPLAIN.md`
2. Ensure status/roadmap language matches actual tested behavior.

Acceptance:
- No contradictory command/flag guidance across canonical docs.
- New context handoff can be copied directly from docs.
