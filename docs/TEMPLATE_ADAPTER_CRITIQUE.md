---
summary: "Critique of DSPy template adapter behavior and boundaries."
read_when:
  - "You are reviewing template adapter design concerns."
  - "You need critique context before changing adapter code."
type: "review"
---

# Template Adapter Integration — Architectural Critique

**Status:** Critical review of `docs/TEMPLATE_ADAPTER_INTEGRATION.md`
**Date:** 2026-02-21
**Upstream reference:** `~/programming/upstream/dspy-template-adapter/`

---

## Expert 1: DSPy Framework Architect

### Fatal Flaws

1. **`parse_mode="chat"` fallback produces format mismatches**

   The integration doc states `parse_mode="chat"` will "delegate to `ChatAdapter.parse()`". However, `ChatAdapter.parse()` expects the completion to contain `[[ ## field_name ## ]]` markers. If the template rendered no such markers (which is the whole point — exact fidelity), the LM won't produce them, and parsing will fail with `AdapterParseError`.

   **Fix:** Either:
   - Remove `parse_mode="chat"` from the proposed modes entirely — it's semantically incompatible.
   - Document it as "legacy fallback" only for signatures that explicitly include ChatAdapter-style markers in their templates.

2. **`{instruction}` slot NOT guaranteed optimizable through the wrapper**

   The doc claims the `{instruction}` slot is optimizable by MIPROv2/COPRO. This is true *only* if:
   - The adapter instance is bound globally (`dspy.configure(adapter=...)`) and the optimizer can access it.
   - The `DSPxTemplateAdapter` wrapper preserves the underlying `TemplateAdapter` instruction field mutation path.

   Current design wraps with `DSPxTemplateAdapter.build()` returning a fresh `TemplateAdapter` per-call. If optimizers cache the adapter at configure-time, per-call rebuilds will break instruction propagation.

   **Fix:** Cache the built adapter per-provider-config tuple, and ensure `signature.instructions` is read *after* any optimizer mutation, not at build-time.

3. **Per-module adapter binding conflicts with global state silently**

   The proposed `Predict(SigGenSignature, adapter=adapter)` pattern uses `settings.context(adapter=self.adapter)` which temporarily overrides the global adapter. However:
   - DSPy callbacks are not guaranteed adapter-aware.
   - Nested module calls (a module calling another Predict) will restore the wrong adapter on exit.

   **Fix:** Document explicit constraint: "Per-module adapter binding is safe only for leaf modules. For composite modules, use global adapter configuration."

### Significant Risks

1. **Demo injection edge cases in optimizer flows**

   `TemplateAdapter._format_demos_as_messages()` auto-injects demos if not consumed by template. But `BootstrapFewShot` and `GEPA` may provide demos with partial fields. The current `_parse_json` requires all output fields present — partial demos will cause `AdapterParseError` at training time.

   **Mitigation:** Add `demo_completion_mode: "strict" | "partial"` config to control whether missing output fields are tolerated in demo parsing.

2. **Thread-safety of `settings.context()` for async/concurrent calls**

   DSPy's `settings.context()` uses `contextvars`. The `Predict.forward()` override correctly uses `with settings.context(...)`. However, if the user's code spawns concurrent calls to the same `Predict` instance with different adapters, the adapter will be correctly scoped. BUT — `DSPxTemplateAdapter.build()` creates new adapter instances; if the same `LMBase` instance is shared across threads with different `provider_caps`, the adapter's parse_mode could differ per call unpredictably.

   **Mitigation:** Make `provider_caps` part of the adapter cache key, not a runtime resolution parameter.

3. **History field extraction mutates inputs**

   `TemplateAdapter.format()` does `inputs.pop(history_field_name)` when extracting `History`. If the same `inputs` dict is reused across multiple calls (e.g., in a retry loop), the history is lost on retry.

   **Mitigation:** The current code does `inputs = dict(inputs)` (shallow copy) at the top, which is safe. Verify this pattern is preserved in the wrapper.

### Minor Improvements

1. **`_TEMPLATE_CONFIG` mutable global in generated programs**

   Embedding `_TEMPLATE_CONFIG = {...}` in generated code is convenient but mutable. Users could accidentally mutate it across runs.

   **Suggestion:** Use `@dataclass(frozen=True)` or `typing.Final` with a factory function.

2. **Missing `__repr__` for debugging**

   `DSPxTemplateAdapter` lacks `__repr__`. Add one showing config hash and resolved parse_mode.

### Open Questions

1. How does `TemplateAdapter` interact with DSPy's `lm.inspect_history(n)`? Will rendered templates appear correctly?
2. Is there a memory leak risk if adapters are cached indefinitely without eviction policy?

