from __future__ import annotations

import hashlib
import importlib
import json
import sys
import threading
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import Any, Iterator, Mapping, TypeGuard, cast

from dspx.services.program_oracle_index import index_program_oracle_evidence_path
from dspx.services.program_oracle_publication_preflight import (
    build_program_oracle_publication_preflight,
    write_program_oracle_publication_preflight,
)
from dspx.services.program_oracle_report import build_program_oracle_evidence_report

PROGRAM_RUNTIME_EPISODE_SCHEMA = "program-runtime-episode-v1"
PROGRAM_BEHAVIOR_RESULTS_SCHEMA = "program-behavior-results-v1"
PROGRAM_ORACLE_EVIDENCE_SCHEMA = "program-oracle-evidence-v1"
PROGRAM_MANIFEST_SCHEMA = "program-candidate-assembly-v1"

CONTRACT_MODES = {"none", "pdf_transition_review"}
_GENERATED_PROGRAM_IMPORT_LOCK = threading.RLock()


def _json_text(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    payload = json.loads(path.expanduser().resolve().read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return payload


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _first_text(*values: object) -> str | None:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return None


def _safe_mapping(value: object) -> dict[str, Any]:
    return (
        {str(key): item for key, item in value.items()}
        if isinstance(value, Mapping)
        else {}
    )


def _manifest_identity(manifest: Mapping[str, Any]) -> dict[str, str | None]:
    request = _safe_mapping(manifest.get("request"))
    candidate = _safe_mapping(manifest.get("candidate_assembly"))
    execution = _safe_mapping(manifest.get("execution_episode"))
    receipt = _safe_mapping(manifest.get("receipt_bundle"))
    return {
        "request_id": _first_text(
            request.get("request_id"),
            candidate.get("request_id"),
            execution.get("request_id"),
            receipt.get("request_id"),
        ),
        "candidate_id": _first_text(
            candidate.get("candidate_id"),
            execution.get("candidate_id"),
            receipt.get("candidate_id"),
        ),
        "assembly_id": _first_text(
            candidate.get("assembly_id"),
            execution.get("assembly_id"),
            receipt.get("assembly_id"),
        ),
        "episode_id": _first_text(
            execution.get("episode_id"), receipt.get("episode_id")
        ),
        "receipt_bundle_id": _first_text(receipt.get("receipt_bundle_id")),
    }


def _validated_manifest(path: Path) -> dict[str, Any]:
    manifest = _load_json_object(path, label="program manifest")
    if manifest.get("schema_version") != PROGRAM_MANIFEST_SCHEMA:
        raise ValueError(
            f"program manifest schema_version must be {PROGRAM_MANIFEST_SCHEMA}"
        )
    candidate = _safe_mapping(manifest.get("candidate_assembly"))
    if candidate.get("artifact_kind") != "program":
        raise ValueError(
            "program manifest candidate_assembly.artifact_kind must be program"
        )
    if not any(_manifest_identity(manifest).values()):
        raise ValueError("program manifest does not expose candidate identity")
    return manifest


def _load_inputs(path: Path) -> dict[str, Any]:
    payload = _load_json_object(path, label="runtime inputs")
    nested = payload.get("inputs")
    if isinstance(nested, Mapping):
        return {str(key): item for key, item in nested.items()}
    return payload


def _data_uri_from_base64(*, data: str, media_type: str) -> str:
    raw = data.strip()
    if raw.startswith("data:"):
        return raw
    return f"data:{media_type};base64,{raw}"


def _materialize_image_descriptor(value: Mapping[str, Any], *, base_dir: Path) -> str:
    descriptor_type = str(value.get("type") or value.get("kind") or "").strip()
    try:
        import dspy
    except (
        Exception
    ) as exc:  # pragma: no cover - import failure is environment-specific
        raise RuntimeError("runtime image descriptors require dspy") from exc

    if descriptor_type == "image_file":
        raw_path = str(value.get("path") or value.get("file") or "").strip()
        if not raw_path:
            raise ValueError("image_file descriptor requires path")
        candidate_path = Path(raw_path).expanduser()
        if not candidate_path.is_absolute():
            candidate_path = base_dir / candidate_path
        image_path = candidate_path.resolve()
        if not image_path.is_file():
            raise ValueError(f"image_file path does not exist: {image_path}")
        return str(dspy.Image(str(image_path)))

    if descriptor_type == "image_base64":
        data = str(value.get("data") or value.get("base64") or "").strip()
        if not data:
            raise ValueError("image_base64 descriptor requires data")
        media_type = str(
            value.get("media_type")
            or value.get("mime_type")
            or value.get("mimeType")
            or "image/png"
        ).strip()
        return str(dspy.Image(_data_uri_from_base64(data=data, media_type=media_type)))

    if descriptor_type == "image_url":
        url = str(value.get("url") or value.get("image_url") or "").strip()
        if not url:
            raise ValueError("image_url descriptor requires url")
        return str(dspy.Image(url))

    raise ValueError(f"unsupported image descriptor type: {descriptor_type}")


def _is_image_descriptor(value: object) -> TypeGuard[Mapping[str, Any]]:
    if not isinstance(value, Mapping):
        return False
    payload = cast(Mapping[str, Any], value)
    descriptor_type = str(payload.get("type") or payload.get("kind") or "").strip()
    return descriptor_type in {"image_file", "image_base64", "image_url"}


def _materialize_runtime_input_value(value: object, *, base_dir: Path) -> Any:
    if _is_image_descriptor(value):
        return _materialize_image_descriptor(value, base_dir=base_dir)
    if isinstance(value, list):
        materialized = [
            _materialize_runtime_input_value(item, base_dir=base_dir) for item in value
        ]
        if value and all(_is_image_descriptor(item) for item in value):
            return "\n".join(str(item) for item in materialized)
        return materialized
    if isinstance(value, Mapping):
        return {
            str(key): _materialize_runtime_input_value(item, base_dir=base_dir)
            for key, item in value.items()
        }
    return value


def _materialize_runtime_inputs(
    runtime_inputs: Mapping[str, Any], *, inputs_path: Path
) -> dict[str, Any]:
    base_dir = inputs_path.expanduser().resolve().parent
    return {
        str(key): _materialize_runtime_input_value(item, base_dir=base_dir)
        for key, item in runtime_inputs.items()
    }


@contextmanager
def _generated_program_module(candidate_root: Path) -> Iterator[Any]:
    names = ("program", "module", "signature")
    root_text = str(candidate_root)
    # Generated program candidates import sibling modules by process-global names
    # (program/module/signature). Keep the whole candidate context serialized so
    # concurrent runtime episodes cannot pop or replace each other's modules.
    with _GENERATED_PROGRAM_IMPORT_LOCK:
        saved: dict[str, ModuleType | None] = {
            name: sys.modules.get(name) for name in names
        }
        for name in names:
            sys.modules.pop(name, None)
        sys.path.insert(0, root_text)
        try:
            yield importlib.import_module("program")
        finally:
            try:
                sys.path.remove(root_text)
            except ValueError:
                pass
            for name in names:
                sys.modules.pop(name, None)
                saved_module = saved[name]
                if saved_module is not None:
                    sys.modules[name] = saved_module


def _jsonable(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return str(value)


def _prediction_mapping(prediction: object) -> dict[str, object]:
    if isinstance(prediction, Mapping):
        return {str(key): item for key, item in prediction.items()}
    for method_name in ("toDict", "to_dict", "model_dump"):
        method = getattr(prediction, method_name, None)
        if callable(method):
            try:
                payload = method()
            except Exception:
                continue
            if isinstance(payload, Mapping):
                return dict(payload)
    return {}


def _configure_provider() -> dict[str, object]:
    try:
        import dspy
        from dspx.provider_registry import create_from_env, ensure_default_providers

        ensure_default_providers()
        lm = create_from_env(default="dspy-lm-auth")
        dspy.configure(lm=lm)
        return {
            "status": "configured",
            "provider": getattr(lm, "model", type(lm).__name__),
        }
    except Exception as exc:
        return {
            "status": "unavailable",
            "error": {"type": type(exc).__name__, "message": str(exc)},
        }


def _strip_json_fence(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        if len(lines) >= 2:
            return "\n".join(lines[1:-1]).strip()
    return text


def _parse_generated_json(raw: object, *, field: str) -> Any:
    if not isinstance(raw, str):
        return raw
    text = _strip_json_fence(raw)
    if not text:
        raise ValueError(f"{field} is empty")
    return json.loads(text)


def _validate_pdf_transition_review_outputs(
    observed: Mapping[str, object],
) -> list[str]:
    errors: list[str] = []
    parsed: dict[str, Any] = {}
    for field in (
        "section_units_json",
        "distillation_frames_json",
        "evidence_cards_json",
        "merge_create_proposals_json",
        "review_packet_json",
        "artifact_contract_manifest_json",
    ):
        if field not in observed:
            errors.append(f"missing required PDF transition output: {field}")
            continue
        try:
            parsed[field] = _parse_generated_json(observed[field], field=field)
        except Exception as exc:
            errors.append(f"{field} is not valid JSON: {type(exc).__name__}: {exc}")
    contract = parsed.get("artifact_contract_manifest_json")
    if (
        not isinstance(contract, Mapping)
        or contract.get("canonical_mutation_performed") is not False
    ):
        errors.append(
            "artifact_contract_manifest_json must state canonical_mutation_performed=false"
        )
    review = parsed.get("review_packet_json")
    if (
        isinstance(review, Mapping)
        and review.get("canonical_mutation_performed") is not False
    ):
        errors.append(
            "review_packet_json must state canonical_mutation_performed=false"
        )
    proposals = parsed.get("merge_create_proposals_json")
    if not isinstance(proposals, list):
        errors.append("merge_create_proposals_json must be a JSON array")
    else:
        for index, proposal in enumerate(proposals):
            if not isinstance(proposal, Mapping):
                errors.append(f"proposal {index} is not an object")
                continue
            proposal_payload = cast(Mapping[str, Any], proposal)
            if proposal_payload.get("canonical_mutation_allowed") is not False:
                errors.append(
                    f"proposal {index} must state canonical_mutation_allowed=false"
                )
            if proposal_payload.get("review_required") is not True:
                errors.append(f"proposal {index} must state review_required=true")
    return errors


def _write_observed_output_files(
    outdir: Path, observed: Mapping[str, object]
) -> list[str]:
    written: list[str] = []
    for field, value in observed.items():
        path = outdir / field
        text = (
            value
            if isinstance(value, str)
            else json.dumps(value, ensure_ascii=False, indent=2)
        )
        path.write_text(str(text).rstrip() + "\n", encoding="utf-8")
        written.append(path.name)
    return sorted(written)


def _runtime_id(*, manifest_hash: str, inputs_hash: str, contract_mode: str) -> str:
    return (
        "prog-run-"
        + _sha256_text(
            json.dumps(
                {
                    "manifest_hash": manifest_hash,
                    "inputs_hash": inputs_hash,
                    "contract_mode": contract_mode,
                },
                sort_keys=True,
            )
        )[:16]
    )


def _oracle_evidence(
    *,
    manifest_identity: Mapping[str, str | None],
    runtime_episode_id: str,
    behavior_results: Mapping[str, Any],
    behavior_results_hash: str,
    inputs_hash: str,
    contract_mode: str,
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    intent = _safe_mapping(manifest.get("intent"))
    raw_summary = behavior_results.get("summary")
    summary = _safe_mapping(raw_summary)
    raw_inputs = behavior_results.get("input_fields")
    raw_outputs = behavior_results.get("output_fields")
    input_fields = (
        [str(item) for item in raw_inputs] if isinstance(raw_inputs, list) else []
    )
    output_fields = (
        [str(item) for item in raw_outputs] if isinstance(raw_outputs, list) else []
    )
    status = str(summary.get("status") or "unknown")
    failure_modes: list[dict[str, Any]] = []
    if status not in {"executed", "executed_valid_review_only", "passed"}:
        failure_modes.append(
            {
                "index": 0,
                "status": status,
                "signals": [str(item) for item in behavior_results.get("notes") or []]
                if isinstance(behavior_results.get("notes"), list)
                else [],
                "mismatched_outputs": [],
                "missing_observed_outputs": [],
            }
        )
    identity = {key: value for key, value in manifest_identity.items() if value}
    identity["runtime_episode_id"] = runtime_episode_id
    oracle_facets = {
        "task_type": str(intent.get("task_type") or "single_module"),
        "metric": f"runtime_episode:{contract_mode}",
        "input_fields": input_fields,
        "output_fields": output_fields,
        "behavior_status": status,
        "status_counts": _safe_mapping(summary.get("status_counts")),
        "has_examples": True,
        "example_count": 1,
        "has_dataset_splits": False,
        "dataset_split_count": 0,
        "evidence_source_count": 1,
        "behavior_source_kinds": ["runtime_inputs"],
        "total_evaluation_count": 1,
        "failure_mode_count": len(failure_modes),
        "has_failures": bool(failure_modes),
        "runtime_episode_id": runtime_episode_id,
        "contract_mode": contract_mode,
    }
    objective = str(
        intent.get("objective")
        or _safe_mapping(behavior_results.get("intent")).get("objective")
        or ""
    )
    oracle_text = "\n".join(
        [
            "schema_version=program-oracle-evidence-v1",
            "evidence_kind=program_execution_episode",
            f"intent.name={intent.get('name') or behavior_results.get('intent_name') or ''}",
            f"intent.objective={objective}",
            f"intent.task_type={oracle_facets['task_type']}",
            f"intent.metric={oracle_facets['metric']}",
            "io.inputs=" + ",".join(input_fields),
            "io.outputs=" + ",".join(output_fields),
            f"identity.runtime_episode_id={runtime_episode_id}",
            f"identity.candidate_id={identity.get('candidate_id')}",
            f"identity.assembly_id={identity.get('assembly_id')}",
            f"behavior.status={status}",
            "behavior.source_kinds=runtime_inputs",
            "behavior.example_count=1",
            "authority=oracle_readability_only_non_authoritative; oracle_ranking=false; "
            "oracle_pruning=false; oracle_promotion=false; governance_authority=false; external_mutation=false",
        ]
    )
    return {
        "schema_version": PROGRAM_ORACLE_EVIDENCE_SCHEMA,
        "evidence_kind": "program_execution_episode",
        "authority": "oracle_readability_only_non_authoritative",
        "non_authority": {
            "oracle_ranking": False,
            "oracle_pruning": False,
            "oracle_promotion": False,
            "governance_authority": False,
            "external_mutation": False,
        },
        "identity": identity,
        "intent": {
            "name": intent.get("name") or behavior_results.get("intent_name"),
            "objective": objective,
            "task_type": oracle_facets["task_type"],
            "metric": oracle_facets["metric"],
            "constraints": list(
                intent.get("constraints")
                or _safe_mapping(behavior_results.get("intent")).get("constraints")
                or []
            ),
        },
        "io": {"inputs": input_fields, "outputs": output_fields},
        "behavior": {
            "result_path": "behavior_results.json",
            "result_hash": behavior_results_hash,
            "summary": dict(summary),
            "statuses": _safe_mapping(summary.get("status_counts")),
            "example_count": 1,
            "evaluation_sources": [
                {
                    "kind": "runtime_inputs",
                    "source_kind": "runtime_inputs",
                    "input_artifact_path": "runtime_inputs.json",
                    "input_artifact_hash": inputs_hash,
                    "behavior_results_path": "behavior_results.json",
                    "behavior_results_hash": behavior_results_hash,
                }
            ],
            "evidence_summary": dict(summary),
            "source_statuses": [status],
            "failure_modes": failure_modes,
        },
        "oracle_facets": oracle_facets,
        "oracle_text": oracle_text,
        "source_artifacts": [
            {
                "kind": "runtime_inputs",
                "path": "runtime_inputs.json",
                "content_hash": inputs_hash,
                "source_kind": "runtime_inputs",
            },
            {
                "kind": "behavior_results",
                "path": "behavior_results.json",
                "content_hash": behavior_results_hash,
                "source_kind": "runtime_inputs",
            },
        ],
    }


def run_program_runtime_episode(
    *,
    manifest_path: Path,
    inputs_path: Path,
    outdir: Path,
    contract_mode: str = "none",
    skip_oracle_index: bool = False,
    publication_preflight_out: Path | None = None,
    publication_target: str | None = None,
    publication_label: str | None = None,
    publisher_id: str | None = None,
    publisher_role: str | None = None,
    publisher_assertion: str | None = None,
    redaction_status: str | None = None,
    retention_class: str | None = None,
) -> dict[str, Any]:
    """Run an existing generated program candidate on explicit runtime inputs.

    The generated candidate is treated as an immutable behavior artifact. This
    function writes a separate runtime episode directory with behavior evidence,
    Oracle-readable evidence, a manifest copy that points at the runtime evidence,
    and optional candidate-local Oracle indexing/reporting. It does not mutate AK,
    governance, canonical notes, or shared Oracle unless a later explicit publish
    command consumes the preflight.
    """

    if contract_mode not in CONTRACT_MODES:
        raise ValueError(
            "contract_mode must be one of: " + ", ".join(sorted(CONTRACT_MODES))
        )
    source_manifest_path = manifest_path.expanduser().resolve()
    candidate_root = source_manifest_path.parent
    manifest = _validated_manifest(source_manifest_path)
    manifest_identity = _manifest_identity(manifest)
    runtime_inputs = _load_inputs(inputs_path)
    materialized_runtime_inputs = _materialize_runtime_inputs(
        runtime_inputs, inputs_path=inputs_path
    )
    source_inputs_text = _json_text({"inputs": runtime_inputs})
    inputs_hash = _sha256_text(source_inputs_text)
    manifest_hash = _sha256_file(source_manifest_path)
    runtime_episode_id = _runtime_id(
        manifest_hash=manifest_hash,
        inputs_hash=inputs_hash,
        contract_mode=contract_mode,
    )

    root = outdir.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    (root / "runtime_inputs.json").write_text(source_inputs_text, encoding="utf-8")

    provider = _configure_provider()
    observed: dict[str, object] = {}
    notes: list[str] = []
    error: dict[str, str] | None = None
    status = "error"
    input_fields: list[str] = []
    output_fields: list[str] = []
    intent_summary: dict[str, object] = {}
    try:
        with _generated_program_module(candidate_root) as program_module:
            spec = program_module.io_spec()
            input_fields = [str(item) for item in spec.get("inputs") or []]
            output_fields = [str(item) for item in spec.get("outputs") or []]
            intent_summary = dict(program_module.intent_summary())
            missing_inputs = [
                name for name in input_fields if name not in runtime_inputs
            ]
            if missing_inputs:
                raise ValueError(
                    "runtime inputs missing declared fields: "
                    + ", ".join(missing_inputs)
                )
            program = program_module.build_program()
            prediction = program(
                **{name: materialized_runtime_inputs[name] for name in input_fields}
            )
            mapped = _prediction_mapping(prediction)
            for name in output_fields:
                if name in mapped:
                    observed[name] = _jsonable(mapped[name])
                elif hasattr(prediction, name):
                    observed[name] = _jsonable(getattr(prediction, name))
            missing_outputs = [
                name
                for name in output_fields
                if name not in observed or observed[name] in (None, "")
            ]
            if missing_outputs:
                status = "degraded_missing_outputs"
                notes.append("missing outputs: " + ", ".join(missing_outputs))
            elif contract_mode == "pdf_transition_review":
                gate_errors = _validate_pdf_transition_review_outputs(observed)
                if gate_errors:
                    status = "failed_boundary"
                    notes.extend(gate_errors)
                else:
                    status = "executed_valid_review_only"
            else:
                status = "executed"
    except Exception as exc:
        error = {"type": type(exc).__name__, "message": str(exc)}
        notes.append(str(exc))

    output_files = _write_observed_output_files(root, observed)
    record: dict[str, object] = {
        "index": 0,
        "source_kind": "runtime_inputs",
        "status": status,
        "inputs": _jsonable(runtime_inputs),
        "observed_outputs": _jsonable(observed),
        "notes": list(notes),
    }
    if error is not None:
        record["error"] = error
    status_counts = {status: 1}
    behavior_results: dict[str, Any] = {
        "schema_version": PROGRAM_BEHAVIOR_RESULTS_SCHEMA,
        "intent": intent_summary,
        "intent_name": intent_summary.get("name"),
        "input_fields": input_fields,
        "output_fields": output_fields,
        "provider": provider,
        "examples": [record],
        "summary": {
            "total": 1,
            "passed": 0,
            "failed": 1 if status.startswith("failed") or status == "error" else 0,
            "error": 1 if status == "error" else 0,
            "degraded": 1 if status.startswith("degraded") else 0,
            "executed": 1
            if status in {"executed", "executed_valid_review_only"}
            else 0,
            "status_counts": status_counts,
            "status": status,
        },
        "runtime_episode_id": runtime_episode_id,
        "authority": "behavior_evidence_only_non_authoritative",
        "non_authority": {
            "optimization_authority": False,
            "promotion_authority": False,
            "oracle_ranking": False,
            "oracle_pruning": False,
            "oracle_promotion": False,
            "governance_authority": False,
            "external_mutation": False,
            "external_authority_mutated": False,
            "winner_selection": False,
        },
    }
    behavior_path = root / "behavior_results.json"
    behavior_path.write_text(_json_text(behavior_results), encoding="utf-8")
    behavior_hash = _sha256_file(behavior_path)

    runtime_manifest = dict(manifest)
    runtime_manifest["source_candidate_manifest"] = {
        "path": str(source_manifest_path),
        "sha256": manifest_hash,
    }
    runtime_manifest["runtime_episode"] = {
        "schema_version": PROGRAM_RUNTIME_EPISODE_SCHEMA,
        "runtime_episode_id": runtime_episode_id,
        "inputs_path": "runtime_inputs.json",
        "inputs_sha256": inputs_hash,
        "behavior_results_path": "behavior_results.json",
        "behavior_results_sha256": behavior_hash,
        "contract_mode": contract_mode,
    }
    runtime_manifest["oracle_readability"] = {
        "schema_version": PROGRAM_ORACLE_EVIDENCE_SCHEMA,
        "path": "oracle_evidence.json",
    }
    runtime_manifest_path = root / "manifest.json"
    runtime_manifest_path.write_text(_json_text(runtime_manifest), encoding="utf-8")

    oracle_evidence = _oracle_evidence(
        manifest_identity=manifest_identity,
        runtime_episode_id=runtime_episode_id,
        behavior_results=behavior_results,
        behavior_results_hash=behavior_hash,
        inputs_hash=inputs_hash,
        contract_mode=contract_mode,
        manifest=manifest,
    )
    oracle_path = root / "oracle_evidence.json"
    oracle_path.write_text(_json_text(oracle_evidence), encoding="utf-8")

    runtime_episode = {
        "schema_version": PROGRAM_RUNTIME_EPISODE_SCHEMA,
        "runtime_episode_id": runtime_episode_id,
        "status": status,
        "contract_mode": contract_mode,
        "candidate_manifest_path": str(source_manifest_path),
        "manifest_path": str(runtime_manifest_path),
        "input_path": str(inputs_path.expanduser().resolve()),
        "output_files": output_files,
        "artifact_hashes": {
            "source_manifest_sha256": manifest_hash,
            "runtime_inputs_sha256": inputs_hash,
            "behavior_results_sha256": behavior_hash,
            "oracle_evidence_sha256": _sha256_file(oracle_path),
        },
        "non_authority": {
            "promotion_authority": False,
            "activation_authority": False,
            "governance_mutated": False,
            "external_authority_mutated": False,
            "shared_oracle_mutated": False,
        },
    }
    (root / "runtime_episode.json").write_text(
        _json_text(runtime_episode), encoding="utf-8"
    )

    oracle_index_result: dict[str, Any] | None = None
    oracle_report: dict[str, Any] | None = None
    index_path = root / "oracle" / "coordinates.db"
    if not skip_oracle_index:
        oracle_index_result = index_program_oracle_evidence_path(
            root, index_path=index_path, limit=1000
        )
        oracle_report = build_program_oracle_evidence_report(
            index_path=index_path, limit=1000
        )
        (root / "program_oracle_report.json").write_text(
            _json_text(oracle_report), encoding="utf-8"
        )

    publication_preflight: dict[str, Any] | None = None
    if publication_preflight_out is not None:
        if not all(
            [
                publication_target,
                publication_label,
                publisher_id,
                publisher_role,
                publisher_assertion,
                redaction_status,
                retention_class,
            ]
        ):
            raise ValueError(
                "publication preflight requires target, label, publisher fields, redaction_status, and retention_class"
            )
        publication_preflight = build_program_oracle_publication_preflight(
            manifest_path=runtime_manifest_path,
            target=str(publication_target),
            publication_label=str(publication_label),
            publisher_id=str(publisher_id),
            publisher_role=str(publisher_role),
            publisher_assertion=str(publisher_assertion),
            redaction_status=str(redaction_status),
            retention_class=str(retention_class),
        )
        write_program_oracle_publication_preflight(
            publication_preflight, publication_preflight_out
        )

    return {
        "schema_version": "program-runtime-episode-workflow-v1",
        "status": "ok"
        if status in {"executed", "executed_valid_review_only"}
        and (skip_oracle_index or (oracle_index_result or {}).get("errors") == 0)
        else "degraded",
        "runtime_episode_id": runtime_episode_id,
        "candidate_manifest_path": str(source_manifest_path),
        "runtime_root": str(root),
        "manifest_path": str(runtime_manifest_path),
        "behavior_results_path": str(behavior_path),
        "oracle_evidence_path": str(oracle_path),
        "oracle_index_path": str(index_path) if not skip_oracle_index else None,
        "oracle_report_path": str(root / "program_oracle_report.json")
        if oracle_report is not None
        else None,
        "publication_preflight_path": str(publication_preflight_out)
        if publication_preflight_out is not None
        else None,
        "steps": {
            "runtime_execution": {
                "status": status,
                "provider": provider,
                "notes": notes,
                "output_files": output_files,
            },
            "oracle_index": {
                "status": "skipped"
                if skip_oracle_index
                else (
                    "ok"
                    if (oracle_index_result or {}).get("errors") == 0
                    else "degraded"
                ),
                "result": oracle_index_result,
            },
            "oracle_report": {
                "status": "skipped"
                if oracle_report is None
                else oracle_report.get("status"),
                "total_records": None
                if oracle_report is None
                else oracle_report.get("total_records"),
            },
            "publication_preflight": {
                "status": "skipped"
                if publication_preflight is None
                else publication_preflight.get("status")
            },
        },
        "effect": {
            "candidate_manifest_mutated": False,
            "runtime_episode_written": True,
            "behavior_results_written": True,
            "oracle_evidence_written": True,
            "oracle_index_mutated": not skip_oracle_index,
            "oracle_index_scope": "runtime-episode local explicit path"
            if not skip_oracle_index
            else "none",
            "oracle_report_written": oracle_report is not None,
            "oracle_publication_preflight_written": publication_preflight is not None,
            "shared_oracle_mutated": False,
            "ak_called": False,
            "external_authority_mutated": False,
            "governance_mutated": False,
            "canonical_notes_mutated": False,
            "promotion_applied": False,
        },
        "non_authority": runtime_episode["non_authority"],
    }
