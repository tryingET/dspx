# summary: "Formats code-generation prompts and renders deterministic minimal programs."
# read_when:
#   - "Changing codegen prompt wording or minimal program golden output."

from __future__ import annotations

from typing import Optional


def format_codegen_spec(
    base_spec: str, language: Optional[str] = None, *, version: str = "v1"
) -> str:
    base = base_spec.strip()
    lang_line = f"Target language: {language}.\n" if language else ""
    if version == "v1":
        return (
            "You are a precise code generator.\n"
            f"{lang_line}"
            "Output only a single code block (no prose).\n"
            "If you must include triple backticks, wrap the entire answer once.\n\n"
            f"Task: {base}\n"
        )
    return base


def render_minimal_program(language: Optional[str], task: str) -> str:
    """Render a minimal deterministic program for golden tests.

    Currently supports Python. Other languages can be added as needed.
    """
    lang = (language or "python").lower()
    if lang == "python":
        # Extract optional quoted text to print if present, else print the task.
        import re

        m = re.search(r'"([^"]+)"|\'([^\']+)\'', task)
        to_print = (
            m.group(1) if m and m.group(1) is not None else (m.group(2) if m else task)
        )
        lines = []
        lines.append('"""Auto-generated minimal script.')
        lines.append(f"Task: {task}")
        lines.append('"""')
        lines.append("")
        lines.append("import sys")
        lines.append("")
        lines.append("")
        lines.append("def main(argv: list[str] | None = None) -> int:")
        lines.append(f"    msg = {to_print!r}")
        lines.append("    print(msg)")
        lines.append("    return 0")
        lines.append("")
        lines.append("")
        lines.append('if __name__ == "__main__":')
        lines.append("    raise SystemExit(main())")
        code = "\n".join(lines)
        return code + ("\n" if not code.endswith("\n") else "")
    # Fallback generic text file
    return f"// minimal program for task: {task}\n"
