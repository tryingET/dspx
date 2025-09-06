from __future__ import annotations

import os
import re
from typing import Optional

import dspy

from dspx.config_loader import load_config_env
from dspx.tracing import enable_mlflow_from_env
from dspx.provider_registry import create_from_env, ensure_default_providers


def _extract_code_block(text: str) -> str:
    fence = re.compile(r"```[\w+-]*\n([\s\S]*?)\n```", re.MULTILINE)
    m = fence.search(text)
    if m:
        return m.group(1).strip()
    return text.strip()


def _build_spec(base_spec: str, language: Optional[str]) -> str:
    constraints = [
        "- Output only a single code block (no prose).",
        "- If you must include triple backticks, wrap the entire answer once.",
        "- Avoid placeholders; provide a minimal runnable example if possible.",
    ]
    lang_line = f"Target language: {language}." if language else ""
    guidance = "\n".join([lang_line] + constraints if lang_line else constraints)
    return (
        f"You are a precise code generator.\n"
        f"Task: {base_spec.strip()}\n\n"
        f"Guidance:\n{guidance}\n"
    )


def run(
    spec: str,
    *,
    language: Optional[str] = None,
    outfile: Optional[str] = None,
    print_all: bool = False,
) -> str:
    # Configure env + tracing
    load_config_env()
    enable_mlflow_from_env()

    # LM options (read from env via provider-specific factories)
    # Kept minimal here; provider registry will apply env when creating the LM.

    # Create LM via provider registry (default: codex-exec)
    ensure_default_providers()
    lm = create_from_env()
    dspy.configure(lm=lm)

    codegen = dspy.Predict("spec -> code")
    full_spec = _build_spec(spec, language)
    result = codegen(spec=full_spec)
    text = result.code if hasattr(result, "code") else str(result)
    code_text = text if print_all else _extract_code_block(text)

    if outfile:
        path = outfile
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(code_text + ("\n" if not code_text.endswith("\n") else ""))
    return code_text
