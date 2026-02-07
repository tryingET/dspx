from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, cast

from dspx.config_loader import load_config_env
from dspx.dtos import SignatureGenRequest
from dspx.lm_base import LMBase
from dspx.provider_registry import create_from_env, ensure_default_providers
from dspx.services.signatures_service import run_generate_dto
from dspx.tracing import enable_mlflow_from_env


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

    m = re.search(
        r"^class\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(\s*dspy\.Signature\s*\)\s*:",
        code,
        re.M,
    )
    if m:
        return m.group(1)
    return None


@dataclass
class _RefinementMemory:
    base_prompt: str
    constraints: list[str] = field(default_factory=list)
    feedback_history: list[str] = field(default_factory=list)

    def add_feedback(self, text: str) -> None:
        t = (text or "").strip()
        if not t:
            return
        self.feedback_history.append(t)

    def build_prompt(self) -> str:
        task = (self.base_prompt or "").strip()
        parts = [task]
        if self.constraints:
            parts.append(
                "Constraints:\n"
                + "\n".join(
                    f"- {c.strip()}" for c in self.constraints if c and c.strip()
                )
            )
        if self.feedback_history:
            parts.append(
                "Refinement feedback history:\n"
                + "\n".join(
                    f"- {f.strip()}" for f in self.feedback_history if f and f.strip()
                )
            )
        return "\n\n".join([p for p in parts if p]).strip()


def _native_generate_signature(
    prompt: str,
    *,
    class_name: str = "GeneratedSignature",
    attempts: int = 1,
    constraints: list[str] | None = None,
    feedback: list[str] | None = None,
    lm: Optional[LMBase] = None,
) -> str:
    options: dict[str, object] = {
        "class_name": class_name,
        "max_attempts": max(1, int(attempts)),
    }
    if constraints:
        options["constraints"] = list(constraints)
    if feedback:
        options["feedback"] = list(feedback)

    req = SignatureGenRequest(
        prompt=prompt,
        template_version="v1",
        options=options,
    )
    res = run_generate_dto(req, lm=lm)
    return res.code


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
    active_lm = cast(Optional[LMBase], lm or create_from_env())

    t0 = time.time()
    budget_ms_env = os.getenv("DSPX_BUDGET_SIGNATURE_MS")
    budget_ms = (
        int(budget_ms_env) if budget_ms_env and budget_ms_env.isdigit() else None
    )
    backend = "native"
    mode = "refine"
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
                extra={"signature.mode": mode, "signature.backend": backend},
            )
    except Exception:
        mlflow = None
        started_run = False

    memory = _RefinementMemory(base_prompt=prompt)
    code = ""
    rounds = 0

    if non_interactive:
        rounds = 1
        code = _native_generate_signature(
            memory.build_prompt(),
            class_name="GeneratedSignature",
            attempts=max(1, int(attempts)),
            constraints=memory.constraints,
            feedback=memory.feedback_history,
            lm=active_lm,
        )
    else:
        for idx in range(max(1, int(attempts))):
            rounds += 1
            code = _native_generate_signature(
                memory.build_prompt(),
                class_name="GeneratedSignature",
                attempts=1,
                constraints=memory.constraints,
                feedback=memory.feedback_history,
                lm=active_lm,
            )
            ans = input("Accept signature? [y/N]: ").strip().lower()
            if ans in {"y", "yes"}:
                break
            if idx == max(1, int(attempts)) - 1:
                break
            feedback = (
                input("Feedback (leave empty for generic): ").strip()
                or "Please improve the signature while preserving prior constraints."
            )
            memory.add_feedback(feedback)

    if wrap_script:
        code = _wrap_script(code)

    cls = _extract_sig_class_name(code)
    if outfile:
        out_path = Path(outfile)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(code, encoding="utf-8")
        # Signature metadata parity with `signature gen`
        try:
            from dspx.cache import cache_dir, make_key, sha256_text

            cache_key = make_key(
                {
                    "kind": "signature",
                    "prompt": prompt,
                    "template_version": template_version,
                    "class_name": cls or "",
                    "mode": mode,
                    "backend": backend,
                    "attempts": int(attempts),
                    "non_interactive": bool(non_interactive),
                    "feedback": list(memory.feedback_history),
                    "constraints": list(memory.constraints),
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
                "mode": mode,
                "backend": backend,
                "attempts": int(attempts),
                "non_interactive": bool(non_interactive),
                "feedback_count": len(memory.feedback_history),
                "constraint_count": len(memory.constraints),
                "rounds": rounds,
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
                            "signature.mode": mode,
                            "signature.backend": backend,
                            "signature.attempts": int(attempts),
                            "signature.non_interactive": bool(non_interactive),
                            "signature.wrap_script": bool(wrap_script),
                            "signature.class_name": cls or "",
                            "signature.prompt_len": len(prompt or ""),
                            "signature.feedback_count": len(memory.feedback_history),
                            "signature.constraint_count": len(memory.constraints),
                            "signature.rounds": rounds,
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
