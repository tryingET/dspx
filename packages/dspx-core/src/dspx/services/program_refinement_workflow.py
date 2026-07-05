from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from dspx.services.artifact_boundary import prepare_sidecar_output_path
from dspx.services.program_refinement_candidate import materialize_refinement_candidate
from dspx.services.program_refinement_comparison import (
    build_program_refinement_candidate_comparison,
    write_program_refinement_candidate_comparison,
)
from dspx.services.program_refinement_gepa_candidate import (
    materialize_gepa_refinement_candidate,
)
from dspx.services.program_refinement_gepa_candidate_contracts import (
    validate_program_refinement_gepa_candidate_result_contract,
)

PROGRAM_REFINEMENT_GENERATE_COMPARE_SCHEMA = (
    "program-refinement-generate-and-compare-result-v1"
)
PROGRAM_REFINEMENT_GEPA_GENERATE_COMPARE_SCHEMA = (
    "program-refinement-gepa-generate-and-compare-result-v1"
)


_WORKFLOW_NON_AUTHORITY = {
    "local_generation_and_comparison_only": True,
    "program_gen_automation": False,
    "automatic_promotion": False,
    "oracle_ranking": False,
    "oracle_pruning": False,
    "oracle_promotion": False,
    "winner_selection": False,
    "external_authority_export": False,
    "governance_authority": False,
    "external_mutation": False,
}


_WORKFLOW_EFFECT = {
    "local_second_candidate_generated": True,
    "local_comparison_written": True,
    "source_program_files_mutated": False,
    "comparison_mutated_source_candidate": False,
    "comparison_mutated_refinement_candidate": False,
    "third_candidate_generated": False,
    "external_authority_mutated": False,
    "governance_mutated": False,
}


_GEPA_WORKFLOW_EFFECT = {
    "local_gepa_candidate_generated": True,
    "local_comparison_written": True,
    "source_program_files_mutated": False,
    "gepa_optimizer_output_mutated": False,
    "comparison_mutated_source_candidate": False,
    "comparison_mutated_gepa_candidate": False,
    "third_candidate_generated": False,
    "external_authority_mutated": False,
    "governance_mutated": False,
}


class ProgramRefinementWorkflowError(ValueError):
    """Raised when an explicit local refinement workflow fails."""


