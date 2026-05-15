from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Optional

from dspx.cache import cache_dir, cache_enabled, make_key, sha256_text
from dspx.generated_code_guard import isolated_subprocess_env
from dspx.run_receipts import (
    build_mlflow_hints,
    build_run_receipt,
    current_receipt_lineage,
    write_run_receipt,
)
from dspx.services.program_contracts import (
    intent_field_specs as _intent_field_specs,
    intent_surface_names as _intent_surface_names,
)
from dspx.services.program_intent import (
    ProgramArtifact,
    ProgramIntent,
    default_outdir as _default_outdir,
    load_program_intent,
)
from dspx.services.program_dataset import (
    SPLIT_NAMES,
    finalize_program_dataset_manifest,
    has_program_dataset,
    materialize_program_dataset_splits,
    render_dataset_split_eval_harness,
)
from dspx.services.program_jury import (
    build_jury_rubric,
    build_jury_selection,
    jury_plan_defaults as _jury_plan_defaults,
)
from dspx.services.program_module_surface import build_program_module_surfaces
from dspx.services.program_promotion import (
    build_promotion_adjudication_request,
    build_promotion_review,
)
from dspx.services.program_surfaces import (
    render_eval_behavior,
    render_eval_examples,
    render_eval_jury,
    render_eval_promotion,
    render_eval_smoke,
    render_module_surface,
    render_direct_run_code,
    render_program_code,
    render_signature_surface,
)
from dspx.services.program_topology import (
    PIPELINE_MATERIALIZED_STATUS,
    materialized_pipeline_topology,
    validate_materializable_pipeline_topology,
)


def _intent_payload(intent: ProgramIntent) -> dict[str, Any]:
    return intent.model_dump(mode="json", exclude_none=True)


