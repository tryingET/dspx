from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Optional

from dspx.cache import cache_dir, cache_enabled, make_key, sha256_text
from dspx.generated_code_guard import isolated_subprocess_env
from dspx.redaction import sanitize_diagnostic_text
from dspx.services.program_capabilities import build_program_capability_registry
from dspx.services.program_generated_policy import (
    verify_program_generated_module_policy,
)
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
from dspx.services.program_intent_normalization import (
    PROGRAM_INTENT_NORMALIZATION_SCHEMA,
    build_program_intent_normalization,
)
from dspx.services.program_execution_episode import build_program_execution_episode
from dspx.services.program_retrievers import (
    PROGRAM_RETRIEVER_SNAPSHOTS_SCHEMA,
    resolve_program_retriever_snapshots,
    retriever_snapshot_text,
)
from dspx.services.program_runtime_outcomes import (
    PROGRAM_RUNTIME_OUTCOMES_SCHEMA,
    build_program_runtime_outcomes,
)
from dspx.services.program_runtime_traces import (
    PROGRAM_RUNTIME_TRACES_SCHEMA,
    build_program_runtime_traces,
)
from dspx.services.program_tool_contracts import (
    PROGRAM_TOOL_CONTRACTS_SCHEMA,
    build_program_tool_contracts,
    materialize_program_tool_adapter_blueprints,
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
    MATERIALIZABLE_DECLARED_TOPOLOGY_KINDS,
    PIPELINE_MATERIALIZED_STATUS,
    PROMPT_INFERRED_PIPELINE_RENDERER,
    RETRIEVE_THEN_ANSWER_RENDERER,
    materialized_pipeline_topology,
    prompt_inferred_pipeline_topology,
    validate_materializable_pipeline_topology,
)


def _intent_payload(intent: ProgramIntent) -> dict[str, Any]:
    return intent.model_dump(mode="json", exclude_none=True)