---

## Expert 2: Provider Abstraction Engineer

### Fatal Flaws

1. **Capability → parse_mode mapping is incomplete and inaccurate**

   The doc's table claims:
   - Claude → `xml` (no `json_mode`)
   - Codex/Gemini CLI → `auto` → `json`

   **Reality check:**
   - Claude 3.5+ *does* support `json_mode` via `--output-format json` or API parameter.
   - Gemini CLI has no guaranteed JSON mode; output is free-form.
   - OpenRouter proxies to underlying models — capability varies per-route.

   **Fix:** Replace static mapping with runtime capability detection:
   ```python
   def _resolve_parse_mode(self, provider_caps):
       if provider_caps and provider_caps.get("json_mode"):
           return "json"
       if provider_caps and provider_caps.get("structured_output_format") == "xml":
           return "xml"
       return "json"  # with json_repair fallback
   ```

2. **`MultiProviderLM` fans out to children with different capabilities — single adapter is wrong**

   If `MultiProviderLM` has `[OpenAI_LM, Claude_LM]` with `json_mode=True` and `json_mode=False` respectively, a single adapter with `parse_mode="json"` will:
   - Work for OpenAI (native JSON).
   - Rely on `json_repair` for Claude (works, but not ideal).

   But the doc doesn't explain how `provider_caps` is obtained for `MultiProviderLM`. `_combine_caps()` uses `any()` for `json_mode` — meaning if *any* child supports JSON, the aggregate reports `json_mode=True`. This is misleading.

   **Fix:**
   - For `MultiProviderLM`, use the *most restrictive* parse_mode across children (i.e., `all()` not `any()` for JSON).
   - Or, document that `MultiProviderLM` requires homogeneous providers for template adapter use.

### Significant Risks

1. **`json_repair` not robust for all CLI-provider quirks**

   `json_repair` handles common issues (trailing commas, unquoted keys) but fails on:
   - Providers that emit JSON wrapped in markdown fences (` ```json ... ``` `).
   - Providers that intersperse JSON with reasoning text ("Let me think... here's the JSON: {...}").
   - Providers that truncate JSON due to token limits.

   **Mitigation:**
   - Pre-process completion with markdown fence stripping.
   - Add `json_extract_strategy: "repair" | "regex" | "custom"` config.

2. **XML parse mode handles nested tags poorly**

   The regex `<{name}>(.*?)</{name}>` with `DOTALL` fails on:
   - Nested tags: `<output><nested>val</nested></output>`
   - CDATA: `<output><![CDATA[<not>a<tag>]]></output>`
   - Malformed: `<output>unclosed`

   **Mitigation:** Use a proper XML parser (`xml.etree.ElementTree` or `lxml`) with fallback to regex.

3. **Degradation path when provider claims `json_mode` but emits invalid JSON**

   If a provider claims `json_mode=True` but still returns invalid JSON (model bug, temperature spike), the current code raises `AdapterParseError` immediately.

   **Mitigation:** Add fallback chain:
   ```python
   try:
       return self._parse_json(signature, completion)
   except AdapterParseError:
       if provider_caps.get("json_mode"):
           logger.warning("Provider claimed json_mode but returned invalid JSON; falling back to json_repair")
           # retry with more aggressive repair
   ```

### Minor Improvements

1. **Missing capability discovery interface**

   The doc uses `getattr(lm, "capabilities", None)` but doesn't standardize the schema. Add `ProviderCapabilities` DTO requirement.

2. **No telemetry for parse_mode selection**

   When `parse_mode="auto"`, log the resolved mode for debugging.

### Open Questions

1. How should `GeminiCLILM` advertise its capabilities? It currently has no `capabilities` attribute.
2. For `OpenRouterLM`, should we query the `/models` endpoint for per-model capability discovery?

---

## Expert 3: Python API Design & DX Specialist

### Fatal Flows

1. **`TemplateAdapterConfig` has escape hatch deficiency**

   Users can't easily extend the message list with dynamic content at runtime (e.g., inject current timestamp, user ID). The `register_helpers` pattern requires pre-declaring import paths, which doesn't support closures or context-dependent values.

   **Fix:** Add `extra_context: Dict[str, Any]` field that merges into the rendering context, and allow callables as values:
   ```python
   extra_context={
       "current_time": lambda: datetime.now().isoformat(),
       "user_id": get_current_user_id,  # callable
   }
   ```

