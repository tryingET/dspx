---
title: "Handle partial demos from optimizers (BootstrapFewShot, GEPA)"
summary: "Upstream DSPy template adapter issue covering partial demos support."
read_when:
  - "You are investigating upstream DSPy template adapter issues."
  - "You need context from docs/upstream-issues/dspy-template-adapter/issues/006-partial-demos.md."
labels: ["bug", "optimizers"]
priority: "medium"
type: "issue"
---

## Describe the bug

DSPy optimizers like `BootstrapFewShot` and `GEPA` may produce demo examples with partial output fields (e.g., a demo that only has some output fields populated).

The current implementation has issues in two places:

### 1. `_format_demos_as_messages()`

Expects all output fields to be present:

```python
for name in signature.output_fields:
    if name in demo:
        out[name] = demo[name]

# Always appends assistant message, even if out is empty
messages.append({
    "role": "assistant",
    "content": json.dumps(serialize_for_json(out), ...)
})
```

### 2. `_parse_json()`

Requires exact field match:

```python
if parsed.keys() != signature.output_fields.keys():
    raise AdapterParseError(...)
```

This causes failures during optimizer training when demos are incomplete.

## Expected behavior

Partial demos should be handled gracefully:
- In demo formatting: include available fields, use placeholder for missing ones
- In parsing during optimization: tolerate missing fields with configurable strictness

## Suggested fix

Add a config option for demo handling:

```python
class TemplateAdapter(Adapter):
    def __init__(
        self,
        messages: list[dict],
        parse_mode: str | Callable = "json",
        demo_mode: Literal["strict", "partial", "skip_incomplete"] = "partial",
        ...
    ):
        ...
        self.demo_mode = demo_mode
```

### Modified `_format_demos_as_messages()`:

```python
def _format_demos_as_messages(self, signature, demos):
    messages = []

    for demo in demos:
        # Check if demo has at least one output field
        has_output = any(k in demo for k in signature.output_fields)

        if not has_output:
            if self.demo_mode == "skip_incomplete":
                continue  # Skip demos with no outputs
            elif self.demo_mode == "strict":
                raise ValueError(f"Demo missing all output fields: {demo}")
            # "partial" mode: still include, may confuse LLM

        # User message (inputs)
        user_parts = []
        for name in signature.input_fields:
            if name in demo:
                user_parts.append(f"{name}: {format_field_value(...)}")
        if not user_parts:
            continue
        messages.append({"role": "user", "content": "\n".join(user_parts)})

        # Assistant message (outputs)
        out = {}
        for name in signature.output_fields:
            if name in demo:
                out[name] = demo[name]
            elif self.demo_mode == "partial":
                out[name] = "[not demonstrated]"  # Placeholder

        if out:
            messages.append({
                "role": "assistant",
                "content": json.dumps(serialize_for_json(out), ...)
            })

    return messages
```

### Modified `_parse_json()` for optimizer mode:

```python
def _parse_json(self, signature, completion, strict: bool = True):
    ...
    if strict:
        if parsed.keys() != signature.output_fields.keys():
            raise AdapterParseError(...)
    else:
        # During optimization, allow partial matches
        missing = set(signature.output_fields.keys()) - set(parsed.keys())
        if missing:
            logger.warning(f"Partial parse: missing fields {missing}")

    return parsed
```

## Workaround

Currently, users can filter demos before passing to the adapter, but this should be built-in for optimizer compatibility.

## Environment

- dspy-template-adapter version: 0.2+
- DSPy version: 2.5+
- Python: 3.11+
