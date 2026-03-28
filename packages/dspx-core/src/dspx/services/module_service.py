from __future__ import annotations

from pathlib import Path
from typing import Any, Optional
import keyword
import re

from dspx.cache import (
    cache_enabled,
    make_key,
    read as cache_read,
    sha256_text,
    write as cache_write,
)
from dspx.coordinates.storage import get_default_index_path
from dspx.dtos import ModuleArtifact, ModuleSpec
from dspx.lm_base import LMBase
from dspx.services.module_synthesis_evidence import (
    ModuleSynthesisEvidenceRequest,
    build_module_synthesis_candidate_prior_audit,
    build_module_synthesis_candidate_prior_divergence_explanation,
    build_module_synthesis_candidate_prior_readiness_advisory,
    build_module_synthesis_candidate_winner_priors,
    build_module_synthesis_history_advisory,
    build_unavailable_module_synthesis_candidate_prior_audit,
    build_unavailable_module_synthesis_candidate_prior_divergence_explanation,
    build_unavailable_module_synthesis_candidate_prior_readiness_advisory,
    build_unavailable_module_synthesis_candidate_winner_priors,
    extract_module_synthesis_candidate_prior_inputs,
    extract_module_synthesis_ranked_candidate_comparison_inputs,
    extract_module_synthesis_ranked_candidate_inputs,
    retrieve_module_synthesis_evidence,
)
from dspx.services.module_synthesis_quality import (
    append_module_quality_event,
    build_module_quality_event_from_metadata,
)
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


_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_module_spec_identifiers(spec: ModuleSpec) -> None:
    seen: set[str] = set()
    invalid: list[str] = []

    for role, values in (("input", spec.inputs or []), ("output", spec.outputs or [])):
        for raw in values:
            name = str(raw).strip()
            if not name:
                invalid.append(f"{role}:<empty>")
                continue
            if not _IDENTIFIER_RE.match(name) or keyword.iskeyword(name):
                invalid.append(f"{role}:{name}")
                continue
            if name in seen:
                invalid.append(f"duplicate:{name}")
                continue
            seen.add(name)

    if invalid:
        detail = ", ".join(invalid)
        raise ValueError(
            "Module inputs/outputs must be unique Python identifiers; "
            f"invalid entries: {detail}"
        )


def _template_version(spec: ModuleSpec) -> Optional[str]:
    value = (
        (spec.options or {}).get("template_version")
        if hasattr(spec, "options")
        else None
    )
    if value is None:
        return None
    return value if isinstance(value, str) else str(value)


def _module_synthesis_evidence_receipts_path(
    promotion_target: Optional[Path],
) -> Optional[Path]:
    configured = _os.getenv("DSPX_MODULE_SYNTHESIS_EVIDENCE_RECEIPTS_PATH")
    if configured:
        return Path(configured)
    if promotion_target is not None:
        return promotion_target.parent
    return None


def _module_synthesis_evidence_oracle_index_path(
    promotion_target: Optional[Path],
) -> Optional[Path]:
    configured = _os.getenv("DSPX_MODULE_SYNTHESIS_EVIDENCE_ORACLE_INDEX_PATH")
    if configured:
        return Path(configured)
    if promotion_target is not None:
        parent = promotion_target.parent
        oracle_root = parent if parent.name == "generated" else (parent / "generated")
        return oracle_root / "oracle" / "coordinates.db"
    return get_default_index_path()


def _module_synthesis_evidence_oracle_top_k() -> int:
    raw = (_os.getenv("DSPX_MODULE_SYNTHESIS_EVIDENCE_ORACLE_TOP_K") or "").strip()
    if not raw:
        return 5
    try:
        return max(1, int(raw))
    except ValueError:
        return 5


def _module_cache_key(
    spec: ModuleSpec,
    *,
    use_signature: bool,
    template_version: Optional[str],
) -> str:
    return make_key(
        {
            "kind": "module",
            "name": spec.name,
            "description": spec.description or "",
            "inputs": list(spec.inputs or []),
            "outputs": list(spec.outputs or []),
            "use_signature": bool(use_signature),
            "template_version": template_version or "v1",
        }
    )


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
            inputs=inputs,
            outputs=outputs,
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


