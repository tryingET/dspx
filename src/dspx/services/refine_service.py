from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import dspy

from dspx.config_loader import load_config_env
from dspx.tracing import enable_mlflow_from_env
from dspx.provider_registry import create_from_env, ensure_default_providers
from dspx.lm_base import LMBase


def _wrap_script(signature_code: str) -> str:
    lines = [
        "# Auto-generated DSPy script",
        "import os",
        "import dspy",
        "from dspx.config_loader import load_config_env",
        "from dspx.tracing import enable_mlflow_from_env",
        "from dspx.provider_registry import ensure_default_providers, create_from_env",
        "",
        "load_config_env()",
        "enable_mlflow_from_env()",
        "ensure_default_providers()",
        "lm = create_from_env()",
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


def _extract_sig_class_name(code: str) -> str | None:
    import re

    # Best-effort: first class inheriting from dspy.Signature.
    m = re.search(
        r"^class\\s+([A-Za-z_][A-Za-z0-9_]*)\\s*\\(\\s*dspy\\.Signature\\s*\\)\\s*:",
        code,
        re.M,
    )
    if m:
        return m.group(1)
    return None


def run_refine(
    prompt: str,
    *,
    outfile: Optional[str] = None,
    attempts: int = 3,
    wrap_script: bool = False,
    non_interactive: bool = False,
    lm: Optional[LMBase] = None,
) -> str:
    import os
    import time

    load_config_env()
    enable_mlflow_from_env()

    ensure_default_providers()
    active_lm = lm or create_from_env()
    dspy.configure(lm=active_lm)

    t0 = time.time()
    budget_ms_env = os.getenv("DSPX_BUDGET_SIGNATURE_MS")
    budget_ms = (
        int(budget_ms_env) if budget_ms_env and budget_ms_env.isdigit() else None
    )
    template_version = "refine-v1"

    # Start MLflow run early so DSPy autolog (if enabled) can attach to it.
    started_run = False
    mlflow = None
    try:
        from dspx.tracing import ensure_run_with_standard_tags, get_mlflow

        mlflow = get_mlflow()
        if mlflow is not None:
            started_run = ensure_run_with_standard_tags(
                "signature",
                template_version=template_version,
                run_name="signature-refine",
                extra={"signature.mode": "refine"},
            )
    except Exception:
        mlflow = None
        started_run = False

    # Ensure vibe-dspy is importable
    # Find repo root by walking up until 'submodules' or '.git' is found
    cur = Path(__file__).resolve().parent
    root = None
    for _ in range(6):
        if (
            (cur / "submodules").exists()
            or (cur / ".git").exists()
            or (cur.parent == cur)
        ):
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
        fb = (
            input("Feedback (leave empty for generic): ").strip()
            or "Please improve the signature."
        )
        return dspy.Prediction(score=0.0, feedback=fb)

    refiner = dspy.Refine(
        module=SignatureGenerator(), N=attempts, reward_fn=reward_fn, threshold=1.0
    )
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

    cls = _extract_sig_class_name(code)
    if outfile:
        out_path = Path(outfile)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(code, encoding="utf-8")
        # Signature metadata parity with `signature gen`
        try:
            from dspx.cache import make_key, sha256_text, cache_dir

            cache_key = make_key(
                {
                    "kind": "signature",
                    "prompt": prompt,
                    "template_version": template_version,
                    "class_name": cls or "",
                    "mode": "refine",
                    "attempts": int(attempts),
                    "non_interactive": bool(non_interactive),
                }
            )
            cfile = cache_dir() / "signature" / f"{cache_key}.json"
            meta = {
                "hash": sha256_text(code),
                "template_version": template_version,
                "class_name": cls or "",
                "cache_key": cache_key,
                "cache_file": str(cfile),
                "cache_enabled": False,
                "mode": "refine",
                "attempts": int(attempts),
                "non_interactive": bool(non_interactive),
            }
            (out_path.parent / (out_path.name + ".meta.json")).write_text(
                __import__("json").dumps(meta, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except Exception:
            pass

    # MLflow logging parity: only log if MLflow is enabled and a run is active.
    if mlflow is not None:
        try:
            if mlflow.active_run() is not None:
                try:
                    mlflow.log_params(
                        {
                            "signature.mode": "refine",
                            "signature.attempts": int(attempts),
                            "signature.non_interactive": bool(non_interactive),
                            "signature.wrap_script": bool(wrap_script),
                            "signature.class_name": cls or "",
                            "signature.prompt_len": len(prompt or ""),
                        }
                    )
                except Exception:
                    pass
                # Artifact: code
                try:
                    name = f"{cls or 'refined_signature'}.py"
                    mlflow.log_text(code, name)
                except Exception:
                    try:
                        mlflow.log_dict({"code": code}, "refined_signature.json")
                    except Exception:
                        pass
                # If outfile exists, log it and its meta
                if outfile:
                    out_path = Path(outfile)
                    try:
                        mlflow.log_artifact(str(out_path))
                    except Exception:
                        pass
                    meta_path = out_path.parent / (out_path.name + ".meta.json")
                    if meta_path.exists():
                        try:
                            mlflow.log_artifact(str(meta_path))
                        except Exception:
                            pass
                duration_ms = (time.time() - t0) * 1000.0
                try:
                    mlflow.log_metrics(
                        {
                            "service.duration_ms": float(duration_ms),
                            "service.budget_exceeded": float(
                                1.0
                                if budget_ms is not None
                                and duration_ms > float(budget_ms)
                                else 0.0
                            ),
                        }
                    )
                except Exception:
                    pass
                if budget_ms is not None:
                    try:
                        mlflow.set_tag("service.budget_ms", str(int(budget_ms)))
                    except Exception:
                        pass
        finally:
            # Close the run if we started it (best-effort).
            if started_run:
                try:
                    mlflow.end_run()
                except Exception:
                    pass
    return code
