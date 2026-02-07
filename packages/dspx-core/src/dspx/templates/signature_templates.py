from __future__ import annotations


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


def render_simple_signature(
    class_name: str, description: str, *, version: str = "v1"
) -> str:
    """Render a minimal, deterministic DSPy Signature class.

    Fields are fixed to: context (InputField[str]), output (OutputField[str]).
    """
    doc = (description or "Auto-generated Signature").strip().replace("\n", " ")
    return "\n".join(
        [
            "import dspy",
            "",
            f"class {class_name}(dspy.Signature):",
            f'    """{doc}"""',
            "",
            "    context: str = dspy.InputField(desc='Upstream context for this step')",
            "    output: str = dspy.OutputField(desc='Result of this step')",
            "",
        ]
    )
