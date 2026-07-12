# summary: "Runs or resumes receipt-bound Oracle semantic analysis for a validated program runtime episode."
# read_when:
#   - "Changing runtime-to-Oracle semantic handoff, semantic sidecar resume behavior, or evidence binding."

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any, Mapping

from dspx.redaction import sanitize_diagnostic_text

from dspx.services.program_oracle_semantic_backend import (
    resolve_program_oracle_semantic_backend,
)
from dspx.services.program_oracle_semantic_contract import OracleSemanticRequest
from dspx.services.program_runtime_episode import (
    load_validated_program_runtime_episode_bundle,
)
from dspx.services.run_replay_service import check_run_receipt

PROGRAM_RUNTIME_ORACLE_SEMANTIC_SCHEMA = "program-runtime-oracle-semantic-v1"
DEFAULT_PROGRAM_RUNTIME_ORACLE_SEMANTIC_NAME = "program_oracle_semantic.json"
_MAX_JSON_BYTES = 500_000


class ProgramRuntimeOracleSemanticError(ValueError):
    """Raised when runtime evidence or an existing semantic sidecar fails closed."""


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ProgramRuntimeOracleSemanticError(
            f"runtime Oracle semantic value must be canonical JSON: {exc}"
        ) from exc


def _json_text(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_json(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _read_json_object(path: Path, *, label: str) -> dict[str, Any]:
    target = path.expanduser().absolute()
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(target, flags)
    except OSError as exc:
        raise ProgramRuntimeOracleSemanticError(
            f"{label} must be an existing regular non-symlink file: {target}"
        ) from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ProgramRuntimeOracleSemanticError(
                f"{label} must be a regular file: {target}"
            )
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            raw = stream.read(_MAX_JSON_BYTES + 1)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if len(raw) > _MAX_JSON_BYTES:
        raise ProgramRuntimeOracleSemanticError(
            f"{label} exceeds the {_MAX_JSON_BYTES}-byte safety bound"
        )
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProgramRuntimeOracleSemanticError(
            f"{label} must be valid UTF-8 JSON: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise ProgramRuntimeOracleSemanticError(f"{label} must contain one JSON object")
    return {str(key): value for key, value in payload.items()}


def _write_private_json_exclusive(path: Path, payload: Mapping[str, Any]) -> None:
    target = path.expanduser().absolute()
    target.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(target, flags, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            descriptor = -1
            stream.write(_json_text(payload))
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    directory = os.open(target.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def _replace_private_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    target = path.expanduser().absolute()
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    try:
        _write_private_json_exclusive(temporary, payload)
        os.replace(temporary, target)
        directory = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def _status_projection(value: object) -> dict[str, Any]:
    mapping = dict(value) if isinstance(value, Mapping) else {}
    return {
        key: mapping.get(key)
        for key in (
            "status",
            "total",
            "passed",
            "failed",
            "error",
            "degraded",
            "executed",
        )
        if key in mapping
    }


def _behavior_projection(behavior_results: Mapping[str, Any]) -> dict[str, Any]:
    """Project only structural behavior facts; never transmit raw inputs/outputs."""

    examples: list[dict[str, Any]] = []
    raw_examples = behavior_results.get("examples")
    if isinstance(raw_examples, list):
        for raw in raw_examples:
            if not isinstance(raw, Mapping):
                continue
            outputs = raw.get("observed_outputs")
            output_mapping = dict(outputs) if isinstance(outputs, Mapping) else {}
            error = raw.get("error")
            error_mapping = dict(error) if isinstance(error, Mapping) else {}
            notes = raw.get("notes")
            examples.append(
                {
                    "index": raw.get("index"),
                    "status": raw.get("status"),
                    "execution_status": raw.get("execution_status"),
                    "output_fields": sorted(str(key) for key in output_mapping),
                    "observed_outputs_sha256": _sha256_json(output_mapping),
                    "quality_evaluation": _status_projection(
                        raw.get("quality_evaluation")
                    ),
                    "notes_count": len(notes) if isinstance(notes, list) else 0,
                    "error_type": error_mapping.get("type"),
                }
            )
    provider = behavior_results.get("provider")
    provider_mapping = dict(provider) if isinstance(provider, Mapping) else {}
    return {
        "summary": _status_projection(behavior_results.get("summary")),
        "execution_status": behavior_results.get("execution_status"),
        "quality_evaluation": _status_projection(
            behavior_results.get("quality_evaluation")
        ),
        "provider_status": provider_mapping.get("status"),
        "examples": examples,
        "authority": behavior_results.get("authority"),
    }


def _request_from_runtime(
    *,
    runtime_episode: Mapping[str, Any],
    behavior_results: Mapping[str, Any],
    oracle_evidence: Mapping[str, Any],
    receipt_path: Path,
    receipt_check: Mapping[str, Any],
) -> OracleSemanticRequest:
    intent = behavior_results.get("intent")
    intent_mapping = dict(intent) if isinstance(intent, Mapping) else {}
    runtime_episode_id = str(runtime_episode.get("runtime_episode_id") or "").strip()
    objective = str(intent_mapping.get("objective") or "").strip()
    if not objective:
        objective = f"Analyze receipt-bound runtime behavior for {runtime_episode_id}"
    quality_criteria = intent_mapping.get("quality_criteria")
    quality_contract = (
        {"criteria": quality_criteria} if quality_criteria is not None else None
    )
    evidence = {
        "runtime_receipt": {
            "path": str(receipt_path),
            "sha256": _sha256_file(receipt_path),
            "check_status": receipt_check.get("status"),
            "checks": receipt_check.get("checks") or {},
        },
        "runtime_episode": {
            key: runtime_episode.get(key)
            for key in (
                "runtime_episode_id",
                "status",
                "execution_status",
                "contract_mode",
                "artifact_hashes",
                "non_authority",
            )
        },
        "behavior": _behavior_projection(behavior_results),
        "oracle_evidence": {
            "schema_version": oracle_evidence.get("schema_version"),
            "runtime_episode_id": oracle_evidence.get("runtime_episode_id"),
            "coordinates_sha256": _sha256_json(
                oracle_evidence.get("coordinates") or {}
            ),
            "authority": oracle_evidence.get("authority"),
        },
    }
    return OracleSemanticRequest(
        objective=objective,
        evidence=evidence,
        quality_contract=quality_contract,
    )


def _source_binding(
    *,
    runtime_episode_path: Path,
    behavior_results_path: Path,
    oracle_evidence_path: Path,
    runtime_receipt_path: Path,
) -> dict[str, Any]:
    return {
        "runtime_episode": {
            "path": str(runtime_episode_path),
            "sha256": _sha256_file(runtime_episode_path),
        },
        "behavior_results": {
            "path": str(behavior_results_path),
            "sha256": _sha256_file(behavior_results_path),
        },
        "oracle_evidence": {
            "path": str(oracle_evidence_path),
            "sha256": _sha256_file(oracle_evidence_path),
        },
        "runtime_receipt": {
            "path": str(runtime_receipt_path),
            "sha256": _sha256_file(runtime_receipt_path),
        },
    }


def _resume_existing(
    *,
    out_path: Path,
    source_binding: Mapping[str, Any],
    request_sha256: str,
) -> dict[str, Any]:
    payload = _read_json_object(out_path, label="runtime Oracle semantic sidecar")
    if payload.get("schema_version") != PROGRAM_RUNTIME_ORACLE_SEMANTIC_SCHEMA:
        raise ProgramRuntimeOracleSemanticError(
            "existing runtime Oracle semantic sidecar schema mismatch"
        )
    if payload.get("source_binding") != source_binding:
        raise ProgramRuntimeOracleSemanticError(
            "existing runtime Oracle semantic sidecar source binding drifted"
        )
    if payload.get("request_sha256") != request_sha256:
        raise ProgramRuntimeOracleSemanticError(
            "existing runtime Oracle semantic sidecar request hash drifted"
        )
    return payload


def run_program_runtime_oracle_semantics(
    *,
    runtime_episode_path: Path,
    out_path: Path | None = None,
) -> dict[str, Any]:
    """Analyze a validated runtime episode once, or reuse its bound sidecar.

    Existing success and failure sidecars are both reused. This avoids silently
    replaying a live model attempt whose transport effects may be indeterminate.
    A deliberate new attempt must use a new output path.
    """

    episode_path = runtime_episode_path.expanduser().resolve()
    episode_declaration = _read_json_object(
        episode_path, label="program runtime Oracle semantic input"
    )
    candidate_manifest_path = (
        Path(str(episode_declaration.get("candidate_manifest_path") or ""))
        .expanduser()
        .resolve()
    )
    candidate_manifest = _read_json_object(
        candidate_manifest_path, label="program runtime source candidate manifest"
    )
    candidate_manifest_sha256 = _sha256_file(candidate_manifest_path)
    bundle = load_validated_program_runtime_episode_bundle(
        runtime_episode_path=episode_path,
        expected_manifest_path=candidate_manifest_path,
        expected_manifest=candidate_manifest,
        expected_manifest_sha256=candidate_manifest_sha256,
        label="program runtime Oracle semantic input",
        error_type=ProgramRuntimeOracleSemanticError,
    )
    root = episode_path.parent
    receipt_path = episode_path.with_name(f"{episode_path.name}.meta.json")
    receipt_check = check_run_receipt(receipt_path)
    if receipt_check.get("status") != "ok":
        raise ProgramRuntimeOracleSemanticError(
            "program runtime receipt must pass replay validation before semantic analysis"
        )
    oracle_evidence_path = root / "oracle_evidence.json"
    oracle_evidence = _read_json_object(
        oracle_evidence_path, label="program runtime Oracle evidence"
    )
    expected_oracle_hash = (bundle.runtime_episode.get("artifact_hashes") or {}).get(
        "oracle_evidence_sha256"
    )
    if expected_oracle_hash != _sha256_file(oracle_evidence_path):
        raise ProgramRuntimeOracleSemanticError(
            "program runtime Oracle evidence hash does not match runtime episode"
        )
    request = _request_from_runtime(
        runtime_episode=bundle.runtime_episode,
        behavior_results=bundle.behavior_results,
        oracle_evidence=oracle_evidence,
        receipt_path=receipt_path,
        receipt_check=receipt_check,
    )
    source_binding = _source_binding(
        runtime_episode_path=bundle.runtime_episode_path,
        behavior_results_path=bundle.behavior_results_path,
        oracle_evidence_path=oracle_evidence_path,
        runtime_receipt_path=receipt_path,
    )
    target = (
        out_path.expanduser().absolute()
        if out_path is not None
        else root / DEFAULT_PROGRAM_RUNTIME_ORACLE_SEMANTIC_NAME
    )
    if target.exists():
        return _resume_existing(
            out_path=target,
            source_binding=source_binding,
            request_sha256=request.request_sha256,
        )

    non_authority = {
        "advisory_local_evidence_only": True,
        "promotion_authority": False,
        "activation_authority": False,
        "winner_selection": False,
        "governance_mutated": False,
    }
    attempt: dict[str, Any] = {
        "schema_version": PROGRAM_RUNTIME_ORACLE_SEMANTIC_SCHEMA,
        "status": "degraded",
        "runtime_episode_id": bundle.runtime_episode.get("runtime_episode_id"),
        "request_sha256": request.request_sha256,
        "source_binding": source_binding,
        "semantic_result": {
            "execution_status": "effect_indeterminate",
            "executed_provider": None,
            "executed_model": None,
            "live_call_succeeded": False,
            "error": "semantic attempt marker exists without a terminal result",
        },
        "effect": {
            "semantic_backend_invoked": None,
            "effect_disposition": "indeterminate",
            "live_call_succeeded": None,
            "sidecar_written": True,
            "runtime_evidence_mutated": False,
            "shared_oracle_mutated": False,
            "external_authority_mutated": False,
        },
        "non_authority": non_authority,
    }
    try:
        _write_private_json_exclusive(target, attempt)
    except FileExistsError:
        return _resume_existing(
            out_path=target,
            source_binding=source_binding,
            request_sha256=request.request_sha256,
        )

    try:
        backend = resolve_program_oracle_semantic_backend()
        result = backend.analyze(request)
        result_payload = result.to_dict()
        semantic_ok = result.execution_status in {"succeeded", "replayed_fixture"}
        payload: dict[str, Any] = {
            **attempt,
            "status": "ok" if semantic_ok else "degraded",
            "semantic_result": result_payload,
            "effect": {
                **attempt["effect"],
                "semantic_backend_invoked": True,
                "effect_disposition": "terminal_result_recorded",
                "live_call_succeeded": result.live_call_succeeded,
            },
        }
    except Exception as exc:
        payload = {
            **attempt,
            "semantic_result": {
                "execution_status": "effect_indeterminate",
                "executed_provider": None,
                "executed_model": None,
                "live_call_succeeded": False,
                "error": sanitize_diagnostic_text(str(exc)),
            },
            "effect": {
                **attempt["effect"],
                "semantic_backend_invoked": True,
                "effect_disposition": "indeterminate",
            },
        }
    _replace_private_json_atomic(target, payload)
    return payload
