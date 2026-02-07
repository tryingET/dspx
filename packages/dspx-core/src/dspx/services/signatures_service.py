from __future__ import annotations

import os as _os
import re
from typing import Any, Optional

import dspy

from dspx.cache import cache_enabled, make_key, read as cache_read, write as cache_write
from dspx.config_loader import load_config_env
from dspx.dtos import SignatureGenRequest, SignatureGenResult
from dspx.lm_base import LMBase
from dspx.provider_registry import create_from_env, ensure_default_providers
from dspx.templates import format_signature_prompt, render_simple_signature
from dspx.tracing import enable_mlflow_from_env
from dspx.upstream_paths import ensure_vibe_on_path


def _extract_code_block(text: str) -> str:
    fence = re.compile(r"```[\\w+-]*\\n([\\s\\S]*?)\\n```", re.MULTILINE)
    m = fence.search(text or "")
    if m:
        return m.group(1).strip()
    return (text or "").strip()


def _extract_signature_name(code: str) -> str | None:
    m = re.search(
        r"^class\\s+([A-Za-z_][A-Za-z0-9_]*)\\s*\\(\\s*dspy\\.Signature\\s*\\)\\s*:",
        code or "",
        re.M,
    )
    if m:
        return m.group(1)
    return None


def _generate_via_native(
    *,
    prompt_for_model: str,
    fallback_description: str,
    class_name_hint: str,
) -> dict[str, Any]:
    predictor = dspy.Predict("task -> code")
    result = predictor(task=prompt_for_model)
    text = result.code if hasattr(result, "code") else str(result)
    code = _extract_code_block(text)
    sig_name = _extract_signature_name(code)

    if not code or sig_name is None:
        code = render_simple_signature(class_name_hint, fallback_description)
        sig_name = class_name_hint

    return {
        "code": code,
        "signature_name": sig_name,
        "task_description": fallback_description,
        "fields": None,
        "reasoning": None,
        "backend": "native",
    }


def _generate_signature_payload(
    *,
    prompt_for_model: str,
    fallback_description: str,
    class_name_hint: str,
) -> dict[str, Any]:
    ensure_vibe_on_path()

    try:
        from signature_generator import SignatureGenerator  # type: ignore

        generator = SignatureGenerator()
        raw = generator.generate_signature(prompt_for_model)
        code = str(raw.get("code") or "")
        sig_name = (
            raw.get("signature_name") or _extract_signature_name(code) or ""
        ).strip() or None

        if not code or sig_name is None:
            return _generate_via_native(
                prompt_for_model=prompt_for_model,
                fallback_description=fallback_description,
                class_name_hint=class_name_hint,
            )

        return {
            "code": code,
            "signature_name": sig_name,
            "task_description": raw.get("task_description") or fallback_description,
            "fields": raw.get("fields"),
            "reasoning": raw.get("reasoning"),
            "backend": "vibe",
        }
    except Exception:
        return _generate_via_native(
            prompt_for_model=prompt_for_model,
            fallback_description=fallback_description,
            class_name_hint=class_name_hint,
        )


def run_generate(prompt: str, *, lm: Optional[LMBase] = None) -> str:
    """Generate a signature class code string from a natural-language prompt."""
    load_config_env()
    enable_mlflow_from_env()

    ensure_default_providers()
    active_lm = lm or create_from_env()
    dspy.configure(lm=active_lm)

    payload = _generate_signature_payload(
        prompt_for_model=format_signature_prompt(prompt, version="v1"),
        fallback_description=prompt,
        class_name_hint="GeneratedSignature",
    )
    return str(payload.get("code") or "")


def run_generate_dto(
    req: SignatureGenRequest, *, lm: Optional[LMBase] = None
) -> SignatureGenResult:
    """DTO-oriented variant that returns structured result.

    If `req.template_version` starts with 'simple', a deterministic template is used
    (no LM calls). Otherwise, uses vibe-dspy when available and a native fallback.
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

    # LM path (vibe-dspy if available; native fallback otherwise)
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
            "DSPX_PI_TIMEOUT",
        ):
            _os.environ[name] = str(secs)

    ensure_default_providers()
    active_lm = lm or create_from_env()
    dspy.configure(lm=active_lm)

    class_name_hint = str(req.options.get("class_name") or "GeneratedSignature")
    prompt_for_model = format_signature_prompt(
        req.prompt, version=req.template_version or "v1"
    )
    payload = _generate_signature_payload(
        prompt_for_model=prompt_for_model,
        fallback_description=req.prompt,
        class_name_hint=class_name_hint,
    )

    res = SignatureGenResult(
        code=str(payload.get("code") or ""),
        signature_name=payload.get("signature_name"),
        task_description=payload.get("task_description"),
        fields=payload.get("fields"),
        reasoning=payload.get("reasoning"),
    )
    backend = str(payload.get("backend") or "unknown")

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
            {
                "code": res.code,
                "task_description": res.task_description,
                "backend": backend,
            },
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
                extra={"signature.backend": backend},
            )
            from dspx.cache import sha256_text

            if mlflow.active_run() is not None:
                mlflow.log_params(
                    {
                        "signature.prompt_len": len(req.prompt),
                        "signature.class_name": res.signature_name or "",
                        "signature.backend": backend,
                    }
                )
                # Prefer log_text if available; else log_dict
                try:
                    mlflow.log_text(res.code, "signature.py")
                except Exception:
                    mlflow.log_dict({"code": res.code}, "signature.json")
                # Attach a tiny manifest for reproducibility
                try:
                    manifest = {
                        "template_version": req.template_version or "v1",
                        "prompt_len": len(req.prompt),
                        "code_hash": sha256_text(res.code),
                        "backend": backend,
                    }
                    mlflow.log_dict(manifest, "signature_manifest.json")
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
                        mlflow.set_tag("service.budget_ms", str(budget_ms))
                    except Exception:
                        pass
                    metrics["service.budget_exceeded"] = (
                        1.0 if duration_ms > float(budget_ms) else 0.0
                    )
                mlflow.log_metrics(metrics)
    except Exception:
        pass
    return res
