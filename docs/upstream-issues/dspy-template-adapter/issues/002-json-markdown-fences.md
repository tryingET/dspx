---
title: "JSON parser doesn't handle markdown-wrapped output"
summary: "Upstream DSPy template adapter issue covering JSON parsing from markdown fences."
read_when:
  - "You are investigating upstream DSPy template adapter issues."
  - "You need context from docs/upstream-issues/dspy-template-adapter/issues/002-json-markdown-fences.md."
labels: ["bug", "parse-mode"]
priority: "high"
type: "issue"
---

## Describe the bug

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
1. The JSON is not at the start of the string
2. Markdown fences are not valid JSON syntax

## Expected behavior

The parser should:
1. Detect and strip markdown fences (` ```json ... ``` ` or ` ``` ... ``` `)
2. Extract JSON from surrounding text when possible
3. Fall back gracefully with clear error messages

## Suggested fix

```python
import re

def _extract_json_from_completion(self, completion: str) -> str:
    """Extract JSON from completion, handling markdown fences and surrounding text."""
    text = completion.strip()

    # Try markdown fence extraction first
    # Matches ```json\n{...}\n``` or ```\n{...}\n```
    fence_pattern = re.compile(
        r"```(?:json)?\s*\n?(.*?)\n?```",
        re.DOTALL | re.IGNORECASE
    )
    match = fence_pattern.search(text)
    if match:
        return match.group(1).strip()

    # Fall back to existing recursive regex for embedded JSON
    # (current behavior)
    match = regex.search(r"\{(?:[^{}]|(?R))*\}", text, regex.DOTALL)
    if match:
        return match.group(0)

    # Return as-is and let json_repair try its best
    return text

def _parse_json(self, signature: type[Signature], completion: str) -> dict[str, Any]:
    """Extract a JSON object from the completion and map to output fields."""
    json_str = self._extract_json_from_completion(completion)
    fields = json_repair.loads(json_str)

    if not isinstance(fields, dict):
        # Try recursive regex as fallback
        match = regex.search(r"\{(?:[^{}]|(?R))*\}", completion, regex.DOTALL)
        if match:
            fields = json_repair.loads(match.group(0))

    if not isinstance(fields, dict):
        raise AdapterParseError(
            adapter_name="TemplateAdapter",
            signature=signature,
            lm_response=completion,
            message="No JSON object found in LM response.",
        )

    # ... rest of existing parsing logic
```

## Workaround

Users can currently pre-process completions with regex before the adapter sees them, but this should be built-in for common cases.

## Environment

- dspy-template-adapter version: 0.2+
- Python: 3.11+
