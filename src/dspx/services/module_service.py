from __future__ import annotations

from typing import Optional

from dspx.dtos import ModuleArtifact, ModuleSpec, SignatureGenRequest
from dspx.lm_base import LMBase
from dspx.services.signatures_service import run_generate_dto
from dspx.templates.module_templates import render_module_skeleton
from dspx.cache import cache_enabled, make_key, read as cache_read, write as cache_write
from dspx.templates.signature_templates import render_simple_signature


def _sig_class_name(module_name: str) -> str:
    import re

    s = re.sub(r"\W+", "_", module_name.strip() or "Module")
    if s[0].isdigit():
        s = f"_{s}"
    return f"Sig_{s}"


def run_generate(
    spec: ModuleSpec,
    *,
    lm: Optional[LMBase] = None,
    use_signature: bool = False,
) -> ModuleArtifact:
    """Generate a reusable dspy.Module skeleton from ModuleSpec.

    - Deterministic template-only path when `spec.options.template_version` starts with 'simple'.
    - If `use_signature=True`, embeds a generated Signature class above the Module and wires Predict.
    - LM-backed generation is reserved for future versions; current implementation focuses on templates.
    """
    import time as _time

    t0 = _time.time()
    tv = (
        (spec.options or {}).get("template_version")
        if hasattr(spec, "options")
        else None
    )
    simple = isinstance(tv, str) and tv.startswith("simple")

    desc = spec.description or ""
    inputs = list(spec.inputs or [])
    outputs = list(spec.outputs or [])

    if simple:
        key = make_key(
            {
                "kind": "module",
                "name": spec.name,
                "description": desc,
                "inputs": inputs,
                "outputs": outputs,
                "use_signature": use_signature,
                "template_version": tv,
            }
        )
        if cache_enabled():
            cached = cache_read("module", key)
            if cached and isinstance(cached.get("code"), str):
                return ModuleArtifact(
                    name=spec.name,
                    code=cached["code"],
                    metadata=cached.get("metadata") or {},
                )
        sig_code = None
        sig_name = None
        if use_signature:
            sig_name = _sig_class_name(spec.name)
            # Use deterministic signature template
            sig_code = render_simple_signature(
                sig_name, desc or f"Signature for {spec.name}"
            )
        code = render_module_skeleton(
            spec.name,
            inputs,
            outputs,
            desc,
            signature_code=sig_code,
            signature_class_name=sig_name,
        )
        meta = {
            "template_version": tv,
            "uses_signature": bool(use_signature),
        }
        art = ModuleArtifact(name=spec.name, code=code, metadata=meta)
        if cache_enabled():
            cache_write("module", key, {"code": art.code, "metadata": art.metadata})
        return art

    # Future: LM-backed path. For now, fallback to deterministic skeleton.
    sig_code = None
    sig_name = None
    if use_signature:
        # Try to generate via signature service (DTO) with a stable template fallback
        try:
            sig_name = _sig_class_name(spec.name)
            req = SignatureGenRequest(
                prompt=desc or f"Module {spec.name} signature",
                template_version="simple-v1",
                options={"class_name": sig_name},
            )
            res = run_generate_dto(req, lm=lm)
            sig_code = res.code or None
        except Exception:
            sig_code = render_simple_signature(
                sig_name or _sig_class_name(spec.name),
                desc or f"Signature for {spec.name}",
            )

    code = render_module_skeleton(
        spec.name,
        inputs,
        outputs,
        desc,
        signature_code=sig_code,
        signature_class_name=sig_name,
    )
    art = ModuleArtifact(
        name=spec.name, code=code, metadata={"uses_signature": bool(use_signature)}
    )
    if cache_enabled():
        key = make_key(
            {
                "kind": "module",
                "name": spec.name,
                "description": desc,
                "inputs": inputs,
                "outputs": outputs,
                "use_signature": use_signature,
                "template_version": tv or "v1",
            }
        )
        cache_write("module", key, {"code": art.code, "metadata": art.metadata})
    # Optional MLflow logging (guarded)
    try:
        from dspx.tracing import ensure_run_with_standard_tags

        if ensure_run_with_standard_tags(
            "module", template_version=tv or "v1", run_name=f"module-{spec.name}"
        ):
            import mlflow
            from dspx.cache import sha256_text

            mlflow.log_params(
                {
                    "module.name": spec.name,
                    "module.inputs": ",".join(inputs),
                    "module.outputs": ",".join(outputs),
                    "module.use_signature": str(bool(use_signature)),
                }
            )  # type: ignore[attr-defined]
            try:
                mlflow.log_text(art.code, f"{spec.name}.py")  # type: ignore[attr-defined]
            except Exception:
                mlflow.log_dict({"code": art.code}, f"{spec.name}.json")  # type: ignore[attr-defined]
            # Attach manifest for reproducibility
            try:
                man = {
                    "template_version": tv or "v1",
                    "uses_signature": bool(use_signature),
                    "name": spec.name,
                    "inputs": inputs,
                    "outputs": outputs,
                }
                mlflow.log_dict(man, f"{spec.name}.manifest.json")  # type: ignore[attr-defined]
            except Exception:
                pass
            mlflow.log_metrics(
                {
                    "module.code_hash_prefix": int(sha256_text(art.code)[:8], 16)
                    % 1_000_000,
                    "service.duration_ms": (_time.time() - t0) * 1000.0,
                }
            )  # type: ignore[attr-defined]
    except Exception:
        pass
    return art
