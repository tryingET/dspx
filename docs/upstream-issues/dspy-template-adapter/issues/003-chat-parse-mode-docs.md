---
title: "Clarify semantics and limitations of parse_mode='chat'"
summary: "Upstream DSPy template adapter issue covering chat parse-mode documentation."
read_when:
  - "You are investigating upstream DSPy template adapter issues."
  - "You need context from docs/upstream-issues/dspy-template-adapter/issues/003-chat-parse-mode-docs.md."
labels: ["documentation", "clarification"]
priority: "medium"
type: "issue"
---

## Summary

The documentation doesn't clearly explain that `parse_mode="chat"` delegates to `ChatAdapter.parse()`, which expects completions in the `[[ ## field_name ## ]]value` format. This format is only produced when the *prompt* instructs the LLM to use it — which defeats the purpose of exact-fidelity custom templates.

## Problem

A user writes a custom template with `parse_mode="chat"`:

```python
TemplateAdapter(
    messages=[{"role": "user", "content": "Return JSON: {inputs()}"}],
    parse_mode="chat",  # <-- This will fail
)
```

The LLM returns JSON (as instructed by the template), but `ChatAdapter.parse()` expects:

```
[[ ## output ## ]]
the actual value
```

This results in `AdapterParseError` with no clear explanation of why the parsing failed.

## Suggested fixes

### Option 1: Add docstring warning

```python
parse_mode: str | Callable = "json",
    """
    How to parse the LM completion into output fields:

    - ``"json"`` — Extract a JSON object and map keys to output fields (default).
    - ``"full_text"`` — Map the entire completion to the single output field.
    - ``"xml"`` — Extract ``<field_name>value</field_name>`` tags.
    - ``"chat"`` — **Advanced:** Delegate to DSPy's ChatAdapter parsing.
      Only works when your template instructs the LLM to use `[[ ## field ## ]]`
      markers. For most custom templates, use `"json"`, `"xml"`, or `"full_text"`.
    - A callable ``(signature, completion) -> dict[str, Any]``.
    """
```

### Option 2: Rename for clarity

Consider renaming to `parse_mode="chat_adapter_markers"` to make semantics explicit.

### Option 3: Add README section

```markdown
### Parse Modes

| Mode | Description | Use Case |
|------|-------------|----------|
| `json` | Extract JSON object, map to output fields | Default, works with most templates |
| `xml` | Extract `<field>value</field>` tags | Claude and XML-friendly providers |
| `full_text` | Entire completion → single output field | Free-form generation tasks |
| `chat` | DSPy ChatAdapter markers | **Advanced**: Only if template uses `[[ ## field ## ]]` format |
| callable | Custom parser function | Complex/proprietary formats |

> ⚠️ **Warning:** `parse_mode="chat"` uses DSPy's built-in ChatAdapter, which expects
> `[[ ## field ## ]]` markers in the completion. This is incompatible with most custom
> templates. Use only if your template explicitly instructs the LLM to use this format.
```

## Environment

- dspy-template-adapter version: 0.2+