def _json_text(payload: Mapping[str, Any] | list[Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _cleanup_failed_program_outdir(root: Path) -> None:
    shutil.rmtree(root, ignore_errors=True)


def _program_cache_file(cache_key: str) -> Path:
    path = cache_dir() / "program" / f"{cache_key}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _build_pre_materialization_intent_normalization(
    intent: ProgramIntent,
    *,
    intent_source: Optional[Path] = None,
) -> dict[str, Any]:
    """Build the direct program-gen assumption review sidecar.

    The sidecar is emitted before candidate surfaces are written so direct
    materialization has the same inspectable assumption/missing-evidence/risk
    membrane as the explicit ``program-gen normalize-intent`` command.
    """

    intent_payload = _intent_payload(intent)
    if intent_source is not None:
        source = intent_source.expanduser().resolve()
        source_payload = {
            "kind": "intent_file",
            "path": str(source),
            "content_hash": sha256_text(source.read_text(encoding="utf-8")),
        }
    else:
        source_payload = {
            "kind": "in_memory_intent",
            "content_hash": sha256_text(
                json.dumps(intent_payload, ensure_ascii=False, sort_keys=True)
            ),
        }
    payload = build_program_intent_normalization(intent, source=source_payload)
    return {
        **payload,
        "status": "normalized_for_direct_materialization",
        "materialization_gate": {
            "status": "emitted_before_candidate_materialization",
            "review_required_before_trusting_outputs": True,
            "blocks_materialization": False,
            "notes": [
                "Direct program-gen now emits this assumption/risk sidecar before writing candidate surfaces.",
                "This sidecar does not approve generation, promotion, activation, or external authority mutation.",
            ],
        },
    }


def _validate_contract_verification_payload(
    payload: Mapping[str, Any],
    *,
    intent_source: Path | None,
) -> None:
    if payload.get("schema_version") != "program-architecture-contract-verification-v1":
        raise ValueError("invalid contract verification schema_version")
    if payload.get("status") != "verified_contract_intent":
        raise ValueError("contract verification is not verified")
    if payload.get("materialization_allowed_by_contract_verification") is not True:
        raise ValueError("contract verification does not allow materialization")
    gate = payload.get("materialization_gate")
    if not isinstance(gate, Mapping) or gate.get("status") != (
        "verified_for_explicit_program_gen_materialization"
    ):
        raise ValueError("contract verification materialization gate is not open")
    if (
        gate.get("allows_live_tools")
        or gate.get("allows_custom_imports")
        or gate.get("allows_external_retrievers")
    ):
        raise ValueError("contract verification unexpectedly allows live effects")
    if intent_source is not None:
        expected_hash = str(
            gate.get("program_gen_must_match_intent_hash") or ""
        ).strip()
        if not expected_hash:
            raise ValueError("contract verification missing intent hash")
        actual_hash = sha256_text(
            intent_source.expanduser().resolve().read_text(encoding="utf-8")
        )
        if actual_hash != expected_hash:
            raise ValueError("contract verification intent_hash_mismatch")


def _contract_verification_metadata(
    path: Optional[Path], *, root: Path, intent_source: Path | None
) -> dict[str, Any] | None:
    if path is None:
        return None
    source = path.expanduser().resolve()
    text = source.read_text(encoding="utf-8")
    payload = json.loads(text)
    _validate_contract_verification_payload(payload, intent_source=intent_source)
    candidate_path = root / "program_architecture_contract_verification.json"
    candidate_path.write_text(text, encoding="utf-8")
    return {
        "path": "program_architecture_contract_verification.json",
        "source_path": str(source),
        "content_hash": sha256_text(text),
        "schema_version": str(
            payload.get("schema_version")
            or "program-architecture-contract-verification-v1"
        ),
        "status": str(payload.get("status") or "unknown"),
        "materialization_gate": dict(payload.get("materialization_gate") or {}),
        "non_authority": dict(payload.get("non_authority") or {}),
    }


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
    inferred_topology = prompt_inferred_pipeline_topology(intent)
    materialized_topology = _default_materialized_topology(intent)
    topology_inferred = False
    if declared_topology:
        topology = declared_topology
        if declared_topology.get("kind") in MATERIALIZABLE_DECLARED_TOPOLOGY_KINDS:
            validate_materializable_pipeline_topology(intent)
            materialized_topology = materialized_pipeline_topology(intent)
            status = str(
                materialized_topology.get("execution_status")
                or PIPELINE_MATERIALIZED_STATUS
            )
            topology_materialized = True
            if declared_topology.get("kind") == "retrieve_then_answer":
                current_renderer = RETRIEVE_THEN_ANSWER_RENDERER
                notes = [
                    "Explicit retrieve_then_answer topology is preserved as declared input and rendered through the bounded topology renderer.",
                    "Only explicit bounded inline or materialization-time local_corpus_snapshot Retriever modules feeding generated Predict/ChainOfThought/ReAct/ProgramOfThought answer modules are supported in this slice.",
                    "No live external retriever, tool binding, custom import, ranking, promotion, or external authority execution is performed; ReAct uses tools=[] and ProgramOfThought uses an empty sandbox.",
                ]
            else:
                kind = str(declared_topology.get("kind") or "pipeline")
                current_renderer = (
                    "pipeline_topology_renderer"
                    if kind == "pipeline"
                    else f"{kind}_topology_renderer"
                )
                notes = [
                    f"Explicit {kind} topology is preserved as declared input and rendered as a bounded composed program.",
                    "Only Predict, ChainOfThought, bounded no-tool ReAct, sandboxed ProgramOfThought, explicit bounded inline Retriever modules, and materialization-time local_corpus_snapshot Retriever modules plus simple when.field/equals routing are supported in this slice.",
                    "No topology inference, broad graph engine, live external tools/retrievers, ReAct tool binding, or ProgramOfThought filesystem/network/env/tool sandbox access is performed.",
                ]
        else:
            status = str(
                declared_topology.get("execution_status") or "declared_not_materialized"
            )
            topology_materialized = False
            current_renderer = "single_module_scaffold"
            notes = [
                "Explicit topology is preserved as a planning contract.",
                "This slice only renders explicit bounded pipeline/router/retrieve_then_answer/extract_transform_validate/generate_critique_revise topology; unsupported kinds remain declared-only.",
                "The generated Python remains the current single-module scaffold for this topology kind.",
            ]
    elif inferred_topology:
        validate_materializable_pipeline_topology(intent)
        topology = inferred_topology
        materialized_topology = materialized_pipeline_topology(intent)
        status = PIPELINE_MATERIALIZED_STATUS
        topology_materialized = True
        topology_inferred = True
        current_renderer = PROMPT_INFERRED_PIPELINE_RENDERER
        notes = list(inferred_topology.get("notes") or [])
    else:
        topology = materialized_topology
        status = str(materialized_topology["execution_status"])
        topology_materialized = True
        current_renderer = "single_module_scaffold"
        notes = [
            "No explicit topology was declared and no prompt cues required richer module inference; program-gen used the existing single-module scaffold.",
        ]
    return {
        "topology": topology,
        "declared_topology": declared_topology or None,
        "inferred_topology": inferred_topology or None,
        "materialized_topology": materialized_topology,
        "topology_execution_status": status,
        "materialization_scope": {
            "topology_declared": bool(declared_topology),
            "topology_inferred": topology_inferred,
            "topology_materialized": topology_materialized,
            "current_renderer": current_renderer,
            "notes": notes,
        },
    }


def build_program_plan(
    intent: ProgramIntent,
    *,
    examples_hash: Optional[str] = None,
    retriever_snapshots_hash: Optional[str] = None,
    runtime_outcomes_hash: Optional[str] = None,
    runtime_traces_hash: Optional[str] = None,
    tool_contracts_hash: Optional[str] = None,
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
        {
            "kind": "capability_registry",
            "path": "program_capability_registry.json",
            "generator": "program-gen",
        },
        {
            "kind": "generated_module_policy",
            "path": "generated_module_policy.json",
            "generator": "program-gen",
        },
        {
            "kind": "runtime_outcomes",
            "path": "program_runtime_outcomes.json",
            "generator": "program-gen",
        },
        {
            "kind": "runtime_traces",
            "path": "program_runtime_traces.json",
            "generator": "program-gen",
        },
        {
            "kind": "tool_contracts",
            "path": "program_tool_contracts.json",
            "generator": "program-gen",
        },
        *(
            [
                {
                    "kind": "retriever_snapshots",
                    "path": "retriever_snapshots.json",
                    "generator": "program-gen",
                }
            ]
            if retriever_snapshots_hash is not None
            else []
        ),
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
        "inferred_topology": topology_contract["inferred_topology"],
        "materialized_topology": topology_contract["materialized_topology"],
        "topology_execution_status": topology_contract["topology_execution_status"],
        "materialization_scope": topology_contract["materialization_scope"],
        "capability_contracts": {
            "schema_version": "program-capability-registry-v1",
            "path": "program_capability_registry.json",
            "status": "descriptor_only_no_runtime_binding",
        },
        "generated_module_policy": {
            "schema_version": "program-generated-module-policy-v1",
            "path": "generated_module_policy.json",
            "status": "passed",
        },
        "runtime_outcomes": {
            "schema_version": PROGRAM_RUNTIME_OUTCOMES_SCHEMA,
            "path": "program_runtime_outcomes.json",
            "content_hash": runtime_outcomes_hash,
            "status": "outcome_contracts_declared",
        },
        "runtime_traces": {
            "schema_version": PROGRAM_RUNTIME_TRACES_SCHEMA,
            "path": "program_runtime_traces.json",
            "content_hash": runtime_traces_hash,
            "status": "runtime_traces_captured_or_not_applicable",
        },
        "tool_contracts": {
            "schema_version": PROGRAM_TOOL_CONTRACTS_SCHEMA,
            "path": "program_tool_contracts.json",
            "content_hash": tool_contracts_hash,
            "status": "descriptor_only_no_tool_binding",
        },
        "retriever_snapshots": {
            "schema_version": PROGRAM_RETRIEVER_SNAPSHOTS_SCHEMA,
            "path": "retriever_snapshots.json",
            "content_hash": retriever_snapshots_hash,
            "status": "materialized_to_bounded_inline_adapters",
        }
        if retriever_snapshots_hash is not None
        else None,
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


def _sanitize_harness_diagnostic(value: object, *, limit: int = 500) -> str:
    text = "" if value is None else str(value)
    sanitized = sanitize_diagnostic_text(text, limit=max(len(text), limit))
    return sanitized[-limit:]


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
    stdout = _sanitize_harness_diagnostic((proc.stdout or "").strip(), limit=500)
    stderr = _sanitize_harness_diagnostic((proc.stderr or "").strip(), limit=500)
    result: dict[str, Any] = {
        "command": [sys.executable, filename],
        "returncode": proc.returncode,
        "stdout": stdout,
        "stderr": stderr,
    }
    if proc.returncode != 0:
        error_stderr = _sanitize_harness_diagnostic(
            (proc.stderr or "").strip(), limit=240
        )
        raise ValueError(
            f"program {label} failed: rc={proc.returncode} stderr={error_stderr}"
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


def _safe_list_count(value: object) -> int:
    return len(value) if isinstance(value, list) else 0


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
            f"runtime_traces.status={oracle_facets.get('runtime_trace_status')}",
            f"runtime_traces.coverage_status={oracle_facets.get('runtime_trace_coverage_status')}",
            f"runtime_traces.source_record_coverage_status={oracle_facets.get('runtime_trace_source_record_coverage_status')}",
            f"runtime_traces.module_call_count={oracle_facets.get('runtime_trace_module_call_count')}",
            f"runtime_traces.final_output_trace_count={oracle_facets.get('runtime_trace_final_output_trace_count')}",
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
        ("runtime_outcomes", "program_runtime_outcomes.json"),
        ("runtime_traces", "program_runtime_traces.json"),
        ("tool_contracts", "program_tool_contracts.json"),
        ("capability_registry", "program_capability_registry.json"),
        ("generated_module_policy", "generated_module_policy.json"),
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


def _oracle_runtime_trace_summary(
    *,
    runtime_traces_payload: Mapping[str, Any],
    runtime_traces_hash: str,
) -> dict[str, Any]:
    raw_coverage = runtime_traces_payload.get("coverage")
    coverage = dict(raw_coverage) if isinstance(raw_coverage, Mapping) else {}
    raw_non_authority = runtime_traces_payload.get("non_authority")
    non_authority = (
        dict(raw_non_authority) if isinstance(raw_non_authority, Mapping) else {}
    )
    return {
        "schema_version": runtime_traces_payload.get("schema_version"),
        "path": "program_runtime_traces.json",
        "content_hash": runtime_traces_hash,
        "status": runtime_traces_payload.get("status"),
        "source_count": runtime_traces_payload.get("source_count"),
        "module_call_count": runtime_traces_payload.get("module_call_count"),
        "final_output_trace_count": runtime_traces_payload.get(
            "final_output_trace_count"
        ),
        "coverage": {
            "schema_version": coverage.get("schema_version"),
            "status": coverage.get("status"),
            "source_record_coverage_status": coverage.get(
                "source_record_coverage_status"
            ),
            "expected_module_count": _safe_list_count(
                coverage.get("expected_module_ids")
            ),
            "captured_module_count": _safe_list_count(
                coverage.get("captured_module_ids")
            ),
            "missing_module_count": _safe_list_count(
                coverage.get("missing_module_ids")
            ),
            "program_output_count": _safe_list_count(coverage.get("program_outputs")),
            "captured_final_output_field_count": _safe_list_count(
                coverage.get("captured_final_output_fields")
            ),
            "missing_final_output_field_count": _safe_list_count(
                coverage.get("missing_final_output_fields")
            ),
        },
        "non_authority": non_authority,
    }


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
    runtime_traces_payload: Mapping[str, Any],
    runtime_traces_hash: str,
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
    runtime_trace_summary = _oracle_runtime_trace_summary(
        runtime_traces_payload=runtime_traces_payload,
        runtime_traces_hash=runtime_traces_hash,
    )
    runtime_trace_coverage = dict(runtime_trace_summary.get("coverage") or {})
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
        "runtime_trace_status": runtime_trace_summary.get("status"),
        "runtime_trace_coverage_status": runtime_trace_coverage.get("status"),
        "runtime_trace_source_record_coverage_status": runtime_trace_coverage.get(
            "source_record_coverage_status"
        ),
        "runtime_trace_module_call_count": runtime_trace_summary.get(
            "module_call_count"
        ),
        "runtime_trace_final_output_trace_count": runtime_trace_summary.get(
            "final_output_trace_count"
        ),
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
        "runtime_traces": runtime_trace_summary,
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


def materialize_program_from_intent(
    intent: ProgramIntent,
    *,
    outdir: Optional[Path] = None,
    intent_source: Optional[Path] = None,
    contract_verification_path: Optional[Path] = None,
) -> ProgramArtifact:
    """Materialize a runnable program-shaped candidate assembly from one intent."""

    root = (
        (outdir if outdir is not None else _default_outdir(intent))
        .expanduser()
        .resolve()
    )
    if root.exists():
        raise ValueError(f"program-gen outdir already exists: {root}")
    try:
        root.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise ValueError(f"program-gen outdir already exists: {root}") from exc
    try:
        return _materialize_program_from_intent_unchecked(
            intent,
            outdir=root,
            intent_source=intent_source,
            contract_verification_path=contract_verification_path,
        )
    except Exception:
        _cleanup_failed_program_outdir(root)
        raise


def _materialize_program_from_intent_unchecked(
    intent: ProgramIntent,
    *,
    outdir: Optional[Path] = None,
    intent_source: Optional[Path] = None,
    contract_verification_path: Optional[Path] = None,
) -> ProgramArtifact:
    root = (
        (outdir if outdir is not None else _default_outdir(intent))
        .expanduser()
        .resolve()
    )
    if root.exists() and any(root.iterdir()):
        raise ValueError(f"program-gen outdir is not empty: {root}")
    root.mkdir(parents=True, exist_ok=True)

    intent, retriever_snapshots_payload = resolve_program_retriever_snapshots(
        intent,
        intent_source=intent_source,
    )
    retriever_snapshots_text = (
        retriever_snapshot_text(retriever_snapshots_payload)
        if retriever_snapshots_payload is not None
        else None
    )
    retriever_snapshots_hash = (
        sha256_text(retriever_snapshots_text)
        if retriever_snapshots_text is not None
        else None
    )

    intent_normalization_payload = _build_pre_materialization_intent_normalization(
        intent,
        intent_source=intent_source,
    )
    intent_normalization_text = _json_text(intent_normalization_payload)
    intent_normalization_hash = sha256_text(intent_normalization_text)

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
    runtime_outcomes_payload = build_program_runtime_outcomes(
        intent,
        module_surfaces=module_surfaces_payload,
    )
    runtime_outcomes_text = _json_text(runtime_outcomes_payload)
    runtime_outcomes_hash = sha256_text(runtime_outcomes_text)
    tool_contracts_payload = materialize_program_tool_adapter_blueprints(
        build_program_tool_contracts(intent), root
    )
    tool_contracts_text = _json_text(tool_contracts_payload)
    tool_contracts_hash = sha256_text(tool_contracts_text)
    capability_registry_payload = build_program_capability_registry(intent)
    capability_registry_text = _json_text(capability_registry_payload)
    generated_module_policy_payload = verify_program_generated_module_policy(
        module_code,
        module_surfaces=module_surfaces_payload,
    )
    generated_module_policy_text = _json_text(generated_module_policy_payload)
    program_plan = build_program_plan(
        intent,
        examples_hash=examples_hash,
        retriever_snapshots_hash=retriever_snapshots_hash,
        runtime_outcomes_hash=runtime_outcomes_hash,
        tool_contracts_hash=tool_contracts_hash,
    )
    jury_payload = dict(program_plan["evaluation_strategy"])
    jury_selection = build_jury_selection(jury_payload)
    jury_rubric = build_jury_rubric(intent, jury_selection)
    behavior_artifact_refs: list[str] = []
    if examples_payload:
        behavior_artifact_refs.append("behavior_results.json")
    if has_program_dataset(intent):
        behavior_artifact_refs.extend(
            f"behavior_results.{split}.json" for split in SPLIT_NAMES
        )
    promotion_review = build_promotion_review(
        intent,
        has_examples=bool(examples_payload),
        jury_selection=jury_selection,
        jury_rubric=jury_rubric,
        has_behavior_results=bool(behavior_artifact_refs),
        behavior_artifact_refs=behavior_artifact_refs,
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
    tool_contracts_hash = sha256_text(tool_contracts_text)
    capability_registry_hash = sha256_text(capability_registry_text)
    generated_module_policy_hash = sha256_text(generated_module_policy_text)
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
        runtime_outcomes_text,
        tool_contracts_text,
        capability_registry_text,
        generated_module_policy_text,
        intent_normalization_text,
        *([retriever_snapshots_text] if retriever_snapshots_text is not None else []),
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
    contract_verification_metadata = _contract_verification_metadata(
        contract_verification_path, root=root, intent_source=intent_source
    )
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
        "program_runtime_outcomes.json": runtime_outcomes_hash,
        "program_tool_contracts.json": tool_contracts_hash,
        "program_capability_registry.json": capability_registry_hash,
        "generated_module_policy.json": generated_module_policy_hash,
        "intent_normalization.json": intent_normalization_hash,
        **(
            {"retriever_snapshots.json": retriever_snapshots_hash}
            if retriever_snapshots_hash is not None
            else {}
        ),
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

    (root / "intent_normalization.json").write_text(
        intent_normalization_text, encoding="utf-8"
    )
    if retriever_snapshots_text is not None:
        (root / "retriever_snapshots.json").write_text(
            retriever_snapshots_text, encoding="utf-8"
        )
    for relative, content in generated_files.items():
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
    (root / "program_runtime_outcomes.json").write_text(
        runtime_outcomes_text, encoding="utf-8"
    )
    (root / "program_tool_contracts.json").write_text(
        tool_contracts_text, encoding="utf-8"
    )
    (root / "program_capability_registry.json").write_text(
        capability_registry_text, encoding="utf-8"
    )
    (root / "generated_module_policy.json").write_text(
        generated_module_policy_text, encoding="utf-8"
    )
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
    runtime_traces_payload = build_program_runtime_traces(
        intent,
        module_surfaces=module_surfaces_payload,
        behavior_results=behavior_results_payload,
        behavior_results_hash=behavior_results_hash,
        dataset_split_behavior_results=dataset_split_behavior_payloads,
        dataset_split_behavior_hashes=dataset_split_behavior_hashes,
    )
    runtime_traces_text = _write_json(
        root / "program_runtime_traces.json", runtime_traces_payload
    )
    runtime_traces_hash = sha256_text(runtime_traces_text)
    surface_hashes["program_runtime_traces.json"] = runtime_traces_hash
    program_plan = build_program_plan(
        intent,
        examples_hash=examples_hash,
        retriever_snapshots_hash=retriever_snapshots_hash,
        runtime_outcomes_hash=runtime_outcomes_hash,
        runtime_traces_hash=runtime_traces_hash,
        tool_contracts_hash=tool_contracts_hash,
    )
    plan_text = _json_text(program_plan)
    plan_hash = sha256_text(plan_text)
    surface_hashes["plan.json"] = plan_hash
    (root / "plan.json").write_text(plan_text, encoding="utf-8")
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
            runtime_traces_payload=runtime_traces_payload,
            runtime_traces_hash=runtime_traces_hash,
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
            "program_runtime_outcomes.json",
            "program_runtime_traces.json",
            "program_tool_contracts.json",
            "program_capability_registry.json",
            "generated_module_policy.json",
            "intent_normalization.json",
            *(
                ["retriever_snapshots.json"]
                if retriever_snapshots_hash is not None
                else []
            ),
            "intent.json",
            *(["examples.json", "behavior_results.json"] if examples_payload else []),
            *(["behavior_episode.json"] if behavior_episode_hash is not None else []),
            *(["oracle_evidence.json"] if oracle_evidence_hash is not None else []),
            "execution_episode.json",
            "manifest.json",
        ]
    )
    execution_episode = build_program_execution_episode(
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
        evaluation_sources=evaluation_sources,
        behavior_evidence_summary=behavior_evidence_summary,
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
            "runtime_outcomes",
            "runtime_traces",
            "tool_contracts",
            "execution_episode",
            "capability_registry",
            "generated_module_policy",
            "intent_normalization",
            *(["retriever_snapshots"] if retriever_snapshots_hash is not None else []),
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
                "kind": "runtime_outcomes",
                "path": "program_runtime_outcomes.json",
                "generator": "program-gen",
                "content_hash": surface_hashes["program_runtime_outcomes.json"],
                "schema_version": runtime_outcomes_payload["schema_version"],
                "status": runtime_outcomes_payload["status"],
                "module_outcome_count": runtime_outcomes_payload[
                    "module_outcome_count"
                ],
            },
            {
                "kind": "runtime_traces",
                "path": "program_runtime_traces.json",
                "generator": "program-gen",
                "content_hash": surface_hashes["program_runtime_traces.json"],
                "schema_version": runtime_traces_payload["schema_version"],
                "status": runtime_traces_payload["status"],
                "module_call_count": runtime_traces_payload["module_call_count"],
                "final_output_trace_count": runtime_traces_payload[
                    "final_output_trace_count"
                ],
            },
            {
                "kind": "tool_contracts",
                "path": "program_tool_contracts.json",
                "generator": "program-gen",
                "content_hash": surface_hashes["program_tool_contracts.json"],
                "schema_version": tool_contracts_payload["schema_version"],
                "status": tool_contracts_payload["status"],
                "tool_contract_count": tool_contracts_payload["tool_contract_count"],
            },
            {
                "kind": "execution_episode",
                "path": "execution_episode.json",
                "generator": "program-gen",
                "content_hash": surface_hashes["execution_episode.json"],
                "schema_version": execution_episode["schema_version"],
                "status": execution_episode["status"],
            },
            {
                "kind": "capability_registry",
                "path": "program_capability_registry.json",
                "generator": "program-gen",
                "content_hash": surface_hashes["program_capability_registry.json"],
                "schema_version": capability_registry_payload["schema_version"],
                "status": capability_registry_payload["status"],
            },
            {
                "kind": "generated_module_policy",
                "path": "generated_module_policy.json",
                "generator": "program-gen",
                "content_hash": surface_hashes["generated_module_policy.json"],
                "schema_version": generated_module_policy_payload["schema_version"],
                "status": generated_module_policy_payload["status"],
            },
            {
                "kind": "intent_normalization",
                "path": "intent_normalization.json",
                "generator": "program-gen",
                "content_hash": surface_hashes["intent_normalization.json"],
                "schema_version": PROGRAM_INTENT_NORMALIZATION_SCHEMA,
                "status": intent_normalization_payload["status"],
            },
            *(
                [
                    {
                        "kind": "retriever_snapshots",
                        "path": "retriever_snapshots.json",
                        "generator": "program-gen",
                        "content_hash": surface_hashes["retriever_snapshots.json"],
                        "schema_version": PROGRAM_RETRIEVER_SNAPSHOTS_SCHEMA,
                        "status": dict(retriever_snapshots_payload or {}).get("status"),
                        "snapshot_count": dict(retriever_snapshots_payload or {}).get(
                            "snapshot_count"
                        ),
                    }
                ]
                if retriever_snapshots_hash is not None
                else []
            ),
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
    assembly_hash = sha256_text(
        _json_text(
            {
                "surface_kinds": candidate_assembly["surface_kinds"],
                "surfaces": [
                    {
                        "kind": surface.get("kind"),
                        "path": surface.get("path"),
                        "content_hash": surface.get("content_hash"),
                    }
                    for surface in candidate_assembly["surfaces"]
                ],
            }
        )
    )
    candidate_assembly["content_hash"] = assembly_hash

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
            "runtime_outcomes_hash": runtime_outcomes_hash,
            "runtime_outcomes_path": "program_runtime_outcomes.json",
            "runtime_traces_hash": runtime_traces_hash,
            "runtime_traces_path": "program_runtime_traces.json",
            "tool_contracts_hash": tool_contracts_hash,
            "tool_contracts_path": "program_tool_contracts.json",
            "capability_registry_hash": capability_registry_hash,
            "capability_registry_path": "program_capability_registry.json",
            "generated_module_policy_hash": generated_module_policy_hash,
            "generated_module_policy_path": "generated_module_policy.json",
            "intent_normalization_hash": intent_normalization_hash,
            "intent_normalization_path": "intent_normalization.json",
            **(
                {
                    "retriever_snapshots_hash": retriever_snapshots_hash,
                    "retriever_snapshots_path": "retriever_snapshots.json",
                }
                if retriever_snapshots_hash is not None
                else {}
            ),
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
                "runtime_outcomes": "program-gen",
                "runtime_traces": "program-gen",
                "tool_contracts": "program-gen",
                "capability_registry": "program-gen",
                "generated_module_policy": "program-gen",
                "intent_normalization": "program-gen",
                **(
                    {"retriever_snapshots": "program-gen"}
                    if retriever_snapshots_hash is not None
                    else {}
                ),
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
            "runtime_outcomes_hash": runtime_outcomes_hash,
            "runtime_traces_hash": runtime_traces_hash,
            "tool_contracts_hash": tool_contracts_hash,
            "capability_registry_hash": capability_registry_hash,
            "generated_module_policy_hash": generated_module_policy_hash,
            "intent_normalization_hash": intent_normalization_hash,
            "retriever_snapshots_hash": retriever_snapshots_hash,
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
        "program_runtime_outcomes": runtime_outcomes_payload,
        "runtime_outcomes_artifact": {
            "path": "program_runtime_outcomes.json",
            "content_hash": runtime_outcomes_hash,
            "schema_version": PROGRAM_RUNTIME_OUTCOMES_SCHEMA,
            "status": runtime_outcomes_payload["status"],
        },
        "program_runtime_traces": runtime_traces_payload,
        "runtime_traces_artifact": {
            "path": "program_runtime_traces.json",
            "content_hash": runtime_traces_hash,
            "schema_version": PROGRAM_RUNTIME_TRACES_SCHEMA,
            "status": runtime_traces_payload["status"],
        },
        "program_tool_contracts": tool_contracts_payload,
        "tool_contracts_artifact": {
            "path": "program_tool_contracts.json",
            "content_hash": tool_contracts_hash,
            "schema_version": PROGRAM_TOOL_CONTRACTS_SCHEMA,
            "status": tool_contracts_payload["status"],
        },
        "program_capability_registry": capability_registry_payload,
        "capability_registry_artifact": {
            "path": "program_capability_registry.json",
            "content_hash": capability_registry_hash,
            "schema_version": capability_registry_payload["schema_version"],
        },
        "program_generated_module_policy": generated_module_policy_payload,
        "generated_module_policy_artifact": {
            "path": "generated_module_policy.json",
            "content_hash": generated_module_policy_hash,
            "schema_version": generated_module_policy_payload["schema_version"],
        },
        "intent_normalization": intent_normalization_payload,
        "program_architecture_contract_verification": contract_verification_metadata,
        "program_architecture_contract_verification_artifact": contract_verification_metadata,
        "intent_normalization_artifact": {
            "path": "intent_normalization.json",
            "content_hash": intent_normalization_hash,
            "schema_version": PROGRAM_INTENT_NORMALIZATION_SCHEMA,
            "status": intent_normalization_payload["status"],
        },
        "retriever_snapshots": retriever_snapshots_payload,
        "retriever_snapshots_artifact": {
            "path": "retriever_snapshots.json",
            "content_hash": retriever_snapshots_hash,
            "schema_version": PROGRAM_RETRIEVER_SNAPSHOTS_SCHEMA,
            "status": dict(retriever_snapshots_payload or {}).get("status"),
        }
        if retriever_snapshots_hash is not None
        else None,
        "pre_materialization_review": {
            "status": "emitted_before_candidate_materialization",
            "path": "intent_normalization.json",
            "content_hash": intent_normalization_hash,
            "assumption_count": len(
                intent_normalization_payload.get("assumptions") or []
            ),
            "missing_evidence_count": len(
                intent_normalization_payload.get("missing_evidence") or []
            ),
            "generation_risk_count": len(
                intent_normalization_payload.get("generation_risks") or []
            ),
            "topology_candidate_count": len(
                dict(
                    intent_normalization_payload.get("generation_assumptions_preview")
                    or {}
                ).get("topology_candidates")
                or []
            ),
            "capability_boundary_keys": sorted(
                dict(
                    dict(
                        intent_normalization_payload.get(
                            "generation_assumptions_preview"
                        )
                        or {}
                    ).get("capability_boundaries")
                    or {}
                )
            ),
            "blocks_materialization": False,
            "non_authority": dict(
                intent_normalization_payload.get("non_authority") or {}
            ),
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
            "runtime_outcomes_hash": runtime_outcomes_hash,
            "runtime_outcomes_path": "program_runtime_outcomes.json",
            "runtime_traces_hash": runtime_traces_hash,
            "runtime_traces_path": "program_runtime_traces.json",
            "tool_contracts_hash": tool_contracts_hash,
            "tool_contracts_path": "program_tool_contracts.json",
            "capability_registry_hash": capability_registry_hash,
            "capability_registry_path": "program_capability_registry.json",
            "generated_module_policy_hash": generated_module_policy_hash,
            "generated_module_policy_path": "generated_module_policy.json",
            "intent_normalization_hash": intent_normalization_hash,
            "intent_normalization_path": "intent_normalization.json",
            "retriever_snapshots_hash": retriever_snapshots_hash,
            "retriever_snapshots_path": "retriever_snapshots.json"
            if retriever_snapshots_hash is not None
            else None,
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
            "program_runtime_outcomes": runtime_outcomes_payload,
            "program_runtime_outcomes_artifact": {
                "path": "program_runtime_outcomes.json",
                "content_hash": runtime_outcomes_hash,
                "schema_version": PROGRAM_RUNTIME_OUTCOMES_SCHEMA,
                "status": runtime_outcomes_payload["status"],
            },
            "program_runtime_traces": runtime_traces_payload,
            "program_runtime_traces_artifact": {
                "path": "program_runtime_traces.json",
                "content_hash": runtime_traces_hash,
                "schema_version": PROGRAM_RUNTIME_TRACES_SCHEMA,
                "status": runtime_traces_payload["status"],
            },
            "program_tool_contracts": tool_contracts_payload,
            "program_tool_contracts_artifact": {
                "path": "program_tool_contracts.json",
                "content_hash": tool_contracts_hash,
                "schema_version": PROGRAM_TOOL_CONTRACTS_SCHEMA,
                "status": tool_contracts_payload["status"],
            },
            "program_capability_registry": capability_registry_payload,
            "program_capability_registry_artifact": {
                "path": "program_capability_registry.json",
                "content_hash": capability_registry_hash,
                "schema_version": capability_registry_payload["schema_version"],
            },
            "program_generated_module_policy": generated_module_policy_payload,
            "program_generated_module_policy_artifact": {
                "path": "generated_module_policy.json",
                "content_hash": generated_module_policy_hash,
                "schema_version": generated_module_policy_payload["schema_version"],
            },
            "program_intent_normalization": intent_normalization_payload,
            "program_intent_normalization_artifact": {
                "path": "intent_normalization.json",
                "content_hash": intent_normalization_hash,
                "schema_version": PROGRAM_INTENT_NORMALIZATION_SCHEMA,
                "status": intent_normalization_payload["status"],
            },
            **(
                {
                    "program_retriever_snapshots": retriever_snapshots_payload,
                    "program_retriever_snapshots_artifact": {
                        "path": "retriever_snapshots.json",
                        "content_hash": retriever_snapshots_hash,
                        "schema_version": PROGRAM_RETRIEVER_SNAPSHOTS_SCHEMA,
                        "status": dict(retriever_snapshots_payload or {}).get("status"),
                    },
                }
                if retriever_snapshots_hash is not None
                else {}
            ),
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
            "runtime_outcomes_hash": runtime_outcomes_hash,
            "runtime_traces_hash": runtime_traces_hash,
            "tool_contracts_hash": tool_contracts_hash,
            "capability_registry_hash": capability_registry_hash,
            "generated_module_policy_hash": generated_module_policy_hash,
            "intent_normalization_hash": intent_normalization_hash,
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
    contract_verification_path: Optional[Path] = None,
) -> ProgramArtifact:
    intent = load_program_intent(intent_path)
    return materialize_program_from_intent(
        intent,
        outdir=outdir,
        intent_source=intent_path,
        contract_verification_path=contract_verification_path,
    )
