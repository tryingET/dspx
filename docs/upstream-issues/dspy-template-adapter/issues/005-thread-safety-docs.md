---
title: "Document thread-safety guarantees for async/concurrent usage"
summary: "Upstream DSPy template adapter issue covering thread-safety documentation."
read_when:
  - "You are investigating upstream DSPy template adapter issues."
  - "You need context from docs/upstream-issues/dspy-template-adapter/issues/005-thread-safety-docs.md."
labels: ["documentation", "async"]
priority: "medium"
type: "issue"
---

## Question

Is `TemplateAdapter` safe to use with:

1. `asyncio` with concurrent calls to the same adapter instance?
2. Multiple threads with different adapters via DSPy's `settings.context()`?
3. A single adapter instance shared across multiple `Predict` instances?

## Potential issue: `_render_used_demos` instance state

The adapter stores state in instance variables during rendering:

```python
_render_used_demos: bool = False  # Class-level default

def _render(self, ...):
    self._render_used_demos = False  # Instance mutation
    ...
    if func_name == "demos":
        self._render_used_demos = True  # Instance mutation
```

If two concurrent calls hit `_render()` on the same adapter instance, they could race on this flag:

```
Thread A: self._render_used_demos = False
Thread B: self._render_used_demos = False
Thread A: demos detected -> self._render_used_demos = True
Thread B: no demos -> self._render_used_demos stays False
Thread A: reads self._render_used_demos -> False (race!)
```

## Other state concerns

- `self._custom_helpers` — dict mutated by `register_helper()` (less concern if setup is done before concurrent use)

## Suggested fixes

### Fix 1: Make `_render_used_demos` a return value

```python
def _render(self, template, ctx, signature, demos) -> tuple[str, bool]:
    """Render template and return (rendered_text, used_demos_flag)."""
    used_demos = False
    ...
    if func_name == "demos":
        used_demos = True
        ...
    return text, used_demos
```

### Fix 2: Document thread-safety guarantees

Add to README and docstrings:

```markdown
### Thread Safety

`TemplateAdapter` instances are **not thread-safe** for concurrent calls to `format()`.

**Safe patterns:**
- One adapter instance per thread
- Call `register_helper()` during setup, before concurrent use
- Use separate `Predict` instances with separate adapters

**Unsafe patterns:**
- Sharing a single adapter instance across threads with concurrent `format()` calls
```

### Fix 3: Use `contextvars` for concurrent isolation

If thread-safety is a goal, use context-local storage:

```python
from contextvars import ContextVar

_render_context: ContextVar[dict] = ContextVar('render_context')

def _render(self, ...):
    ctx = _render_context.get({})
    ctx['used_demos'] = False
    _render_context.set(ctx)
    ...
```

## Recommendation

At minimum, document the current behavior. If thread-safety is desired, implement Fix 1 (return value) as it's the cleanest solution.

## Environment

- dspy-template-adapter version: 0.2+
- Python: 3.11+
