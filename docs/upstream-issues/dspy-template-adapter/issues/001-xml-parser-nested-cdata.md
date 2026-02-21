---
title: "XML parser fails on nested tags and CDATA"
labels: ["bug", "parse-mode"]
priority: "high"
---

## Describe the bug

The current XML parser uses a regex pattern:
```python
pattern = re.compile(rf"<{re.escape(name)}>(.*?)</{re.escape(name)}>", re.DOTALL)
```

This fails in several real-world scenarios:

### 1. Nested tags
Inner XML is captured incorrectly:
```xml
<output>
  <nested>value</nested>
</output>
```
The `.*?` captures incorrectly due to greedy/non-greedy ambiguity with nested same tags.

### 2. CDATA sections
Content containing `<` or `>` characters:
```xml
<output><![CDATA[<not>a<tag>]]></output>
```
The regex doesn't recognize CDATA boundaries.

### 3. Malformed/unclosed tags
No graceful degradation:
```xml
<output>unclosed content
```

## Expected behavior

- Nested tags should be captured as the full inner content (including nested XML).
- CDATA should be correctly unwrapped.
- Malformed XML should provide actionable error with position hints.

## Suggested fix

Use `xml.etree.ElementTree` for robust parsing:

```python
import xml.etree.ElementTree as ET

def _parse_xml(self, signature, completion):
    """Extract output fields from XML with proper handling of nested tags and CDATA."""
    import xml.etree.ElementTree as ET

    parsed = {}

    for name, field_info in signature.output_fields.items():
        try:
            # Wrap in root to handle fragments
            wrapped = f"<root>{completion}</root>"
            root = ET.fromstring(wrapped)
            elem = root.find(name)

            if elem is not None:
                # Get text content
                text = "".join(elem.itertext())
                parsed[name] = text.strip()

        except ET.ParseError:
            # Fallback to regex for partial/malformed XML
            pattern = re.compile(rf"<{re.escape(name)}>(.*?)</{re.escape(name)}>", re.DOTALL)
            match = pattern.search(completion)
            if match:
                raw_value = match.group(1).strip()
                try:
                    parsed[name] = parse_value(raw_value, field_info.annotation)
                except Exception as e:
                    raise AdapterParseError(
                        adapter_name="TemplateAdapter",
                        signature=signature,
                        lm_response=completion,
                        message=f"Failed to parse XML field '{name}': {e}",
                    )

    # Validate all required fields present
    if parsed.keys() != signature.output_fields.keys():
        missing = set(signature.output_fields.keys()) - set(parsed.keys())
        raise AdapterParseError(
            adapter_name="TemplateAdapter",
            signature=signature,
            lm_response=completion,
            parsed_result=parsed,
            message=f"Missing XML tags for output fields: {missing}",
        )

    return parsed
```

## Environment

- dspy-template-adapter version: 0.2+
- Python: 3.11+