def _json_text(payload: Mapping[str, Any] | list[Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _program_cache_file(cache_key: str) -> Path:
    path = cache_dir() / "program" / f"{cache_key}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _build_ids(intent: ProgramIntent, surface_bundle_text: str) -> dict[str, str]:
    payload = _intent_payload(intent)
    request_id = f"prog-req-{make_key({'intent': payload})[:12]}"
    candidate_id = f"prog-cand-{make_key({'request_id': request_id, 'code': surface_bundle_text})[:12]}"
    assembly_id = (
        f"prog-asm-{make_key({'candidate_id': candidate_id, 'intent': payload})[:12]}"
    )
    episode_id = (
        f"prog-ep-{make_key({'assembly_id': assembly_id, 'phase': 'materialize'})[:12]}"
    )
    receipt_bundle_id = f"prog-rb-{make_key({'episode_id': episode_id, 'code': surface_bundle_text})[:12]}"
    return {
        "request_id": request_id,
        "candidate_id": candidate_id,
        "assembly_id": assembly_id,
        "episode_id": episode_id,
        "receipt_bundle_id": receipt_bundle_id,
    }


def _examples_plan_metadata(
    intent: ProgramIntent, *, examples_hash: Optional[str]
) -> dict[str, Any]:
    if intent.examples_path:
        source = "examples_path"
    elif intent.examples:
        source = "inline"
    else:
        source = "none"
    return {
        "source": source,
        "count": len(intent.examples or []),
        "path": intent.examples_path,
        "hash": examples_hash,
    }


def _dataset_plan_metadata(intent: ProgramIntent) -> dict[str, Any]:
    if intent.dataset:
        split = dict(intent.dataset.get("split") or {})
        return {
            "source": "dataset_path",
            "path": intent.dataset.get("path"),
            "input_fields": list(intent.dataset.get("input_fields") or intent.inputs),
            "output_fields": list(
                intent.dataset.get("output_fields") or intent.outputs
            ),
            "split": {
                "strategy": split.get("strategy"),
                "train": split.get("train"),
                "validation": split.get("validation"),
                "test": split.get("test"),
                "seed": split.get("seed", 42),
            },
        }
    if intent.datasets:
        return {
            "source": "explicit_splits",
            "paths": {split: intent.datasets.get(split) for split in SPLIT_NAMES},
            "input_fields": list(intent.inputs),
            "output_fields": list(intent.outputs),
        }
    return {"source": "none"}


def _default_materialized_topology(intent: ProgramIntent) -> dict[str, Any]:
    names = _intent_surface_names(intent)
    return {
        "kind": "single_module",
        "execution_status": "single_module_scaffold_materialized",
        "modules": [
            {
                "id": "generated_module",
                "primitive": "Predict",
                "signature": {
                    "name": names["signature_class"],
                    "inputs": list(intent.inputs),
                    "outputs": list(intent.outputs),
                },
                "role": "Default generated single-module scaffold.",
                "name": names["module_class"],
                "module_class": names["module_class"],
            }
        ],
        "edges": [
            {"from": "input", "to": "generated_module"},
            {"from": "generated_module", "to": "output"},
        ],
    }


def _topology_plan_contract(intent: ProgramIntent) -> dict[str, Any]:
    declared_topology = dict(intent.topology or {})
    materialized_topology = _default_materialized_topology(intent)
    if declared_topology:
        topology = declared_topology
        if declared_topology.get("kind") == "pipeline":
            validate_materializable_pipeline_topology(intent)
            materialized_topology = materialized_pipeline_topology(intent)
            status = PIPELINE_MATERIALIZED_STATUS
            topology_materialized = True
            current_renderer = "pipeline_topology_renderer"
            notes = [
                "Explicit pipeline topology is preserved as declared input and rendered as a composed program.",
                "Only Predict and ChainOfThought module primitives plus simple when.field/equals routing are supported in this slice.",
                "No topology inference, broad graph engine, tools, retrievers, ReAct, or ProgramOfThought execution is performed.",
            ]
        else:
            status = str(
                declared_topology.get("execution_status") or "declared_not_materialized"
            )
            topology_materialized = False
            current_renderer = "single_module_scaffold"
            notes = [
                "Explicit topology is preserved as a planning contract.",
                "This slice only renders explicit pipeline topology; unsupported kinds remain declared-only.",
                "The generated Python remains the current single-module scaffold for this topology kind.",
            ]
    else:
        topology = materialized_topology
        status = str(materialized_topology["execution_status"])
        topology_materialized = True
        current_renderer = "single_module_scaffold"
        notes = [
            "No explicit topology was declared; program-gen used the existing single-module scaffold.",
        ]
    return {
        "topology": topology,
        "declared_topology": declared_topology or None,
        "materialized_topology": materialized_topology,
        "topology_execution_status": status,
        "materialization_scope": {
            "topology_declared": bool(declared_topology),
            "topology_materialized": topology_materialized,
            "current_renderer": current_renderer,
            "notes": notes,
        },
    }


def build_program_plan(
    intent: ProgramIntent, *, examples_hash: Optional[str] = None
) -> dict[str, Any]:
    """Build the deterministic ProgramPlan v1 contract from a ProgramIntent."""

    topology_contract = _topology_plan_contract(intent)
    has_examples = bool(intent.examples)
    has_dataset = has_program_dataset(intent)
    has_behavior_evidence = has_examples or has_dataset
    surfaces: list[dict[str, Any]] = [
        {"kind": "plan", "path": "plan.json", "generator": "program-gen"},
        {"kind": "jury", "path": "jury.json", "generator": "program-gen"},
        {
            "kind": "jury_selection",
            "path": "jury_selection.json",
            "generator": "program-gen",
        },
        {
            "kind": "jury_rubric",
            "path": "jury_rubric.json",
            "generator": "program-gen",
        },
        {
            "kind": "promotion_review",
            "path": "promotion_review.json",
            "generator": "program-gen",
        },
        {
            "kind": "promotion_adjudication_request",
            "path": "promotion_adjudication_request.json",
            "generator": "program-gen",
        },
        {
            "kind": "promotion_decision_template",
            "path": "promotion_decision_template.json",
            "generator": "program-gen",
        },
        {"kind": "intent", "path": "intent.json", "generator": "program-gen"},
        {
            "kind": "module_surfaces",
            "path": "module_surfaces.json",
            "generator": "program-gen",
        },
        {
            "kind": "execution_episode",
            "path": "execution_episode.json",
            "generator": "program-gen",
        },
        {"kind": "signature", "path": "signature.py", "generator": "signature-gen"},
        {"kind": "module", "path": "module.py", "generator": "module-gen"},
        {"kind": "program", "path": "program.py", "generator": "program-gen"},
        {"kind": "direct_runner", "path": "direct_run.py", "generator": "program-gen"},
        {"kind": "smoke_harness", "path": "eval_smoke.py", "generator": "program-gen"},
        {"kind": "jury_harness", "path": "eval_jury.py", "generator": "program-gen"},
        {
            "kind": "promotion_harness",
            "path": "eval_promotion.py",
            "generator": "program-gen",
        },
    ]
    if has_examples:
        surfaces.extend(
            [
                {
                    "kind": "examples",
                    "path": "examples.json",
                    "generator": "program-gen",
                },
                {
                    "kind": "examples_harness",
                    "path": "eval_examples.py",
                    "generator": "program-gen",
                },
                {
                    "kind": "behavior_results",
                    "path": "behavior_results.json",
                    "generator": "program-gen",
                },
            ]
        )
    if has_behavior_evidence:
        surfaces.extend(
            [
                {
                    "kind": "behavior_harness",
                    "path": "eval_behavior.py",
                    "generator": "program-gen",
                },
                {
                    "kind": "behavior_episode",
                    "path": "behavior_episode.json",
                    "generator": "program-gen",
                },
                {
                    "kind": "oracle_evidence",
                    "path": "oracle_evidence.json",
                    "generator": "program-gen",
                },
            ]
        )
    if has_dataset:
        dataset_surfaces: list[dict[str, Any]] = [
            {
                "kind": "dataset_manifest",
                "path": "dataset_manifest.json",
                "generator": "program-gen",
            }
        ]
        for split in SPLIT_NAMES:
            dataset_surfaces.extend(
                [
                    {
                        "kind": f"dataset_split_{split}",
                        "path": f"splits/{split}.jsonl",
                        "generator": "program-gen",
                    },
                    {
                        "kind": f"dataset_split_harness_{split}",
                        "path": f"eval_{split}.py",
                        "generator": "program-gen",
                    },
                    {
                        "kind": f"dataset_split_behavior_results_{split}",
                        "path": f"behavior_results.{split}.json",
                        "generator": "program-gen",
                    },
                ]
            )
        surfaces.extend(dataset_surfaces)
    return {
        "schema_version": "program-plan-v1",
        "intent": {
            "schema_version": intent.schema_version,
            "name": intent.name,
            "objective": intent.objective,
        },
        "task_type": intent.task_type or "single_module",
        "fields": {
            "inputs": _intent_field_specs(intent, role="input"),
            "outputs": _intent_field_specs(intent, role="output"),
        },
        "topology": topology_contract["topology"],
        "declared_topology": topology_contract["declared_topology"],
        "materialized_topology": topology_contract["materialized_topology"],
        "topology_execution_status": topology_contract["topology_execution_status"],
        "materialization_scope": topology_contract["materialization_scope"],
        "surfaces": surfaces,
        "metric": intent.metric or "unspecified",
        "runtime": dict(intent.runtime),
        "constraints": list(intent.constraints),
        "examples": _examples_plan_metadata(intent, examples_hash=examples_hash),
        "dataset": _dataset_plan_metadata(intent),
        "evaluation_strategy": _jury_plan_defaults(intent),
        "non_authority": {
            "candidate_assembly": "materialized_not_promoted",
            "program_gen_evidence": "non_authoritative",
            "oracle_role": "behavioral_interpreter_only",
            "ranking_pruning_promotion": False,
            "governance_authority": False,
        },
    }


def _write_json(path: Path, payload: Mapping[str, Any] | list[Any]) -> str:
    text = _json_text(payload)
    path.write_text(text, encoding="utf-8")
    return text


def _program_harness_timeout_seconds() -> float:
    raw = os.getenv("DSPX_PROGRAM_HARNESS_TIMEOUT", "60")
    try:
        return max(1.0, float(raw))
    except ValueError:
        return 60.0


def _run_python_harness(root: Path, filename: str, *, label: str) -> dict[str, Any]:
    source_root = Path(__file__).resolve().parents[2]
    env = isolated_subprocess_env()
    for key, value in os.environ.items():
        if key.startswith("DSPX_") or key.startswith("MLFLOW_"):
            env[key] = value
    existing_pythonpath = os.environ.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(source_root)
        if not existing_pythonpath
        else f"{source_root}{os.pathsep}{existing_pythonpath}"
    )
    proc = subprocess.run(
        [sys.executable, filename],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=_program_harness_timeout_seconds(),
        check=False,
        env=env,
    )
    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    result: dict[str, Any] = {
        "command": [sys.executable, filename],
        "returncode": proc.returncode,
        "stdout": stdout[-500:],
        "stderr": stderr[-500:],
    }
    if proc.returncode != 0:
        raise ValueError(
            f"program {label} failed: rc={proc.returncode} stderr={stderr[-240:]}"
        )
    return result


def _run_eval_smoke(root: Path) -> dict[str, Any]:
    return _run_python_harness(root, "eval_smoke.py", label="eval smoke")


def _run_eval_examples(root: Path) -> dict[str, Any]:
    return _run_python_harness(root, "eval_examples.py", label="examples validation")


def _behavior_results_has_retryable_codex_stream_error(
    payload: Mapping[str, Any],
) -> bool:
    summary = payload.get("summary")
    if not isinstance(summary, Mapping) or summary.get("status") != "error":
        return False
    examples = payload.get("examples")
    if not isinstance(examples, list) or not examples:
        return False
    for record in examples:
        if not isinstance(record, Mapping) or record.get("status") != "error":
            return False
        error = record.get("error")
        if not isinstance(error, Mapping):
            return False
        message = str(error.get("message") or "").casefold()
        if "stream must be set to true" not in message:
            return False
    return True


def _run_eval_dataset_split(root: Path, split: str) -> dict[str, Any]:
    return _run_python_harness(
        root, f"eval_{split}.py", label=f"dataset split {split} validation"
    )


def _run_eval_jury(root: Path) -> dict[str, Any]:
    return _run_python_harness(root, "eval_jury.py", label="jury validation")


def _run_eval_promotion(root: Path) -> dict[str, Any]:
    return _run_python_harness(root, "eval_promotion.py", label="promotion validation")


def _run_eval_behavior(root: Path) -> dict[str, Any]:
    return _run_python_harness(root, "eval_behavior.py", label="behavior orchestration")


def _safe_int(value: object, *, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return default
        try:
            return int(text)
        except ValueError:
            return default
    if isinstance(value, float):
        return int(value)
    return default


def _behavior_status_counts(
    behavior_results: Mapping[str, Any], behavior_summary: Mapping[str, Any]
) -> dict[str, int]:
    raw_counts = behavior_summary.get("status_counts")
    if isinstance(raw_counts, Mapping):
        return {
            str(status): _safe_int(count)
            for status, count in sorted(
                raw_counts.items(), key=lambda item: str(item[0])
            )
        }
    records = behavior_results.get("examples")
    counts: dict[str, int] = {}
    if isinstance(records, list):
        for raw_record in records:
            if not isinstance(raw_record, Mapping):
                continue
            status = str(raw_record.get("status") or "unknown")
            counts[status] = counts.get(status, 0) + 1
    return {status: counts[status] for status in sorted(counts)}


def _behavior_failure_modes(
    behavior_results: Mapping[str, Any], *, output_fields: list[str]
) -> list[dict[str, Any]]:
    records = behavior_results.get("examples")
    if not isinstance(records, list):
        return []
    failure_modes: list[dict[str, Any]] = []
    for raw_record in records:
        if not isinstance(raw_record, Mapping):
            continue
        record = dict(raw_record)
        status = str(record.get("status") or "unknown")
        raw_expected = record.get("expected_outputs")
        raw_observed = record.get("observed_outputs")
        expected = dict(raw_expected) if isinstance(raw_expected, Mapping) else {}
        observed = dict(raw_observed) if isinstance(raw_observed, Mapping) else {}
        compared_fields = [name for name in output_fields if name in observed]
        mismatched_outputs = sorted(
            name
            for name in compared_fields
            if str(expected.get(name, "")) != str(observed.get(name, ""))
        )
        missing_observed_outputs = sorted(
            name for name in output_fields if name not in observed
        )
        raw_notes = record.get("notes")
        notes = (
            [str(note) for note in raw_notes if str(note).strip()]
            if isinstance(raw_notes, list)
            else []
        )
        raw_error = record.get("error")
        error = dict(raw_error) if isinstance(raw_error, Mapping) else None
        signals: list[str] = []
        if status == "error" and error is not None:
            signals.append(f"error:{error.get('type') or 'unknown'}")
        if status.startswith("degraded"):
            signals.append(status)
        signals.extend(f"mismatch:{name}" for name in mismatched_outputs)
        signals.extend(f"missing_observed:{name}" for name in missing_observed_outputs)
        if notes:
            signals.extend(f"note:{note}" for note in notes)
        if status == "passed" and not signals:
            continue
        failure_mode: dict[str, Any] = {
            "index": record.get("index"),
            "status": status,
            "signals": signals,
            "mismatched_outputs": mismatched_outputs,
            "missing_observed_outputs": missing_observed_outputs,
            "notes": notes,
        }
        if error is not None:
            failure_mode["error"] = error
        failure_modes.append(failure_mode)
    return failure_modes


def _oracle_text(
    *,
    intent: ProgramIntent,
    ids: Mapping[str, str],
    oracle_facets: Mapping[str, Any],
    failure_modes: list[dict[str, Any]],
) -> str:
    status_counts = oracle_facets.get("status_counts")
    status_text = "none"
    if isinstance(status_counts, Mapping) and status_counts:
        status_text = ",".join(
            f"{status}:{status_counts[status]}" for status in sorted(status_counts)
        )
    source_kinds = oracle_facets.get("behavior_source_kinds")
    source_kind_text = "none"
    if isinstance(source_kinds, list) and source_kinds:
        source_kind_text = ",".join(str(kind) for kind in source_kinds)
    failure_text = "none"
    if failure_modes:
        failure_parts = []
        for failure in failure_modes[:10]:
            failure_parts.append(
                " ".join(
                    [
                        f"source={failure.get('source_kind') or 'examples'}",
                        f"split={failure.get('split') or 'none'}",
                        f"index={failure.get('index')}",
                        f"status={failure.get('status')}",
                        "mismatches="
                        + ",".join(failure.get("mismatched_outputs") or []),
                        "missing="
                        + ",".join(failure.get("missing_observed_outputs") or []),
                        "signals=" + ",".join(failure.get("signals") or []),
                    ]
                )
            )
        failure_text = "; ".join(failure_parts)
    return "\n".join(
        [
            "schema_version=program-oracle-evidence-v1",
            "evidence_kind=program_execution_episode",
            f"intent.name={intent.name}",
            f"intent.objective={intent.objective}",
            f"intent.task_type={intent.task_type or 'single_module'}",
            f"intent.metric={intent.metric or 'unspecified'}",
            "io.inputs=" + ",".join(intent.inputs),
            "io.outputs=" + ",".join(intent.outputs),
            "constraints=" + " | ".join(intent.constraints),
            f"identity.request_id={ids['request_id']}",
            f"identity.candidate_id={ids['candidate_id']}",
            f"identity.assembly_id={ids['assembly_id']}",
            f"identity.episode_id={ids['episode_id']}",
            f"identity.receipt_bundle_id={ids['receipt_bundle_id']}",
            f"behavior.status={oracle_facets.get('behavior_status')}",
            f"behavior.example_count={oracle_facets.get('example_count')}",
            f"behavior.total_evaluation_count={oracle_facets.get('total_evaluation_count')}",
            f"behavior.evidence_source_count={oracle_facets.get('evidence_source_count')}",
            f"behavior.source_kinds={source_kind_text}",
            f"behavior.status_counts={status_text}",
            f"behavior.failure_modes={failure_text}",
            "authority=oracle_readability_only_non_authoritative; "
            "oracle_ranking=false; oracle_pruning=false; oracle_promotion=false; "
            "governance_authority=false; external_mutation=false",
        ]
    )


def _oracle_source_artifacts(
    *,
    intent_hash: str,
    plan_hash: str,
    examples_hash: str | None,
    evaluation_sources: list[dict[str, Any]],
    surface_hashes: Mapping[str, str],
) -> list[dict[str, Any]]:
    source_artifacts: list[dict[str, Any]] = [
        {"kind": "intent", "path": "intent.json", "content_hash": intent_hash},
        {"kind": "plan", "path": "plan.json", "content_hash": plan_hash},
    ]
    if examples_hash is not None:
        source_artifacts.append(
            {"kind": "examples", "path": "examples.json", "content_hash": examples_hash}
        )
    for source in evaluation_sources:
        behavior_path = source.get("behavior_results_path")
        behavior_hash = source.get("behavior_results_hash")
        if behavior_path and behavior_hash:
            source_artifacts.append(
                {
                    "kind": "behavior_results",
                    "path": str(behavior_path),
                    "content_hash": str(behavior_hash),
                    "source_kind": source.get("source_kind"),
                    **({"split": source.get("split")} if source.get("split") else {}),
                }
            )
        source_path = source.get("source_artifact_path") or source.get(
            "input_artifact_path"
        )
        source_hash = source.get("source_artifact_hash") or source.get(
            "input_artifact_hash"
        )
        if source_path and source_hash:
            source_artifacts.append(
                {
                    "kind": str(source.get("kind") or "evaluation_source"),
                    "path": str(source_path),
                    "content_hash": str(source_hash),
                    "source_kind": source.get("source_kind"),
                    **({"split": source.get("split")} if source.get("split") else {}),
                }
            )
    for kind, path in (
        ("dataset_manifest", "dataset_manifest.json"),
        ("module_surfaces", "module_surfaces.json"),
        ("signature", "signature.py"),
        ("module", "module.py"),
        ("program", "program.py"),
    ):
        content_hash = surface_hashes.get(path)
        if content_hash:
            source_artifacts.append(
                {
                    "kind": kind,
                    "path": path,
                    "content_hash": content_hash,
                }
            )
    deduped: dict[tuple[str, str, str | None], dict[str, Any]] = {}
    for artifact in source_artifacts:
        key = (
            str(artifact.get("kind")),
            str(artifact.get("path")),
            str(artifact.get("split")) if artifact.get("split") else None,
        )
        deduped[key] = artifact
    return sorted(deduped.values(), key=lambda item: str(item["path"]))


def _source_failure_modes(
    *,
    evaluation_sources: list[dict[str, Any]],
    source_payloads: Mapping[str, Mapping[str, Any]],
    output_fields: list[str],
) -> list[dict[str, Any]]:
    failure_modes: list[dict[str, Any]] = []
    for source in evaluation_sources:
        behavior_path = source.get("behavior_results_path")
        if not behavior_path:
            continue
        payload = source_payloads.get(str(behavior_path))
        if payload is None:
            continue
        for failure in _behavior_failure_modes(payload, output_fields=output_fields):
            failure_modes.append(
                {
                    "source_kind": source.get("source_kind"),
                    "split": source.get("split"),
                    "behavior_results_path": behavior_path,
                    **failure,
                }
            )
    return failure_modes


def _build_oracle_evidence(
    *,
    intent: ProgramIntent,
    ids: Mapping[str, str],
    intent_hash: str,
    plan_hash: str,
    examples_hash: str | None,
    evaluation_sources: list[dict[str, Any]],
    behavior_evidence_summary: Mapping[str, Any],
    source_payloads: Mapping[str, Mapping[str, Any]],
    behavior_results_hash: str | None,
    behavior_summary: Mapping[str, Any] | None,
    surface_hashes: Mapping[str, str],
) -> dict[str, Any]:
    output_fields = list(intent.outputs)
    status_counts = {
        str(status): _safe_int(count)
        for status, count in dict(
            behavior_evidence_summary.get("status_counts") or {}
        ).items()
    }
    failure_modes = _source_failure_modes(
        evaluation_sources=evaluation_sources,
        source_payloads=source_payloads,
        output_fields=output_fields,
    )
    example_count = _safe_int(
        dict(behavior_summary or {}).get("total"), default=len(intent.examples or [])
    )
    total_evaluation_count = _safe_int(behavior_evidence_summary.get("total"))
    source_kinds = sorted(
        {
            str(source.get("source_kind"))
            for source in evaluation_sources
            if str(source.get("source_kind") or "").strip()
        }
    )
    dataset_split_count = sum(
        1 for source in evaluation_sources if source.get("kind") == "dataset_split"
    )
    behavior_status = str(behavior_evidence_summary.get("status") or "unknown")
    oracle_facets = {
        "task_type": intent.task_type or "single_module",
        "metric": intent.metric or "unspecified",
        "input_fields": list(intent.inputs),
        "output_fields": output_fields,
        "behavior_status": behavior_status,
        "status_counts": status_counts,
        "has_examples": bool(intent.examples),
        "example_count": example_count,
        "has_dataset_splits": dataset_split_count > 0,
        "dataset_split_count": dataset_split_count,
        "evidence_source_count": len(evaluation_sources),
        "behavior_source_kinds": source_kinds,
        "total_evaluation_count": total_evaluation_count,
        "failure_mode_count": len(failure_modes),
        "has_failures": bool(failure_modes),
    }
    oracle_text = _oracle_text(
        intent=intent,
        ids=ids,
        oracle_facets=oracle_facets,
        failure_modes=failure_modes,
    )
    source_artifacts = _oracle_source_artifacts(
        intent_hash=intent_hash,
        plan_hash=plan_hash,
        examples_hash=examples_hash,
        evaluation_sources=evaluation_sources,
        surface_hashes=surface_hashes,
    )
    return {
        "schema_version": "program-oracle-evidence-v1",
        "evidence_kind": "program_execution_episode",
        "authority": "oracle_readability_only_non_authoritative",
        "non_authority": {
            "oracle_ranking": False,
            "oracle_pruning": False,
            "oracle_promotion": False,
            "governance_authority": False,
            "external_mutation": False,
        },
        "identity": {
            "request_id": ids["request_id"],
            "candidate_id": ids["candidate_id"],
            "assembly_id": ids["assembly_id"],
            "episode_id": ids["episode_id"],
            "receipt_bundle_id": ids["receipt_bundle_id"],
        },
        "intent": {
            "name": intent.name,
            "objective": intent.objective,
            "task_type": intent.task_type or "single_module",
            "metric": intent.metric or "unspecified",
            "constraints": list(intent.constraints),
        },
        "io": {"inputs": list(intent.inputs), "outputs": output_fields},
        "behavior": {
            "result_path": "behavior_results.json" if behavior_results_hash else None,
            "result_hash": behavior_results_hash,
            "summary": dict(behavior_summary or {}),
            "statuses": _behavior_status_counts(
                source_payloads.get("behavior_results.json") or {},
                dict(behavior_summary or {}),
            )
            if behavior_summary is not None
            else {},
            "example_count": example_count,
            "evaluation_sources": evaluation_sources,
            "evidence_summary": dict(behavior_evidence_summary),
            "source_statuses": list(
                behavior_evidence_summary.get("source_statuses") or []
            ),
            "failure_modes": failure_modes,
        },
        "oracle_facets": oracle_facets,
        "oracle_text": oracle_text,
        "source_artifacts": source_artifacts,
    }


def _oracle_readability_summary(
    oracle_evidence: Mapping[str, Any], *, path: str, content_hash: str
) -> dict[str, Any]:
    facets = dict(oracle_evidence.get("oracle_facets") or {})
    oracle_text = str(oracle_evidence.get("oracle_text") or "")
    return {
        "schema_version": oracle_evidence.get("schema_version"),
        "evidence_kind": oracle_evidence.get("evidence_kind"),
        "authority": oracle_evidence.get("authority"),
        "path": path,
        "content_hash": content_hash,
        "behavior_status": facets.get("behavior_status"),
        "status_counts": facets.get("status_counts") or {},
        "example_count": facets.get("example_count"),
        "failure_mode_count": facets.get("failure_mode_count"),
        "has_failures": facets.get("has_failures"),
        "oracle_text_hash": sha256_text(oracle_text),
    }


def _harness_status(result: Mapping[str, Any] | None) -> str:
    if result is None:
        return "not_applicable"
    return "passed" if result.get("returncode") == 0 else "failed"


def _safe_summary_int(summary: Mapping[str, Any], key: str) -> int:
    value = summary.get(key)
    return value if isinstance(value, int) else 0


def _behavior_source_status(summary: Mapping[str, Any]) -> str:
    return str(summary.get("status") or "executed")


def _behavior_provider(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    if payload is None:
        return {}
    raw_provider = payload.get("provider")
    return dict(raw_provider) if isinstance(raw_provider, Mapping) else {}


def _build_behavior_evidence_summary(
    sources: list[dict[str, Any]],
) -> dict[str, Any]:
    if not sources:
        return {
            "status": "not_applicable",
            "source_count": 0,
            "executed_source_count": 0,
            "total": 0,
            "passed": 0,
            "failed": 0,
            "error": 0,
            "degraded": 0,
            "no_examples_source_count": 0,
            "status_counts": {},
            "source_statuses": [],
        }

    totals = {"total": 0, "passed": 0, "failed": 0, "error": 0, "degraded": 0}
    status_counts: dict[str, int] = {}
    source_statuses: list[dict[str, Any]] = []
    no_examples_source_count = 0
    for source in sources:
        summary = dict(source.get("summary") or {})
        status = _behavior_source_status(summary)
        status_counts[status] = status_counts.get(status, 0) + 1
        if status == "no_examples":
            no_examples_source_count += 1
        for key in totals:
            totals[key] += _safe_summary_int(summary, key)
        source_statuses.append(
            {
                "kind": source.get("kind"),
                "source_kind": source.get("source_kind"),
                "split": source.get("split"),
                "status": status,
                "count": source.get("count"),
                "behavior_results_path": source.get("behavior_results_path"),
            }
        )

    if totals["total"] == 0:
        aggregate_status = "no_examples"
    elif totals["error"] == totals["total"]:
        aggregate_status = "error"
    elif totals["failed"]:
        aggregate_status = "failed"
    elif totals["degraded"]:
        aggregate_status = "degraded"
    elif totals["passed"] == totals["total"]:
        aggregate_status = "passed"
    else:
        aggregate_status = "executed"

    return {
        "status": aggregate_status,
        "source_count": len(sources),
        "executed_source_count": len(sources) - no_examples_source_count,
        **totals,
        "no_examples_source_count": no_examples_source_count,
        "status_counts": status_counts,
        "source_statuses": source_statuses,
    }


def _build_evaluation_sources(
    *,
    intent: ProgramIntent,
    examples_hash: str | None,
    examples_result: Mapping[str, Any] | None,
    dataset_manifest_hash: str | None,
    dataset_manifest_payload: Mapping[str, Any] | None,
    dataset_split_results: Mapping[str, Mapping[str, Any]],
    dataset_split_behavior_payloads: Mapping[str, Mapping[str, Any]],
    dataset_split_behavior_hashes: Mapping[str, str],
    behavior_results_hash: str | None,
    behavior_summary: Mapping[str, Any] | None,
    behavior_results_payload: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    metric = intent.metric or "unspecified"
    if behavior_results_hash is not None:
        summary = dict(behavior_summary or {})
        sources.append(
            {
                "kind": "examples",
                "source_kind": "examples_path"
                if intent.examples_path
                else "inline_examples",
                "source_path": intent.examples_path,
                "input_artifact_path": "examples.json",
                "input_artifact_hash": examples_hash,
                "behavior_results_path": "behavior_results.json",
                "behavior_results_hash": behavior_results_hash,
                "status": _behavior_source_status(summary),
                "count": _safe_summary_int(summary, "total"),
                "summary": summary,
                "metric": metric,
                "provider": _behavior_provider(behavior_results_payload),
                "harness": {
                    "path": "eval_examples.py",
                    "status": _harness_status(examples_result),
                    "returncode": examples_result.get("returncode")
                    if examples_result is not None
                    else None,
                },
            }
        )

    dataset_artifacts = (
        dict(dataset_manifest_payload.get("artifacts") or {})
        if dataset_manifest_payload is not None
        else {}
    )
    for split in SPLIT_NAMES:
        behavior_hash = dataset_split_behavior_hashes.get(split)
        if behavior_hash is None:
            continue
        payload = dict(dataset_split_behavior_payloads.get(split) or {})
        summary = dict(payload.get("summary") or {})
        artifact = dict(dataset_artifacts.get(split) or {})
        split_path = str(artifact.get("path") or f"splits/{split}.jsonl")
        behavior_path = str(
            artifact.get("behavior_results") or f"behavior_results.{split}.json"
        )
        harness_path = str(artifact.get("eval_harness") or f"eval_{split}.py")
        sources.append(
            {
                "kind": "dataset_split",
                "source_kind": "dataset_split",
                "split": split,
                "source_path": split_path,
                "source_artifact_path": split_path,
                "source_artifact_hash": artifact.get("content_hash"),
                "dataset_manifest_path": "dataset_manifest.json",
                "dataset_manifest_hash": dataset_manifest_hash,
                "behavior_results_path": behavior_path,
                "behavior_results_hash": behavior_hash,
                "status": _behavior_source_status(summary),
                "count": _safe_summary_int(summary, "total"),
                "summary": summary,
                "metric": metric,
                "provider": _behavior_provider(payload),
                "harness": {
                    "path": harness_path,
                    "status": _harness_status(dataset_split_results.get(split)),
                    "returncode": dataset_split_results.get(split, {}).get(
                        "returncode"
                    ),
                },
            }
        )
    return sources


def _build_execution_episode_contract(
    *,
    ids: Mapping[str, str],
    intent: ProgramIntent,
    generated_file_names: list[str],
    smoke_result: Mapping[str, Any],
    jury_result: Mapping[str, Any],
    promotion_result: Mapping[str, Any],
    examples_result: Mapping[str, Any] | None,
    behavior_episode_result: Mapping[str, Any] | None,
    behavior_episode_hash: str | None,
    behavior_episode_payload: Mapping[str, Any] | None,
    examples_hash: str | None,
    dataset_manifest_hash: str | None,
    dataset_manifest_payload: Mapping[str, Any] | None,
    dataset_split_results: Mapping[str, Mapping[str, Any]],
    dataset_split_behavior_payloads: Mapping[str, Mapping[str, Any]],
    dataset_split_behavior_hashes: Mapping[str, str],
    behavior_results_hash: str | None,
    behavior_summary: Mapping[str, Any] | None,
    behavior_results_payload: Mapping[str, Any] | None,
    oracle_evidence_hash: str | None,
    oracle_readability_summary: Mapping[str, Any] | None,
    oracle_readability_facets: Mapping[str, Any] | None,
) -> dict[str, Any]:
    examples_count = len(intent.examples or [])
    dataset_artifacts = (
        dict(dataset_manifest_payload.get("artifacts") or {})
        if dataset_manifest_payload is not None
        else {}
    )
    behavior_status = None
    if behavior_summary is not None:
        behavior_status = str(behavior_summary.get("status") or "executed")
    behavioral_evaluation = {
        "status": behavior_status if behavior_status is not None else "not_applicable",
        "examples_count": examples_count,
        "result_artifact": "behavior_results.json"
        if behavior_results_hash is not None
        else None,
        "result_hash": behavior_results_hash,
        "summary": dict(behavior_summary or {}),
    }
    oracle_readability = {
        "status": "captured" if oracle_evidence_hash is not None else "not_applicable",
        "oracle_invoked": False,
        "result_artifact": "oracle_evidence.json"
        if oracle_evidence_hash is not None
        else None,
        "result_hash": oracle_evidence_hash,
        "summary": dict(oracle_readability_summary or {}),
        "facets": dict(oracle_readability_facets or {}),
    }
    evaluation_sources = _build_evaluation_sources(
        intent=intent,
        examples_hash=examples_hash,
        examples_result=examples_result,
        dataset_manifest_hash=dataset_manifest_hash,
        dataset_manifest_payload=dataset_manifest_payload,
        dataset_split_results=dataset_split_results,
        dataset_split_behavior_payloads=dataset_split_behavior_payloads,
        dataset_split_behavior_hashes=dataset_split_behavior_hashes,
        behavior_results_hash=behavior_results_hash,
        behavior_summary=behavior_summary,
        behavior_results_payload=behavior_results_payload,
    )
    behavior_evidence_summary = _build_behavior_evidence_summary(evaluation_sources)
    provider_conditions: dict[str, Any] = {}
    if behavior_results_payload is not None:
        provider_conditions["examples"] = _behavior_provider(behavior_results_payload)
    if dataset_split_behavior_payloads:
        provider_conditions["dataset_splits"] = {
            split: _behavior_provider(payload)
            for split, payload in dataset_split_behavior_payloads.items()
        }
    declared_topology = dict(intent.topology or {})
    if declared_topology.get("kind") == "pipeline":
        topology_execution = {
            "declared_topology_present": True,
            "declared_topology_kind": "pipeline",
            "materialized": True,
            "status": PIPELINE_MATERIALIZED_STATUS,
            "current_renderer": "pipeline_topology_renderer",
            "materialized_topology_kind": "pipeline",
            "notes": [
                "Explicit pipeline topology was rendered into signature.py, module.py, and program.py.",
                "Routing supports only simple when.field/equals clauses; no executable expressions are evaluated.",
            ],
        }
    else:
        topology_execution = {
            "declared_topology_present": bool(declared_topology),
            "declared_topology_kind": declared_topology.get("kind"),
            "materialized": not bool(declared_topology),
            "status": str(
                declared_topology.get("execution_status")
                or "single_module_scaffold_materialized"
            ),
            "current_renderer": "single_module_scaffold",
            "materialized_topology_kind": "single_module",
            "notes": [
                "Explicit topology is declared-only unless materialized is true.",
                "program.py delegates to the generated single module scaffold for non-pipeline topology kinds.",
            ],
        }
    return {
        "schema_version": "program-execution-episode-v1",
        "episode_id": ids["episode_id"],
        "request_id": ids["request_id"],
        "candidate_id": ids["candidate_id"],
        "assembly_id": ids["assembly_id"],
        "phase": "materialize",
        "evaluator": "deterministic_program_bundle_smoke",
        "status": "passed",
        "status_scope": "materialization_and_binding_checks",
        "authority": "execution_episode_evidence_only_non_authoritative",
        "runtime_conditions": {
            "runtime": dict(intent.runtime),
            "metric": intent.metric or "unspecified",
            "providers": provider_conditions,
        },
        "materialization": {
            "status": "passed",
            "generated_file_count": len(generated_file_names),
            "generated_files": list(generated_file_names),
        },
        "checks": {
            "compile": {
                "status": "passed",
                "files": [
                    name for name in generated_file_names if name.endswith(".py")
                ],
            },
            "smoke": {
                "status": _harness_status(smoke_result),
                "returncode": smoke_result.get("returncode"),
                "command": smoke_result.get("command"),
            },
            "examples_binding": {
                "status": _harness_status(examples_result),
                "examples_count": examples_count,
                "artifact_refs": ["examples.json", "eval_examples.py"]
                if examples_result is not None
                else [],
            },
            "dataset_binding": {
                "status": "passed"
                if dataset_manifest_payload is not None
                else "not_applicable",
                "dataset_manifest": "dataset_manifest.json"
                if dataset_manifest_payload is not None
                else None,
                "split_artifacts": {
                    split: {
                        "split_path": artifact.get("path"),
                        "eval_harness": artifact.get("eval_harness"),
                        "behavior_results": artifact.get("behavior_results"),
                        "record_count": artifact.get("record_count"),
                    }
                    for split, artifact in dataset_artifacts.items()
                    if isinstance(artifact, Mapping)
                },
            },
            "jury_binding": {
                "status": _harness_status(jury_result),
                "returncode": jury_result.get("returncode"),
                "artifact_refs": [
                    "jury.json",
                    "jury_selection.json",
                    "jury_rubric.json",
                    "eval_jury.py",
                ],
            },
            "promotion_binding": {
                "status": _harness_status(promotion_result),
                "returncode": promotion_result.get("returncode"),
                "artifact_refs": [
                    "promotion_review.json",
                    "promotion_adjudication_request.json",
                    "promotion_decision_template.json",
                    "eval_promotion.py",
                ],
            },
        },
        "behavior_status": behavior_status,
        "topology_execution": topology_execution,
        "evaluation_sources": evaluation_sources,
        "behavior_evidence_summary": behavior_evidence_summary,
        "behavior_orchestration": {
            "status": _harness_status(behavior_episode_result),
            "harness": "eval_behavior.py"
            if behavior_episode_result is not None
            else None,
            "returncode": behavior_episode_result.get("returncode")
            if behavior_episode_result is not None
            else None,
            "result_artifact": "behavior_episode.json"
            if behavior_episode_hash is not None
            else None,
            "result_hash": behavior_episode_hash,
            "summary": dict(dict(behavior_episode_payload or {}).get("summary") or {}),
        },
        "behavioral_evaluation": behavioral_evaluation,
        "behavior_results": {
            "path": "behavior_results.json",
            "content_hash": behavior_results_hash,
            "summary": dict(behavior_summary or {}),
        }
        if behavior_results_hash is not None
        else None,
        "dataset_evaluation": {
            "status": "captured"
            if dataset_manifest_payload is not None
            else "not_applicable",
            "dataset_manifest": {
                "path": "dataset_manifest.json",
                "content_hash": dataset_manifest_hash,
                "schema_version": dataset_manifest_payload.get("schema_version"),
            }
            if dataset_manifest_payload is not None
            else None,
            "split_results": {
                split: {
                    "harness": dict(dataset_split_results.get(split) or {}),
                    "behavior_results_path": dataset_artifacts.get(split, {}).get(
                        "behavior_results"
                    )
                    if isinstance(dataset_artifacts.get(split), Mapping)
                    else None,
                    "behavior_results_hash": dataset_split_behavior_hashes.get(split),
                    "summary": dict(
                        dataset_split_behavior_payloads.get(split, {}).get("summary")
                        or {}
                    ),
                }
                for split in SPLIT_NAMES
            },
        },
        "oracle_readability": oracle_readability,
        "oracle_evidence": {
            "path": "oracle_evidence.json",
            "content_hash": oracle_evidence_hash,
            "summary": dict(oracle_readability_summary or {}),
            "facets": dict(oracle_readability_facets or {}),
        }
        if oracle_evidence_hash is not None
        else None,
        "non_authority": {
            "evidence_only": True,
            "oracle_role": "not_invoked",
            "oracle_ranking": False,
            "oracle_pruning": False,
            "oracle_promotion": False,
            "ranking_pruning_promotion": False,
            "promotion_authority": False,
            "oracle_authority": False,
            "winner_selection": False,
            "automatic_promotion": False,
            "governance_authority": False,
            "ak_mutation": False,
            "governance_mutation": False,
            "external_mutation": False,
            "external_authority_mutated": False,
        },
        "metadata": {
            "smoke": dict(smoke_result),
            "jury": dict(jury_result),
            "promotion": dict(promotion_result),
            **(
                {"examples": dict(examples_result)}
                if examples_result is not None
                else {}
            ),
            **(
                {"behavior_episode": dict(behavior_episode_payload)}
                if behavior_episode_payload is not None
                else {}
            ),
            **(
                {
                    "dataset": {
                        "manifest": dict(dataset_manifest_payload),
                        "split_harnesses": {
                            split: dict(result)
                            for split, result in dataset_split_results.items()
                        },
                        "split_behavior_results": {
                            split: dict(payload)
                            for split, payload in dataset_split_behavior_payloads.items()
                        },
                    }
                }
                if dataset_manifest_payload is not None
                else {}
            ),
            **(
                {"behavior_results": dict(behavior_results_payload)}
                if behavior_results_payload is not None
                else {}
            ),
        },
        "notes": [
            "Materialization, binding checks, behavioral evaluation, and Oracle readability are separate episode sections.",
            "eval_examples.py is the example-backed behavior harness when examples exist.",
            "Oracle readability is captured without invoking Oracle or mutating an index.",
            "This artifact is evidence only and cannot rank, prune, promote, export, or mutate governance authority.",
        ],
    }


def materialize_program_from_intent(
    intent: ProgramIntent,
    *,
    outdir: Optional[Path] = None,
    intent_source: Optional[Path] = None,
) -> ProgramArtifact:
    """Materialize a runnable program-shaped candidate assembly from one intent."""

    root = (
        (outdir if outdir is not None else _default_outdir(intent))
        .expanduser()
        .resolve()
    )
    root.mkdir(parents=True, exist_ok=True)

    signature_code, signature_metadata = render_signature_surface(intent)
    module_code, module_metadata = render_module_surface(intent)
    program_code = render_program_code(intent)
    direct_run_code = render_direct_run_code(intent)
    eval_smoke_code = render_eval_smoke(intent)
    eval_jury_code = render_eval_jury()
    eval_promotion_code = render_eval_promotion()
    has_behavior_evidence = bool(intent.examples) or has_program_dataset(intent)
    eval_behavior_code = render_eval_behavior(intent) if has_behavior_evidence else None
    dataset_eval_codes = {
        split: render_dataset_split_eval_harness(split)
        for split in SPLIT_NAMES
        if has_program_dataset(intent)
    }
    examples_payload = list(intent.examples or [])
    examples_text = _json_text(examples_payload) if examples_payload else None
    examples_hash = sha256_text(examples_text) if examples_text is not None else None
    module_surfaces_payload = build_program_module_surfaces(intent)
    module_surfaces_text = _json_text(module_surfaces_payload)
    program_plan = build_program_plan(intent, examples_hash=examples_hash)
    jury_payload = dict(program_plan["evaluation_strategy"])
    jury_selection = build_jury_selection(jury_payload)
    jury_rubric = build_jury_rubric(intent, jury_selection)
    promotion_review = build_promotion_review(
        intent,
        has_examples=bool(examples_payload),
        jury_selection=jury_selection,
        jury_rubric=jury_rubric,
        has_behavior_results=bool(examples_payload),
    )
    promotion_adjudication_request = build_promotion_adjudication_request(
        promotion_review
    )
    promotion_decision_template = dict(
        promotion_adjudication_request["decision_record_template"]
    )
    plan_text = _json_text(program_plan)
    jury_text = _json_text(jury_payload)
    jury_selection_text = _json_text(jury_selection)
    jury_rubric_text = _json_text(jury_rubric)
    promotion_review_text = _json_text(promotion_review)
    promotion_adjudication_request_text = _json_text(promotion_adjudication_request)
    promotion_decision_template_text = _json_text(promotion_decision_template)
    plan_hash = sha256_text(plan_text)
    module_surfaces_hash = sha256_text(module_surfaces_text)
    jury_hash = sha256_text(jury_text)
    jury_selection_hash = sha256_text(jury_selection_text)
    jury_rubric_hash = sha256_text(jury_rubric_text)
    promotion_review_hash = sha256_text(promotion_review_text)
    promotion_adjudication_request_hash = sha256_text(
        promotion_adjudication_request_text
    )
    promotion_decision_template_hash = sha256_text(promotion_decision_template_text)
    eval_examples_code = render_eval_examples(intent) if examples_payload else None
    bundle_parts = [
        plan_text,
        jury_text,
        jury_selection_text,
        jury_rubric_text,
        promotion_review_text,
        promotion_adjudication_request_text,
        promotion_decision_template_text,
        module_surfaces_text,
        signature_code,
        module_code,
        program_code,
        direct_run_code,
        eval_smoke_code,
        eval_jury_code,
        eval_promotion_code,
    ]
    if eval_examples_code is not None:
        bundle_parts.append(eval_examples_code)
    bundle_parts.extend(
        dataset_eval_codes[split] for split in sorted(dataset_eval_codes)
    )
    if eval_behavior_code is not None:
        bundle_parts.append(eval_behavior_code)
    surface_bundle_text = "\n\n".join(bundle_parts)
    ids = _build_ids(intent, surface_bundle_text)
    intent_payload = _intent_payload(intent)
    intent_hash = sha256_text(json.dumps(intent_payload, sort_keys=True))
    surface_hashes = {
        "plan.json": plan_hash,
        "jury.json": jury_hash,
        "jury_selection.json": jury_selection_hash,
        "jury_rubric.json": jury_rubric_hash,
        "promotion_review.json": promotion_review_hash,
        "promotion_adjudication_request.json": promotion_adjudication_request_hash,
        "promotion_decision_template.json": promotion_decision_template_hash,
        "module_surfaces.json": module_surfaces_hash,
        "signature.py": sha256_text(signature_code),
        "module.py": sha256_text(module_code),
        "program.py": sha256_text(program_code),
        "direct_run.py": sha256_text(direct_run_code),
        "eval_smoke.py": sha256_text(eval_smoke_code),
        "eval_jury.py": sha256_text(eval_jury_code),
        "eval_promotion.py": sha256_text(eval_promotion_code),
    }
    if eval_examples_code is not None:
        surface_hashes["eval_examples.py"] = sha256_text(eval_examples_code)
    for split, code in dataset_eval_codes.items():
        surface_hashes[f"eval_{split}.py"] = sha256_text(code)
    if eval_behavior_code is not None:
        surface_hashes["eval_behavior.py"] = sha256_text(eval_behavior_code)
    program_hash = surface_hashes["program.py"]
    assembly_hash = sha256_text(surface_bundle_text)

    generated_files = {
        "signature.py": signature_code,
        "module.py": module_code,
        "program.py": program_code,
        "direct_run.py": direct_run_code,
        "eval_smoke.py": eval_smoke_code,
        "eval_jury.py": eval_jury_code,
        "eval_promotion.py": eval_promotion_code,
    }
    if eval_examples_code is not None:
        generated_files["eval_examples.py"] = eval_examples_code
    for split, code in dataset_eval_codes.items():
        generated_files[f"eval_{split}.py"] = code
    if eval_behavior_code is not None:
        generated_files["eval_behavior.py"] = eval_behavior_code
    for relative, content in generated_files.items():
        compile(content, str(root / relative), "exec")
        (root / relative).write_text(content, encoding="utf-8")

    (root / "plan.json").write_text(plan_text, encoding="utf-8")
    (root / "jury.json").write_text(jury_text, encoding="utf-8")
    (root / "jury_selection.json").write_text(jury_selection_text, encoding="utf-8")
    (root / "jury_rubric.json").write_text(jury_rubric_text, encoding="utf-8")
    (root / "promotion_review.json").write_text(promotion_review_text, encoding="utf-8")
    (root / "promotion_adjudication_request.json").write_text(
        promotion_adjudication_request_text, encoding="utf-8"
    )
    (root / "promotion_decision_template.json").write_text(
        promotion_decision_template_text, encoding="utf-8"
    )
    (root / "module_surfaces.json").write_text(module_surfaces_text, encoding="utf-8")
    _write_json(root / "intent.json", intent_payload)
    if examples_text is not None:
        (root / "examples.json").write_text(examples_text, encoding="utf-8")
    dataset_manifest_payload = materialize_program_dataset_splits(
        intent,
        root=root,
        intent_source=intent_source,
    )
    smoke_result = _run_eval_smoke(root)
    jury_result = _run_eval_jury(root)
    promotion_result = _run_eval_promotion(root)
    examples_result = _run_eval_examples(root) if examples_payload else None
    behavior_episode_result = (
        _run_eval_behavior(root) if eval_behavior_code is not None else None
    )
    behavior_episode_payload: dict[str, Any] | None = None
    behavior_episode_hash: str | None = None
    if eval_behavior_code is not None:
        behavior_episode_path = root / "behavior_episode.json"
        if not behavior_episode_path.exists():
            raise ValueError(
                "program behavior harness did not write behavior_episode.json"
            )
        behavior_episode_text = behavior_episode_path.read_text(encoding="utf-8")
        behavior_episode_hash = sha256_text(behavior_episode_text)
        surface_hashes["behavior_episode.json"] = behavior_episode_hash
        raw_behavior_episode = json.loads(behavior_episode_text)
        if isinstance(raw_behavior_episode, dict):
            behavior_episode_payload = raw_behavior_episode
    dataset_split_results: dict[str, dict[str, Any]] = {}
    dataset_split_behavior_payloads: dict[str, dict[str, Any]] = {}
    dataset_split_behavior_hashes: dict[str, str] = {}
    dataset_manifest_hash: str | None = None
    if dataset_manifest_payload is not None:
        for split in SPLIT_NAMES:
            dataset_split_results[split] = _run_eval_dataset_split(root, split)
            behavior_path = root / f"behavior_results.{split}.json"
            if not behavior_path.exists():
                raise ValueError(
                    f"program dataset split harness did not write {behavior_path.name}"
                )
            behavior_text = behavior_path.read_text(encoding="utf-8")
            dataset_split_behavior_hashes[split] = sha256_text(behavior_text)
            raw_payload = json.loads(behavior_text)
            if isinstance(raw_payload, dict):
                dataset_split_behavior_payloads[split] = raw_payload
        dataset_manifest_payload, dataset_manifest_hash = (
            finalize_program_dataset_manifest(
                dataset_manifest_payload,
                root=root,
            )
        )
        surface_hashes["dataset_manifest.json"] = dataset_manifest_hash
        dataset_artifacts = dict(dataset_manifest_payload.get("artifacts") or {})
        for split in SPLIT_NAMES:
            split_artifact = dict(dataset_artifacts.get(split) or {})
            split_path = str(split_artifact.get("path") or f"splits/{split}.jsonl")
            behavior_path = str(
                split_artifact.get("behavior_results")
                or f"behavior_results.{split}.json"
            )
            surface_hashes[split_path] = str(split_artifact.get("content_hash"))
            surface_hashes[behavior_path] = dataset_split_behavior_hashes[split]
    behavior_results_payload: dict[str, Any] | None = None
    behavior_results_hash: str | None = None
    behavior_summary: dict[str, Any] | None = None
    oracle_evidence_payload: dict[str, Any] | None = None
    oracle_evidence_hash: str | None = None
    oracle_readability_summary: dict[str, Any] | None = None
    oracle_readability_facets: dict[str, Any] | None = None
    if examples_payload:
        behavior_results_path = root / "behavior_results.json"
        if not behavior_results_path.exists():
            raise ValueError(
                "program examples harness did not write behavior_results.json"
            )
        behavior_results_text = behavior_results_path.read_text(encoding="utf-8")
        raw_behavior_payload = json.loads(behavior_results_text)
        if isinstance(
            raw_behavior_payload, dict
        ) and _behavior_results_has_retryable_codex_stream_error(raw_behavior_payload):
            examples_result = _run_eval_examples(root)
            behavior_results_text = behavior_results_path.read_text(encoding="utf-8")
            raw_behavior_payload = json.loads(behavior_results_text)
        behavior_results_hash = sha256_text(behavior_results_text)
        surface_hashes["behavior_results.json"] = behavior_results_hash
        if isinstance(raw_behavior_payload, dict):
            behavior_results_payload = raw_behavior_payload
            raw_summary = behavior_results_payload.get("summary")
            if isinstance(raw_summary, dict):
                behavior_summary = dict(raw_summary)
    evaluation_sources = _build_evaluation_sources(
        intent=intent,
        examples_hash=examples_hash,
        examples_result=examples_result,
        dataset_manifest_hash=dataset_manifest_hash,
        dataset_manifest_payload=dataset_manifest_payload,
        dataset_split_results=dataset_split_results,
        dataset_split_behavior_payloads=dataset_split_behavior_payloads,
        dataset_split_behavior_hashes=dataset_split_behavior_hashes,
        behavior_results_hash=behavior_results_hash,
        behavior_summary=behavior_summary,
        behavior_results_payload=behavior_results_payload,
    )
    behavior_evidence_summary = _build_behavior_evidence_summary(evaluation_sources)
    source_payloads: dict[str, Mapping[str, Any]] = {}
    if behavior_results_payload is not None:
        source_payloads["behavior_results.json"] = behavior_results_payload
    for split, payload in dataset_split_behavior_payloads.items():
        source_payloads[f"behavior_results.{split}.json"] = payload
    if evaluation_sources:
        oracle_evidence_payload = _build_oracle_evidence(
            intent=intent,
            ids=ids,
            intent_hash=intent_hash,
            plan_hash=plan_hash,
            examples_hash=examples_hash,
            evaluation_sources=evaluation_sources,
            behavior_evidence_summary=behavior_evidence_summary,
            source_payloads=source_payloads,
            behavior_results_hash=behavior_results_hash,
            behavior_summary=behavior_summary,
            surface_hashes=surface_hashes,
        )
        oracle_evidence_text = _write_json(
            root / "oracle_evidence.json", oracle_evidence_payload
        )
        oracle_evidence_hash = sha256_text(oracle_evidence_text)
        surface_hashes["oracle_evidence.json"] = oracle_evidence_hash
        oracle_readability_summary = _oracle_readability_summary(
            oracle_evidence_payload,
            path="oracle_evidence.json",
            content_hash=oracle_evidence_hash,
        )
        oracle_readability_facets = dict(oracle_evidence_payload["oracle_facets"])
    dataset_generated_file_names: list[str] = []
    if dataset_manifest_payload is not None:
        dataset_generated_file_names.append("dataset_manifest.json")
        dataset_artifacts_for_names = dict(
            dataset_manifest_payload.get("artifacts") or {}
        )
        for split in SPLIT_NAMES:
            artifact = dict(dataset_artifacts_for_names.get(split) or {})
            dataset_generated_file_names.extend(
                [
                    str(artifact.get("path") or f"splits/{split}.jsonl"),
                    str(
                        artifact.get("behavior_results")
                        or f"behavior_results.{split}.json"
                    ),
                ]
            )
    generated_file_names = sorted(
        [
            *generated_files.keys(),
            *dataset_generated_file_names,
            "plan.json",
            "jury.json",
            "jury_selection.json",
            "jury_rubric.json",
            "promotion_review.json",
            "promotion_adjudication_request.json",
            "promotion_decision_template.json",
            "module_surfaces.json",
            "intent.json",
            *(["examples.json", "behavior_results.json"] if examples_payload else []),
            *(["behavior_episode.json"] if behavior_episode_hash is not None else []),
            *(["oracle_evidence.json"] if oracle_evidence_hash is not None else []),
            "execution_episode.json",
            "manifest.json",
        ]
    )
    execution_episode = _build_execution_episode_contract(
        ids=ids,
        intent=intent,
        generated_file_names=generated_file_names,
        smoke_result=smoke_result,
        jury_result=jury_result,
        promotion_result=promotion_result,
        examples_result=examples_result,
        behavior_episode_result=behavior_episode_result,
        behavior_episode_hash=behavior_episode_hash,
        behavior_episode_payload=behavior_episode_payload,
        examples_hash=examples_hash,
        dataset_manifest_hash=dataset_manifest_hash,
        dataset_manifest_payload=dataset_manifest_payload,
        dataset_split_results=dataset_split_results,
        dataset_split_behavior_payloads=dataset_split_behavior_payloads,
        dataset_split_behavior_hashes=dataset_split_behavior_hashes,
        behavior_results_hash=behavior_results_hash,
        behavior_summary=behavior_summary,
        behavior_results_payload=behavior_results_payload,
        oracle_evidence_hash=oracle_evidence_hash,
        oracle_readability_summary=oracle_readability_summary,
        oracle_readability_facets=oracle_readability_facets,
    )
    execution_episode_text = _write_json(
        root / "execution_episode.json", execution_episode
    )
    execution_episode_hash = sha256_text(execution_episode_text)
    surface_hashes["execution_episode.json"] = execution_episode_hash
    topology_execution = dict(execution_episode["topology_execution"])

    dataset_candidate_surfaces: list[dict[str, Any]] = []
    dataset_evidence: dict[str, Any] | None = None
    if dataset_manifest_payload is not None and dataset_manifest_hash is not None:
        dataset_artifacts = dict(dataset_manifest_payload.get("artifacts") or {})
        dataset_candidate_surfaces.append(
            {
                "kind": "dataset_manifest",
                "path": "dataset_manifest.json",
                "generator": "program-gen",
                "content_hash": dataset_manifest_hash,
                "schema_version": dataset_manifest_payload["schema_version"],
                "status": dataset_manifest_payload["status"],
            }
        )
        split_evidence: dict[str, dict[str, Any]] = {}
        for split in SPLIT_NAMES:
            artifact = dict(dataset_artifacts.get(split) or {})
            split_path = str(artifact.get("path") or f"splits/{split}.jsonl")
            harness_path = str(artifact.get("eval_harness") or f"eval_{split}.py")
            behavior_path = str(
                artifact.get("behavior_results") or f"behavior_results.{split}.json"
            )
            dataset_candidate_surfaces.extend(
                [
                    {
                        "kind": f"dataset_split_{split}",
                        "path": split_path,
                        "generator": "program-gen",
                        "content_hash": surface_hashes[split_path],
                        "record_count": artifact.get("record_count"),
                    },
                    {
                        "kind": f"dataset_split_harness_{split}",
                        "path": harness_path,
                        "generator": "program-gen",
                        "content_hash": surface_hashes[harness_path],
                    },
                    {
                        "kind": f"dataset_split_behavior_results_{split}",
                        "path": behavior_path,
                        "generator": "program-gen",
                        "content_hash": surface_hashes[behavior_path],
                        "schema_version": "program-behavior-results-v1",
                        "summary": dict(
                            dataset_split_behavior_payloads.get(split, {}).get(
                                "summary"
                            )
                            or {}
                        ),
                    },
                ]
            )
            split_evidence[split] = {
                "split_path": split_path,
                "split_hash": surface_hashes[split_path],
                "record_count": artifact.get("record_count"),
                "eval_harness": harness_path,
                "eval_harness_hash": surface_hashes[harness_path],
                "behavior_results_path": behavior_path,
                "behavior_results_hash": surface_hashes[behavior_path],
                "summary": dict(
                    dataset_split_behavior_payloads.get(split, {}).get("summary") or {}
                ),
            }
        dataset_evidence = {
            "dataset_manifest_path": "dataset_manifest.json",
            "dataset_manifest_hash": dataset_manifest_hash,
            "split_artifacts": split_evidence,
        }

    candidate_assembly = {
        "assembly_id": ids["assembly_id"],
        "request_id": ids["request_id"],
        "candidate_id": ids["candidate_id"],
        "artifact_kind": "program",
        "surface_kinds": [
            "plan",
            "jury",
            "jury_selection",
            "jury_rubric",
            "promotion_review",
            "promotion_adjudication_request",
            "promotion_decision_template",
            "intent",
            "module_surfaces",
            "execution_episode",
            *(["examples", "behavior_results"] if examples_payload else []),
            *(
                ["behavior_harness", "behavior_episode", "oracle_evidence"]
                if eval_behavior_code is not None
                else []
            ),
            *(
                [
                    "dataset_manifest",
                    "dataset_split",
                    "dataset_split_harness",
                    "dataset_split_behavior_results",
                ]
                if dataset_manifest_payload is not None
                else []
            ),
            "signature",
            "module",
            "program",
            "direct_runner",
            "eval_harness",
            "jury_harness",
            "promotion_harness",
        ],
        "root_path": str(root),
        "entrypoint": "program.py",
        "content_hash": assembly_hash,
        "status": "materialized",
        "surfaces": [
            {
                "kind": "plan",
                "path": "plan.json",
                "generator": "program-gen",
                "content_hash": surface_hashes["plan.json"],
                "schema_version": program_plan["schema_version"],
            },
            {
                "kind": "jury",
                "path": "jury.json",
                "generator": "program-gen",
                "content_hash": surface_hashes["jury.json"],
                "schema_version": jury_payload["schema_version"],
            },
            {
                "kind": "jury_selection",
                "path": "jury_selection.json",
                "generator": "program-gen",
                "content_hash": surface_hashes["jury_selection.json"],
                "schema_version": jury_selection["schema_version"],
                "status": jury_selection["status"],
            },
            {
                "kind": "jury_rubric",
                "path": "jury_rubric.json",
                "generator": "program-gen",
                "content_hash": surface_hashes["jury_rubric.json"],
                "schema_version": jury_rubric["schema_version"],
            },
            {
                "kind": "promotion_review",
                "path": "promotion_review.json",
                "generator": "program-gen",
                "content_hash": surface_hashes["promotion_review.json"],
                "schema_version": promotion_review["schema_version"],
                "promotion_state": promotion_review["promotion_state"],
            },
            {
                "kind": "promotion_adjudication_request",
                "path": "promotion_adjudication_request.json",
                "generator": "program-gen",
                "content_hash": surface_hashes["promotion_adjudication_request.json"],
                "schema_version": promotion_adjudication_request["schema_version"],
                "status": promotion_adjudication_request["status"],
            },
            {
                "kind": "promotion_decision_template",
                "path": "promotion_decision_template.json",
                "generator": "program-gen",
                "content_hash": surface_hashes["promotion_decision_template.json"],
                "schema_version": promotion_decision_template["schema_version"],
                "status": promotion_decision_template["status"],
            },
            {
                "kind": "module_surfaces",
                "path": "module_surfaces.json",
                "generator": "program-gen",
                "content_hash": surface_hashes["module_surfaces.json"],
                "schema_version": module_surfaces_payload["schema_version"],
                "status": module_surfaces_payload["status"],
                "module_surface_count": module_surfaces_payload["module_surface_count"],
            },
            {
                "kind": "execution_episode",
                "path": "execution_episode.json",
                "generator": "program-gen",
                "content_hash": surface_hashes["execution_episode.json"],
                "schema_version": execution_episode["schema_version"],
                "status": execution_episode["status"],
            },
            *dataset_candidate_surfaces,
            {
                "kind": "signature",
                "path": "signature.py",
                "generator": "signature-gen",
                "content_hash": surface_hashes["signature.py"],
                "metadata": signature_metadata,
            },
            {
                "kind": "module",
                "path": "module.py",
                "generator": "module-gen",
                "content_hash": surface_hashes["module.py"],
                "metadata": module_metadata,
            },
            {
                "kind": "program",
                "path": "program.py",
                "generator": "program-gen",
                "content_hash": surface_hashes["program.py"],
            },
            {
                "kind": "direct_runner",
                "path": "direct_run.py",
                "generator": "program-gen",
                "content_hash": surface_hashes["direct_run.py"],
            },
            {
                "kind": "eval_harness",
                "path": "eval_smoke.py",
                "generator": "program-gen",
                "content_hash": surface_hashes["eval_smoke.py"],
            },
            {
                "kind": "jury_harness",
                "path": "eval_jury.py",
                "generator": "program-gen",
                "content_hash": surface_hashes["eval_jury.py"],
            },
            {
                "kind": "promotion_harness",
                "path": "eval_promotion.py",
                "generator": "program-gen",
                "content_hash": surface_hashes["eval_promotion.py"],
            },
            *(
                [
                    {
                        "kind": "examples_harness",
                        "path": "eval_examples.py",
                        "generator": "program-gen",
                        "content_hash": surface_hashes["eval_examples.py"],
                    },
                    {
                        "kind": "behavior_results",
                        "path": "behavior_results.json",
                        "generator": "program-gen",
                        "content_hash": surface_hashes["behavior_results.json"],
                        "schema_version": "program-behavior-results-v1",
                        "summary": behavior_summary or {},
                    },
                ]
                if eval_examples_code is not None
                else []
            ),
            *(
                [
                    {
                        "kind": "behavior_harness",
                        "path": "eval_behavior.py",
                        "generator": "program-gen",
                        "content_hash": surface_hashes["eval_behavior.py"],
                    },
                    {
                        "kind": "behavior_episode",
                        "path": "behavior_episode.json",
                        "generator": "program-gen",
                        "content_hash": surface_hashes["behavior_episode.json"],
                        "schema_version": "program-behavior-episode-v1",
                        "summary": dict(
                            dict(behavior_episode_payload or {}).get("summary") or {}
                        ),
                    },
                    {
                        "kind": "oracle_evidence",
                        "path": "oracle_evidence.json",
                        "generator": "program-gen",
                        "content_hash": surface_hashes["oracle_evidence.json"],
                        "schema_version": "program-oracle-evidence-v1",
                        "summary": oracle_readability_summary or {},
                        "facets": oracle_readability_facets or {},
                    },
                ]
                if eval_behavior_code is not None and oracle_evidence_hash is not None
                else []
            ),
        ],
    }
    receipt_bundle = {
        "receipt_bundle_id": ids["receipt_bundle_id"],
        "request_id": ids["request_id"],
        "candidate_id": ids["candidate_id"],
        "assembly_id": ids["assembly_id"],
        "episode_id": ids["episode_id"],
        "status": "captured",
        "evidence": {
            "intent_hash": intent_hash,
            "plan_hash": plan_hash,
            "jury_hash": jury_hash,
            "jury_selection_hash": jury_selection_hash,
            "jury_rubric_hash": jury_rubric_hash,
            "promotion_review_hash": promotion_review_hash,
            "promotion_adjudication_request_hash": promotion_adjudication_request_hash,
            "promotion_decision_template_hash": promotion_decision_template_hash,
            "module_surfaces_hash": module_surfaces_hash,
            "module_surfaces_path": "module_surfaces.json",
            "execution_episode_hash": execution_episode_hash,
            "execution_episode_path": "execution_episode.json",
            "topology_execution": topology_execution,
            "program_hash": program_hash,
            "assembly_hash": assembly_hash,
            "surface_hashes": surface_hashes,
            **({"examples_hash": examples_hash} if examples_hash is not None else {}),
            **(
                {"behavior_results_hash": behavior_results_hash}
                if behavior_results_hash is not None
                else {}
            ),
            **(
                {
                    "behavior_episode_hash": behavior_episode_hash,
                    "behavior_episode_path": "behavior_episode.json",
                }
                if behavior_episode_hash is not None
                else {}
            ),
            **(
                {
                    "oracle_evidence_hash": oracle_evidence_hash,
                    "oracle_evidence_path": "oracle_evidence.json",
                    "oracle_readability_summary": oracle_readability_summary,
                    "oracle_readability_facets": oracle_readability_facets,
                }
                if oracle_evidence_hash is not None
                else {}
            ),
            **({"dataset": dataset_evidence} if dataset_evidence is not None else {}),
            **(
                {"dataset_manifest_hash": dataset_manifest_hash}
                if dataset_manifest_hash is not None
                else {}
            ),
            "surface_generation": {
                "plan": "program-gen",
                "jury": "program-gen",
                "jury_selection": "program-gen",
                "jury_rubric": "program-gen",
                "promotion_review": "program-gen",
                "promotion_adjudication_request": "program-gen",
                "promotion_decision_template": "program-gen",
                "module_surfaces": "program-gen",
                "execution_episode": "program-gen",
                "signature": "signature-gen",
                "module": "module-gen",
                "program": "program-gen",
                "direct_runner": "program-gen",
                "eval_harness": "program-gen",
                "jury_harness": "program-gen",
                "promotion_harness": "program-gen",
                **(
                    {
                        "examples_harness": "program-gen",
                        "behavior_results": "program-gen",
                    }
                    if examples_result is not None
                    else {}
                ),
                **(
                    {
                        "behavior_harness": "program-gen",
                        "behavior_episode": "program-gen",
                        "oracle_evidence": "program-gen",
                    }
                    if behavior_episode_hash is not None
                    else {}
                ),
                **(
                    {
                        "dataset_manifest": "program-gen",
                        "dataset_split": "program-gen",
                        "dataset_split_harness": "program-gen",
                        "dataset_split_behavior_results": "program-gen",
                    }
                    if dataset_evidence is not None
                    else {}
                ),
            },
            "generated_files": generated_file_names,
            "smoke": smoke_result,
            "jury": jury_result,
            "promotion": promotion_result,
            **({"examples": examples_result} if examples_result is not None else {}),
            **(
                {"behavior_episode": behavior_episode_payload}
                if behavior_episode_payload is not None
                else {}
            ),
            **(
                {
                    "dataset_manifest": dataset_manifest_payload,
                    "dataset_split_results": dataset_split_results,
                    "dataset_split_behavior_results": dataset_split_behavior_payloads,
                }
                if dataset_manifest_payload is not None
                else {}
            ),
            **(
                {"behavior_results": behavior_results_payload}
                if behavior_results_payload is not None
                else {}
            ),
            **(
                {"behavior_summary": behavior_summary}
                if behavior_summary is not None
                else {}
            ),
            **(
                {
                    "oracle_readability": {
                        "path": "oracle_evidence.json",
                        "content_hash": oracle_evidence_hash,
                        "summary": oracle_readability_summary,
                        "facets": oracle_readability_facets,
                    }
                }
                if oracle_evidence_hash is not None
                else {}
            ),
        },
    }

    manifest = {
        "schema_version": "program-candidate-assembly-v1",
        "request": {
            "request_id": ids["request_id"],
            "source_command": "program-gen",
            "goal": intent.objective,
            "intent_source": str(intent_source.expanduser().resolve())
            if intent_source is not None
            else None,
            "intent_hash": intent_hash,
            "plan_hash": plan_hash,
            "jury_hash": jury_hash,
            "jury_selection_hash": jury_selection_hash,
            "jury_rubric_hash": jury_rubric_hash,
            "promotion_review_hash": promotion_review_hash,
            "promotion_adjudication_request_hash": promotion_adjudication_request_hash,
            "promotion_decision_template_hash": promotion_decision_template_hash,
            "module_surfaces_hash": module_surfaces_hash,
            "execution_episode_hash": execution_episode_hash,
            "dataset_manifest_hash": dataset_manifest_hash,
            "dataset_split_behavior_results_hashes": dict(
                dataset_split_behavior_hashes
            ),
            "behavior_results_hash": behavior_results_hash,
            "behavior_episode_hash": behavior_episode_hash,
            "oracle_evidence_hash": oracle_evidence_hash,
        },
        "intent": intent_payload,
        "program_plan": program_plan,
        "program_jury_selection": jury_selection,
        "program_jury_rubric": jury_rubric,
        "program_promotion_review": promotion_review,
        "program_promotion_adjudication_request": promotion_adjudication_request,
        "program_promotion_decision_template": promotion_decision_template,
        "program_module_surfaces": module_surfaces_payload,
        "module_surfaces_artifact": {
            "path": "module_surfaces.json",
            "content_hash": module_surfaces_hash,
            "schema_version": module_surfaces_payload["schema_version"],
        },
        "execution_episode_artifact": {
            "path": "execution_episode.json",
            "content_hash": execution_episode_hash,
            "schema_version": execution_episode["schema_version"],
        },
        "behavior_episode_artifact": {
            "path": "behavior_episode.json",
            "content_hash": behavior_episode_hash,
            "schema_version": "program-behavior-episode-v1",
        }
        if behavior_episode_hash is not None
        else None,
        "dataset_manifest": dataset_manifest_payload,
        "dataset_manifest_artifact": {
            "path": "dataset_manifest.json",
            "content_hash": dataset_manifest_hash,
            "schema_version": dataset_manifest_payload["schema_version"],
        }
        if dataset_manifest_payload is not None and dataset_manifest_hash is not None
        else None,
        "dataset_split_evidence": dataset_evidence,
        "topology_execution": topology_execution,
        "oracle_readability": {
            "path": "oracle_evidence.json",
            "content_hash": oracle_evidence_hash,
            "summary": oracle_readability_summary,
            "facets": oracle_readability_facets,
        }
        if oracle_evidence_hash is not None
        else None,
        "candidate_assembly": candidate_assembly,
        "execution_episode": execution_episode,
        "receipt_bundle": receipt_bundle,
    }
    manifest_path = root / "manifest.json"
    manifest_text = _write_json(manifest_path, manifest)
    manifest_hash = sha256_text(manifest_text)

    cache_key = make_key({"kind": "program", "intent": intent_payload})
    cache_file = _program_cache_file(cache_key)
    cache_is_enabled = cache_enabled()
    if cache_is_enabled:
        _write_json(
            cache_file,
            {
                "code": manifest_text,
                "manifest": manifest,
                "intent": intent_payload,
                "kind": "program",
            },
        )

    receipt = build_run_receipt(
        run_kind="program-gen",
        output_path=manifest_path,
        output_hash=manifest_hash,
        template_version="program-candidate-assembly-v1",
        cache_key=cache_key,
        cache_file=str(cache_file),
        cache_enabled=cache_is_enabled,
        replay_inputs={"intent": intent_payload},
        run_summary={
            "backend": "program_candidate_assembly",
            "assembly_id": ids["assembly_id"],
            "episode_id": ids["episode_id"],
            "receipt_bundle_id": ids["receipt_bundle_id"],
            "plan_hash": plan_hash,
            "jury_hash": jury_hash,
            "jury_selection_hash": jury_selection_hash,
            "jury_rubric_hash": jury_rubric_hash,
            "promotion_review_hash": promotion_review_hash,
            "promotion_adjudication_request_hash": promotion_adjudication_request_hash,
            "promotion_decision_template_hash": promotion_decision_template_hash,
            "module_surfaces_hash": module_surfaces_hash,
            "module_surfaces_path": "module_surfaces.json",
            "execution_episode_hash": execution_episode_hash,
            "execution_episode_path": "execution_episode.json",
            "dataset_manifest_hash": dataset_manifest_hash,
            "dataset_manifest_path": "dataset_manifest.json"
            if dataset_manifest_hash is not None
            else None,
            "dataset_split_evidence": dataset_evidence,
            "topology_execution": topology_execution,
            "behavior_results_hash": behavior_results_hash,
            "behavior_summary": behavior_summary,
            "behavior_episode_hash": behavior_episode_hash,
            "behavior_episode_path": "behavior_episode.json"
            if behavior_episode_hash is not None
            else None,
            "oracle_evidence_hash": oracle_evidence_hash,
            "oracle_readability_summary": oracle_readability_summary,
            "oracle_readability_facets": oracle_readability_facets,
            "generated_files": generated_file_names,
        },
        extra={
            "program_intent": intent_payload,
            "program_plan": program_plan,
            "program_jury_selection": jury_selection,
            "program_jury_rubric": jury_rubric,
            "program_promotion_review": promotion_review,
            "program_promotion_adjudication_request": promotion_adjudication_request,
            "program_promotion_decision_template": promotion_decision_template,
            "program_module_surfaces": module_surfaces_payload,
            "program_module_surfaces_artifact": {
                "path": "module_surfaces.json",
                "content_hash": module_surfaces_hash,
                "schema_version": module_surfaces_payload["schema_version"],
            },
            "program_execution_episode_artifact": {
                "path": "execution_episode.json",
                "content_hash": execution_episode_hash,
                "schema_version": execution_episode["schema_version"],
            },
            **(
                {
                    "program_behavior_episode_artifact": {
                        "path": "behavior_episode.json",
                        "content_hash": behavior_episode_hash,
                        "schema_version": "program-behavior-episode-v1",
                    }
                }
                if behavior_episode_hash is not None
                else {}
            ),
            **(
                {
                    "program_dataset_manifest": dataset_manifest_payload,
                    "program_dataset_manifest_artifact": {
                        "path": "dataset_manifest.json",
                        "content_hash": dataset_manifest_hash,
                        "schema_version": dataset_manifest_payload["schema_version"],
                    },
                    "program_dataset_split_evidence": dataset_evidence,
                }
                if dataset_manifest_payload is not None
                and dataset_manifest_hash is not None
                else {}
            ),
            "program_topology_execution": topology_execution,
            **(
                {"program_behavior_results": behavior_results_payload}
                if behavior_results_payload is not None
                else {}
            ),
            **(
                {"program_behavior_episode": behavior_episode_payload}
                if behavior_episode_payload is not None
                else {}
            ),
            **(
                {"program_oracle_evidence": oracle_evidence_payload}
                if oracle_evidence_payload is not None
                else {}
            ),
            **(
                {
                    "program_oracle_readability": {
                        "path": "oracle_evidence.json",
                        "content_hash": oracle_evidence_hash,
                        "summary": oracle_readability_summary,
                        "facets": oracle_readability_facets,
                    }
                }
                if oracle_evidence_hash is not None
                else {}
            ),
            "program_candidate_assembly": candidate_assembly,
            "program_execution_episode": execution_episode,
            "program_receipt_bundle": receipt_bundle,
            "mlflow_hints": build_mlflow_hints(
                run_kind="program-gen",
                template_version="program-candidate-assembly-v1",
                output_path=manifest_path,
                output_hash=manifest_hash,
                cache_key=cache_key,
                extra_expected_tags={"service": "program"},
            ),
            **current_receipt_lineage(),
        },
        outcome="success",
    )
    receipt_path = write_run_receipt(manifest_path, receipt)

    return ProgramArtifact(
        name=intent.name,
        root_path=str(root),
        files={
            relative: str((root / relative).resolve()) for relative in generated_files
        },
        manifest=manifest,
        receipt_path=str(receipt_path),
        metadata={
            "request_id": ids["request_id"],
            "candidate_id": ids["candidate_id"],
            "assembly_id": ids["assembly_id"],
            "episode_id": ids["episode_id"],
            "receipt_bundle_id": ids["receipt_bundle_id"],
            "intent_hash": intent_hash,
            "plan_hash": plan_hash,
            "jury_hash": jury_hash,
            "jury_selection_hash": jury_selection_hash,
            "jury_rubric_hash": jury_rubric_hash,
            "promotion_review_hash": promotion_review_hash,
            "promotion_adjudication_request_hash": promotion_adjudication_request_hash,
            "promotion_decision_template_hash": promotion_decision_template_hash,
            "module_surfaces_hash": module_surfaces_hash,
            "execution_episode_hash": execution_episode_hash,
            "dataset_manifest_hash": dataset_manifest_hash,
            "dataset_split_behavior_results_hashes": dict(
                dataset_split_behavior_hashes
            ),
            "topology_execution": topology_execution,
            "behavior_results_hash": behavior_results_hash,
            "behavior_summary": behavior_summary,
            "behavior_episode_hash": behavior_episode_hash,
            "oracle_evidence_hash": oracle_evidence_hash,
            "oracle_readability_summary": oracle_readability_summary,
            "oracle_readability_facets": oracle_readability_facets,
            "program_hash": program_hash,
            "assembly_hash": assembly_hash,
        },
    )


def run_generate_from_intent_path(
    intent_path: Path,
    *,
    outdir: Optional[Path] = None,
) -> ProgramArtifact:
    intent = load_program_intent(intent_path)
    return materialize_program_from_intent(
        intent,
        outdir=outdir,
        intent_source=intent_path,
    )