2. **Error messages are NOT actionable when adapter not installed**

   The proposed error:
   ```
   "dspy-template-adapter is not installed. Install with: pip install dspx-core[templates]"
   ```
   Is good, but the check happens at `DSPxTemplateAdapter.__init__`, not at CLI parse time. Users who pass `--template-config` but haven't installed the dep will get a late error after other work has started.

   **Fix:** Check availability at CLI entrypoint when `--template-config` is passed; fail fast with install instructions.

### Significant Risks

1. **YAML config file format lacks validation**

   The doc shows a YAML example but doesn't specify:
   - Required vs optional fields
   - Validation of `role` enum values
   - How errors are reported

   **Mitigation:** Add JSON Schema for the config file and validate at load time with clear error messages pointing to line numbers.

2. **`parse_mode: "auto"` behavior is not debuggable**

   Users won't know which parse_mode was selected. The `--verbose` flag should log the resolution chain.

3. **`register_helpers: {name: "import.path.fn"}` has security implications**

   Users could load arbitrary code. If configs are shared (e.g., in a team), this is an RCE vector.

   **Mitigation:**
   - Add `allow_helpers: bool` gate (default `False`).
   - Validate import paths against an allowlist.

### Minor Improvements

1. **DTO hierarchy over-engineered for Phase 1**

   `TemplateMessage` + `TemplateAdapterConfig` + extension of `SignatureGenRequest` adds three new types for an optional feature. Consider a single flat config dict initially, promote to typed DTOs once the API stabilizes.

2. **Generated program embeds `_TEMPLATE_CONFIG` as mutable global**

   Already flagged by Expert 1. Suggest generating a `get_template_config()` factory function instead.

3. **Missing `--dry-run` flag for template preview**

   Users should be able to `dspx signature gen "task" --template-config ./triage.yaml --dry-run` to see rendered messages without calling the LM.

### Open Questions

1. Should `TemplateAdapterConfig` be hashable for caching? If so, how to handle `extra_context` with callables?
2. What's the migration path for users who already have custom `dspy.Predict` subclasses? Will they need to change to `dspy_template_adapter.Predict`?

---

## Synthesis: Prioritized Revision List

### P0 — Must fix before implementation

| # | Issue | Owner | Fix |
|---|-------|-------|-----|
| 1 | `parse_mode="chat"` is incompatible with exact-fidelity templates | Framework | Remove from proposed modes or add explicit warning |
| 2 | `{instruction}` slot not optimizable due to per-call adapter rebuild | Framework | Cache adapter per-config, read `signature.instructions` at render time |
| 3 | Capability → parse_mode mapping is wrong (Claude has json_mode) | Provider | Use runtime detection, not static table |
| 4 | `MultiProviderLM` aggregate capabilities mislead adapter selection | Provider | Use `all()` for json_mode, or require homogeneous providers |
| 5 | Late error when adapter not installed but config provided | DX | Check at CLI entrypoint, fail fast |

### P1 — Address with mitigation

| # | Issue | Owner | Mitigation |
|---|-------|-------|------------|
| 6 | Per-module adapter binding conflicts with global state | Framework | Document leaf-module-only constraint |
| 7 | `json_repair` not robust for markdown-wrapped JSON | Provider | Pre-process with fence stripping |
| 8 | XML parser fails on nested/CDATA/malformed | Provider | Switch to `ElementTree` with fallback |
| 9 | YAML config lacks validation | DX | Add JSON Schema, validate at load |
| 10 | `register_helpers` RCE risk | DX | Add `allow_helpers` gate + allowlist |

### P2 — Nice-to-haves

| # | Issue | Owner | Improvement |
|---|-------|-------|-------------|
| 11 | `_TEMPLATE_CONFIG` mutable global | DX | Generate factory function |
| 12 | Missing `__repr__` for debugging | Framework | Add `__repr__` |
| 13 | No `--dry-run` for template preview | DX | Add flag |
| 14 | No telemetry for parse_mode resolution | Provider | Log resolved mode |

---

## Recommended Next Steps

1. **Update `TEMPLATE_ADAPTER_INTEGRATION.md`** with P0 fixes before any code is written.
2. **Create `ProviderCapabilities` contract** in `dspx/capabilities.py` with explicit fields:
   - `json_mode: bool`
   - `structured_output_format: Literal["json", "xml", "none"]`
   - `supports_tools: bool`
3. **Add adapter availability check** in CLI entrypoint (`dspx/cli/`) for `--template-config` path.
4. **Prototype `DSPxTemplateAdapter`** with caching keyed by `(config_hash, provider_caps_hash)`.
5. **Write integration tests** for `MultiProviderLM` + template adapter edge cases before declaring Phase 1 complete.
