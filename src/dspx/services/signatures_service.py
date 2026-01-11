from __future__ import annotations


import dspy
import sys
from pathlib import Path
from typing import Optional

from dspx.config_loader import load_config_env
from dspx.tracing import enable_mlflow_from_env
from dspx.provider_registry import create_from_env, ensure_default_providers
from dspx.lm_base import LMBase
from dspx.dtos import SignatureGenRequest, SignatureGenResult
from dspx.templates import render_simple_signature, format_signature_prompt
from dspx.cache import cache_enabled, make_key, read as cache_read, write as cache_write
import os as _os


def run_generate(prompt: str, *, lm: Optional[LMBase] = None) -> str:
    """Generate a signature class code string from a natural-language prompt.

    Accepts an optional `lm` of type LMBase to allow tests to inject a stub LM.
    """
    load_config_env()
    enable_mlflow_from_env()

    ensure_default_providers()
    active_lm = lm or create_from_env()
    dspy.configure(lm=active_lm)

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

    generator = SignatureGenerator()
    result = generator.generate_signature(prompt)
    return result.get("code") or ""


def run_generate_dto(
    req: SignatureGenRequest, *, lm: Optional[LMBase] = None
) -> SignatureGenResult:
    """DTO-oriented variant that returns structured result.

    If `req.template_version` starts with 'simple', a deterministic template is used
    (no LM calls). Otherwise, falls back to vibe-dspy generation.
    """
    import time as _time

    t0 = _time.time()
    # Fast path: template-only generation for deterministic tests
    if (req.template_version or "").startswith("simple"):
        cls_name = str(req.options.get("class_name") or "GeneratedSignature")
        key = make_key(
            {
                "kind": "signature",
                "prompt": req.prompt,
                "template_version": req.template_version or "simple-v1",
                "class_name": cls_name,
                "options": req.options,
            }
        )
        if cache_enabled():
            cached = cache_read("signature", key)
            if cached and isinstance(cached.get("code"), str):
                return SignatureGenResult(
                    code=cached["code"],
                    signature_name=cls_name,
                    task_description=cached.get("task_description") or req.prompt,
                )
        code = render_simple_signature(cls_name, req.prompt)
        if cache_enabled():
            cache_write(
                "signature", key, {"code": code, "task_description": req.prompt}
            )
        return SignatureGenResult(
            code=code,
            signature_name=cls_name,
            task_description=req.prompt,
            fields=None,
            reasoning=None,
        )

    # LM path (vibe-dspy)
    load_config_env()
    enable_mlflow_from_env()

    # Budget: propagate provider timeouts if set, and log later
    budget_ms_env = _os.getenv("DSPX_BUDGET_SIGNATURE_MS")
    budget_ms = (
        int(budget_ms_env) if budget_ms_env and budget_ms_env.isdigit() else None
    )
    if budget_ms:
        # best-effort propagate to known providers
        secs = max(1, int((budget_ms + 999) // 1000))
        for name in (
            "CODEX_TIMEOUT",
            "CLAUDE_TIMEOUT",
            "GEMINI_TIMEOUT",
            "OPENROUTER_TIMEOUT",
        ):
            _os.environ[name] = str(secs)

    ensure_default_providers()
    active_lm = lm or create_from_env()
    dspy.configure(lm=active_lm)

    # Ensure vibe-dspy is importable (same as run_generate)
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

    generator = SignatureGenerator()
    prompt = format_signature_prompt(req.prompt, version=req.template_version or "v1")
    raw = generator.generate_signature(prompt)
    res = SignatureGenResult(
        code=raw.get("code") or "",
        signature_name=raw.get("signature_name"),
        task_description=raw.get("task_description"),
        fields=raw.get("fields"),
        reasoning=raw.get("reasoning"),
    )
    # Cache LM-backed result as well
    key = make_key(
        {
            "kind": "signature",
            "prompt": req.prompt,
            "template_version": req.template_version or "v1",
            "options": req.options,
        }
    )
    if cache_enabled() and res.code:
        cache_write(
            "signature",
            key,
            {"code": res.code, "task_description": res.task_description},
        )
    # Optional MLflow logging (guarded)
    try:
        from dspx.tracing import ensure_run_with_standard_tags, get_mlflow

        mlflow = get_mlflow()
        if mlflow is not None:
            ensure_run_with_standard_tags(
                "signature",
                template_version=req.template_version or "v1",
                run_name=f"signature-{res.signature_name or ''}",
            )
            from dspx.cache import sha256_text

            if mlflow.active_run() is not None:  # type: ignore[attr-defined]
                mlflow.log_params(
                    {
                        "signature.prompt_len": len(req.prompt),
                        "signature.class_name": res.signature_name or "",
                    }
                )  # type: ignore[attr-defined]
                # Prefer log_text if available; else log_dict
                try:
                    mlflow.log_text(res.code, "signature.py")  # type: ignore[attr-defined]
                except Exception:
                    mlflow.log_dict(  # type: ignore[attr-defined]
                        {"code": res.code}, "signature.json"
                    )
                # Attach a tiny manifest for reproducibility
                try:
                    manifest = {
                        "template_version": req.template_version or "v1",
                        "prompt_len": len(req.prompt),
                        "code_hash": sha256_text(res.code),
                    }
                    mlflow.log_dict(manifest, "signature_manifest.json")  # type: ignore[attr-defined]
                except Exception:
                    pass
                duration_ms = (_time.time() - t0) * 1000.0
                metrics = {
                    "signature.code_hash_prefix": int(sha256_text(res.code)[:8], 16)
                    % 1_000_000,
                    "service.duration_ms": duration_ms,
                }
                if budget_ms is not None:
                    try:
                        mlflow.set_tag("service.budget_ms", str(budget_ms))  # type: ignore[attr-defined]
                    except Exception:
                        pass
                    metrics["service.budget_exceeded"] = (
                        1.0 if duration_ms > float(budget_ms) else 0.0
                    )
                mlflow.log_metrics(metrics)  # type: ignore[attr-defined]
    except Exception:
        pass
    return res
