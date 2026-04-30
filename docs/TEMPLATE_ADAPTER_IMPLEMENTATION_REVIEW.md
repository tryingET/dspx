---
summary: "Implementation review for the DSPy template adapter."
read_when:
  - "You are changing or reviewing template adapter implementation."
  - "You need prior implementation review context."
type: "review"
---

# Template Adapter Implementation Review

**Date:** 2026-02-21
**Review scope:** ProviderCapabilities, CLI fast-fail, MultiProviderLM aggregation

---

## Expert 1: Capabilities Contract Reviewer

### Bugs Found

1. **ProviderCapabilities is mutable** — Pydantic `BaseModel` is mutable by default. Users could accidentally mutate capabilities at runtime.

   **Fix:** Add `model_config = ConfigDict(frozen=True)` or use `@dataclass(frozen=True)`:
   ```python
   from pydantic import BaseModel, ConfigDict

   class ProviderCapabilities(BaseModel):
       model_config = ConfigDict(frozen=True)
       # ... fields
   ```

### Design Questions

1. **Should `supports_vision` and `supports_audio` be in base contract?**
   - Currently in base, but most providers don't use them.
   - **Recommendation:** Keep in base for now, but mark as "optional extensions" in docstring.

2. **Is `Literal["json", "xml", "none"]` complete?**
   - Missing: `"yaml"`, `"markdown"`, `"chat"` (for DSPy's ChatAdapter format)
   - **Recommendation:** Add `"yaml"` for future-proofing. Skip `"chat"` as it's semantically different (requires markers in prompt).

### Minor Improvements

1. Add `__repr__` customization for cleaner debugging output.

---

## Expert 2: Provider Implementation Reviewer

### Bugs Found

1. **`_combine_caps()` returns `json_mode=True` for empty provider list**

   ```python
   json_mode = all(
       getattr(getattr(p, "capabilities", None), "json_mode", False)
       for p in providers
   )
   # If providers=[], then all() returns True!
   ```

   **Fix:** Add explicit empty check:
   ```python
   if not providers:
       return ProviderCapabilities()  # Return defaults

   json_mode = all(...)
   ```

2. **`_combine_caps()` doesn't aggregate `supports_vision` or `supports_audio`**

   New fields added to `ProviderCapabilities` but not included in aggregation.

   **Fix:** Add aggregation logic:
   ```python
   supports_vision = any(
       getattr(getattr(p, "capabilities", None), "supports_vision", False)
       for p in providers
   )
   supports_audio = any(
       getattr(getattr(p, "capabilities", None), "supports_audio", False)
       for p in providers
   )
   ```

### Design Questions

1. **Is `ClaudeHeadlessLM.structured_output_format` correct?**
   - Current: `"json"` when `output_format in {"json", "stream-json"}`, else `"xml"`
   - Claude 3.5+ actually supports native JSON mode, so this is reasonable.
   - **Recommendation:** Correct as-is.

2. **Is `CodexExecLM.json_mode=True` correct?**
   - Codex is OpenAI-based and supports JSON mode, but not all models guarantee valid JSON.
   - **Recommendation:** Keep `True` but add comment noting model-dependent behavior.

3. **Is `OpenRouterLM.structured_output_format="none"` too conservative?**
   - OpenRouter proxies to many models, some support JSON, some don't.
   - **Recommendation:** Keep `"none"` as safe default. Could add model-aware detection later.

### Test Gaps

1. **No tests for `_combine_caps()` edge cases:**
   - Empty provider list
   - Provider with `capabilities=None`
   - Provider with missing capability fields

---

## Expert 3: CLI Integration Reviewer

### Bugs Found

1. **`--template-config` doesn't validate file existence**

   If user passes `--template-config ./missing.yaml` and adapter is installed, the command proceeds and will fail later with a confusing error.

   **Fix:** Check file exists before adapter availability:
   ```python
   if template_config is not None:
       if not template_config.exists():
           typer.echo(f"Error: Template config file not found: {template_config}", err=True)
           raise typer.Exit(code=2)
       _require_template_adapter("template-config")
   ```

### Design Questions

1. **Should `--template-config` be added to `mermaid sig` and `mermaid gen`?**
   - These commands also use signature generation under the hood.
   - **Recommendation:** Yes, for consistency. But defer to future work since mermaid commands are less commonly used with templates.

2. **Should there be a `--template-adapter` boolean flag separate from `--template-config`?**
   - Current: `--template-config` implies adapter usage.
   - **Recommendation:** No, `--template-config` is sufficient. Users who want default templates can use a config file.

### Test Gaps

1. **Missing test for non-existent config file:**
   ```python
   def test_cli_signature_gen_template_config_fails_on_missing_file(monkeypatch):
       """Test that --template-config fails when file doesn't exist."""
       monkeypatch.setenv("MLFLOW_ENABLE", "0")

       result = runner.invoke(
           app,
           ["signature", "gen", "test", "--template-config", "/nonexistent.yaml"],
       )

       assert result.exit_code == 2
       assert "not found" in result.stderr.lower() or "not found" in result.stdout.lower()
   ```

2. **Missing test for when adapter IS available:**
   - Current tests only verify fast-fail when adapter NOT installed.
   - Should test that `--template-config` works when adapter IS installed (even if just parsing the config).

---

## Expert 4: Type Safety Reviewer

### Bugs Found

None. The `# type: ignore[import-untyped]` on the dspy_template_adapter import is justified since it's an optional dependency.

### Minor Improvements

1. **Consider using `TypedDict` for the aggregation result** instead of building inline.

2. **Export `StructuredOutputFormat` type alias for reuse:**
   ```python
   from typing import Literal, TypeAlias

   StructuredOutputFormat: TypeAlias = Literal["json", "xml", "none"]

   class ProviderCapabilities(BaseModel):
       structured_output_format: StructuredOutputFormat = Field(...)
   ```

---

## Summary: Must-Fix Before Proceeding

| # | Bug | Location | Fix |
|---|-----|----------|-----|
| 1 | ProviderCapabilities mutable | `capabilities.py` | Add `frozen=True` config |
| 2 | Empty provider list → json_mode=True | `multi_provider_lm.py` | Add empty check |
| 3 | Missing supports_vision/audio aggregation | `multi_provider_lm.py` | Add aggregation |
| 4 | No file existence check for --template-config | `cli/dspx.py` | Add check before adapter check |

## Summary: Test Gaps to Address

| # | Gap | Location |
|---|-----|----------|
| 1 | `_combine_caps()` edge cases | `tests/test_multi_provider_lm.py` |
| 2 | Non-existent config file | `tests/test_cli_dspx.py` |
| 3 | Adapter available + valid config | `tests/test_cli_dspx.py` (skip if not installed) |

---

## Next Steps

1. Fix all P0 bugs (4 items above)
2. Add missing tests (3 test gaps)
3. Update the canonical project direction docs under `docs/project/` if this review changes the active wave
4. Proceed to TemplateAdapterConfig DTO
