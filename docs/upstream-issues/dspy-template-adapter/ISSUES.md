---
summary: "Tracked upstream issues for the DSPy template adapter."
read_when:
  - "You are investigating DSPy template adapter upstream issues."
  - "You need known issue context for adapter work."
type: "reference"
---

# Upstream Issues for dspy-template-adapter

**Target repo:** https://github.com/MaximeRivest/dspy-template-adapter
**Generated:** 2026-02-21
**Context:** DSPx integration review (`docs/TEMPLATE_ADAPTER_CRITIQUE.md`)

---

## Issue 1: XML parser fails on nested tags and CDATA

**Labels:** `bug`, `parse-mode`

### Title
`parse_mode="xml"` fails on nested tags, CDATA sections, and malformed XML

### Body
**Describe the bug**
The current XML parser uses a regex pattern:
```python
pattern = re.compile(rf"<{re.escape(name)}>(.*?)</{re.escape(name)}>", re.DOTALL)
```

This fails in several real-world scenarios:

1. **Nested tags** — Inner XML is captured incorrectly:
   ```xml
   <output>
     <nested>value</nested>
   </output>
   ```
   The `.*?` will capture `<nested>value` (greedy/non-greedy ambiguity with nested same tags).

2. **CDATA sections** — Content containing `<` or `>` characters:
   ```xml
   <output><![CDATA[<not>a<tag>]]></output>
   ```
   The regex doesn't recognize CDATA boundaries.

3. **Malformed/unclosed tags** — No graceful degradation:
   ```xml
   <output>unclosed content
   ```

**Expected behavior**
- Nested tags should be captured as the full inner content (including nested XML).
- CDATA should be correctly unwrapped.
- Malformed XML should provide actionable error with position hints.

**Suggested fix**
Use `xml.etree.ElementTree` for robust parsing:

```python
import xml.etree.ElementTree as ET

def _parse_xml(self, signature, completion):
    # Try to extract root-level tags first
    parsed = {}
    for name in signature.output_fields:
        # Use ElementTree for proper XML parsing
        try:
            # Wrap in root to handle fragments
            wrapped = f"<root>{completion}</root>"
            root = ET.fromstring(wrapped)
            elem = root.find(name)
            if elem is not None:
                # Get full inner content including nested XML
                text = elem.text or ""
                # Include tail text from children if any
                for child in elem:
                    text += ET.tostring(child, encoding="unicode")
                parsed[name] = text.strip()
        except ET.ParseError as e:
            # Fallback to regex for partial matches
            ...
```

**Environment**
- dspy-template-adapter version: 0.2+
- Python: 3.11+

---

## Issue 2: JSON parser doesn't handle markdown-wrapped output

**Labels:** `bug`, `parse-mode`

### Title
`parse_mode="json"` fails when LLM wraps JSON in markdown fences

### Body
**Describe the bug**
Many LLMs (especially reasoning models) wrap JSON output in markdown code fences:

```
Let me analyze this...

```json
{
  "result": "value"
}
```
```

The current `_parse_json` implementation passes the raw completion to `json_repair.loads()`, which fails because:
1. The JSON is not at the start of the string.
2. Markdown fences are not valid JSON syntax.

**Expected behavior**
The parser should:
1. Detect and strip markdown fences (```json ... ``` or ``` ... ```).
2. Extract JSON from surrounding text when possible.
3. Fall back gracefully with clear error messages.

**Suggested fix**

```python
import re

def _extract_json_from_completion(self, completion: str) -> str:
    """Extract JSON from completion, handling markdown fences and surrounding text."""
    text = completion.strip()

    # Try markdown fence extraction
    fence_pattern = re.compile(
        r"```(?:json)?\s*\n?(.*?)\n?```",
        re.DOTALL | re.IGNORECASE
    )
    match = fence_pattern.search(text)
    if match:
        return match.group(1).strip()

    # Try to find JSON object with recursive regex (existing behavior)
    match = regex.search(r"\{(?:[^{}]|(?R))*\}", text, regex.DOTALL)
    if match:
        return match.group(0)

    return text

def _parse_json(self, signature, completion):
    json_str = self._extract_json_from_completion(completion)
    fields = json_repair.loads(json_str)
    # ... rest of parsing
```

**Workaround**
Users can currently pre-process the completion with regex before passing to adapter, but this should be built-in.

---

## Issue 3: Clarify semantics and limitations of `parse_mode="chat"`

**Labels:** `documentation`, `clarification`

### Title
`parse_mode="chat"` is incompatible with exact-fidelity templates

### Body
**Summary**
The documentation doesn't clearly explain that `parse_mode="chat"` delegates to `ChatAdapter.parse()`, which expects completions in the `[[ ## field_name ## ]]value` format. This format is only produced when the *prompt* instructs the LLM to use it — which defeats the purpose of exact-fidelity custom templates.

**Problem**
A user writes a custom template with `parse_mode="chat"`:
```python
TemplateAdapter(
    messages=[{"role": "user", "content": "Return JSON: {inputs()}"}],
    parse_mode="chat",  # <-- This will fail
)
```

The LLM returns JSON (as instructed), but `ChatAdapter.parse()` expects:
```
[[ ## output ## ]]
the actual value
```

This results in `AdapterParseError` with no clear explanation of why.

**Suggested fix**
1. Add a warning in docstrings when `parse_mode="chat"` is used with custom templates.
2. Consider renaming to `parse_mode="chat_adapter_markers"` to make semantics explicit.
3. Add a note in README:

> **`parse_mode="chat"`** — Uses DSPy's built-in ChatAdapter parsing. Only works when your template instructs the LLM to use `[[ ## field ## ]]` markers. For most custom templates, use `"json"`, `"xml"`, or `"full_text"`.

**Environment**
- dspy-template-adapter version: 0.2+

---

## Issue 4: Add `__repr__` for debugging

**Labels:** `enhancement`, `dx`

### Title
Add `__repr__` to `TemplateAdapter` for easier debugging

### Body
**Current behavior**
```python
>>> adapter = TemplateAdapter(messages=[...], parse_mode="json")
>>> adapter
<dspy_template_adapter.template_adapter.TemplateAdapter object at 0x...>
```

This provides no useful information when debugging or logging.

**Desired behavior**
```python
>>> adapter = TemplateAdapter(messages=[...], parse_mode="json")
>>> adapter
TemplateAdapter(parse_mode="json", messages=2, helpers=0)

>>> adapter.register_helper("my_fn", lambda ctx, **kw: "test")
>>> adapter
TemplateAdapter(parse_mode="json", messages=2, helpers=1)
```

**Suggested implementation**

```python
def __repr__(self) -> str:
    return (
        f"{self.__class__.__name__}("
        f"parse_mode={self.parse_mode!r}, "
        f"messages={len(self.message_templates)}, "
        f"helpers={len(self._custom_helpers)}"
        f")"
    )
```

---

## Issue 5: Thread-safety documentation for async/concurrent usage

**Labels:** `documentation`, `async`

### Title
Document thread-safety guarantees for async/concurrent usage

### Body
**Question**
Is `TemplateAdapter` safe to use with:
1. `asyncio` with concurrent calls to the same adapter instance?
2. Multiple threads with different adapters via DSPy's `settings.context()`?
3. A single adapter instance shared across multiple `Predict` instances?

**Current observation**
The adapter stores state in instance variables:
- `self._custom_helpers` — dict, mutated by `register_helper()`
- `self._render_used_demos` — set during `_render()` (instance var, not local)

The `_render_used_demos` pattern is particularly concerning:
```python
_render_used_demos: bool = False  # Class-level default

def _render(self, ...):
    self._render_used_demos = False  # Instance mutation
    ...
    if func_name == "demos":
        self._render_used_demos = True  # Instance mutation
```

If two concurrent calls hit `_render()`, they could race on this flag.

**Suggested fix**
1. Make `_render_used_demos` a return value from `_render()` rather than instance state.
2. Document explicit thread-safety guarantees (or lack thereof).
3. Consider using `contextvars` for concurrent call isolation.

---

## Issue 6: Handle partial demos in optimizer flows

**Labels:** `bug`, `optimizers`

### Title
Partial demos from optimizers (BootstrapFewShot, GEPA) cause parse errors

### Body
**Describe the bug**
DSPy optimizers like `BootstrapFewShot` and `GEPA` may produce demo examples with partial output fields (e.g., a demo that only has some output fields populated).

Current `_format_demos_as_messages()` and `_parse_json()` expect all output fields to be present:
```python
if parsed.keys() != signature.output_fields.keys():
    raise AdapterParseError(...)
```

This causes failures during optimizer training when demos are incomplete.

**Expected behavior**
Partial demos should be handled gracefully:
- In demo formatting: include available fields, mark missing ones with placeholder.
- In parsing during optimization: tolerate missing fields.

**Suggested fix**
Add a config option for demo completion strictness:

```python
class TemplateAdapter(Adapter):
    def __init__(
        self,
        messages: list[dict],
        parse_mode: str = "json",
        demo_mode: Literal["strict", "partial"] = "partial",  # NEW
        ...
    ):
        ...
```

When `demo_mode="partial"`:
- Missing output fields in demos are omitted from the assistant message.
- Parsing during training allows partial matches.

---

## Issue 7: Add `preview()` return type annotation

**Labels:** `enhancement`, `type-hints`

### Title
`preview()` method lacks return type annotation

### Body
**Current code**
```python
def preview(
    self,
    signature: type[Signature],
    demos: list[dict[str, Any]] | None = None,
    inputs: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:  # <-- Has annotation, good!
```

Actually this one is fine! But I noticed the file uses some inconsistent type hints. Minor cleanup suggestion:

**Minor improvements**
1. Add `from __future__ import annotations` at top for cleaner hints.
2. Use `list[dict[str, Any]]` consistently instead of `List[Dict[str, Any]]`.

---

## Summary Table

| Issue | Priority | Type | Effort |
|-------|----------|------|--------|
| #1 XML parser nested/CDATA | High | Bug | Medium |
| #2 JSON markdown fences | High | Bug | Low |
| #3 parse_mode="chat" docs | Medium | Docs | Low |
| #4 `__repr__` for debugging | Low | DX | Low |
| #5 Thread-safety docs | Medium | Docs | Low |
| #6 Partial demos | Medium | Bug | Medium |
| #7 Type hints cleanup | Low | Polish | Low |

---

## Cross-reference

- DSPx integration doc: `docs/TEMPLATE_ADAPTER_INTEGRATION.md`
- DSPx critique: `docs/TEMPLATE_ADAPTER_CRITIQUE.md`
- Upstream repo: https://github.com/MaximeRivest/dspy-template-adapter
