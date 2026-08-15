# summary: "Keeps module generation as a stable facade over rendering, synthesis, evidence, caching, and telemetry."
# read_when:
#   - "Changing reusable DSPy module generation or its public service boundary."

from __future__ import annotations

from pathlib import Path
from typing import Optional
import os as _os

from dspx.cache import cache_enabled, read as cache_read, write as cache_write
from dspx.dtos import ModuleArtifact, ModuleSpec
from dspy import BaseLM
from dspx.services.module_artifacts import (
    module_cache_key as _module_cache_key,
    render_seed_module_code,
    template_version as _template_version,
    validate_module_spec_identifiers as _validate_module_spec_identifiers,
)
from dspx.services.module_synthesis_evidence import retrieve_module_synthesis_evidence
from dspx.services.module_synthesis_quality import (
    append_module_quality_event,
    build_module_quality_event_from_metadata,
)
from dspx.services.module_synthesis_runtime import (
    build_module_metadata as _build_metadata,
)


def _generate_base_code(
    spec: ModuleSpec,
    *,
    use_signature: bool,
    template_version: Optional[str],
) -> str:
    return render_seed_module_code(
        spec,
        use_signature=use_signature,
        template_version=template_version,
    )


def _materialize_metadata(
    spec: ModuleSpec,
    *,
    code: str,
    use_signature: bool,
    template_version: Optional[str],
    promotion_target: Optional[Path],
    base_metadata: Optional[dict] = None,
) -> tuple[str, dict]:
    return _build_metadata(
        spec,
        code=code,
        use_signature=use_signature,
        template_version=template_version,
        promotion_target=promotion_target,
        base_metadata=base_metadata,
        evidence_retriever=retrieve_module_synthesis_evidence,
        quality_event_builder=build_module_quality_event_from_metadata,
        quality_event_appender=append_module_quality_event,
    )


def run_generate(
    spec: ModuleSpec,
    *,
    lm: Optional[BaseLM] = None,
    use_signature: bool = False,
    promotion_target: Optional[Path] = None,
) -> ModuleArtifact:
    """Generate a reusable ``dspy.Module`` scaffold from ``ModuleSpec``.

    ``module_service`` is intentionally kept as the stable public facade. Pure
    artifact rendering, synthesis-runtime execution, advisory evidence assembly,
    and governance-only diagnostics live in narrower module_* service files.
    """
    import time as _time

    del lm  # LM-backed module synthesis is still reserved for future versions.

    t0 = _time.time()
    budget_ms_env = _os.getenv("DSPX_BUDGET_MODULE_MS")
    budget_ms = (
        int(budget_ms_env) if budget_ms_env and budget_ms_env.isdigit() else None
    )
    tv = _template_version(spec)
    simple = isinstance(tv, str) and tv.startswith("simple")

    inputs = list(spec.inputs or [])
    outputs = list(spec.outputs or [])
    _validate_module_spec_identifiers(spec)

    key = _module_cache_key(
        spec,
        use_signature=use_signature,
        template_version=tv if simple else (tv or "v1"),
    )
    if simple and cache_enabled():
        cached = cache_read("module", key)
        if cached and isinstance(cached.get("code"), str):
            selected_code, metadata = _materialize_metadata(
                spec,
                code=cached["code"],
                use_signature=use_signature,
                template_version=tv,
                promotion_target=promotion_target,
                base_metadata=(
                    cached.get("metadata")
                    if isinstance(cached.get("metadata"), dict)
                    else None
                ),
            )
            return ModuleArtifact(
                name=spec.name,
                code=selected_code,
                metadata=metadata,
            )

    code = _generate_base_code(
        spec,
        use_signature=use_signature,
        template_version=tv,
    )
    base_metadata: dict[str, object] = {
        "uses_signature": bool(use_signature),
        "inputs": inputs,
        "outputs": outputs,
        "io_spec": {"inputs": inputs, "outputs": outputs},
    }
    if tv is not None:
        base_metadata["template_version"] = tv

    selected_code, metadata = _materialize_metadata(
        spec,
        code=code,
        use_signature=use_signature,
        template_version=tv,
        promotion_target=promotion_target,
        base_metadata=base_metadata,
    )
    art = ModuleArtifact(name=spec.name, code=selected_code, metadata=metadata)
    if cache_enabled():
        cache_write("module", key, {"code": art.code, "metadata": art.metadata})

    if not simple:
        _log_module_generation_to_mlflow(
            art=art,
            spec=spec,
            inputs=inputs,
            outputs=outputs,
            use_signature=use_signature,
            template_version=tv,
            budget_ms=budget_ms,
            started_at=t0,
        )
    return art


def _log_module_generation_to_mlflow(
    *,
    art: ModuleArtifact,
    spec: ModuleSpec,
    inputs: list[str],
    outputs: list[str],
    use_signature: bool,
    template_version: Optional[str],
    budget_ms: Optional[int],
    started_at: float,
) -> None:
    try:
        import time as _time

        from dspx.cache import sha256_text
        from dspx.tracing import ensure_run_with_standard_tags, get_mlflow

        mlflow = get_mlflow()
        if mlflow is None:
            return
        ensure_run_with_standard_tags(
            "module",
            template_version=template_version or "v1",
            run_name=f"module-{spec.name}",
            run_kind="module-gen",
        )
        if mlflow.active_run() is None:
            return
        mlflow.log_params(
            {
                "module.name": spec.name,
                "module.inputs": ",".join(inputs),
                "module.outputs": ",".join(outputs),
                "module.use_signature": str(bool(use_signature)),
            }
        )
        try:
            mlflow.log_text(art.code, f"{spec.name}.py")
        except Exception:
            mlflow.log_dict({"code": art.code}, f"{spec.name}.json")
        try:
            man = {
                "template_version": template_version or "v1",
                "uses_signature": bool(use_signature),
                "name": spec.name,
                "inputs": inputs,
                "outputs": outputs,
            }
            mlflow.log_dict(man, f"{spec.name}.manifest.json")
        except Exception:
            pass
        duration_ms = (_time.time() - started_at) * 1000.0
        metrics = {
            "module.code_hash_prefix": int(sha256_text(art.code)[:8], 16) % 1_000_000,
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