def _json_text(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _workflow_root_labels(paths: Mapping[str, Path]) -> dict[str, Path]:
    return {
        label: path
        for label, path in paths.items()
        if label == "outdir" or label.endswith("_outdir") or label.endswith("_root")
    }


def _workflow_input_labels(paths: Mapping[str, Path]) -> dict[str, Path]:
    return {label: path for label, path in paths.items() if label.endswith("_input")}


def assert_distinct_workflow_output_paths(
    *, artifact_label: str, **paths: Path | None
) -> None:
    """Fail closed when a composed workflow is asked to overlap outputs.

    File sidecars must be distinct from one another and must not be written into
    generated/source artifact roots that the workflow claims it does not mutate.
    """

    resolved: dict[str, Path] = {
        label: path.expanduser().resolve()
        for label, path in paths.items()
        if path is not None
    }
    protected_inputs = _workflow_input_labels(resolved)
    outputs = {
        label: path for label, path in resolved.items() if label not in protected_inputs
    }
    seen: dict[Path, str] = {}
    for label, path in outputs.items():
        previous = seen.get(path)
        if previous is not None:
            raise ProgramRefinementWorkflowError(
                f"{artifact_label} output paths must be distinct: {previous} and {label} both resolve to {path}"
            )
        seen[path] = label

    protected_roots = _workflow_root_labels(outputs)
    for label, path in outputs.items():
        for input_label, input_path in protected_inputs.items():
            if (
                path == input_path
                or _is_relative_to(path, input_path)
                or _is_relative_to(input_path, path)
            ):
                raise ProgramRefinementWorkflowError(
                    f"{artifact_label} {label} output path must not overlap "
                    f"protected input {input_label}: {path} vs {input_path}"
                )
        if label in protected_roots:
            continue
        for root_label, root in protected_roots.items():
            if path == root or _is_relative_to(path, root):
                raise ProgramRefinementWorkflowError(
                    f"{artifact_label} {label} output path must not be inside {root_label}: {path} under {root}"
                )


def materialize_and_compare_refinement_candidate(
    *,
    manifest_path: Path,
    refinement_proposal_path: Path,
    decision_record_path: Path,
    outdir: Path,
    comparison_out_path: Path,
) -> dict[str, Any]:
    """Explicitly generate one second candidate, then compare local behavior evidence."""

    manifest_path = manifest_path.expanduser().resolve()
    refinement_proposal_path = refinement_proposal_path.expanduser().resolve()
    decision_record_path = decision_record_path.expanduser().resolve()
    outdir = outdir.expanduser().resolve()
    comparison_out_path = comparison_out_path.expanduser().resolve()
    assert_distinct_workflow_output_paths(
        artifact_label="program refinement generate-and-compare workflow",
        source_root=manifest_path.parent,
        outdir=outdir,
        comparison_out=comparison_out_path,
    )
    try:
        generation = materialize_refinement_candidate(
            manifest_path=manifest_path,
            refinement_proposal_path=refinement_proposal_path,
            decision_record_path=decision_record_path,
            outdir=outdir,
        )
        candidate_manifest_path = (
            Path(str(generation["candidate"]["manifest_path"])).expanduser().resolve()
        )
        comparison = build_program_refinement_candidate_comparison(
            source_manifest_path=manifest_path,
            candidate_manifest_path=candidate_manifest_path,
            refinement_proposal_path=refinement_proposal_path,
            decision_record_path=decision_record_path,
        )
        comparison_payload = write_program_refinement_candidate_comparison(
            comparison,
            comparison_out_path,
        )
    except Exception as exc:
        raise ProgramRefinementWorkflowError(str(exc)) from exc

    status = (
        "materialized_and_compared"
        if comparison_payload.get("status") == "compared"
        else "materialized_with_insufficient_behavior_evidence"
    )
    return {
        "schema_version": PROGRAM_REFINEMENT_GENERATE_COMPARE_SCHEMA,
        "status": status,
        "created_from": {
            "manifest_path": str(manifest_path),
            "refinement_proposal_path": str(refinement_proposal_path),
            "decision_record_path": str(decision_record_path),
        },
        "generation": generation,
        "comparison_sidecar": {
            "path": str(comparison_out_path),
            "schema_version": comparison_payload.get("schema_version"),
            "status": comparison_payload.get("status"),
            "source_identity": comparison_payload.get("source_identity"),
            "candidate_identity": comparison_payload.get("candidate_identity"),
            "behavior_delta": comparison_payload.get("behavior_comparison", {}).get(
                "delta"
            ),
            "interpretation": comparison_payload.get("interpretation"),
        },
        "effect": dict(_WORKFLOW_EFFECT),
        "non_authority": dict(_WORKFLOW_NON_AUTHORITY),
        "notes": [
            "This explicit workflow materializes one local second candidate and writes one local comparison sidecar.",
            "It is not program-gen automation and does not rank, select a winner, promote, export authority, or mutate governance.",
            "Comparison uses current generated local behavior evidence: behavior_episode.json plus example-backed behavior_results.json when present.",
        ],
    }


def materialize_and_compare_gepa_refinement_candidate(
    *,
    manifest_path: Path,
    gepa_result_path: Path,
    outdir: Path,
    comparison_out_path: Path,
    gepa_candidate_result_out: Path | None = None,
) -> dict[str, Any]:
    """Explicitly materialize one GEPA candidate, then compare behavior evidence."""

    manifest_path = manifest_path.expanduser().resolve()
    gepa_result_path = gepa_result_path.expanduser().resolve()
    outdir = outdir.expanduser().resolve()
    comparison_out_path = comparison_out_path.expanduser().resolve()
    gepa_candidate_result_out = (
        gepa_candidate_result_out.expanduser().resolve()
        if gepa_candidate_result_out is not None
        else None
    )
    assert_distinct_workflow_output_paths(
        artifact_label="program GEPA materialize-and-compare workflow",
        source_root=manifest_path.parent,
        outdir=outdir,
        comparison_out=comparison_out_path,
        gepa_candidate_result_out=gepa_candidate_result_out,
        gepa_result_input=gepa_result_path,
    )
    try:
        generation = materialize_gepa_refinement_candidate(
            manifest_path=manifest_path,
            gepa_result_path=gepa_result_path,
            outdir=outdir,
            result_out=gepa_candidate_result_out,
        )
        candidate_manifest_path = (
            Path(str(generation["candidate"]["manifest_path"])).expanduser().resolve()
        )
        comparison = build_program_refinement_candidate_comparison(
            source_manifest_path=manifest_path,
            candidate_manifest_path=candidate_manifest_path,
        )
        comparison_payload = write_program_refinement_candidate_comparison(
            comparison,
            comparison_out_path,
        )
    except Exception as exc:
        raise ProgramRefinementWorkflowError(str(exc)) from exc

    status = (
        "materialized_and_compared_gepa_candidate"
        if comparison_payload.get("status") == "compared"
        else "materialized_gepa_candidate_with_insufficient_behavior_evidence"
    )
    return {
        "schema_version": PROGRAM_REFINEMENT_GEPA_GENERATE_COMPARE_SCHEMA,
        "status": status,
        "created_from": {
            "manifest_path": str(manifest_path),
            "gepa_refinement_result_path": str(gepa_result_path),
        },
        "generation": generation,
        "comparison_sidecar": {
            "path": str(comparison_out_path),
            "schema_version": comparison_payload.get("schema_version"),
            "status": comparison_payload.get("status"),
            "source_identity": comparison_payload.get("source_identity"),
            "candidate_identity": comparison_payload.get("candidate_identity"),
            "behavior_delta": comparison_payload.get("behavior_comparison", {}).get(
                "delta"
            ),
            "interpretation": comparison_payload.get("interpretation"),
        },
        "effect": dict(_GEPA_WORKFLOW_EFFECT),
        "non_authority": {
            **dict(_WORKFLOW_NON_AUTHORITY),
            "local_generation_and_comparison_only": False,
            "local_gepa_generation_and_comparison_only": True,
        },
        "notes": [
            "This explicit workflow materializes one local GEPA-backed candidate and writes one local comparison sidecar.",
            "It is not program-gen automation and does not rank, select a winner, promote, export authority, or mutate governance.",
            "Comparison uses current generated local behavior evidence: behavior_episode.json plus example-backed behavior_results.json when present.",
            "GEPA optimizer output is advisory local evidence, not approval or promotion authority.",
        ],
    }


def _workflow_protected_roots(payload: Mapping[str, Any]) -> list[Path]:
    roots: list[Path] = []
    created_from = payload.get("created_from")
    if isinstance(created_from, Mapping):
        for key in ("manifest_path", "source_manifest_path"):
            raw_path = created_from.get(key)
            if isinstance(raw_path, str) and raw_path.strip():
                roots.append(Path(raw_path).expanduser().resolve().parent)
    generation = payload.get("generation")
    candidate = generation.get("candidate") if isinstance(generation, Mapping) else None
    if isinstance(candidate, Mapping):
        raw_root = candidate.get("root_path")
        raw_manifest = candidate.get("manifest_path")
        if isinstance(raw_root, str) and raw_root.strip():
            roots.append(Path(raw_root).expanduser().resolve())
        elif isinstance(raw_manifest, str) and raw_manifest.strip():
            roots.append(Path(raw_manifest).expanduser().resolve().parent)
    return roots


def _validate_gepa_workflow_summary_payload(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != PROGRAM_REFINEMENT_GEPA_GENERATE_COMPARE_SCHEMA:
        return
    created_from = payload.get("created_from")
    if not isinstance(created_from, Mapping):
        raise ProgramRefinementWorkflowError(
            "program GEPA workflow summary is missing created_from"
        )
    generation = payload.get("generation")
    if not isinstance(generation, Mapping):
        raise ProgramRefinementWorkflowError(
            "program GEPA workflow summary is missing generation sidecar"
        )
    validate_program_refinement_gepa_candidate_result_contract(
        generation,
        expected_source_manifest_path=Path(
            str(created_from.get("manifest_path") or "")
        ),
        expected_gepa_result_path=Path(
            str(created_from.get("gepa_refinement_result_path") or "")
        ),
        label="program GEPA workflow generation summary",
        error_type=ProgramRefinementWorkflowError,
    )


def write_program_refinement_workflow_result(
    result: Mapping[str, Any],
    out_path: Path,
) -> dict[str, Any]:
    """Optionally write a local workflow receipt sidecar."""

    payload = dict(result)
    out_path = prepare_sidecar_output_path(
        out_path,
        payload=payload,
        artifact_label="program refinement workflow result",
        payload_artifact_root_policy="forbid",
        extra_protected_roots=_workflow_protected_roots(payload),
    )
    _validate_gepa_workflow_summary_payload(payload)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(_json_text(payload), encoding="utf-8")
    return payload
