from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

import dspy

from config_loader import load_config_env
from tracing import enable_mlflow_from_env
from dspx.provider_registry import create_from_env, ensure_default_providers


def _wrap_script(signature_code: str) -> str:
    lines = [
        "# Auto-generated DSPy script (Codex Exec enabled)",
        "import os",
        "import dspy",
        "from codex_exec_lm import CodexExecLM",
        "from config_loader import load_config_env",
        "from tracing import enable_mlflow_from_env",
        "",
        "load_config_env()",
        "enable_mlflow_from_env()",
        "MODEL = os.getenv('CODEX_MODEL', 'gpt-5')",
        "lm = CodexExecLM(model_flag=MODEL, auto_mode=False, dangerously_bypass=True, reasoning_effort='minimal')",
        "dspy.configure(lm=lm)",
        "",
        signature_code,
        "",
        "def demo():",
        "    pass",
        "",
        "if __name__ == '__main__':",
        "    demo()",
    ]
    return "\n".join(lines)


def run_refine(prompt: str, *, outfile: Optional[str] = None, attempts: int = 3, wrap_script: bool = False, non_interactive: bool = False) -> str:
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

    def reward_fn(args, pred):
        if non_interactive:
            return 1.0
        ans = input("Accept signature? [y/N]: ").strip().lower()
        if ans in {"y", "yes"}:
            return 1.0
        fb = input("Feedback (leave empty for generic): ").strip() or "Please improve the signature."
        return dspy.Prediction(score=0.0, feedback=fb)

    refiner = dspy.Refine(module=SignatureGenerator(), N=attempts, reward_fn=reward_fn, threshold=1.0)
    try:
        pred = refiner(prompt=prompt)
        code = SignatureGenerator.generate_code(pred)
    except Exception:
        # Fallback to single-shot generation if refine fails
        gen = SignatureGenerator()
        result = gen.generate_signature(prompt)
        code = result.get("code") or ""
    if wrap_script:
        code = _wrap_script(code)

    if outfile:
        Path(outfile).parent.mkdir(parents=True, exist_ok=True)
        Path(outfile).write_text(code, encoding="utf-8")
    return code
