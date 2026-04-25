from __future__ import annotations

from typing import Any
import keyword
import re


def sanitize_ident(name: str, fallback: str = "IntentProgram") -> str:
    value = re.sub(r"\W+", "_", str(name or "").strip()) or fallback
    if value[0].isdigit():
        value = f"_{value}"
    if keyword.iskeyword(value):
        value = f"{value}_"
    return value


def surface_description(text: str) -> str:
    """Return text safe for existing triple-quoted signature/module renderers."""

    compact = str(text or "").replace("\r", " ").replace("\n", " ").strip()
    return (compact or "Auto-generated DSPy program").replace('"""', "'''")


def intent_surface_names(intent: Any) -> dict[str, str]:
    program_class = sanitize_ident(intent.name)
    return {
        "program_class": program_class,
        "signature_class": f"{program_class}Signature",
        "module_class": f"{program_class}Module",
    }


def intent_field_specs(intent: Any, *, role: str) -> list[dict[str, Any]]:
    fields = intent.input_fields if role == "input" else intent.output_fields
    names = intent.inputs if role == "input" else intent.outputs
    if fields:
        return [dict(item) for item in fields]
    return [
        {
            "name": name,
            "type": "str",
            "desc": f"{name.replace('_', ' ')} ({role})",
        }
        for name in names
    ]
