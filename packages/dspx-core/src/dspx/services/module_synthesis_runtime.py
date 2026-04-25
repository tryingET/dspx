from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

from dspx.cache import sha256_text
from dspx.dtos import ModuleSpec
from dspx.services.module_artifacts import (
    candidate_sources,
    module_cache_key,
    selected_candidate_code,
)
from dspx.services.module_governance import (
    EvidenceRetriever,
    synthesis_diagnostics_for_artifact,
)
from dspx.services.module_synthesis_evidence import retrieve_module_synthesis_evidence
from dspx.services.module_synthesis_quality import (
    append_module_quality_event,
    build_module_quality_event_from_metadata,
)
from dspx.synthesis import execute_module_synthesis_bundle, module_synthesis_run_summary

QualityEventBuilder = Callable[..., Any]
QualityEventAppender = Callable[[dict[str, Any]], Any]


def build_module_metadata(
    spec: ModuleSpec,
    *,
    code: str,
    use_signature: bool,
    template_version: Optional[str],
    promotion_target: Optional[Path] = None,
    base_metadata: Optional[dict[str, Any]] = None,
    evidence_retriever: EvidenceRetriever = retrieve_module_synthesis_evidence,
    quality_event_builder: QualityEventBuilder = build_module_quality_event_from_metadata,
    quality_event_appender: QualityEventAppender = append_module_quality_event,
) -> tuple[str, dict[str, Any]]:
    metadata: dict[str, Any] = dict(base_metadata or {})
    if template_version is not None:
        metadata["template_version"] = template_version
    metadata["uses_signature"] = bool(use_signature)
    metadata["name"] = spec.name
    metadata["inputs"] = list(spec.inputs or [])
    metadata["outputs"] = list(spec.outputs or [])
    metadata["io_spec"] = {
        "inputs": list(spec.inputs or []),
        "outputs": list(spec.outputs or []),
    }
    metadata["local_controls"] = {
        "use_signature": bool(use_signature),
        "template_version": template_version,
        "cache_key": module_cache_key(
            spec,
            use_signature=use_signature,
            template_version=template_version,
        ),
    }

    sources = candidate_sources(
        spec,
        code=code,
        use_signature=use_signature,
        template_version=template_version,
    )
    synthesis_bundle = execute_module_synthesis_bundle(
        spec,
        code=code,
        candidate_sources=sources,
        use_signature=use_signature,
        promotion_target=promotion_target,
        strategy_metadata={
            "fan_out_kind": "deterministic_template_variants",
            "seed_template_version": template_version,
        },
    )
    selected_code = selected_candidate_code(synthesis_bundle, code)
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
    metadata["synthesis_diagnostics"] = synthesis_diagnostics_for_artifact(
        spec,
        code=selected_code,
        use_signature=use_signature,
        template_version=template_version,
        promotion_target=promotion_target,
        synthesis_payload=synthesis_payload,
        selected_candidate_id=(
            str(run_summary.get("selected_candidate_id"))
            if run_summary.get("selected_candidate_id") not in {None, ""}
            else None
        ),
        evidence_retriever=evidence_retriever,
    )

    try:
        quality_event = quality_event_builder(
            metadata,
            use_signature=use_signature,
            promotion_requested=promotion_target is not None,
            output_hash=selected_output_hash,
        )
        quality_event_appender(quality_event.payload)
        metadata["quality_event"] = quality_event.payload
        metadata["quality_event_status"] = "ok"
    except Exception as exc:
        metadata["quality_event_status"] = "unavailable"
        metadata["quality_event_error"] = {
            "type": exc.__class__.__name__,
            "message": str(exc),
        }
    return selected_code, metadata
