from __future__ import annotations

import os
from typing import Optional

import dspy
import sys
from pathlib import Path

from config_loader import load_config_env
from tracing import enable_mlflow_from_env
from codex_exec_lm import CodexExecLM


def run_generate(prompt: str) -> str:
    load_config_env()
    enable_mlflow_from_env()

    model = os.getenv("CODEX_MODEL", "gpt-5")
    lm = CodexExecLM(model_flag=model, auto_mode=False, dangerously_bypass=True, reasoning_effort="minimal")
    dspy.configure(lm=lm)

    # Ensure vibe-dspy is importable
    here = Path(__file__).resolve().parents[2]
    vibe_src = here / "submodules" / "vibe-dspy" / "src"
    if vibe_src.is_dir() and str(vibe_src) not in sys.path:
        sys.path.insert(0, str(vibe_src))

    from signature_generator import SignatureGenerator  # type: ignore

    generator = SignatureGenerator()
    result = generator.generate_signature(prompt)
    return result.get("code") or ""
