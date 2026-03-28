from __future__ import annotations

import re
from typing import Any


def format_signature_prompt(base_prompt: str, *, version: str = "v1") -> str:
    """Wrap a user prompt with stable guidance for signature generation.

    This is intentionally minimal for determinism during tests.
    """
    base = base_prompt.strip()
    if version == "v1":
        return (
            "You are generating a DSPy Signature class.\n"
            "Return only valid Python code for a single class.\n"
            "Include a clear docstring.\n\n"
            f"Task: {base}\n"
        )
    # Future versions may add more structure.
    return base


def format_signature_spec_prompt(
    base_prompt: str,
    *,
    class_name_hint: str = "GeneratedSignature",
    version: str = "spec-v1",
    json_mode: bool = False,
    constraints: list[str] | None = None,
    feedback: list[str] | None = None,
) -> str:
    """Build a spec-first prompt for signature generation.

    The model is asked to emit a JSON payload describing the signature schema,
    then DSPx renders deterministic Python from that schema.
    """
    base = base_prompt.strip()
    c_lines = [f"- {c.strip()}" for c in (constraints or []) if c and c.strip()]
    f_lines = [f"- {f.strip()}" for f in (feedback or []) if f and f.strip()]

    json_contract = (
        '{"class_name":"...","description":"...","inputs":[{"name":"...","type":"str","desc":"..."}],'
        '"outputs":[{"name":"...","type":"str","desc":"..."}]}'
    )

    mode_line = (
        "Output must be a strict JSON object and nothing else."
        if json_mode
        else "Output JSON only (no prose). If needed, wrap JSON once in ```json fences."
    )

    sections: list[str] = [
        "You are designing a DSPy Signature schema.",
        mode_line,
        "Return fields as explicit input/output lists.",
        f"Use class name: {class_name_hint} (unless invalid, then provide closest valid identifier).",
        "JSON contract:",
        json_contract,
        "Task:",
        base,
    ]

    if c_lines:
        sections.extend(["Constraints:", *c_lines])
    if f_lines:
        sections.extend(["Feedback history:", *f_lines])

    if version == "spec-v1":
        return "\n".join(sections) + "\n"
    return base


