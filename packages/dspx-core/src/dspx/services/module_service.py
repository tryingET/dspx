from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from dspx.cache import cache_enabled, make_key, read as cache_read, write as cache_write
from dspx.dtos import ModuleArtifact, ModuleSpec, SignatureGenRequest
from dspx.lm_base import LMBase
from dspx.services.signatures_service import run_generate_dto
from dspx.synthesis import execute_module_synthesis_bundle, module_synthesis_run_summary
from dspx.templates.module_templates import render_module_skeleton
from dspx.templates.signature_templates import render_simple_signature
import os as _os


def _sig_class_name(module_name: str) -> str:
    import re

    s = re.sub(r"\W+", "_", module_name.strip() or "Module")
    if s[0].isdigit():
        s = f"_{s}"
    return f"Sig_{s}"


def _template_version(spec: ModuleSpec) -> Optional[str]:
    value = (
        (spec.options or {}).get("template_version")
        if hasattr(spec, "options")
        else None
    )
    if value is None:
        return None
    return value if isinstance(value, str) else str(value)


def _insert_after_first_blank_line(code: str, block: str) -> str:
    lines = code.splitlines()
    if not lines:
        return block if block.endswith("\n") else block + "\n"
    if len(lines) > 1 and lines[0].startswith("import ") and lines[1] == "":
        new_lines = [lines[0], "", *block.splitlines(), *lines[2:]]
    else:
        new_lines = [*block.splitlines(), *lines]
    rendered = "\n".join(new_lines)
    return rendered if rendered.endswith("\n") else rendered + "\n"


def _with_trace_comment(code: str) -> str:
    return _insert_after_first_blank_line(
        code,
        "# Ranked synthesis candidate variant\nMODULE_VARIANT = 'traceable'",
    )


def _with_helper_docstrings(code: str) -> str:
    replacements = {
        "def build_student(*, use_cot: bool = False) -> dspy.Module:\n": (
            "def build_student(*, use_cot: bool = False) -> dspy.Module:\n"
            '    """Construct the generated module for runtime selection."""\n'
        ),
        "def io_spec() -> dict[str, list[str]]:\n": (
            "def io_spec() -> dict[str, list[str]]:\n"
            '    """Return the declared module IO contract."""\n'
        ),
        "def output_weights() -> dict[str, float]:\n": (
            "def output_weights() -> dict[str, float]:\n"
            '    """Provide deterministic output weighting for evaluation."""\n'
        ),
        "def normalize_output(\n": ("def normalize_output(\n"),
    }
    updated = code
    for old, new in replacements.items():
        if old in updated and new not in updated:
            updated = updated.replace(old, new, 1)
    needle = ") -> tuple[str, str]:\n"
    doc = (
        ") -> tuple[str, str]:\n"
        '    """Normalize gold/pred pairs for deterministic checks."""\n'
    )
    if needle in updated and doc not in updated:
        updated = updated.replace(needle, doc, 1)
    return updated


def _seed_code(
    spec: ModuleSpec,
    *,
    base_code: str,
    use_signature: bool,
    template_version: Optional[str],
) -> str:
    simple = isinstance(template_version, str) and template_version.startswith("simple")
    if not simple:
        return base_code

    desc = spec.description or ""
    inputs = list(spec.inputs or [])
    outputs = list(spec.outputs or [])
    sig_code = None
    sig_name = None
    if use_signature:
        sig_name = _sig_class_name(spec.name)
        sig_code = render_simple_signature(
            sig_name,
            desc or f"Signature for {spec.name}",
        )
    return render_module_skeleton(
        spec.name,
        inputs,
        outputs,
        desc,
        signature_code=sig_code,
        signature_class_name=sig_name,
    )


def _candidate_sources(
    spec: ModuleSpec,
    *,
    code: str,
    use_signature: bool,
    template_version: Optional[str],
) -> list[dict[str, Any]]:
    seed_code = _seed_code(
        spec,
        base_code=code,
        use_signature=use_signature,
        template_version=template_version,
    )
    raw_variants = [
        (
            "baseline",
            "Baseline deterministic scaffold",
            seed_code,
            1.0,
            "Preserve the compact baseline render as the control candidate.",
        ),
        (
            "traceable",
            "Traceable scaffold",
            _with_trace_comment(seed_code),
            2.0,
            "Prefer candidates that expose an explicit trace marker for receipts and replay.",
        ),
        (
            "explainable_helpers",
            "Explainable helper scaffold",
            _with_helper_docstrings(seed_code),
            3.0,
            "Prefer candidates that make helper intent explicit for replay and inspection.",
        ),
    ]

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for variant_id, label, variant_code, bonus, basis in raw_variants:
        if variant_code in seen:
            continue
        seen.add(variant_code)
        deduped.append(
            {
                "code": variant_code,
                "artifact_metadata": {
                    "variant_id": variant_id,
                    "variant_label": label,
                },
                "candidate_metadata": {
                    "variant_id": variant_id,
                    "variant_label": label,
                    "selection_bonus": bonus,
                    "selection_basis": basis,
                },
                "lineage": {
                    "variant_id": variant_id,
                    "variant_origin": "deterministic_template_variant",
                },
            }
        )
    return deduped