def _build_unavailable_synthesis_diagnostics(
    spec: ModuleSpec,
    *,
    use_signature: bool,
    promotion_target: Optional[Path],
    synthesis_payload: dict[str, Any] | None,
    selected_candidate_id: str | None,
    output_hash: str | None,
    cache_key: str | None,
    retrieval_error: dict[str, Any],
) -> dict[str, Any]:
    request = ModuleSynthesisEvidenceRequest.from_spec(
        spec,
        use_signature=use_signature,
    )
    receipts_path = (
        _module_synthesis_evidence_receipts_path(promotion_target)
        or (Path.cwd() / "generated")
    ).resolve()
    oracle_index_path = (
        _module_synthesis_evidence_oracle_index_path(promotion_target)
        or get_default_index_path()
    ).resolve()
    evidence_bundle = {
        "request": request.to_dict(),
        "retrieval_order": [
            "exact_match_receipts",
            "replay_verification",
            "oracle_neighbors",
        ],
        "exact_match_receipts": [],
        "oracle_neighbors": [],
        "receipts_path": str(receipts_path),
        "oracle_index_path": str(oracle_index_path),
        "receipts_scanned": 0,
        "oracle_query_text": request.oracle_query_text(),
        "receipt_scan_errors": [],
        "receipt_scan_error_count": 0,
        "exact_match_receipt_scan_errors": [],
        "exact_match_receipt_scan_error_count": 0,
        "oracle_lookup_status": "unavailable",
        "oracle_lookup_error": dict(retrieval_error),
        "oracle_index_available": False,
        "positive_evidence_count": 0,
    }
    current_candidates = extract_module_synthesis_candidate_prior_inputs(
        synthesis_payload
    )
    candidate_prior_audit = build_unavailable_module_synthesis_candidate_prior_audit(
        selected_candidate_id=selected_candidate_id,
        current_candidates=current_candidates,
        notes=["candidate-prior audit unavailable because evidence retrieval failed"],
    )
    candidate_prior_divergence_explanation = build_unavailable_module_synthesis_candidate_prior_divergence_explanation(
        candidate_prior_audit=candidate_prior_audit,
        notes=[
            "candidate-prior divergence explanation unavailable because evidence retrieval failed"
        ],
    )
    candidate_prior_readiness_advisory = build_unavailable_module_synthesis_candidate_prior_readiness_advisory(
        notes=[
            "candidate-prior readiness advisory unavailable because evidence retrieval failed"
        ],
    )
    return {
        "evidence_bundle_version": "v1",
        "retrieval_status": "unavailable",
        "retrieval_error": dict(retrieval_error),
        "evidence_summary": {
            "exact_match_receipt_count": 0,
            "positive_evidence_count": 0,
            "oracle_neighbor_count": 0,
            "oracle_index_available": False,
            "oracle_lookup_status": "unavailable",
            "receipt_scan_error_count": 0,
        },
        "evidence_bundle": evidence_bundle,
        "historical_convergence_advisory": {
            "advisory_version": "v1",
            "status": "unavailable",
            "selected_artifact": {
                "selected_candidate_id": selected_candidate_id,
                "output_hash": output_hash,
                "cache_key": cache_key,
            },
            "history_summary": {
                "exact_match_receipt_count": 0,
                "positive_evidence_count": 0,
                "oracle_neighbor_count": 0,
            },
            "matching_positive_receipts": [],
            "divergent_positive_receipts": [],
            "notes": ["evidence retrieval unavailable"],
        },
        "candidate_winner_priors": build_unavailable_module_synthesis_candidate_winner_priors(
            current_candidates=current_candidates,
            notes=[
                "candidate winner-prior payload unavailable because evidence retrieval failed"
            ],
        ),
        "candidate_prior_audit": candidate_prior_audit,
        "candidate_prior_divergence_explanation": (
            candidate_prior_divergence_explanation
        ),
        "candidate_prior_readiness_advisory": candidate_prior_readiness_advisory,
    }


