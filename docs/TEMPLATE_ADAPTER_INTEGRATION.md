---
summary: "Architecture for optional dspy-template-adapter integration"
read_when:
  - "You are adding prompt template control features"
  - "You are implementing provider-aware output format selection"
  - "You are extending signature/module generation with custom adapters"
---

# Template Adapter Integration Architecture

## Overview

This document describes how to optionally integrate [dspy-template-adapter](https://github.com/MaximeRivest/dspy-template-adapter) into DSPx. The integration provides:

1. **Exact prompt fidelity** — User-defined message templates with no hidden rewriting
2. **Provider-aware output formats** — Auto-select `json`/`xml`/`full_text` based on provider capabilities
3. **Optimizer-compatible templates** — `{instruction}` slot is optimizable by MIPRO/COPRO
4. **Finetuning data export** — Generate OpenAI-compatible training data from runs

**Key principle:** Optional, non-breaking, layered integration. Core dspx functionality works without this dependency.

---

## Current State

### dspx Prompt Handling

```
services/ (SignatureService, CodegenService, etc.)
    ↓
templates/ (signature_templates.py, codegen_templates.py)
    ↓ format_signature_spec_prompt(), render_signature_from_spec()
dspy.Predict("task -> spec_json")  # Uses DSPy's default ChatAdapter
    ↓
providers/ (CodexExecLM, ClaudeHeadlessLM, etc.)
```

Problems:
- No user control over exact message structure
- Output format is hardcoded (JSON-ish parsing)
- Optimizers can't easily tune prompt structure

### dspy-template-adapter Capabilities

```python
TemplateAdapter(
    messages=[
        {"role": "system", "content": "{instruction}"},
        {"role": "user", "content": "{inputs(style='yaml')}"},
    ],
    parse_mode="json",  # or "xml", "full_text", "chat", or callable
)
```

- Template syntax: `{field}`, `{instruction}`, `{inputs()}`, `{outputs()}`, `{demos()}`
- Parse modes: `json` (with `json_repair`), `xml`, `full_text`, `chat`, custom callable
- Works with DSPy optimizers (MIPRO, COPRO, BootstrapFewShot, GEPA)
- `format_finetune_data()` for training data export

---

## Integration Architecture

### Layer Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        User API Layer                                │
│  CLI flags: --template-adapter, --parse-mode, --template-config     │
└─────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Service Layer (opt-in)                          │
│  SignatureService, CodegenService, ModuleService                     │
│  - If template_adapter_config provided → use DSPxTemplateAdapter    │
│  - Else → use existing template functions (unchanged)               │
└─────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    DSPx Adapter Wrapper                              │
│  packages/dspx-core/src/dspx/adapters/prompt_adapter.py             │
│                                                                      │
│  - TemplateAdapterConfig DTO                                         │
│  - DSPxTemplateAdapter (provider-aware wrapper)                      │
│  - Capability → parse_mode mapping                                   │
│  - Integration with ProviderRegistry                                 │
└─────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                 dspy-template-adapter (optional dep)                 │
│  TemplateAdapter, Predict (per-module adapter binding)               │
└─────────────────────────────────────────────────────────────────────┘
```

### Package Structure

```
packages/dspx-core/
├── pyproject.toml              # Add optional dep: [project.optional-dependencies].templates
├── src/dspx/
│   ├── adapters/
│   │   ├── __init__.py         # Export prompt_adapter symbols
│   │   ├── datasets.py         # Existing
│   │   ├── eval.py             # Existing
│   │   ├── stores.py           # Existing
│   │   └── prompt_adapter.py   # NEW: TemplateAdapterConfig, DSPxTemplateAdapter
│   ├── dtos.py                 # Add TemplateAdapterConfig
│   └── services/
│       ├── signatures_service.py  # Opt-in use of template adapter
│       ├── codegen_service.py     # Opt-in use of template adapter
│       └── ...
```

---

## DTOs

### TemplateAdapterConfig

```python
# packages/dspx-core/src/dspx/dtos.py

class TemplateMessage(BaseModel):
    """A single message template."""
    role: Literal["system", "user", "assistant", "demos", "history"]
    content: Optional[str] = None  # Required except for demos/history directives
    # For demos directive customization:
    user_template: Optional[str] = Field(default=None, alias="user")
    assistant_template: Optional[str] = Field(default=None, alias="assistant")


class TemplateAdapterConfig(BaseModel):
    """Configuration for TemplateAdapter integration."""

    messages: List[TemplateMessage] = Field(
        default_factory=lambda: [
            TemplateMessage(role="system", content="{instruction}"),
            TemplateMessage(role="user", content="{inputs(style='yaml')}"),
        ],
        description="Message templates for the adapter",
    )

    parse_mode: Literal["json", "xml", "full_text", "chat", "auto"] = Field(
        default="auto",
        description="Output parsing mode. 'auto' selects based on provider capabilities.",
    )

    custom_parse_fn: Optional[str] = Field(
        default=None,
        description="Import path to custom parse function (signature, completion) -> dict",
    )

    register_helpers: Dict[str, str] = Field(
        default_factory=dict,
        description="Map of helper name -> import path for custom template functions",
    )

    class Config:
        # Allow extra fields for future extensibility
        extra = "allow"
```

### Extended Request DTOs

```python
# Add to existing SignatureGenRequest
class SignatureGenRequest(BaseModel):
    prompt: str
    use_cot: bool = Field(default=False)
    template_version: Optional[str] = None
    options: Dict[str, Any] = Field(default_factory=dict)

    # NEW: opt-in template adapter
    template_adapter: Optional[TemplateAdapterConfig] = Field(
        default=None,
        description="If provided, use TemplateAdapter instead of built-in templates",
    )
```

---

## Core Components

### DSPxTemplateAdapter (Wrapper)

```python
# packages/dspx-core/src/dspx/adapters/prompt_adapter.py

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Literal, Optional

from dspx.dtos import TemplateAdapterConfig

if TYPE_CHECKING:
    from dspy.signatures.signature import Signature
    from dspx.lm_base import LMBase

# Lazy import marker
_TEMPLATE_ADAPTER_AVAILABLE: bool | None = None


def _check_available() -> bool:
    global _TEMPLATE_ADAPTER_AVAILABLE
    if _TEMPLATE_ADAPTER_AVAILABLE is None:
        try:
            import dspy_template_adapter  # noqa: F401
            _TEMPLATE_ADAPTER_AVAILABLE = True
        except ImportError:
            _TEMPLATE_ADAPTER_AVAILABLE = False
    return _TEMPLATE_ADAPTER_AVAILABLE


class DSPxTemplateAdapter:
    """Provider-aware wrapper around dspy-template-adapter.

    Responsibilities:
    - Lazy-load dspy-template-adapter only when needed
    - Auto-select parse_mode based on provider capabilities
    - Provide stable dspx API even if upstream changes
    - Graceful fallback when adapter not installed
    """

    def __init__(self, config: TemplateAdapterConfig):
        if not _check_available():
            raise ImportError(
                "dspy-template-adapter is not installed. "
                "Install with: pip install dspx-core[templates] or pip install dspy-template-adapter"
            )

        from dspy_template_adapter import TemplateAdapter

        self._config = config
        self._adapter: TemplateAdapter | None = None
        self._parse_mode_override: str | Callable | None = None

    def _resolve_parse_mode(
        self,
        provider_caps: dict[str, Any] | None,
    ) -> str | Callable:
        """Resolve parse_mode, handling 'auto' selection."""
        mode = self._config.parse_mode

        if mode == "auto":
            # Auto-select based on provider capabilities
            if provider_caps:
                if provider_caps.get("json_mode"):
                    return "json"
                # Claude works well with XML
                if provider_caps.get("provider_type") == "claude":
                    return "xml"
            # Default fallback
            return "json"

        if mode == "chat":
            return "chat"

        if self._config.custom_parse_fn:
            # Lazy-load custom parse function
            return self._load_parse_fn(self._config.custom_parse_fn)

        return mode

    def _load_parse_fn(self, import_path: str) -> Callable:
        """Load a custom parse function from import path."""
        module_path, fn_name = import_path.rsplit(".", 1)
        import importlib
        module = importlib.import_module(module_path)
        return getattr(module, fn_name)

    def build(
        self,
        provider_caps: dict[str, Any] | None = None,
    ) -> "dspy_template_adapter.TemplateAdapter":
        """Build the underlying TemplateAdapter with resolved parse_mode."""
        from dspy_template_adapter import TemplateAdapter

        messages = [m.model_dump(exclude_none=True) for m in self._config.messages]
        parse_mode = self._resolve_parse_mode(provider_caps)

        adapter = TemplateAdapter(
            messages=messages,
            parse_mode=parse_mode,
        )

        # Register custom helpers
        for name, import_path in self._config.register_helpers.items():
            fn = self._load_parse_fn(import_path)
            adapter.register_helper(name, fn)

        return adapter

    def preview(
        self,
        signature: type[Signature],
        inputs: dict[str, Any],
        demos: list[dict[str, Any]] | None = None,
        provider_caps: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Preview rendered messages without calling LM."""
        adapter = self.build(provider_caps)
        return adapter.preview(signature, demos or [], inputs)


# Convenience factory
def create_template_adapter(
    config: TemplateAdapterConfig | dict[str, Any] | None,
    provider_caps: dict[str, Any] | None = None,
) -> DSPxTemplateAdapter | None:
    """Factory function for creating adapter from config.

    Returns None if config is None (use default behavior).
    """
    if config is None:
        return None

    if isinstance(config, dict):
        config = TemplateAdapterConfig(**config)

    return DSPxTemplateAdapter(config)
```

---

## Service Integration

### SignatureService Integration

```python
# packages/dspx-core/src/dspx/services/signatures_service.py

def _run_signature_spec_generation(
    prompt_for_model: str,
    *,
    lm: LMBase | None = None,
    template_adapter_config: TemplateAdapterConfig | None = None,
    # ... existing params
) -> dict[str, Any]:
    """Internal: run signature spec generation with optional template adapter."""

    active_lm = lm or _get_default_lm()
    dspy.configure(lm=active_lm)

    # Build signature for the generation task
    class SigGenSignature(dspy.Signature):
        """Generate a DSPy signature schema from a task description."""
        task: str = dspy.InputField(desc="Task description")
        spec_json: str = dspy.OutputField(desc="JSON signature schema")

    # Check if template adapter is requested and available
    if template_adapter_config:
        from dspx.adapters.prompt_adapter import create_template_adapter

        adapter_wrapper = create_template_adapter(
            template_adapter_config,
            provider_caps=getattr(active_lm, "capabilities", None),
        )

        if adapter_wrapper:
            from dspy_template_adapter import Predict

            adapter = adapter_wrapper.build(
                provider_caps=getattr(active_lm, "capabilities", None)
            )
            predictor = Predict(SigGenSignature, adapter=adapter)
            result = predictor(task=prompt_for_model)
            return {"spec_json": result.spec_json}

    # Fallback: existing behavior with dspy.Predict
    predictor = dspy.Predict("task -> spec_json")
    result = predictor(task=prompt_for_model)
    return {"spec_json": result.spec_json}
```

### Generated Program Templates

For generated programs (Mermaid workflows, modules), embed template config:

```python
# Generated program output (example)
"""
import dspy
from dspy_template_adapter import TemplateAdapter, Predict

# Template configuration (optional customization)
_TEMPLATE_CONFIG = {
    "messages": [
        {"role": "system", "content": "{instruction}"},
        {"role": "user", "content": "{inputs(style='xml')}"},
    ],
    "parse_mode": "xml",
}

class StepSignature(dspy.Signature):
    \"\"\"Process a workflow step.\"\"\"
    context: str = dspy.InputField()
    output: str = dspy.OutputField()

# Users can override _TEMPLATE_CONFIG before running
_adapter = TemplateAdapter(**_TEMPLATE_CONFIG)
step_module = Predict(StepSignature, adapter=_adapter)
"""
```

---

## CLI Integration

### New Flags

```bash
# Signature generation with custom template
dspx signature gen "Summarize text" \
    --template-adapter \
    --parse-mode json \
    --system-prompt "You are a precise summarizer. {instruction}"

# Using a template config file
dspx signature gen "Classify tickets" \
    --template-config ./templates/triage.yaml

# Export finetuning data from recent runs
dspx signature export-finetune --output ./finetune_data.jsonl
```

### Template Config File Format

```yaml
# templates/triage.yaml
messages:
  - role: system
    content: |
      You are a ticket classifier. {instruction}
      Respond with valid JSON containing the output fields.
  - role: user
    content: |
      {inputs(style='yaml')}

parse_mode: json

# Optional: custom helpers
register_helpers:
  format_priority: myapp.template_helpers.format_priority
```

---

## Capability → Parse Mode Mapping

| Provider Type | `json_mode` | Recommended `parse_mode` | Notes |
|---------------|-------------|-------------------------|-------|
| OpenAI GPT-4 | ✅ | `json` | Native JSON mode |
| Claude | ❌ | `xml` | XML tags work better than JSON escaping |
| Codex/Gemini CLI | Varies | `auto` → `json` | Uses `json_repair` for robustness |
| OpenRouter | Varies | `auto` | Depends on underlying model |
| Multi-provider | Mixed | `json` | Safest default for composite |

---

## Dependency Management

### pyproject.toml

```toml
[project.optional-dependencies]
templates = [
    "dspy-template-adapter>=0.2",
]

# For development
[dependency-groups]
dev = [
    # ... existing
    "dspy-template-adapter>=0.2",
]
```

### Feature Detection Pattern

```python
# In services, always check availability
def _use_template_adapter(config: TemplateAdapterConfig | None) -> bool:
    if config is None:
        return False

    try:
        import dspy_template_adapter  # noqa: F401
        return True
    except ImportError:
        logger.warning(
            "template_adapter_config provided but dspy-template-adapter not installed. "
            "Falling back to default behavior. Install with: pip install dspx-core[templates]"
        )
        return False
```

---

## Testing Strategy

### Unit Tests (No Network)

```python
# tests/adapters/test_prompt_adapter.py

import pytest

def test_adapter_not_available_graceful():
    """Test graceful handling when dspy-template-adapter not installed."""
    with pytest.MonkeyPatch.context() as m:
        m.setattr(
            "dspx.adapters.prompt_adapter._TEMPLATE_ADAPTER_AVAILABLE",
            False
        )

        from dspx.adapters.prompt_adapter import DSPxTemplateAdapter
        from dspx.dtos import TemplateAdapterConfig

        config = TemplateAdapterConfig()
        with pytest.raises(ImportError, match="not installed"):
            DSPxTemplateAdapter(config)


def test_parse_mode_auto_selection():
    """Test auto parse_mode selection based on capabilities."""
    from dspx.adapters.prompt_adapter import DSPxTemplateAdapter
    from dspx.dtos import TemplateAdapterConfig

    # Skip if adapter not installed
    pytest.importorskip("dspy_template_adapter")

    # JSON-capable provider
    config = TemplateAdapterConfig(parse_mode="auto")
    adapter = DSPxTemplateAdapter(config)
    mode = adapter._resolve_parse_mode({"json_mode": True})
    assert mode == "json"

    # Claude-like provider
    mode = adapter._resolve_parse_mode({"provider_type": "claude"})
    assert mode == "xml"
```

### Integration Tests (With DSPy)

```python
# tests/integration/test_template_adapter_live.py

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_LIVE_DSPY"),
    reason="Set RUN_LIVE_DSPY=1 for live tests"
)


def test_signature_gen_with_template_adapter():
    """Live test: signature generation with custom template."""
    pytest.importorskip("dspy_template_adapter")

    from dspx.services.signatures_service import generate_signature
    from dspx.dtos import SignatureGenRequest, TemplateAdapterConfig, TemplateMessage

    config = TemplateAdapterConfig(
        messages=[
            TemplateMessage(role="system", content="{instruction}"),
            TemplateMessage(role="user", content="{inputs(style='yaml')}"),
        ],
        parse_mode="json",
    )

    req = SignatureGenRequest(
        prompt="Classify customer feedback into sentiment and category",
        template_adapter=config,
    )

    result = generate_signature(req)
    assert result.code
    assert "dspy.Signature" in result.code
```

---

## Migration Path

### Phase 1: Infrastructure (Non-Breaking)

1. Add `dspy-template-adapter` as optional dependency
2. Add `TemplateAdapterConfig` DTO
3. Add `DSPxTemplateAdapter` wrapper in `adapters/prompt_adapter.py`
4. Update `SignatureGenRequest` with optional `template_adapter` field
5. Add feature detection and graceful fallback

### Phase 2: Service Integration

1. Wire `SignatureService` to use adapter when configured
2. Wire `CodegenService` to use adapter when configured
3. Add `--template-config` CLI flag

### Phase 3: Generated Programs

1. Update Mermaid workflow generator to emit adapter-ready code
2. Add module template config support
3. Document customization patterns

### Phase 4: Finetuning Export

1. Add `dspx signature export-finetune` command
2. Implement `format_finetune_data` pipeline
3. Support OpenAI and other provider formats

---

## Open Questions

1. **Default template strategy:** Should dspx provide default templates for common tasks (summarization, classification, etc.) that users can customize?

2. **Optimizer integration depth:** How deeply should `{instruction}` slots integrate with MIPRO/COPRO? Full pass-through or constrained tuning?

3. **Multi-provider templates:** For `MultiProviderLM`, should each child get its own adapter with provider-specific parse modes?

4. **Version pinning:** Pin to specific dspy-template-adapter version or allow range? Recommendation: `>=0.2,<1.0` until 1.0 stable.

---

## References

- Upstream repo: `~/programming/upstream/dspy-template-adapter/`
- Key files:
  - `dspy_template_adapter/template_adapter.py` — Core adapter implementation
  - `dspy_template_adapter/predict.py` — Per-module adapter binding
  - `README.md` — Full API documentation
