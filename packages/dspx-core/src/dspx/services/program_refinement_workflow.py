# summary: "Composes explicit local refinement or GEPA candidate materialization with behavior comparison and workflow receipts."
# read_when:
#   - "Changing generate-and-compare workflows, output overlap guards, comparison summaries, or GEPA workflow validation."
from __future__ import annotations

import hashlib
import json
import os
import stat
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
from dspx.services.program_runtime_episode import run_program_runtime_episode

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


def _runtime_inputs_sha256(runtime_episode_path: Path) -> str:
    try:
        payload = json.loads(runtime_episode_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProgramRefinementWorkflowError(
            "GEPA runtime comparison requires a valid runtime episode"
        ) from exc
    artifacts = payload.get("artifact_hashes") if isinstance(payload, Mapping) else None
    digest = (
        artifacts.get("runtime_inputs_sha256")
        if isinstance(artifacts, Mapping)
        else None
    )
    if not isinstance(digest, str) or len(digest) != 64:
        raise ProgramRefinementWorkflowError(
            "GEPA runtime episode is missing its runtime input hash"
        )
    return digest


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
    runtime_inputs_path: Path | None = None,
    source_runtime_episode_path: Path | None = None,
    candidate_runtime_outdir: Path | None = None,
) -> dict[str, Any]:
    """Materialize one GEPA candidate and compare behavior plus optional runtime evidence."""

    manifest_path = manifest_path.expanduser().resolve()
    gepa_result_path = gepa_result_path.expanduser().resolve()
    outdir = outdir.expanduser().resolve()
    comparison_out_path = comparison_out_path.expanduser().resolve()
    gepa_candidate_result_out = (
        gepa_candidate_result_out.expanduser().resolve()
        if gepa_candidate_result_out is not None
        else None
    )
    runtime_arguments = (
        runtime_inputs_path,
        source_runtime_episode_path,
        candidate_runtime_outdir,
    )
    if any(value is not None for value in runtime_arguments) and not all(
        value is not None for value in runtime_arguments
    ):
        raise ProgramRefinementWorkflowError(
            "GEPA runtime comparison requires runtime inputs, source episode, and candidate output together"
        )
    runtime_inputs_path = (
        runtime_inputs_path.expanduser().resolve()
        if runtime_inputs_path is not None
        else None
    )
    source_runtime_episode_path = (
        source_runtime_episode_path.expanduser().resolve()
        if source_runtime_episode_path is not None
        else None
    )
    candidate_runtime_outdir = (
        candidate_runtime_outdir.expanduser().resolve()
        if candidate_runtime_outdir is not None
        else None
    )
    if candidate_runtime_outdir is not None:
        assert runtime_inputs_path is not None
        assert source_runtime_episode_path is not None
        expected_runtime_inputs = (
            source_runtime_episode_path.parent / "runtime_inputs.json"
        )
        if runtime_inputs_path != expected_runtime_inputs:
            raise ProgramRefinementWorkflowError(
                "GEPA candidate runtime must reuse the source runtime episode inputs"
            )
        if candidate_runtime_outdir.exists() or candidate_runtime_outdir.is_symlink():
            raise ProgramRefinementWorkflowError(
                "GEPA candidate runtime output must not already exist"
            )
        for protected_root in (manifest_path.parent, outdir):
            if (
                candidate_runtime_outdir == protected_root
                or _is_relative_to(candidate_runtime_outdir, protected_root)
                or _is_relative_to(protected_root, candidate_runtime_outdir)
            ):
                raise ProgramRefinementWorkflowError(
                    "GEPA candidate runtime output must be disjoint from candidate roots"
                )
    assert_distinct_workflow_output_paths(
        artifact_label="program GEPA materialize-and-compare workflow",
        source_root=manifest_path.parent,
        outdir=outdir,
        comparison_out=comparison_out_path,
        gepa_candidate_result_out=gepa_candidate_result_out,
        candidate_runtime_outdir=candidate_runtime_outdir,
        runtime_inputs_input=runtime_inputs_path,
        source_runtime_episode_input=source_runtime_episode_path,
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
        candidate_runtime_episode_path: Path | None = None
        runtime_descriptor: int | None = None
        if candidate_runtime_outdir is not None:
            assert runtime_inputs_path is not None
            assert source_runtime_episode_path is not None
            parent_descriptor = os.open(
                candidate_runtime_outdir.parent,
                os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
            )
            try:
                os.mkdir(
                    candidate_runtime_outdir.name,
                    mode=0o700,
                    dir_fd=parent_descriptor,
                )
                runtime_root_before = os.stat(
                    candidate_runtime_outdir.name,
                    dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
                if not stat.S_ISDIR(runtime_root_before.st_mode):
                    raise ProgramRefinementWorkflowError(
                        "GEPA candidate runtime output must be a directory"
                    )
                source_inputs_sha256 = _runtime_inputs_sha256(
                    source_runtime_episode_path
                )
                if (
                    hashlib.sha256(runtime_inputs_path.read_bytes()).hexdigest()
                    != source_inputs_sha256
                ):
                    raise ProgramRefinementWorkflowError(
                        "GEPA source runtime inputs drifted from the source episode"
                    )
                runtime_descriptor = os.open(
                    candidate_runtime_outdir.name,
                    os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=parent_descriptor,
                )
                runtime = run_program_runtime_episode(
                    manifest_path=candidate_manifest_path,
                    inputs_path=runtime_inputs_path,
                    outdir=Path(f"/proc/self/fd/{runtime_descriptor}"),
                    skip_oracle_index=True,
                )
                runtime_root_after = os.stat(
                    candidate_runtime_outdir.name,
                    dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
                runtime_descriptor_after = os.fstat(runtime_descriptor)
                if (
                    not stat.S_ISDIR(runtime_root_after.st_mode)
                    or runtime_root_after.st_dev != runtime_root_before.st_dev
                    or runtime_root_after.st_ino != runtime_root_before.st_ino
                    or runtime_descriptor_after.st_dev != runtime_root_before.st_dev
                    or runtime_descriptor_after.st_ino != runtime_root_before.st_ino
                ):
                    raise ProgramRefinementWorkflowError(
                        "GEPA candidate runtime output identity changed during execution"
                    )
                if runtime.get("status") != "ok":
                    raise ProgramRefinementWorkflowError(
                        "GEPA candidate runtime evidence did not complete successfully"
                    )
                candidate_runtime_episode_path = Path(
                    f"/proc/self/fd/{runtime_descriptor}/runtime_episode.json"
                )
                if (
                    _runtime_inputs_sha256(candidate_runtime_episode_path)
                    != source_inputs_sha256
                ):
                    raise ProgramRefinementWorkflowError(
                        "GEPA source and candidate runtime inputs do not match"
                    )
            except Exception:
                if runtime_descriptor is not None:
                    os.close(runtime_descriptor)
                    runtime_descriptor = None
                raise
            finally:
                os.close(parent_descriptor)
        try:
            comparison = build_program_refinement_candidate_comparison(
                source_manifest_path=manifest_path,
                candidate_manifest_path=candidate_manifest_path,
                source_runtime_episode_path=source_runtime_episode_path,
                candidate_runtime_episode_path=candidate_runtime_episode_path,
            )
        finally:
            if runtime_descriptor is not None:
                os.close(runtime_descriptor)
        if candidate_runtime_episode_path is not None:
            assert candidate_runtime_outdir is not None
            runtime_comparison = comparison.get("runtime_evidence_comparison")
            created_from = comparison.get("created_from")
            recorded_runtime_path = (
                created_from.get("candidate_runtime_episode_path")
                if isinstance(created_from, Mapping)
                else None
            )
            expected_runtime_path = str(
                candidate_runtime_outdir / "runtime_episode.json"
            )
            if recorded_runtime_path != expected_runtime_path:
                raise ProgramRefinementWorkflowError(
                    "GEPA comparison candidate runtime path escaped its canonical root"
                )
            source_runtime = (
                runtime_comparison.get("source")
                if isinstance(runtime_comparison, Mapping)
                else None
            )
            candidate_runtime = (
                runtime_comparison.get("candidate")
                if isinstance(runtime_comparison, Mapping)
                else None
            )
            source_hashes = (
                source_runtime.get("artifact_hashes")
                if isinstance(source_runtime, Mapping)
                else None
            )
            candidate_hashes = (
                candidate_runtime.get("artifact_hashes")
                if isinstance(candidate_runtime, Mapping)
                else None
            )
            source_input_hash = (
                source_hashes.get("runtime_inputs_hash")
                if isinstance(source_hashes, Mapping)
                else None
            )
            candidate_input_hash = (
                candidate_hashes.get("runtime_inputs_hash")
                if isinstance(candidate_hashes, Mapping)
                else None
            )
            if (
                not isinstance(runtime_comparison, Mapping)
                or runtime_comparison.get("compared") is not True
                or not isinstance(source_input_hash, str)
                or source_input_hash != candidate_input_hash
            ):
                raise ProgramRefinementWorkflowError(
                    "GEPA comparison requires source and candidate runtime evidence over identical inputs"
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
            "Comparison uses current generated behavior evidence and, when supplied, validated source and candidate runtime episodes over identical inputs.",
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
