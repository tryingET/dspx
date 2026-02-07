from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

import dspy

from dspx.config_loader import load_config_env
from dspx.tracing import enable_mlflow_from_env
from dspx.provider_registry import create_from_env, ensure_default_providers
from dspx.lm_base import LMBase
from dspx.dtos import CodegenRequest, CodegenResult
from dspx.templates import format_codegen_spec, render_minimal_program
from dspx.cache import cache_enabled, make_key, read as cache_read, write as cache_write
import os as _os


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

    # Create LM via provider registry (default: pi-rpc)
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
        # Write a versioned run receipt for replay/explain.
        try:
            from dspx.cache import make_key, cache_dir, sha256_text
            from dspx.run_receipts import build_run_receipt, write_run_receipt

            lang = language or "python"
            cache_key = make_key(
                {
                    "kind": "codegen",
                    "spec": spec,
                    "language": lang,
                    "template_version": "v1",
                    "options": {},
                }
            )
            cfile = cache_dir() / "codegen" / f"{cache_key}.json"
            meta = build_run_receipt(
                run_kind="codegen",
                output_path=Path(path),
                output_hash=sha256_text(code_text),
                template_version="v1",
                cache_key=cache_key,
                cache_file=str(cfile),
                cache_enabled=cache_enabled(),
                replay_inputs={
                    "spec": spec,
                    "language": lang,
                    "template_version": "v1",
                    "options": {},
                },
                extra={
                    "language": lang,
                    "spec_len": len(spec),
                },
            )
            write_run_receipt(Path(path), meta)
        except Exception:
            pass
        # MLflow: log artifacts (best-effort)
        try:
            from dspx.tracing import ensure_run_from_env, get_mlflow

            mlflow = get_mlflow()
            if mlflow is not None:
                ensure_run_from_env(
                    tags={"service": "codegen", "language": language or "python"}
                )
                if mlflow.active_run() is not None:
                    try:
                        mlflow.log_artifact(path)
                    except Exception:
                        pass
                    meta_path = path + ".meta.json"
                    if os.path.exists(meta_path):
                        try:
                            mlflow.log_artifact(meta_path)
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
    # Budget propagation to providers (best-effort)
    budget_ms_env = _os.getenv("DSPX_BUDGET_CODEGEN_MS")
    budget_ms = (
        int(budget_ms_env) if budget_ms_env and budget_ms_env.isdigit() else None
    )
    if budget_ms:
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

    codegen = dspy.Predict("spec -> code")
    full_spec = format_codegen_spec(
        req.spec, req.language, version=req.template_version or "v1"
    )
    import time as _time

    t0 = _time.time()
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
        from dspx.tracing import ensure_run_with_standard_tags, get_mlflow

        mlflow = get_mlflow()
        if mlflow is not None:
            ensure_run_with_standard_tags(
                "codegen",
                template_version=req.template_version or "v1",
                run_name=f"codegen-{req.language or 'python'}",
            )
            from dspx.cache import sha256_text

            if mlflow.active_run() is not None:
                mlflow.log_params(
                    {
                        "codegen.language": req.language or "",
                        "codegen.spec_len": len(req.spec),
                    }
                )
                try:
                    mlflow.log_text(res.code, "codegen_output.txt")
                except Exception:
                    mlflow.log_dict({"code": res.code}, "codegen_output.json")
                # Attach manifest for reproducibility
                try:
                    man = {
                        "template_version": req.template_version or "v1",
                        "language": req.language or "python",
                        "spec_len": len(req.spec),
                        "code_hash_prefix": int(sha256_text(res.code)[:8], 16)
                        % 1_000_000,
                    }
                    mlflow.log_dict(man, "codegen_manifest.json")
                except Exception:
                    pass
                duration_ms = (_time.time() - t0) * 1000.0
                metrics = {
                    "codegen.code_hash_prefix": int(sha256_text(res.code)[:8], 16)
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