def _safe_identifier(name: str, default: str, *, class_name: bool = False) -> str:
    cleaned = re.sub(r"\W+", "_", (name or "").strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    if not cleaned:
        cleaned = default
    if cleaned and cleaned[0].isdigit():
        cleaned = f"_{cleaned}"
    if class_name:
        parts = [p for p in cleaned.split("_") if p]
        cleaned = "".join(p[:1].upper() + p[1:] for p in parts) or default
    return cleaned


def _sanitize_type_hint(type_hint: str | None) -> str:
    t = (type_hint or "str").strip()
    if not t:
        return "str"

    if t.startswith("Optional[") and t.endswith("]"):
        inner = _sanitize_type_hint(t[len("Optional[") : -1])
        return f"Optional[{inner}]"

    if t.startswith("Literal[") and t.endswith("]"):
        body = t[len("Literal[") : -1].strip()
        # Keep only quoted string literals for safety/determinism.
        vals = re.findall(r"'([^']+)'|\"([^\"]+)\"", body)
        flat = [a or b for a, b in vals if (a or b)]
        if not flat:
            return "str"
        encoded = ", ".join(repr(v) for v in flat)
        return f"Literal[{encoded}]"

    if t.startswith("list[") and t.endswith("]"):
        inner = _sanitize_type_hint(t[len("list[") : -1])
        return f"list[{inner}]"

    if t.startswith("dict[") and t.endswith("]"):
        return "dict[str, Any]"

    if t in {"str", "int", "float", "bool", "Any"}:
        return t

    return "str"


def _normalize_fields(
    items: list[dict[str, Any]] | None,
    *,
    role: str,
    default_name: str,
) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for idx, raw in enumerate(items or []):
        name_raw = str(raw.get("name") or raw.get("field") or "").strip()
        name = _safe_identifier(name_raw, f"{default_name}_{idx + 1}")
        if name in seen:
            suffix = 2
            base = name
            while f"{base}_{suffix}" in seen:
                suffix += 1
            name = f"{base}_{suffix}"
        seen.add(name)
        desc = str(raw.get("desc") or raw.get("description") or "").strip()
        if not desc:
            desc = f"{name.replace('_', ' ')} ({role})"
        out.append(
            {
                "name": name,
                "type": _sanitize_type_hint(str(raw.get("type") or "str")),
                "desc": desc,
            }
        )
    return out


def render_signature_from_spec(
    class_name: str,
    description: str,
    *,
    inputs: list[dict[str, Any]] | None = None,
    outputs: list[dict[str, Any]] | None = None,
    version: str = "spec-v1",
) -> str:
    """Render deterministic signature code from a structured spec."""
    cls = _safe_identifier(class_name, "GeneratedSignature", class_name=True)
    doc = (description or "Auto-generated Signature").strip().replace("\n", " ")

    in_fields = _normalize_fields(
        [{k: v for k, v in item.items()} for item in (inputs or [])],
        role="input",
        default_name="context",
    )
    out_fields = _normalize_fields(
        [{k: v for k, v in item.items()} for item in (outputs or [])],
        role="output",
        default_name="output",
    )

    if not in_fields:
        in_fields = [
            {
                "name": "context",
                "type": "str",
                "desc": "Upstream context for this step",
            }
        ]
    if not out_fields:
        out_fields = [
            {
                "name": "output",
                "type": "str",
                "desc": "Result of this step",
            }
        ]

    typing_symbols: set[str] = set()
    for f in [*in_fields, *out_fields]:
        t = str(f.get("type") or "")
        if "Optional[" in t:
            typing_symbols.add("Optional")
        if "Literal[" in t:
            typing_symbols.add("Literal")
        if "Any" in t:
            typing_symbols.add("Any")

    lines: list[str] = ["import dspy"]
    if typing_symbols:
        ordered = [n for n in ("Any", "Literal", "Optional") if n in typing_symbols]
        lines.append(f"from typing import {', '.join(ordered)}")
    lines.extend(["", f"class {cls}(dspy.Signature):", f'    """{doc}"""', ""])

    for f in in_fields:
        lines.append(
            f"    {f['name']}: {f['type']} = dspy.InputField(desc={f['desc']!r})"
        )
    for f in out_fields:
        lines.append(
            f"    {f['name']}: {f['type']} = dspy.OutputField(desc={f['desc']!r})"
        )
    lines.append("")

    code = "\n".join(lines)
    if version.startswith("spec"):
        return code
    return code


def render_simple_signature(
    class_name: str,
    description: str,
    *,
    version: str = "v1",
    inputs: list[str] | None = None,
    outputs: list[str] | None = None,
) -> str:
    """Render a minimal, deterministic DSPy Signature class.

    Defaults remain `context -> output`, but callers may provide explicit
    input/output field names when a stronger IO contract is available.
    """
    doc = (description or "Auto-generated Signature").strip().replace("\n", " ")
    input_names = [str(item) for item in (inputs or []) if str(item).strip()] or [
        "context"
    ]
    output_names = [str(item) for item in (outputs or []) if str(item).strip()] or [
        "output"
    ]

    lines = [
        "import dspy",
        "",
        f"class {class_name}(dspy.Signature):",
        f'    """{doc}"""',
        "",
    ]
    for name in input_names:
        desc = f"{name.replace('_', ' ')} (input)"
        lines.append(f"    {name}: str = dspy.InputField(desc={desc!r})")
    for name in output_names:
        desc = f"{name.replace('_', ' ')} (output)"
        lines.append(f"    {name}: str = dspy.OutputField(desc={desc!r})")
    lines.append("")
    return "\n".join(lines)
