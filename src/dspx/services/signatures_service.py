from __future__ import annotations

import os
from typing import Optional

import dspy
import sys
from pathlib import Path

from dspx.config_loader import load_config_env
from dspx.tracing import enable_mlflow_from_env
from dspx.provider_registry import create_from_env, ensure_default_providers


def run_generate(prompt: str) -> str:
    load_config_env()
    enable_mlflow_from_env()

    ensure_default_providers()
    lm = create_from_env()
    dspy.configure(lm=lm)

    # Ensure vibe-dspy is importable
    # Find repo root by walking up until 'submodules' or '.git' is found
    cur = Path(__file__).resolve().parent
    root = None
    for _ in range(6):
        if (cur / "submodules").exists() or (cur / ".git").exists() or (cur.parent == cur):
            root = cur
            break
        cur = cur.parent
    root = root or Path(__file__).resolve().parents[3]
    vibe_src = root / "submodules" / "vibe-dspy" / "src"
    if vibe_src.is_dir() and str(vibe_src) not in sys.path:
        sys.path.insert(0, str(vibe_src))

    from signature_generator import SignatureGenerator  # type: ignore

    generator = SignatureGenerator()
    result = generator.generate_signature(prompt)
    return result.get("code") or ""