def _selected_candidate_code(bundle: Any, fallback: str) -> str:
    selected_candidate_id = (
        bundle.promotion_shell.selected_candidate_id
        if bundle.promotion_shell is not None
        else bundle.promotion_decision.candidate_id
    )
    if selected_candidate_id is None:
        return fallback
    for workspace in bundle.candidate_workspaces:
        if workspace.candidate_id == selected_candidate_id:
            path = Path(workspace.artifact_path)
            if path.exists():
                return path.read_text(encoding="utf-8")
    return fallback


def _build_metadata(
    spec: ModuleSpec,
    *,
    code: str,
    use_signature: bool,
    template_version: Optional[str],
    promotion_target: Optional[Path] = None,
    base_metadata: Optional[dict[str, Any]] = None,
) -> tuple[str, dict[str, Any]]:
    metadata: dict[str, Any] = dict(base_metadata or {})
    if template_version is not None:
        metadata["template_version"] = template_version
    metadata["uses_signature"] = bool(use_signature)

    candidate_sources = _candidate_sources(
        spec,
        code=code,
        use_signature=use_signature,
        template_version=template_version,
    )
    synthesis_bundle = execute_module_synthesis_bundle(
        spec,
        code=code,
        candidate_sources=candidate_sources,
        use_signature=use_signature,
        promotion_target=promotion_target,
        strategy_metadata={
            "fan_out_kind": "deterministic_template_variants",
            "seed_template_version": template_version,
        },
    )
    selected_code = _selected_candidate_code(synthesis_bundle, code)
    run_summary = module_synthesis_run_summary(synthesis_bundle)
    evaluation_status = run_summary.get("evaluation_status")
    if evaluation_status != "passed":
        raise RuntimeError(
            f"Module synthesis runtime validation failed for {spec.name}: "
            f"status={evaluation_status}"
        )

    metadata.update(run_summary)
    metadata["run_summary"] = run_summary
    metadata["selected_candidate_id"] = run_summary.get("selected_candidate_id")
    metadata["selected_candidate_rank"] = run_summary.get("selected_candidate_rank")
    metadata["synthesis"] = synthesis_bundle.model_dump(mode="json")
    return selected_code, metadata


def run_generate(
    spec: ModuleSpec,
    *,
    lm: Optional[LMBase] = None,
    use_signature: bool = False,
    promotion_target: Optional[Path] = None,
) -> ModuleArtifact:
    """Generate a reusable dspy.Module skeleton from ModuleSpec.

    - Deterministic template-only path when `spec.options.template_version` starts with 'simple'.
    - If `use_signature=True`, embeds a generated Signature class above the Module and wires Predict.
    - LM-backed generation is reserved for future versions; current implementation focuses on templates.
    """
    import time as _time

    t0 = _time.time()
    budget_ms_env = _os.getenv("DSPX_BUDGET_MODULE_MS")
    budget_ms = (
        int(budget_ms_env) if budget_ms_env and budget_ms_env.isdigit() else None
    )
    tv = _template_version(spec)
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
                selected_code, metadata = _build_metadata(
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
        sig_code = None
        sig_name = None
        if use_signature:
            sig_name = _sig_class_name(spec.name)
            sig_code = render_simple_signature(
                sig_name,
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
        selected_code, meta = _build_metadata(
            spec,
            code=code,
            use_signature=use_signature,
            template_version=tv,
            promotion_target=promotion_target,
            base_metadata={
                "template_version": tv,
                "uses_signature": bool(use_signature),
            },
        )
        art = ModuleArtifact(name=spec.name, code=selected_code, metadata=meta)
        if cache_enabled():
            cache_write("module", key, {"code": art.code, "metadata": art.metadata})
        return art

    sig_code = None
    sig_name = None
    if use_signature:
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
    selected_code, metadata = _build_metadata(
        spec,
        code=code,
        use_signature=use_signature,
        template_version=tv,
        promotion_target=promotion_target,
        base_metadata={"uses_signature": bool(use_signature)},
    )
    art = ModuleArtifact(name=spec.name, code=selected_code, metadata=metadata)
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
    try:
        from dspx.tracing import ensure_run_with_standard_tags, get_mlflow

        mlflow = get_mlflow()
        if mlflow is not None:
            ensure_run_with_standard_tags(
                "module",
                template_version=tv or "v1",
                run_name=f"module-{spec.name}",
                run_kind="module-gen",
            )
            from dspx.cache import sha256_text

            if mlflow.active_run() is not None:
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
                        "template_version": tv or "v1",
                        "uses_signature": bool(use_signature),
                        "name": spec.name,
                        "inputs": inputs,
                        "outputs": outputs,
                    }
                    mlflow.log_dict(man, f"{spec.name}.manifest.json")
                except Exception:
                    pass
                duration_ms = (_time.time() - t0) * 1000.0
                metrics = {
                    "module.code_hash_prefix": int(sha256_text(art.code)[:8], 16)
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
    return art