def _build_synthesis_diagnostics(
    spec: ModuleSpec,
    *,
    use_signature: bool,
    promotion_target: Optional[Path],
    synthesis_payload: dict[str, Any] | None,
    selected_candidate_id: str | None,
    output_hash: str | None,
    cache_key: str | None,
) -> dict[str, Any]:
    try:
        evidence_bundle = retrieve_module_synthesis_evidence(
            spec,
            use_signature=use_signature,
            receipts_path=_module_synthesis_evidence_receipts_path(promotion_target),
            oracle_index_path=_module_synthesis_evidence_oracle_index_path(
                promotion_target
            ),
            oracle_top_k=_module_synthesis_evidence_oracle_top_k(),
        )
    except Exception as exc:
        return _build_unavailable_synthesis_diagnostics(
            spec,
            use_signature=use_signature,
            promotion_target=promotion_target,
            synthesis_payload=synthesis_payload,
            selected_candidate_id=selected_candidate_id,
            output_hash=output_hash,
            cache_key=cache_key,
            retrieval_error={
                "type": exc.__class__.__name__,
                "message": str(exc),
            },
        )

    payload = evidence_bundle.to_dict()
    current_candidates = extract_module_synthesis_candidate_prior_inputs(
        synthesis_payload
    )
    ranked_candidates = extract_module_synthesis_ranked_candidate_inputs(
        synthesis_payload
    )
    ranked_candidate_comparison_inputs = (
        extract_module_synthesis_ranked_candidate_comparison_inputs(synthesis_payload)
    )
    retrieval_status = (
        "degraded"
        if evidence_bundle.receipt_scan_error_count > 0
        or evidence_bundle.oracle_lookup_status == "unavailable"
        else "ok"
    )
    candidate_winner_priors = build_module_synthesis_candidate_winner_priors(
        evidence_bundle,
        current_candidates=current_candidates,
    )
    candidate_prior_audit = build_module_synthesis_candidate_prior_audit(
        candidate_winner_priors,
        current_candidates=current_candidates,
        ranked_candidates=ranked_candidates,
        selected_candidate_id=selected_candidate_id,
    )
    return {
        "evidence_bundle_version": "v1",
        "retrieval_status": retrieval_status,
        "evidence_summary": {
            "exact_match_receipt_count": len(evidence_bundle.exact_match_receipts),
            "positive_evidence_count": evidence_bundle.positive_evidence_count,
            "oracle_neighbor_count": len(evidence_bundle.oracle_neighbors),
            "oracle_index_available": evidence_bundle.oracle_index_available,
            "oracle_lookup_status": evidence_bundle.oracle_lookup_status,
            "receipt_scan_error_count": evidence_bundle.receipt_scan_error_count,
        },
        "evidence_bundle": payload,
        "historical_convergence_advisory": build_module_synthesis_history_advisory(
            evidence_bundle,
            selected_candidate_id=selected_candidate_id,
            output_hash=output_hash,
            cache_key=cache_key,
        ),
        "candidate_winner_priors": candidate_winner_priors,
        "candidate_prior_audit": candidate_prior_audit,
        "candidate_prior_divergence_explanation": (
            build_module_synthesis_candidate_prior_divergence_explanation(
                candidate_prior_audit,
                ranked_candidate_comparison_inputs=ranked_candidate_comparison_inputs,
            )
        ),
        "candidate_prior_readiness_advisory": (
            build_module_synthesis_candidate_prior_readiness_advisory(
                evidence_bundle,
            )
        ),
    }


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
    synthesis_payload = synthesis_bundle.model_dump(mode="json")
    metadata["synthesis"] = synthesis_payload
    selected_output_hash = sha256_text(selected_code)
    metadata["synthesis_diagnostics"] = _build_synthesis_diagnostics(
        spec,
        use_signature=use_signature,
        promotion_target=promotion_target,
        synthesis_payload=synthesis_payload,
        selected_candidate_id=(
            str(run_summary.get("selected_candidate_id"))
            if run_summary.get("selected_candidate_id") not in {None, ""}
            else None
        ),
        output_hash=selected_output_hash,
        cache_key=_module_cache_key(
            spec,
            use_signature=use_signature,
            template_version=template_version,
        ),
    )

    try:
        quality_event = build_module_quality_event_from_metadata(
            metadata,
            use_signature=use_signature,
            promotion_requested=promotion_target is not None,
            output_hash=selected_output_hash,
        )
        append_module_quality_event(quality_event.payload)
        metadata["quality_event"] = quality_event.payload
        metadata["quality_event_status"] = "ok"
    except Exception as exc:
        metadata["quality_event_status"] = "unavailable"
        metadata["quality_event_error"] = {
            "type": exc.__class__.__name__,
            "message": str(exc),
        }
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
    _validate_module_spec_identifiers(spec)

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
                inputs=inputs,
                outputs=outputs,
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
        sig_name = _sig_class_name(spec.name)
        sig_code = render_simple_signature(
            sig_name,
            desc or f"Signature for {spec.name}",
            inputs=inputs,
            outputs=outputs,
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
