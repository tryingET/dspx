---
title: "Add __repr__ to TemplateAdapter for easier debugging"
summary: "Upstream DSPy template adapter issue covering repr/debugging support."
read_when:
  - "You are investigating upstream DSPy template adapter issues."
  - "You need context from docs/upstream-issues/dspy-template-adapter/issues/004-repr-for-debugging.md."
labels: ["enhancement", "dx"]
priority: "low"
type: "issue"
---

## Current behavior

```python
>>> adapter = TemplateAdapter(messages=[...], parse_mode="json")
>>> adapter
<dspy_template_adapter.template_adapter.TemplateAdapter object at 0x7f8a1b2c3d40>
```

This provides no useful information when debugging or logging.

## Desired behavior

```python
>>> adapter = TemplateAdapter(messages=[...], parse_mode="json")
>>> adapter
TemplateAdapter(parse_mode='json', messages=2, helpers=0)

>>> adapter.register_helper("my_fn", lambda ctx, **kw: "test")
>>> adapter
TemplateAdapter(parse_mode='json', messages=2, helpers=1)

>>> print(f"Using adapter: {adapter}")
Using adapter: TemplateAdapter(parse_mode='json', messages=2, helpers=1)
```

## Suggested implementation

```python
def __repr__(self) -> str:
    """Return a concise, informative string representation."""
    return (
        f"{self.__class__.__name__}("
        f"parse_mode={self.parse_mode!r}, "
        f"messages={len(self.message_templates)}, "
        f"helpers={len(self._custom_helpers)}"
        f")"
    )
```

For even better debugging, consider including message roles:

```python
def __repr__(self) -> str:
    """Return a concise, informative string representation."""
    roles = [m.get("role", "?") for m in self.message_templates]
    return (
        f"{self.__class__.__name__}("
        f"parse_mode={self.parse_mode!r}, "
        f"roles={roles!r}, "
        f"helpers={len(self._custom_helpers)}"
        f")"
    )
```

## Benefits

- Easier debugging in interactive sessions
- Better log messages when tracing adapter usage
- Helps distinguish multiple adapter instances

## Environment

- dspy-template-adapter version: 0.2+
