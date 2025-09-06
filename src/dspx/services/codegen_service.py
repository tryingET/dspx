from __future__ import annotations

import os
import re
from typing import Optional

import dspy

from dspx.config_loader import load_config_env
from dspx.tracing import enable_mlflow_from_env
from dspx.provider_registry import create_from_env, ensure_default_providers
from dspx.lm_base import LMBase
from dspx.dtos import CodegenRequest, CodegenResult
from dspx.templates import format_codegen_spec, render_minimal_program
from dspx.cache import cache_enabled, make_key, read as cache_read, write as cache_write


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
    lm: Optional[LMBase] = None,
) -> str:
    # Configure env + tracing
    load_config_env()
    enable_mlflow_from_env()

    # LM options (read from env via provider-specific factories)
    # Kept minimal here; provider registry will apply env when creating the LM.

    # Create LM via provider registry (default: codex-exec)
    ensure_default_providers()
    active_lm = lm or create_from_env()
    dspy.configure(lm=active_lm)

    codegen = dspy.Predict("spec -> code")
    full_spec = format_codegen_spec(spec, language, version="v1")
    result = codegen(spec=full_spec)
    text = result.code if hasattr(result, "code") else str(result)
    code_text = text if print_all else _extract_code_block(text)

    if outfile:
        path = outfile
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(code_text + ("\n" if not code_text.endswith("\n") else ""))
        # Write a metadata file with hash
        try:
            from dspx.cache import sha256_text
            import json as _json

            meta = {
                "hash": sha256_text(code_text),
                "language": language or "python",
                "spec": spec,
            }
            with open(path + ".meta.json", "w", encoding="utf-8") as mf:
                mf.write(_json.dumps(meta, ensure_ascii=False, indent=2))
        except Exception:
            pass
        # MLflow: log artifacts (best-effort)
        try:
            from dspx.tracing import ensure_run_from_env
            import mlflow

            ensure_run_from_env(
                tags={"service": "codegen", "language": language or "python"}
            )
            try:
                mlflow.log_artifact(path)  # type: ignore[attr-defined]
            except Exception:
                pass
            meta_path = path + ".meta.json"
            if os.path.exists(meta_path):
                try:
                    mlflow.log_artifact(meta_path)  # type: ignore[attr-defined]
                except Exception:
                    pass
        except Exception:
            pass
    return code_text


def run_dto(req: CodegenRequest, *, lm: Optional[LMBase] = None) -> CodegenResult:
    """DTO-oriented codegen. Supports template-only deterministic path."""
    # Template-only deterministic path (no LM required)
    if (req.template_version or "").startswith("simple"):
        key = make_key(
            {
                "kind": "codegen",
                "spec": req.spec,
                "language": (req.language or "python"),
                "template_version": req.template_version or "simple-v1",
                "options": req.options,
            }
        )
        if cache_enabled():
            cached = cache_read("codegen", key)
            if cached and isinstance(cached.get("code"), str):
                return CodegenResult(
                    code=cached["code"], language=(req.language or "python")
                )
        code = render_minimal_program(req.language, req.spec)
        if cache_enabled():
            cache_write(
                "codegen", key, {"code": code, "language": (req.language or "python")}
            )
        return CodegenResult(code=code, language=(req.language or "python"))

    # LM-backed codegen path
    load_config_env()
    enable_mlflow_from_env()
    ensure_default_providers()
    active_lm = lm or create_from_env()
    dspy.configure(lm=active_lm)

    codegen = dspy.Predict("spec -> code")
    full_spec = format_codegen_spec(
        req.spec, req.language, version=req.template_version or "v1"
    )
    result = codegen(spec=full_spec)
    text = result.code if hasattr(result, "code") else str(result)
    res = CodegenResult(code=text, language=req.language, raw_text=str(result))
    key = make_key(
        {
            "kind": "codegen",
            "spec": req.spec,
            "language": (req.language or "python"),
            "template_version": req.template_version or "v1",
            "options": req.options,
        }
    )
    if cache_enabled() and res.code:
        cache_write(
            "codegen", key, {"code": res.code, "language": (req.language or "python")}
        )
    # Optional MLflow logging (guarded)
    try:
        from dspx.tracing import ensure_run_from_env

        if ensure_run_from_env(
            tags={
                "service": "codegen",
                "template_version": req.template_version or "v1",
            }
        ):
            import mlflow
            from dspx.cache import sha256_text

            mlflow.log_params(
                {
                    "codegen.language": req.language or "",
                    "codegen.spec_len": len(req.spec),
                }
            )  # type: ignore[attr-defined]
            try:
                mlflow.log_text(res.code, "codegen_output.txt")  # type: ignore[attr-defined]
            except Exception:
                mlflow.log_dict({"code": res.code}, "codegen_output.json")  # type: ignore[attr-defined]
            mlflow.log_metrics(
                {
                    "codegen.code_hash_prefix": int(sha256_text(res.code)[:8], 16)
                    % 1_000_000
                }
            )  # type: ignore[attr-defined]
    except Exception:
        pass
    return res
