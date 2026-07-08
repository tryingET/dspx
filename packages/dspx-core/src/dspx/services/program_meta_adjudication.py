from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from dspx.services.artifact_boundary import prepare_sidecar_output_path
from dspx.services.program_evidence_adjudication_validation import (
    validate_program_evidence_adjudication_contract,
)
from dspx.services.program_oracle_publication import (
    ProgramOraclePublicationError,
    validate_program_oracle_publication_preflight_contract,
    validate_program_oracle_publication_receipt_contract,
)
from dspx.services.program_runtime_episode import (
    PROGRAM_RUNTIME_EPISODE_SCHEMA,
    validate_program_runtime_episode_contract,
)
from dspx.services.program_refinement import (
    ProgramRefinementError,
    load_program_manifest,
)

PROGRAM_META_ADJUDICATION_PLAN_SCHEMA = "program-meta-adjudication-plan-v1"
PROGRAM_TARGET_PROFILE_SCHEMA = "program-target-profile-v1"
PROGRAM_JURY_REQUIREMENTS_SCHEMA = "program-jury-requirements-v1"
PROGRAM_META_JURY_SELECTION_SCHEMA = "program-meta-jury-selection-v1"
PROGRAM_JURY_VERIFICATION_SCHEMA = "program-jury-verification-v1"
PROGRAM_ADJUDICATOR_FORMATION_SCHEMA = "program-adjudicator-formation-v1"
PROGRAM_ADJUDICATOR_VERIFICATION_SCHEMA = "program-adjudicator-verification-v1"
PROGRAM_ADJUDICATOR_DELEGATION_SCHEMA = "program-adjudicator-delegation-v1"
PROGRAM_EVIDENCE_ADJUDICATION_SCHEMA = "program-evidence-adjudication-v1"
PROGRAM_ADJUDICATION_BEHAVIOR_TRACE_SCHEMA = "program-adjudication-behavior-trace-v1"
PROGRAM_ADJUDICATION_GEPA_EXAMPLE_SCHEMA = "program-adjudication-gepa-example-v1"

_EXPECTED_SIDECAR_SCHEMAS = {
    "behavior_results": "program-behavior-results-v1",
    "behavior_episode": "program-behavior-episode-v1",
    "runtime_episode": PROGRAM_RUNTIME_EPISODE_SCHEMA,
    "oracle_report": "program-oracle-evidence-report-v1",
    "oracle_publication_receipt": "program-oracle-shared-publication-receipt-v1",
    "jury_results": "program-jury-results-v2",
    "review": "program-promotion-review-refined-v1",
    "decision_record": "program-promotion-decision-record-v1",
    "activation_packet": "generated-cognition-program-production-activation-packet-v1",
    "generation_target_contract": "gen-target-contract-v1",
    "generation_fitness_suite": "gen-fitness-suite-v1",
    "generation_gate_preflight": "gen-generation-gate-preflight-v1",
    "generation_traceability": "gen-traceability-v1",
    "generation_fitness_results": "gen-fitness-results-v1",
    "target_profile": PROGRAM_TARGET_PROFILE_SCHEMA,
    "jury_requirements": PROGRAM_JURY_REQUIREMENTS_SCHEMA,
    "meta_jury_selection": PROGRAM_META_JURY_SELECTION_SCHEMA,
    "jury_verification": PROGRAM_JURY_VERIFICATION_SCHEMA,
    "program_adjudicator_formation": PROGRAM_ADJUDICATOR_FORMATION_SCHEMA,
    "program_adjudicator_verification": PROGRAM_ADJUDICATOR_VERIFICATION_SCHEMA,
    "program_adjudicator_delegation": PROGRAM_ADJUDICATOR_DELEGATION_SCHEMA,
    "program_evidence_adjudication": PROGRAM_EVIDENCE_ADJUDICATION_SCHEMA,
    "adjudication_behavior_trace": PROGRAM_ADJUDICATION_BEHAVIOR_TRACE_SCHEMA,
    "adjudication_gepa_example": PROGRAM_ADJUDICATION_GEPA_EXAMPLE_SCHEMA,
}

_DEFAULT_SIDECAR_FILES = {
    "behavior_results": "behavior_results.json",
    "behavior_episode": "behavior_episode.json",
    "runtime_episode": "runtime_episode.json",
    "oracle_report": "program_oracle_report.json",
    "oracle_publication_receipt": "program_oracle_publication_receipt.json",
    "jury_results": "jury_results.json",
    "review": "promotion_review_refined.json",
    "decision_record": "promotion_decision_record.json",
    "activation_packet": "activation_packet.json",
    "generation_target_contract": "generation_target_contract.json",
    "generation_fitness_suite": "generation_fitness_suite.json",
    "generation_gate_preflight": "generation_gate_preflight.json",
    "generation_traceability": "generation_traceability.json",
    "generation_fitness_results": "generation_fitness_results.json",
    "target_profile": "target_profile.json",
    "jury_requirements": "jury_requirements.json",
    "meta_jury_selection": "meta_jury_selection.json",
    "jury_verification": "jury_verification.json",
    "program_adjudicator_formation": "program_adjudicator_formation.json",
    "program_adjudicator_verification": "program_adjudicator_verification.json",
    "program_adjudicator_delegation": "program_adjudicator_delegation.json",
    "program_evidence_adjudication": "program_evidence_adjudication.json",
    "adjudication_behavior_trace": "adjudication_behavior_trace.json",
    "adjudication_gepa_example": "adjudication_gepa_example.json",
}

_NON_AUTHORITY = {
    "activation_authority": False,
    "promotion_authority": False,
    "oracle_authority": False,
    "governance_authority": False,
    "external_authority": False,
    "external_mutation": False,
}

_EFFECT = {
    "candidate_files_mutated": False,
    "canonical_target_mutated": False,
    "ak_mutated": False,
    "governance_mutated": False,
    "oracle_index_mutated": False,
    "shared_oracle_mutated": False,
    "provider_called": False,
}


class ProgramMetaAdjudicationError(ValueError):
    """Raised when meta-adjudication planning inputs are invalid."""


def _safe_mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items()}


def _safe_list(value: object) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _first_text(*values: object) -> str | None:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return None


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _slug(value: str) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug or "unspecified"


def _json_text(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _prepare_guarded_sidecar_output(
    out_path: Path, *, payload: Mapping[str, Any], artifact_label: str
) -> Path:
    try:
        return prepare_sidecar_output_path(
            out_path,
            payload=payload,
            artifact_label=artifact_label,
            payload_artifact_root_policy="forbid",
        )
    except ValueError as exc:
        raise ProgramMetaAdjudicationError(str(exc)) from exc


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.expanduser().read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProgramMetaAdjudicationError(f"{label} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ProgramMetaAdjudicationError(
            f"{label} must be valid JSON: {path}"
        ) from exc
    if not isinstance(payload, dict):
        raise ProgramMetaAdjudicationError(
            f"{label} must contain a JSON object: {path}"
        )
    return payload


def _load_hash_bound_ref(
    ref: object, *, expected_schema: str, label: str
) -> tuple[bool, str, dict[str, Any] | None]:
    ref_map = _safe_mapping(ref)
    raw_path = _first_text(ref_map.get("path"))
    expected_sha256 = _first_text(ref_map.get("sha256"))
    ref_schema = _first_text(ref_map.get("schema_version"))
    missing = []
    if not raw_path:
        missing.append("path")
    if not expected_sha256:
        missing.append("sha256")
    if ref_schema != expected_schema:
        missing.append("schema_version")
    if missing:
        return False, "missing_or_invalid_" + ",".join(missing), None
    assert raw_path is not None
    assert expected_sha256 is not None

    path = Path(raw_path).expanduser()
    try:
        payload = _load_json_object(path, label=label)
        actual_sha256 = _sha256_file(path)
    except ProgramMetaAdjudicationError as exc:
        return False, str(exc), None
    if actual_sha256 != expected_sha256:
        return False, "sha256_mismatch", None
    if payload.get("schema_version") != expected_schema:
        return False, "payload_schema_mismatch", None
    return True, "complete", payload


def _all_declared_false(payload: object, keys: Mapping[str, bool]) -> bool:
    payload_map = _safe_mapping(payload)
    return all(payload_map.get(key) is False for key in keys)


def _identity_matches(actual: Mapping[str, Any], expected: Mapping[str, Any]) -> bool:
    return all(
        _first_text(actual.get(key)) == _first_text(expected.get(key))
        for key in (
            "request_id",
            "candidate_id",
            "assembly_id",
            "episode_id",
            "receipt_bundle_id",
        )
    )


def _raise_contract_error(error_type: type[Exception], message: str) -> None:
    raise error_type(message)


def validate_program_meta_adjudication_plan_contract(
    plan: Mapping[str, Any],
    *,
    expected_identities: object,
    valid_manifest_hashes: object,
    supplied_sidecar_refs: Mapping[str, tuple[Path, str]] | None = None,
    label: str = "program meta-adjudication plan",
    error_type: type[Exception] = ProgramMetaAdjudicationError,
) -> dict[str, Any]:
    """Validate a meta-adjudication plan at a final-consumer boundary."""

    if plan.get("schema_version") != PROGRAM_META_ADJUDICATION_PLAN_SCHEMA:
        _raise_contract_error(
            error_type,
            f"{label} schema_version must be {PROGRAM_META_ADJUDICATION_PLAN_SCHEMA}",
        )
    if plan.get("status") != "planned_not_executed":
        _raise_contract_error(
            error_type, f"{label} status must be planned_not_executed"
        )
    if plan.get("lifecycle_state") != "meta_adjudication_plan_ready":
        _raise_contract_error(
            error_type,
            f"{label} lifecycle_state must be meta_adjudication_plan_ready",
        )
    non_authority = _safe_mapping(plan.get("non_authority"))
    invalid_non_authority = [
        key for key in _NON_AUTHORITY if non_authority.get(key) is not False
    ]
    if invalid_non_authority:
        _raise_contract_error(
            error_type,
            f"{label} non_authority flags must remain false authority claims: "
            + ", ".join(invalid_non_authority),
        )
    effect = _safe_mapping(plan.get("effect"))
    invalid_effect = [key for key in _EFFECT if effect.get(key) is not False]
    if invalid_effect:
        _raise_contract_error(
            error_type,
            f"{label} effect flags must remain local/no-effect false: "
            + ", ".join(f"{key} false" for key in invalid_effect),
        )

    expected = (
        [
            _safe_mapping(item)
            for item in expected_identities
            if isinstance(item, Mapping)
        ]
        if isinstance(expected_identities, list | tuple | set)
        else []
    )
    identity = _safe_mapping(plan.get("identity"))
    if expected and not any(_identity_matches(identity, item) for item in expected):
        _raise_contract_error(
            error_type,
            f"{label} identity does not match expected candidate/source identity",
        )

    valid_hashes = (
        {str(item).strip() for item in valid_manifest_hashes if str(item).strip()}
        if isinstance(valid_manifest_hashes, list | tuple | set)
        else set()
    )
    manifest = _safe_mapping(plan.get("manifest"))
    manifest_hash = _first_text(manifest.get("sha256"))
    if valid_hashes and manifest_hash not in valid_hashes:
        _raise_contract_error(
            error_type, f"{label} manifest sha256 does not match current manifest"
        )

    sidecars = _safe_mapping(plan.get("sidecars"))
    supplied = supplied_sidecar_refs or {}
    present_sidecar_payloads: dict[str, dict[str, Any]] = {}
    for key, raw_status in sidecars.items():
        if not isinstance(raw_status, Mapping) or raw_status.get("present") is not True:
            continue
        status = _safe_mapping(raw_status)
        if status.get("status") != "present" or status.get(
            "schema_version"
        ) != status.get("required_schema"):
            _raise_contract_error(
                error_type,
                f"{label} {key} sidecar must have present status and expected schema",
            )
        raw_path = _first_text(status.get("path"))
        claimed_hash = _first_text(status.get("sha256"))
        if raw_path is None or claimed_hash is None:
            _raise_contract_error(
                error_type, f"{label} {key} sidecar ref must include path and sha256"
            )
        assert raw_path is not None
        assert claimed_hash is not None
        path = Path(raw_path).expanduser().resolve()
        if not path.exists():
            _raise_contract_error(
                error_type, f"{label} {key} sidecar is missing: {path}"
            )
        if _sha256_file(path) != claimed_hash:
            _raise_contract_error(
                error_type, f"{label} {key} sidecar sha256 does not match current file"
            )
        supplied_ref = supplied.get(key)
        if supplied_ref is not None:
            supplied_path, supplied_hash = supplied_ref
            if (
                path != supplied_path.expanduser().resolve()
                or claimed_hash != supplied_hash
            ):
                _raise_contract_error(
                    error_type,
                    f"{label} {key} sidecar does not match supplied {key}",
                )
        if key == "program_evidence_adjudication":
            present_sidecar_payloads[key] = _load_json_object(
                path, label=f"{label} {key} sidecar"
            )

    evidence_adjudication = present_sidecar_payloads.get(
        "program_evidence_adjudication"
    )
    if evidence_adjudication is not None:
        manifest_path = _first_text(manifest.get("path"))
        if manifest_path is None:
            _raise_contract_error(error_type, f"{label} manifest path is required")
        assert manifest_path is not None
        try:
            _validate_program_evidence_adjudication_sidecar(
                manifest_path=Path(manifest_path),
                adjudication=evidence_adjudication,
                sibling_sidecars=sidecars,
            )
        except ProgramMetaAdjudicationError as exc:
            _raise_contract_error(error_type, str(exc))
    return {"manifest_sha256": manifest_hash, "identity": identity}


def _manifest_root(manifest_path: Path) -> Path:
    return manifest_path.expanduser().resolve().parent


def _identity_from_manifest(manifest: Mapping[str, Any]) -> dict[str, str | None]:
    request = _safe_mapping(manifest.get("request"))
    candidate_assembly = _safe_mapping(manifest.get("candidate_assembly"))
    execution_episode = _safe_mapping(manifest.get("execution_episode"))
    receipt_bundle = _safe_mapping(manifest.get("receipt_bundle"))
    return {
        "request_id": _first_text(
            request.get("request_id"),
            candidate_assembly.get("request_id"),
            execution_episode.get("request_id"),
            receipt_bundle.get("request_id"),
        ),
        "candidate_id": _first_text(
            candidate_assembly.get("candidate_id"),
            execution_episode.get("candidate_id"),
            receipt_bundle.get("candidate_id"),
        ),
        "assembly_id": _first_text(
            candidate_assembly.get("assembly_id"),
            execution_episode.get("assembly_id"),
            receipt_bundle.get("assembly_id"),
        ),
        "episode_id": _first_text(
            execution_episode.get("episode_id"), receipt_bundle.get("episode_id")
        ),
        "receipt_bundle_id": _first_text(receipt_bundle.get("receipt_bundle_id")),
    }


def _sidecar_path(manifest_path: Path, *, key: str, explicit_path: Path | None) -> Path:
    if explicit_path is not None:
        return explicit_path.expanduser().resolve()
    return _manifest_root(manifest_path) / _DEFAULT_SIDECAR_FILES[key]


def _validate_runtime_episode_sidecar(
    *,
    manifest_path: Path,
    runtime_episode_path: Path,
    runtime_episode: Mapping[str, Any],
) -> None:
    manifest_file = manifest_path.expanduser().resolve()
    manifest = load_program_manifest(manifest_file)
    validate_program_runtime_episode_contract(
        runtime_episode,
        runtime_episode_path=runtime_episode_path,
        expected_manifest_path=manifest_file,
        expected_manifest=manifest,
        expected_manifest_sha256=_sha256_file(manifest_file),
        error_type=ProgramMetaAdjudicationError,
    )


def _validate_oracle_publication_receipt_sidecar(
    *,
    manifest_path: Path,
    receipt_path: Path,
    receipt: Mapping[str, Any],
) -> None:
    source = _safe_mapping(receipt.get("source"))
    preflight_file = _first_text(source.get("preflight_file"))
    preflight_sha256 = _first_text(source.get("preflight_sha256"))
    if preflight_file is None or preflight_sha256 is None:
        raise ProgramOraclePublicationError(
            "oracle_publication_receipt source preflight ref is required"
        )
    raw_preflight_path = Path(preflight_file).expanduser()
    preflight_path = (
        raw_preflight_path
        if raw_preflight_path.is_absolute()
        else receipt_path.parent / raw_preflight_path
    ).resolve()
    preflight = _load_json_object(
        preflight_path,
        label="oracle_publication_receipt source preflight",
    )
    actual_preflight_sha256 = _sha256_file(preflight_path)
    if actual_preflight_sha256 != preflight_sha256:
        raise ProgramOraclePublicationError(
            "oracle_publication_receipt source.preflight_sha256 does not match current preflight"
        )
    manifest_file = manifest_path.expanduser().resolve()
    validate_program_oracle_publication_preflight_contract(
        preflight,
        expected_manifest_path=manifest_file,
        expected_manifest_hash=_sha256_file(manifest_file),
        preflight_path=preflight_path,
    )
    manifest = load_program_manifest(manifest_file)
    validate_program_oracle_publication_receipt_contract(
        receipt,
        expected_identities=(_identity_from_manifest(manifest),),
        preflight=preflight,
        preflight_sha256=actual_preflight_sha256,
    )


def _validated_sidecar_ref(
    sidecars: Mapping[str, Mapping[str, Any]], key: str
) -> tuple[Path, str] | None:
    sidecar = _safe_mapping(sidecars.get(key))
    if sidecar.get("present") is not True:
        return None
    if sidecar.get("status") != "present":
        return None
    if sidecar.get("schema_version") != sidecar.get("required_schema"):
        return None
    path_text = _first_text(sidecar.get("path"))
    sha256 = _first_text(sidecar.get("sha256"))
    if path_text is None or sha256 is None:
        return None
    return Path(path_text).expanduser().resolve(), sha256


def _validated_sidecar_hash(
    sidecars: Mapping[str, Mapping[str, Any]], key: str
) -> str | None:
    ref = _validated_sidecar_ref(sidecars, key)
    return ref[1] if ref is not None else None


def _validate_program_evidence_adjudication_sidecar(
    *,
    manifest_path: Path,
    adjudication: Mapping[str, Any],
    sibling_sidecars: Mapping[str, Mapping[str, Any]],
) -> None:
    manifest_file = manifest_path.expanduser().resolve()
    manifest = load_program_manifest(manifest_file)
    runtime_ref = _validated_sidecar_ref(sibling_sidecars, "runtime_episode")
    validate_program_evidence_adjudication_contract(
        adjudication,
        expected_identity=_identity_from_manifest(manifest),
        current_manifest_path=manifest_file,
        current_manifest_hash=_sha256_file(manifest_file),
        behavior_results_hash=_validated_sidecar_hash(
            sibling_sidecars, "behavior_results"
        ),
        behavior_episode_hash=_validated_sidecar_hash(
            sibling_sidecars, "behavior_episode"
        ),
        oracle_report_hash=_validated_sidecar_hash(sibling_sidecars, "oracle_report"),
        activation_packet_hash=_validated_sidecar_hash(
            sibling_sidecars, "activation_packet"
        ),
        generation_fitness_results_hash=_validated_sidecar_hash(
            sibling_sidecars, "generation_fitness_results"
        ),
        expected_runtime_episode_path=runtime_ref[0] if runtime_ref else None,
        expected_runtime_episode_hash=runtime_ref[1] if runtime_ref else None,
        error_type=ProgramMetaAdjudicationError,
    )


def _sidecar_status(
    manifest_path: Path,
    *,
    key: str,
    explicit_path: Path | None = None,
    sibling_sidecars: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    path = _sidecar_path(manifest_path, key=key, explicit_path=explicit_path)
    required_schema = _EXPECTED_SIDECAR_SCHEMAS[key]
    status: dict[str, Any] = {
        "key": key,
        "path": str(path),
        "present": path.exists(),
        "required_schema": required_schema,
    }
    if not path.exists():
        if explicit_path is not None:
            status["status"] = "missing_explicit_path"
        else:
            status["status"] = "missing"
        return status
    payload = _load_json_object(path, label=f"{key} sidecar")
    schema = payload.get("schema_version")
    sidecar_status = "present" if schema == required_schema else "schema_mismatch"
    warning = None
    if schema == required_schema and key == "runtime_episode":
        try:
            _validate_runtime_episode_sidecar(
                manifest_path=manifest_path,
                runtime_episode_path=path,
                runtime_episode=payload,
            )
        except ProgramMetaAdjudicationError as exc:
            sidecar_status = "contract_invalid"
            warning = str(exc)
    if schema == required_schema and key == "oracle_publication_receipt":
        try:
            _validate_oracle_publication_receipt_sidecar(
                manifest_path=manifest_path,
                receipt_path=path,
                receipt=payload,
            )
        except (ProgramOraclePublicationError, ProgramMetaAdjudicationError) as exc:
            sidecar_status = "contract_invalid"
            warning = str(exc)
    if schema == required_schema and key == "program_evidence_adjudication":
        try:
            _validate_program_evidence_adjudication_sidecar(
                manifest_path=manifest_path,
                adjudication=payload,
                sibling_sidecars=sibling_sidecars or {},
            )
        except ProgramMetaAdjudicationError as exc:
            sidecar_status = "contract_invalid"
            warning = str(exc)
    status.update(
        {
            "status": sidecar_status,
            "schema_version": schema,
            "sha256": _sha256_file(path),
            "payload_status": payload.get("status"),
            "rendered_state": payload.get("rendered_state"),
        }
    )
    if schema != required_schema:
        status["warning"] = f"expected schema_version {required_schema}"
    elif warning is not None:
        status["warning"] = warning
    return status


def _manifest_text(manifest: Mapping[str, Any]) -> str:
    intent = _safe_mapping(manifest.get("intent"))
    request = _safe_mapping(manifest.get("request"))
    parts: list[str] = []
    for value in (
        intent.get("name"),
        intent.get("objective"),
        intent.get("task_type"),
        intent.get("metric"),
        request.get("goal"),
        request.get("intent_source"),
    ):
        if value:
            parts.append(str(value))
    for key in ("inputs", "outputs", "constraints"):
        parts.extend(_string_list(intent.get(key)))
    parts.append(json.dumps(intent.get("promotion", {}), sort_keys=True))
    parts.append(json.dumps(intent.get("options", {}), sort_keys=True))
    return "\n".join(parts).lower()


def _target_profile(
    manifest: Mapping[str, Any],
    *,
    manifest_path: Path | None = None,
    target_fidelity_sidecars: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    intent = _safe_mapping(manifest.get("intent"))
    request = _safe_mapping(manifest.get("request"))
    text = _manifest_text(manifest)
    risks: list[dict[str, str]] = [
        {
            "risk_id": "behavior_quality",
            "reason": "every generated program needs behavior and regression evidence",
        },
        {
            "risk_id": "authority_boundary",
            "reason": "DSPx evidence must not be mistaken for production activation authority",
        },
    ]
    if any(
        token in text for token in ("source", "zotero", "citation", "marker", "rag")
    ):
        risks.append(
            {
                "risk_id": "source_grounding",
                "reason": "target mentions source/citation/Zotero/Marker/RAG grounding",
            }
        )
    if any(token in text for token in ("obsidian", "wiki", "atlas", "canonical")):
        risks.append(
            {
                "risk_id": "canonical_mutation_boundary",
                "reason": "target mentions Obsidian/Wiki/Atlas/canonical artifact boundaries",
            }
        )
    if any(token in text for token in ("review", "proposal", "queue", "human")):
        risks.append(
            {
                "risk_id": "review_queue_boundary",
                "reason": "target mentions review/proposal/human queue semantics",
            }
        )
    if any(
        token in text for token in ("deploy", "activation", "production", "rollout")
    ):
        risks.append(
            {
                "risk_id": "rollout_rollback",
                "reason": "target mentions deployment/activation/production rollout",
            }
        )
    target_sidecars = target_fidelity_sidecars or {}
    present_target_sidecars = sorted(
        key for key, status in target_sidecars.items() if status.get("present")
    )
    if present_target_sidecars or any(
        token in text for token in ("target", "fidelity", "fitness", "protocol")
    ):
        risks.append(
            {
                "risk_id": "target_protocol_fidelity",
                "reason": "target-fidelity contract/fitness evidence must distinguish runnable success from target-protocol success",
            }
        )
    profile: dict[str, Any] = {
        "schema_version": PROGRAM_TARGET_PROFILE_SCHEMA,
        "status": "derived_from_manifest",
        "authority": "target_profile_evidence_only_non_authoritative",
        "intent_name": _first_text(intent.get("name")),
        "objective": _first_text(intent.get("objective"), request.get("goal")),
        "task_type": _first_text(intent.get("task_type")),
        "metric": _first_text(intent.get("metric")),
        "inputs": _string_list(intent.get("inputs")),
        "outputs": _string_list(intent.get("outputs")),
        "declared_constraints": _string_list(intent.get("constraints")),
        "intent_source": _first_text(request.get("intent_source")),
        "risks": risks,
        "target_fidelity_evidence": {
            "present_sidecars": present_target_sidecars,
            "fitness_results_status": _safe_mapping(
                target_sidecars.get("generation_fitness_results")
            ).get("payload_status"),
            "fitness_results_rendered_state": _safe_mapping(
                target_sidecars.get("generation_fitness_results")
            ).get("rendered_state"),
            "fitness_results_schema": _safe_mapping(
                target_sidecars.get("generation_fitness_results")
            ).get("schema_version"),
        },
        "non_authority": dict(_NON_AUTHORITY),
        "effect": dict(_EFFECT),
    }
    if manifest_path is not None:
        resolved_manifest = manifest_path.expanduser().resolve()
        profile["identity"] = _identity_from_manifest(manifest)
        profile["manifest"] = {
            "path": str(resolved_manifest),
            "sha256": _sha256_file(resolved_manifest),
            "schema_version": manifest.get("schema_version"),
        }
    return profile


def _jury_requirements(profile: Mapping[str, Any]) -> dict[str, Any]:
    risk_ids = {
        str(risk.get("risk_id"))
        for risk in _safe_list(profile.get("risks"))
        if isinstance(risk, Mapping)
    }
    perspectives = [
        {
            "perspective": "behavior_evidence",
            "reason": "verify generated behavior evidence is complete and not overclaimed",
        },
        {
            "perspective": "target_domain",
            "reason": "verify target-specific semantics and acceptance risks",
        },
        {
            "perspective": "authority_boundary",
            "reason": "verify DSPx/Oracle/jury results remain evidence only",
        },
    ]
    if "source_grounding" in risk_ids:
        perspectives.append(
            {
                "perspective": "source_grounding",
                "reason": "verify provenance and source refs are preserved",
            }
        )
    if "canonical_mutation_boundary" in risk_ids:
        perspectives.append(
            {
                "perspective": "canonical_mutation_safety",
                "reason": "verify no canonical target surface is mutated by evidence generation",
            }
        )
    if "review_queue_boundary" in risk_ids:
        perspectives.append(
            {
                "perspective": "review_surface",
                "reason": "verify generated artifacts remain review/proposal-only",
            }
        )
    if "target_protocol_fidelity" in risk_ids:
        perspectives.append(
            {
                "perspective": "target_protocol_fidelity",
                "reason": "verify target-fidelity sidecars distinguish runnable success from target-protocol evidence review eligibility",
            }
        )
    perspectives.append(
        {
            "perspective": "rollout_rollback",
            "reason": "verify activation requests include owner, binding, and rollback evidence",
        }
    )
    return {
        "schema_version": PROGRAM_JURY_REQUIREMENTS_SCHEMA,
        "status": "planned_not_executed",
        "authority": "jury_requirements_evidence_only_non_authoritative",
        "minimum_jurors": min(3, len(perspectives)),
        "required_perspectives": perspectives,
        "selection_constraints": {
            "prefer_diverse_perspectives": True,
            "require_authority_boundary_reviewer": True,
            "require_provider_identity_when_model_backed": True,
            "require_conflict_overlap_check": True,
        },
        "non_authority": dict(_NON_AUTHORITY),
        "effect": dict(_EFFECT),
    }


def _sidecar_is_present_valid(sidecar: Mapping[str, Any]) -> bool:
    return (
        sidecar.get("present") is True
        and sidecar.get("status") == "present"
        and sidecar.get("schema_version") == sidecar.get("required_schema")
    )


def _missing_evidence(sidecars: Mapping[str, Mapping[str, Any]]) -> list[str]:
    missing: list[str] = []
    if (
        not _sidecar_is_present_valid(sidecars["behavior_results"])
        and not _sidecar_is_present_valid(sidecars["behavior_episode"])
        and not _sidecar_is_present_valid(sidecars["runtime_episode"])
    ):
        missing.append("behavior_evidence")
    for key, label in (
        ("oracle_report", "oracle_report"),
        ("jury_results", "program_jury_results"),
        ("review", "refined_promotion_review"),
        ("decision_record", "domain_or_adjudicator_decision_record"),
        ("activation_packet", "activation_evidence_packet"),
    ):
        if not _sidecar_is_present_valid(sidecars[key]):
            missing.append(label)
    for key, label in (
        ("generation_target_contract", "generation_target_contract"),
        ("generation_fitness_suite", "generation_fitness_suite"),
        ("generation_gate_preflight", "generation_gate_preflight"),
        ("generation_traceability", "generation_traceability"),
        ("generation_fitness_results", "generation_fitness_results"),
        ("target_profile", "target_profile"),
        ("jury_requirements", "jury_requirements"),
        ("meta_jury_selection", "meta_jury_selection"),
        ("jury_verification", "jury_panel_verification"),
        ("program_adjudicator_formation", "program_adjudicator_formation"),
        ("program_adjudicator_verification", "program_adjudicator_verification"),
        ("program_adjudicator_delegation", "program_adjudicator_delegation"),
        ("program_evidence_adjudication", "program_evidence_adjudication"),
        ("adjudication_behavior_trace", "adjudication_behavior_trace"),
        ("adjudication_gepa_example", "adjudication_gepa_example"),
    ):
        if not _sidecar_is_present_valid(sidecars[key]):
            missing.append(label)
    missing.append("adjudication_behavior_trace_publication")
    return missing


def _sidecar_command_option(
    sidecars: Mapping[str, Mapping[str, Any]], *, key: str, option: str
) -> str:
    sidecar = _safe_mapping(sidecars.get(key))
    if not _sidecar_is_present_valid(sidecar):
        return ""
    path = _first_text(sidecar.get("path"))
    if path is None:
        return ""
    return f" {option} {path}"


def _next_commands(
    manifest_path: Path, sidecars: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    manifest_arg = str(manifest_path.expanduser().resolve())
    root = _manifest_root(manifest_path)
    generation_target_profile_args = "".join(
        [
            _sidecar_command_option(
                sidecars,
                key="generation_target_contract",
                option="--generation-target-contract",
            ),
            _sidecar_command_option(
                sidecars,
                key="generation_fitness_suite",
                option="--generation-fitness-suite",
            ),
            _sidecar_command_option(
                sidecars,
                key="generation_gate_preflight",
                option="--generation-gate-preflight",
            ),
            _sidecar_command_option(
                sidecars,
                key="generation_traceability",
                option="--generation-traceability",
            ),
            _sidecar_command_option(
                sidecars,
                key="generation_fitness_results",
                option="--generation-fitness-results",
            ),
        ]
    )
    adjudication_evidence_args = "".join(
        [
            _sidecar_command_option(
                sidecars,
                key="runtime_episode",
                option="--runtime-episode",
            ),
            _sidecar_command_option(
                sidecars,
                key="generation_traceability",
                option="--generation-traceability",
            ),
            _sidecar_command_option(
                sidecars,
                key="generation_fitness_results",
                option="--generation-fitness-results",
            ),
        ]
    )
    commands: list[dict[str, Any]] = []
    jury_results_out = root.parent / f"{root.name}-promotion" / "jury_results.json"
    if not _sidecar_is_present_valid(sidecars["jury_results"]):
        commands.append(
            {
                "step": "run_deterministic_jury_baseline",
                "implemented": True,
                "command": (
                    "dspx program-promote jury "
                    f"--manifest {manifest_arg} --out {jury_results_out} --json"
                ),
            }
        )
    if not (
        _sidecar_is_present_valid(sidecars["behavior_results"])
        or _sidecar_is_present_valid(sidecars["behavior_episode"])
        or _sidecar_is_present_valid(sidecars["runtime_episode"])
    ):
        commands.append(
            {
                "step": "run_runtime_episode",
                "implemented": True,
                "command": (
                    "dspx program-run "
                    f"--manifest {manifest_arg} --inputs <runtime-inputs.json> "
                    f"--outdir {root.parent / f'{root.name}-runtime-episode'} --json"
                ),
                "note": "writes program-runtime-episode-v1 local runtime evidence; evidence only, not activation authority",
            }
        )
    if not sidecars["oracle_report"].get("present"):
        commands.append(
            {
                "step": "produce_oracle_report",
                "implemented": True,
                "command": (
                    "dspx program-loop --intent <intent.yaml> "
                    "--outdir <fresh-candidate-dir> --json"
                ),
                "note": "program-loop writes candidate-local Oracle evidence/report; keep shared publication explicit",
            }
        )
    commands.append(
        {
            "step": "write_target_profile",
            "implemented": True,
            "command": (
                "dspx program-promote target-profile "
                f"--manifest {manifest_arg}{generation_target_profile_args} "
                f"--out {root / 'target_profile.json'} --json"
            ),
        }
    )
    commands.append(
        {
            "step": "write_jury_requirements",
            "implemented": True,
            "command": (
                "dspx program-promote jury-requirements "
                f"--target-profile {root / 'target_profile.json'} "
                f"--out {root / 'jury_requirements.json'} --json"
            ),
        }
    )
    commands.append(
        {
            "step": "select_meta_jury_panel",
            "implemented": True,
            "command": (
                "dspx program-promote jury-panel "
                f"--jury-requirements {root / 'jury_requirements.json'} "
                f"--out {root / 'meta_jury_selection.json'} --json"
            ),
        }
    )
    commands.append(
        {
            "step": "verify_meta_jury_panel",
            "implemented": True,
            "command": (
                "dspx program-promote verify-jury-panel "
                f"--jury-selection {root / 'meta_jury_selection.json'} "
                f"--out {root / 'jury_verification.json'} --json"
            ),
        }
    )
    commands.append(
        {
            "step": "form_program_adjudicator",
            "implemented": True,
            "command": (
                "dspx program-promote adjudicator-formation "
                f"--jury-verification {root / 'jury_verification.json'} "
                f"--out {root / 'program_adjudicator_formation.json'} --json"
            ),
        }
    )
    commands.append(
        {
            "step": "verify_program_adjudicator",
            "implemented": True,
            "command": (
                "dspx program-promote verify-program-adjudicator "
                f"--adjudicator-formation {root / 'program_adjudicator_formation.json'} "
                f"--out {root / 'program_adjudicator_verification.json'} --json"
            ),
        }
    )
    commands.append(
        {
            "step": "delegate_generated_program_adjudicator",
            "implemented": True,
            "command": (
                "dspx program-promote adjudicator-delegation "
                f"--manifest {manifest_arg} "
                f"--adjudicator-verification {root / 'program_adjudicator_verification.json'} "
                f"--out {root / 'program_adjudicator_delegation.json'} --json"
            ),
        }
    )
    commands.append(
        {
            "step": "adjudicate_program_evidence",
            "implemented": True,
            "command": (
                "dspx program-promote evidence-adjudication "
                f"--manifest {manifest_arg} "
                f"--adjudicator-verification {root / 'program_adjudicator_verification.json'}"
                f"{adjudication_evidence_args} "
                f"--out {root / 'program_evidence_adjudication.json'} --json"
            ),
        }
    )
    commands.append(
        {
            "step": "generated_program_adjudicator_decision",
            "implemented": True,
            "command": (
                "dspx program-promote generated-adjudicator-decision "
                f"--evidence-adjudication {root / 'program_evidence_adjudication.json'} "
                f"--adjudicator-delegation {root / 'program_adjudicator_delegation.json'} "
                f"--out {root / 'promotion_decision_record.json'} --json"
            ),
        }
    )
    commands.append(
        {
            "step": "write_adjudication_behavior_trace",
            "implemented": True,
            "command": (
                "dspx program-promote adjudication-behavior-trace "
                f"--evidence-adjudication {root / 'program_evidence_adjudication.json'} "
                f"--out {root / 'adjudication_behavior_trace.json'} --json"
            ),
        }
    )
    commands.append(
        {
            "step": "write_adjudication_gepa_example",
            "implemented": True,
            "command": (
                "dspx program-promote adjudication-gepa-example "
                f"--trace {root / 'adjudication_behavior_trace.json'} "
                f"--out {root / 'adjudication_gepa_example.json'} --json"
            ),
        }
    )
    commands.append(
        {
            "step": "phase6_publish_adjudication_trace",
            "implemented": True,
            "command": (
                "dspx oracle adjudication-trace publish-preflight "
                f"--trace {root / 'adjudication_behavior_trace.json'} "
                "--target shared-postgres --publication-label adjudication_behavior_trace "
                "--publisher-id <publisher> --publisher-role <role> "
                "--publisher-assertion <checked-custody-assertion> "
                "--redaction-status checked --retention-class retained_behavior_memory "
                f"--out {root / 'adjudication_trace_publication_preflight.json'} --json"
            ),
        }
    )
    return commands


def build_program_target_profile(
    *,
    manifest_path: Path,
    generation_target_contract_path: Path | None = None,
    generation_fitness_suite_path: Path | None = None,
    generation_gate_preflight_path: Path | None = None,
    generation_traceability_path: Path | None = None,
    generation_fitness_results_path: Path | None = None,
) -> dict[str, Any]:
    """Build a first-class target profile sidecar without model calls."""

    try:
        manifest = load_program_manifest(manifest_path)
    except ProgramRefinementError as exc:
        raise ProgramMetaAdjudicationError(str(exc)) from exc
    sidecars = {
        "generation_target_contract": _sidecar_status(
            manifest_path,
            key="generation_target_contract",
            explicit_path=generation_target_contract_path,
        ),
        "generation_fitness_suite": _sidecar_status(
            manifest_path,
            key="generation_fitness_suite",
            explicit_path=generation_fitness_suite_path,
        ),
        "generation_gate_preflight": _sidecar_status(
            manifest_path,
            key="generation_gate_preflight",
            explicit_path=generation_gate_preflight_path,
        ),
        "generation_traceability": _sidecar_status(
            manifest_path,
            key="generation_traceability",
            explicit_path=generation_traceability_path,
        ),
        "generation_fitness_results": _sidecar_status(
            manifest_path,
            key="generation_fitness_results",
            explicit_path=generation_fitness_results_path,
        ),
    }
    return _target_profile(
        manifest,
        manifest_path=manifest_path,
        target_fidelity_sidecars=sidecars,
    )


def write_program_target_profile(
    profile: Mapping[str, Any], out_path: Path
) -> dict[str, Any]:
    if profile.get("schema_version") != PROGRAM_TARGET_PROFILE_SCHEMA:
        raise ProgramMetaAdjudicationError(
            "target profile schema_version must be " + PROGRAM_TARGET_PROFILE_SCHEMA
        )
    out = out_path.expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(profile)
    out.write_text(_json_text(payload), encoding="utf-8")
    return payload


def build_program_jury_requirements(
    *, manifest_path: Path | None = None, target_profile_path: Path | None = None
) -> dict[str, Any]:
    """Build first-class jury requirements from a target profile or manifest."""

    if target_profile_path is not None:
        profile = _load_json_object(target_profile_path, label="target profile")
        if profile.get("schema_version") != PROGRAM_TARGET_PROFILE_SCHEMA:
            raise ProgramMetaAdjudicationError(
                "target profile schema_version must be " + PROGRAM_TARGET_PROFILE_SCHEMA
            )
        requirements = _jury_requirements(profile)
        requirements["target_profile"] = {
            "path": str(target_profile_path.expanduser().resolve()),
            "sha256": _sha256_file(target_profile_path.expanduser().resolve()),
            "schema_version": profile.get("schema_version"),
        }
        if isinstance(profile.get("identity"), Mapping):
            requirements["identity"] = dict(profile["identity"])
        return requirements
    if manifest_path is None:
        raise ProgramMetaAdjudicationError(
            "either manifest_path or target_profile_path is required"
        )
    profile = build_program_target_profile(manifest_path=manifest_path)
    return _jury_requirements(profile)


def write_program_jury_requirements(
    requirements: Mapping[str, Any], out_path: Path
) -> dict[str, Any]:
    if requirements.get("schema_version") != PROGRAM_JURY_REQUIREMENTS_SCHEMA:
        raise ProgramMetaAdjudicationError(
            "jury requirements schema_version must be "
            + PROGRAM_JURY_REQUIREMENTS_SCHEMA
        )
    out = out_path.expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(requirements)
    out.write_text(_json_text(payload), encoding="utf-8")
    return payload


def build_program_meta_jury_selection(
    *,
    manifest_path: Path | None = None,
    target_profile_path: Path | None = None,
    jury_requirements_path: Path | None = None,
) -> dict[str, Any]:
    """Build a deterministic meta-jury selection sidecar without model calls."""

    requirements: dict[str, Any]
    requirements_ref: dict[str, Any] | None = None
    if jury_requirements_path is not None:
        requirements = _load_json_object(
            jury_requirements_path, label="jury requirements"
        )
        if requirements.get("schema_version") != PROGRAM_JURY_REQUIREMENTS_SCHEMA:
            raise ProgramMetaAdjudicationError(
                "jury requirements schema_version must be "
                + PROGRAM_JURY_REQUIREMENTS_SCHEMA
            )
        requirements_ref = {
            "path": str(jury_requirements_path.expanduser().resolve()),
            "sha256": _sha256_file(jury_requirements_path.expanduser().resolve()),
            "schema_version": requirements.get("schema_version"),
        }
    else:
        requirements = build_program_jury_requirements(
            manifest_path=manifest_path, target_profile_path=target_profile_path
        )

    required_perspectives = [
        dict(item)
        for item in _safe_list(requirements.get("required_perspectives"))
        if isinstance(item, Mapping) and _first_text(item.get("perspective"))
    ]
    selected_jurors: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in required_perspectives:
        perspective = str(item["perspective"])
        if perspective in seen:
            continue
        seen.add(perspective)
        selected_jurors.append(
            {
                "juror_id": f"meta_juror_{_slug(perspective)}",
                "perspective": perspective,
                "kind": "deterministic_role_juror",
                "model_backed": False,
                "provider": None,
                "model": None,
                "qualification": item.get("reason"),
                "selection_reason": "selected to cover required target-risk perspective",
                "authority": "advisory_evidence_only",
            }
        )

    selected_perspectives = [str(juror["perspective"]) for juror in selected_jurors]
    missing_perspectives = [
        str(item["perspective"])
        for item in required_perspectives
        if str(item["perspective"]) not in selected_perspectives
    ]
    minimum_jurors = int(requirements.get("minimum_jurors") or 0)
    status = (
        "selected"
        if len(selected_jurors) >= minimum_jurors and not missing_perspectives
        else "selection_incomplete"
    )
    selection: dict[str, Any] = {
        "schema_version": PROGRAM_META_JURY_SELECTION_SCHEMA,
        "status": status,
        "authority": "meta_jury_selection_evidence_only_non_authoritative",
        "minimum_jurors": minimum_jurors,
        "selected_jurors": selected_jurors,
        "coverage": {
            "required_perspectives": [
                str(item["perspective"]) for item in required_perspectives
            ],
            "selected_perspectives": selected_perspectives,
            "missing_perspectives": missing_perspectives,
        },
        "selection_constraints": _safe_mapping(
            requirements.get("selection_constraints")
        ),
        "selection_method": "deterministic_required_perspective_coverage_v1",
        "notes": [
            "This sidecar selects deterministic role-jurors only.",
            "No model/provider was called and no production authority was granted.",
            "Model-backed juror nomination remains a future explicit phase.",
        ],
        "non_authority": dict(_NON_AUTHORITY),
        "effect": dict(_EFFECT),
    }
    if requirements_ref is not None:
        selection["jury_requirements"] = requirements_ref
    if isinstance(requirements.get("identity"), Mapping):
        selection["identity"] = dict(requirements["identity"])
    return selection


def write_program_meta_jury_selection(
    selection: Mapping[str, Any], out_path: Path
) -> dict[str, Any]:
    if selection.get("schema_version") != PROGRAM_META_JURY_SELECTION_SCHEMA:
        raise ProgramMetaAdjudicationError(
            "meta jury selection schema_version must be "
            + PROGRAM_META_JURY_SELECTION_SCHEMA
        )
    out = out_path.expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(selection)
    out.write_text(_json_text(payload), encoding="utf-8")
    return payload


def build_program_jury_verification(*, jury_selection_path: Path) -> dict[str, Any]:
    """Verify a deterministic meta-jury selection without judging the program."""

    selection = _load_json_object(jury_selection_path, label="meta jury selection")
    if selection.get("schema_version") != PROGRAM_META_JURY_SELECTION_SCHEMA:
        raise ProgramMetaAdjudicationError(
            "meta jury selection schema_version must be "
            + PROGRAM_META_JURY_SELECTION_SCHEMA
        )
    jurors = [
        dict(item)
        for item in _safe_list(selection.get("selected_jurors"))
        if isinstance(item, Mapping)
    ]
    perspectives = [str(juror.get("perspective") or "") for juror in jurors]
    perspective_set = {perspective for perspective in perspectives if perspective}
    constraints = _safe_mapping(selection.get("selection_constraints"))
    coverage = _safe_mapping(selection.get("coverage"))
    required_perspectives = set(_string_list(coverage.get("required_perspectives")))
    missing_perspectives = sorted(required_perspectives - perspective_set)
    minimum_jurors = int(selection.get("minimum_jurors") or 0)
    duplicate_perspectives = sorted(
        perspective
        for perspective in perspective_set
        if perspectives.count(perspective) > 1
    )
    missing_provider_identity = [
        str(juror.get("juror_id") or "unknown")
        for juror in jurors
        if juror.get("model_backed") is True
        and (not juror.get("provider") or not juror.get("model"))
    ]
    checks = [
        {
            "check": "minimum_jurors_satisfied",
            "ok": len(jurors) >= minimum_jurors,
            "detail": f"selected={len(jurors)} minimum={minimum_jurors}",
        },
        {
            "check": "required_perspective_coverage_complete",
            "ok": not missing_perspectives,
            "detail": ",".join(missing_perspectives) or "complete",
        },
        {
            "check": "authority_boundary_present",
            "ok": (
                not constraints.get("require_authority_boundary_reviewer")
                or "authority_boundary" in perspective_set
            ),
            "detail": "authority_boundary perspective required by selection constraints",
        },
        {
            "check": "no_duplicate_perspectives",
            "ok": not duplicate_perspectives,
            "detail": ",".join(duplicate_perspectives) or "none",
        },
        {
            "check": "model_backed_jurors_have_provider_identity",
            "ok": not missing_provider_identity,
            "detail": ",".join(missing_provider_identity)
            or "not_applicable_or_complete",
        },
        {
            "check": "selection_has_no_authority_effect",
            "ok": _safe_mapping(selection.get("non_authority")).get(
                "activation_authority"
            )
            is False
            and _safe_mapping(selection.get("effect")).get("provider_called") is False,
            "detail": "selection must be evidence-only and local in this phase",
        },
    ]
    failed_checks = [str(check["check"]) for check in checks if not check["ok"]]
    verified = not failed_checks
    return {
        "schema_version": PROGRAM_JURY_VERIFICATION_SCHEMA,
        "status": "verified" if verified else "revise_jury_selection",
        "authority": "jury_verification_evidence_only_non_authoritative",
        "dspx_adjudicator": {
            "id": "dspx_meta_adjudicator_v1",
            "mode": "deterministic_contract_check",
            "scope": "judge_jury_fitness_not_program_promotion_or_activation",
            "model_backed": False,
        },
        "jury_selection": {
            "path": str(jury_selection_path.expanduser().resolve()),
            "sha256": _sha256_file(jury_selection_path.expanduser().resolve()),
            "schema_version": selection.get("schema_version"),
        },
        "checks": checks,
        "failed_checks": failed_checks,
        "approved_for_program_adjudicator_formation": verified,
        "next_required_action": (
            "form_program_adjudicator" if verified else "revise_jury_selection"
        ),
        "non_authority": dict(_NON_AUTHORITY),
        "effect": dict(_EFFECT),
    }


def write_program_jury_verification(
    verification: Mapping[str, Any], out_path: Path
) -> dict[str, Any]:
    if verification.get("schema_version") != PROGRAM_JURY_VERIFICATION_SCHEMA:
        raise ProgramMetaAdjudicationError(
            "jury verification schema_version must be "
            + PROGRAM_JURY_VERIFICATION_SCHEMA
        )
    out = out_path.expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(verification)
    out.write_text(_json_text(payload), encoding="utf-8")
    return payload


def build_program_adjudicator_formation(
    *, jury_verification_path: Path, jury_selection_path: Path | None = None
) -> dict[str, Any]:
    """Form a deterministic program-specific adjudicator from a verified jury."""

    verification = _load_json_object(jury_verification_path, label="jury verification")
    if verification.get("schema_version") != PROGRAM_JURY_VERIFICATION_SCHEMA:
        raise ProgramMetaAdjudicationError(
            "jury verification schema_version must be "
            + PROGRAM_JURY_VERIFICATION_SCHEMA
        )
    if (
        verification.get("status") != "verified"
        or verification.get("approved_for_program_adjudicator_formation") is not True
    ):
        raise ProgramMetaAdjudicationError(
            "jury verification must be verified before forming a program adjudicator"
        )

    selection_path = jury_selection_path
    if selection_path is None:
        verification_selection = _safe_mapping(verification.get("jury_selection"))
        raw_path = _first_text(verification_selection.get("path"))
        if raw_path:
            selection_path = Path(raw_path)
    if selection_path is None:
        raise ProgramMetaAdjudicationError(
            "jury selection path is required when verification does not reference it"
        )
    resolved_selection_path = selection_path.expanduser().resolve()
    selection = _load_json_object(resolved_selection_path, label="meta jury selection")
    if selection.get("schema_version") != PROGRAM_META_JURY_SELECTION_SCHEMA:
        raise ProgramMetaAdjudicationError(
            "meta jury selection schema_version must be "
            + PROGRAM_META_JURY_SELECTION_SCHEMA
        )
    selection_sha256 = _sha256_file(resolved_selection_path)
    verification_selection = _safe_mapping(verification.get("jury_selection"))
    if (
        verification_selection.get("schema_version")
        != PROGRAM_META_JURY_SELECTION_SCHEMA
    ):
        raise ProgramMetaAdjudicationError(
            "jury verification must reference a program-meta-jury-selection-v1 sidecar"
        )
    verification_selection_sha256 = _first_text(verification_selection.get("sha256"))
    if not verification_selection_sha256:
        raise ProgramMetaAdjudicationError(
            "jury verification must bind the verified jury selection sha256"
        )
    if verification_selection_sha256 != selection_sha256:
        raise ProgramMetaAdjudicationError(
            "meta jury selection does not match the verified jury selection hash"
        )

    jurors = [
        dict(item)
        for item in _safe_list(selection.get("selected_jurors"))
        if isinstance(item, Mapping)
    ]
    perspectives = [str(juror.get("perspective")) for juror in jurors]
    adjudicator_roles = [
        {
            "role_id": f"program_adjudicator_{_slug(perspective)}",
            "source_juror_id": juror.get("juror_id"),
            "perspective": perspective,
            "responsibility": "judge program evidence for this perspective and report missing evidence",
            "model_backed": False,
        }
        for juror, perspective in zip(jurors, perspectives, strict=False)
        if perspective and perspective != "None"
    ]
    required_inputs = [
        "manifest.json",
        "behavior_results.json or behavior_episode.json",
        "program_oracle_report.json when available",
        "program-meta-jury-selection-v1",
        "program-jury-verification-v1",
    ]
    if "canonical_mutation_safety" in perspectives:
        required_inputs.append(
            "canonical mutation / review-only adapter receipt when target writes review artifacts"
        )
    if "rollout_rollback" in perspectives:
        required_inputs.append(
            "rollout owner, canonical binding ref, and rollback plan before activation"
        )

    return {
        "schema_version": PROGRAM_ADJUDICATOR_FORMATION_SCHEMA,
        "status": "formed",
        "authority": "program_adjudicator_formation_evidence_only_non_authoritative",
        "program_adjudicator": {
            "id": "program_adjudicator_from_verified_meta_jury_v1",
            "formation_method": "deterministic_verified_jury_perspective_composition_v1",
            "model_backed": False,
            "roles": adjudicator_roles,
            "decision_scope": "judge_program_evidence_not_activation_authority",
            "allowed_outputs": [
                "program evidence judgment",
                "missing evidence requests",
                "risk-specific rationale",
                "recommendation for domain decision packet",
            ],
            "forbidden_outputs": [
                "production activation",
                "canonical target mutation",
                "AK/governance mutation",
                "Oracle promotion authority",
            ],
            "required_inputs": required_inputs,
        },
        "jury_verification": {
            "path": str(jury_verification_path.expanduser().resolve()),
            "sha256": _sha256_file(jury_verification_path.expanduser().resolve()),
            "schema_version": verification.get("schema_version"),
        },
        "jury_selection": {
            "path": str(resolved_selection_path),
            "sha256": selection_sha256,
            "schema_version": selection.get("schema_version"),
        },
        "next_required_action": "verify_program_adjudicator",
        "notes": [
            "The verified deterministic jury forms a deterministic program adjudicator contract only.",
            "No program evidence has been judged by this formation sidecar.",
            "Production activation authority remains outside DSPx.",
        ],
        "non_authority": dict(_NON_AUTHORITY),
        "effect": dict(_EFFECT),
    }


def write_program_adjudicator_formation(
    formation: Mapping[str, Any], out_path: Path
) -> dict[str, Any]:
    if formation.get("schema_version") != PROGRAM_ADJUDICATOR_FORMATION_SCHEMA:
        raise ProgramMetaAdjudicationError(
            "program adjudicator formation schema_version must be "
            + PROGRAM_ADJUDICATOR_FORMATION_SCHEMA
        )
    out = out_path.expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(formation)
    out.write_text(_json_text(payload), encoding="utf-8")
    return payload


def build_program_adjudicator_verification(
    *, adjudicator_formation_path: Path
) -> dict[str, Any]:
    """Verify a formed program adjudicator contract without judging program evidence."""

    formation = _load_json_object(
        adjudicator_formation_path, label="program adjudicator formation"
    )
    if formation.get("schema_version") != PROGRAM_ADJUDICATOR_FORMATION_SCHEMA:
        raise ProgramMetaAdjudicationError(
            "program adjudicator formation schema_version must be "
            + PROGRAM_ADJUDICATOR_FORMATION_SCHEMA
        )
    adjudicator = _safe_mapping(formation.get("program_adjudicator"))
    roles = [
        dict(item)
        for item in _safe_list(adjudicator.get("roles"))
        if isinstance(item, Mapping)
    ]
    role_perspectives = {
        str(role.get("perspective")) for role in roles if role.get("perspective")
    }
    forbidden_outputs = set(_string_list(adjudicator.get("forbidden_outputs")))
    required_forbidden = {
        "production activation",
        "canonical target mutation",
        "AK/governance mutation",
        "Oracle promotion authority",
    }
    jury_ref_ok, jury_ref_detail, jury_verification = _load_hash_bound_ref(
        formation.get("jury_verification"),
        expected_schema=PROGRAM_JURY_VERIFICATION_SCHEMA,
        label="jury verification ref",
    )
    selection_ref_ok, selection_ref_detail, _selection = _load_hash_bound_ref(
        formation.get("jury_selection"),
        expected_schema=PROGRAM_META_JURY_SELECTION_SCHEMA,
        label="jury selection ref",
    )
    formation_selection_sha256 = _first_text(
        _safe_mapping(formation.get("jury_selection")).get("sha256")
    )
    verified_selection_sha256 = None
    jury_verification_approves_formation = False
    if jury_verification is not None:
        verified_selection_sha256 = _first_text(
            _safe_mapping(jury_verification.get("jury_selection")).get("sha256")
        )
        jury_verification_approves_formation = (
            jury_verification.get("status") == "verified"
            and jury_verification.get("approved_for_program_adjudicator_formation")
            is True
        )
    checks = [
        {
            "check": "formation_status_is_formed",
            "ok": formation.get("status") == "formed",
            "detail": str(formation.get("status")),
        },
        {
            "check": "roles_present",
            "ok": bool(roles),
            "detail": f"role_count={len(roles)}",
        },
        {
            "check": "authority_boundary_role_present",
            "ok": "authority_boundary" in role_perspectives,
            "detail": "authority_boundary role required",
        },
        {
            "check": "model_backed_roles_have_provider_identity",
            "ok": not [
                role.get("role_id")
                for role in roles
                if role.get("model_backed") is True
                and (not role.get("provider") or not role.get("model"))
            ],
            "detail": "model-backed roles require provider/model identity",
        },
        {
            "check": "forbidden_outputs_preserve_authority_boundary",
            "ok": required_forbidden.issubset(forbidden_outputs),
            "detail": ",".join(sorted(required_forbidden - forbidden_outputs))
            or "complete",
        },
        {
            "check": "verified_jury_provenance_present_and_hash_bound",
            "ok": jury_ref_ok and jury_verification_approves_formation,
            "detail": "complete"
            if jury_ref_ok and jury_verification_approves_formation
            else ("jury_verification_not_approved" if jury_ref_ok else jury_ref_detail),
        },
        {
            "check": "jury_selection_provenance_present_and_hash_bound",
            "ok": selection_ref_ok,
            "detail": selection_ref_detail,
        },
        {
            "check": "formation_selection_matches_verified_jury",
            "ok": bool(formation_selection_sha256)
            and formation_selection_sha256 == verified_selection_sha256,
            "detail": "complete"
            if formation_selection_sha256 == verified_selection_sha256
            else "selection_sha256_mismatch",
        },
        {
            "check": "formation_has_no_authority_effect",
            "ok": _all_declared_false(formation.get("non_authority"), _NON_AUTHORITY)
            and _all_declared_false(formation.get("effect"), _EFFECT),
            "detail": "formation must be evidence-only and local in this phase",
        },
    ]
    failed_checks = [str(check["check"]) for check in checks if not check["ok"]]
    verified = not failed_checks
    return {
        "schema_version": PROGRAM_ADJUDICATOR_VERIFICATION_SCHEMA,
        "status": "verified" if verified else "revise_program_adjudicator",
        "authority": "program_adjudicator_verification_evidence_only_non_authoritative",
        "dspx_adjudicator": {
            "id": "dspx_meta_adjudicator_v1",
            "mode": "deterministic_contract_check",
            "scope": "judge_program_adjudicator_fitness_not_program_promotion_or_activation",
            "model_backed": False,
        },
        "program_adjudicator_formation": {
            "path": str(adjudicator_formation_path.expanduser().resolve()),
            "sha256": _sha256_file(adjudicator_formation_path.expanduser().resolve()),
            "schema_version": formation.get("schema_version"),
        },
        "checks": checks,
        "failed_checks": failed_checks,
        "approved_for_program_evidence_adjudication": verified,
        "next_required_action": (
            "adjudicate_program_evidence" if verified else "revise_program_adjudicator"
        ),
        "non_authority": dict(_NON_AUTHORITY),
        "effect": dict(_EFFECT),
    }


def write_program_adjudicator_verification(
    verification: Mapping[str, Any], out_path: Path
) -> dict[str, Any]:
    if verification.get("schema_version") != PROGRAM_ADJUDICATOR_VERIFICATION_SCHEMA:
        raise ProgramMetaAdjudicationError(
            "program adjudicator verification schema_version must be "
            + PROGRAM_ADJUDICATOR_VERIFICATION_SCHEMA
        )
    out = out_path.expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(verification)
    out.write_text(_json_text(payload), encoding="utf-8")
    return payload


def build_program_adjudicator_delegation(
    *, manifest_path: Path, adjudicator_verification_path: Path
) -> dict[str, Any]:
    """Let the DSPx/meta adjudicator delegate local decision scope to the generated-program adjudicator."""

    try:
        manifest = load_program_manifest(manifest_path)
    except ProgramRefinementError as exc:
        raise ProgramMetaAdjudicationError(str(exc)) from exc
    verification = _load_expected_sidecar(
        adjudicator_verification_path,
        key="program_adjudicator_verification",
        label="program adjudicator verification",
    )
    promotion_review = _safe_mapping(manifest.get("program_promotion_review"))
    adjudicator = _safe_mapping(promotion_review.get("adjudicator"))
    adjudicator_id = _first_text(adjudicator.get("id"))
    adjudicator_kind = _first_text(adjudicator.get("kind"))
    checks = [
        {
            "check": "generated_program_adjudicator_declared",
            "ok": bool(adjudicator_id and adjudicator_kind),
            "detail": adjudicator_id or "missing",
        },
        {
            "check": "dspx_meta_adjudicator_verified_program_adjudicator",
            "ok": verification.get("status") == "verified"
            and verification.get("approved_for_program_evidence_adjudication") is True,
            "detail": str(verification.get("status")),
        },
        {
            "check": "generated_program_adjudicator_kind_can_decide_locally",
            "ok": adjudicator_kind
            in {"ai_agent", "ai_council", "hybrid", "policy_gate"},
            "detail": adjudicator_kind or "missing",
        },
        {
            "check": "verification_has_no_authority_effect",
            "ok": _all_declared_false(verification.get("non_authority"), _NON_AUTHORITY)
            and _all_declared_false(verification.get("effect"), _EFFECT),
            "detail": "verification must be evidence-only and local",
        },
    ]
    failed_checks = [str(check["check"]) for check in checks if not check["ok"]]
    delegated = not failed_checks
    return {
        "schema_version": PROGRAM_ADJUDICATOR_DELEGATION_SCHEMA,
        "status": "delegated" if delegated else "revise_generated_program_adjudicator",
        "authority": "program_adjudicator_delegation_evidence_only_non_authoritative",
        "dspx_meta_adjudicator": {
            "id": "dspx_meta_adjudicator_v1",
            "decision": "approve_generated_program_adjudicator_to_record_local_decision"
            if delegated
            else "revise_generated_program_adjudicator",
            "scope": "judge_generated_program_adjudicator_fitness_not_program_promotion_or_activation",
            "model_backed": False,
        },
        "generated_program_adjudicator": {
            "id": adjudicator_id,
            "kind": adjudicator_kind,
            "authority": adjudicator.get("authority"),
            "status": adjudicator.get("status"),
            "approved_to_decide": delegated,
            "decision_scope": "generated_program_local_promotion_decision_only",
            "promotion_authority": False,
            "activation_authority": False,
            "source": "manifest.program_promotion_review.adjudicator",
        },
        "manifest": _artifact_ref(
            manifest_path, schema_version="program-candidate-assembly-v1"
        ),
        "program_adjudicator_verification": _artifact_ref(
            adjudicator_verification_path,
            schema_version=PROGRAM_ADJUDICATOR_VERIFICATION_SCHEMA,
        ),
        "checks": checks,
        "failed_checks": failed_checks,
        "next_required_action": (
            "generated_program_adjudicator_decide"
            if delegated
            else "revise_generated_program_adjudicator"
        ),
        "non_authority": dict(_NON_AUTHORITY),
        "effect": dict(_EFFECT),
    }


def write_program_adjudicator_delegation(
    delegation: Mapping[str, Any], out_path: Path
) -> dict[str, Any]:
    if delegation.get("schema_version") != PROGRAM_ADJUDICATOR_DELEGATION_SCHEMA:
        raise ProgramMetaAdjudicationError(
            "program adjudicator delegation schema_version must be "
            + PROGRAM_ADJUDICATOR_DELEGATION_SCHEMA
        )
    out = out_path.expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(delegation)
    out.write_text(_json_text(payload), encoding="utf-8")
    return payload


def _artifact_ref(path: Path, *, schema_version: str | None = None) -> dict[str, Any]:
    resolved = path.expanduser().resolve()
    return {
        "path": str(resolved),
        "sha256": _sha256_file(resolved),
        **({"schema_version": schema_version} if schema_version else {}),
    }


def _default_existing_path(
    manifest_path: Path, *, explicit_path: Path | None, default_name: str
) -> Path | None:
    if explicit_path is not None:
        return explicit_path.expanduser().resolve()
    candidate = _manifest_root(manifest_path) / default_name
    return candidate if candidate.exists() else None


def _load_expected_sidecar(path: Path, *, key: str, label: str) -> dict[str, Any]:
    payload = _load_json_object(path, label=label)
    expected_schema = _EXPECTED_SIDECAR_SCHEMAS[key]
    if payload.get("schema_version") != expected_schema:
        raise ProgramMetaAdjudicationError(
            f"{label} schema_version must be {expected_schema}"
        )
    return payload


def _summary_int(value: object, *, field: str) -> int:
    if value in {None, ""}:
        return 0
    if isinstance(value, bool) or not isinstance(value, int | str):
        raise ProgramMetaAdjudicationError(
            f"behavior summary {field} must be an integer"
        )
    try:
        number = int(value)
    except ValueError as exc:
        raise ProgramMetaAdjudicationError(
            f"behavior summary {field} must be an integer"
        ) from exc
    if number < 0:
        raise ProgramMetaAdjudicationError(
            f"behavior summary {field} must be non-negative"
        )
    return number


def _validate_behavior_results_contract(
    *,
    payload: Mapping[str, Any],
    path: Path,
    manifest: Mapping[str, Any],
) -> None:
    request = _safe_mapping(manifest.get("request"))
    expected_hash = _first_text(request.get("behavior_results_hash"))
    if expected_hash is None:
        raise ProgramMetaAdjudicationError(
            "behavior results cannot be consumed because manifest does not declare behavior_results_hash"
        )
    if _sha256_file(path.expanduser().resolve()) != expected_hash:
        raise ProgramMetaAdjudicationError(
            "behavior results sha256 does not match manifest behavior_results_hash"
        )
    if payload.get("authority") != "behavior_evidence_only_non_authoritative":
        raise ProgramMetaAdjudicationError(
            "behavior results authority must remain evidence-only"
        )
    non_authority = _safe_mapping(payload.get("non_authority"))
    for key in (
        "optimization_authority",
        "promotion_authority",
        "oracle_ranking",
        "oracle_pruning",
        "oracle_promotion",
        "governance_authority",
        "external_mutation",
        "external_authority_mutated",
        "winner_selection",
    ):
        if non_authority.get(key) is not False:
            raise ProgramMetaAdjudicationError(
                f"behavior results non_authority flag must remain false: {key}"
            )
    manifest_intent = _safe_mapping(manifest.get("intent"))
    behavior_intent = _safe_mapping(payload.get("intent"))
    expected_name = _first_text(manifest_intent.get("name"))
    if (
        expected_name
        and _first_text(payload.get("intent_name"), behavior_intent.get("name"))
        != expected_name
    ):
        raise ProgramMetaAdjudicationError(
            "behavior results intent identity does not match manifest"
        )
    for field, behavior_key in (
        ("inputs", "input_fields"),
        ("outputs", "output_fields"),
    ):
        expected_values = _string_list(manifest_intent.get(field))
        actual_values = _string_list(payload.get(behavior_key))
        if expected_values and actual_values and actual_values != expected_values:
            raise ProgramMetaAdjudicationError(
                f"behavior results {behavior_key} do not match manifest intent"
            )


def _validate_behavior_episode_contract(
    *,
    payload: Mapping[str, Any],
    path: Path,
    manifest: Mapping[str, Any],
) -> None:
    request = _safe_mapping(manifest.get("request"))
    expected_hash = _first_text(request.get("behavior_episode_hash"))
    if expected_hash is None:
        raise ProgramMetaAdjudicationError(
            "behavior episode cannot be consumed because manifest does not declare behavior_episode_hash"
        )
    if _sha256_file(path.expanduser().resolve()) != expected_hash:
        raise ProgramMetaAdjudicationError(
            "behavior episode sha256 does not match manifest behavior_episode_hash"
        )
    if payload.get("authority") != "behavior_evidence_only_non_authoritative":
        raise ProgramMetaAdjudicationError(
            "behavior episode authority must remain evidence-only"
        )
    non_authority = _safe_mapping(payload.get("non_authority"))
    for key in (
        "optimization_authority",
        "promotion_authority",
        "oracle_ranking",
        "oracle_pruning",
        "oracle_promotion",
        "governance_authority",
        "external_mutation",
        "external_authority_mutated",
        "winner_selection",
    ):
        if non_authority.get(key) is not False:
            raise ProgramMetaAdjudicationError(
                f"behavior episode non_authority flag must remain false: {key}"
            )


def _behavior_summary(behavior: Mapping[str, Any] | None) -> dict[str, Any]:
    if behavior is None:
        return {
            "present": False,
            "status": "missing",
            "passed": 0,
            "failed": 0,
            "error": 0,
            "total": 0,
        }
    summary = _safe_mapping(behavior.get("summary"))
    return {
        "present": True,
        "status": _first_text(summary.get("status"), behavior.get("status"), "unknown"),
        "passed": _summary_int(summary.get("passed"), field="passed"),
        "failed": _summary_int(summary.get("failed"), field="failed"),
        "error": _summary_int(summary.get("error"), field="error"),
        "degraded": _summary_int(summary.get("degraded"), field="degraded"),
        "total": _summary_int(
            summary.get("total") or len(_safe_list(behavior.get("examples"))) or 0,
            field="total",
        ),
    }


def _role_judgment(
    *,
    role: Mapping[str, Any],
    manifest_text: str,
    behavior_summary: Mapping[str, Any],
    oracle_report: Mapping[str, Any] | None,
    activation_packet: Mapping[str, Any] | None,
    generation_fitness_results: Mapping[str, Any] | None,
) -> dict[str, Any]:
    perspective = str(role.get("perspective") or "unspecified")
    status = "supports_domain_review"
    missing_evidence: list[str] = []
    rationale = "deterministic evidence contract check passed for this perspective"

    behavior_present = behavior_summary.get("present") is True
    behavior_passed = behavior_summary.get("status") == "passed"
    activation_effect = (
        _safe_mapping(activation_packet.get("effect")) if activation_packet else {}
    )
    activation_boundary = (
        _safe_mapping(activation_packet.get("boundary_checks"))
        if activation_packet
        else {}
    )

    if perspective == "behavior_evidence":
        if not behavior_present:
            status = "needs_more_evidence"
            missing_evidence.append(
                "behavior_results.json, behavior_episode.json, or runtime_episode.json"
            )
            rationale = "no behavior evidence sidecar was available"
        elif not behavior_passed:
            status = "withhold"
            rationale = "behavior evidence did not report passed status"
    elif perspective == "authority_boundary":
        authority_boundary_values = [
            value for key, value in activation_boundary.items() if "authority" in key
        ]
        if activation_packet and any(
            value is True for value in authority_boundary_values
        ):
            status = "withhold"
            rationale = "activation packet boundary checks report authority drift"
        elif (
            activation_packet
            and activation_effect.get("production_activation_applied") is True
        ):
            status = "withhold"
            rationale = (
                "activation packet reports production activation already applied"
            )
        else:
            rationale = "DSPx evidence remains non-authoritative and activation remains outside DSPx"
    elif perspective == "source_grounding":
        if not any(
            token in manifest_text
            for token in ("source", "zotero", "citation", "marker", "rag")
        ):
            status = "needs_more_evidence"
            missing_evidence.append("source grounding declaration")
            rationale = "target does not expose deterministic source-grounding cues"
        elif oracle_report is None:
            status = "supports_domain_review_with_caveat"
            missing_evidence.append("program_oracle_report.json")
            rationale = "source-sensitive target has behavior evidence but no Oracle report sidecar"
    elif perspective == "canonical_mutation_safety":
        if not any(
            token in manifest_text
            for token in ("review", "proposal", "canonical", "wiki", "atlas")
        ):
            status = "needs_more_evidence"
            missing_evidence.append("canonical mutation boundary declaration")
            rationale = "canonical mutation safety could not be established from target declaration"
        elif activation_effect.get("production_activation_applied") is True:
            status = "withhold"
            rationale = "activation effect reports production activation"
        else:
            rationale = "target declares review/canonical boundary and no activation effect is reported"
    elif perspective == "review_surface":
        if not any(
            token in manifest_text for token in ("review", "proposal", "human", "queue")
        ):
            status = "needs_more_evidence"
            missing_evidence.append("review surface declaration")
            rationale = "review/proposal surface is not deterministically declared"
        else:
            rationale = "review/proposal surface is deterministically declared"
    elif perspective == "target_protocol_fidelity":
        if generation_fitness_results is None:
            status = "needs_more_evidence"
            missing_evidence.append("generation_fitness_results.json")
            rationale = "target-bound evidence needs generation fitness results before downstream review"
        elif generation_fitness_results.get("status") != "fitness_passed":
            status = "withhold"
            rationale = "generation fitness results do not report fitness_passed"
        elif generation_fitness_results.get("rendered_state") != (
            "eligible_for_downstream_evidence_review"
        ):
            status = "withhold"
            rationale = "fitness_passed is not rendered as eligible_for_downstream_evidence_review"
        else:
            rationale = "target-fidelity result permits downstream evidence review only, not approval or activation"
    elif perspective == "rollout_rollback":
        if activation_packet is None:
            status = "needs_more_evidence"
            missing_evidence.append("activation_packet.json")
            rationale = "rollout/rollback posture requires an activation packet before domain decision"
        elif activation_packet.get("canonical_binding_ref") in {None, ""}:
            status = "supports_domain_review_with_caveat"
            missing_evidence.append("canonical binding ref before rollout")
            rationale = "packet is ready for domain decision but not rollout/activation"
        else:
            rationale = "activation packet includes a canonical binding ref"
    elif perspective == "target_domain":
        if not behavior_present:
            status = "needs_more_evidence"
            missing_evidence.append("behavior evidence")
            rationale = "target-domain judgment needs behavior evidence"
        else:
            rationale = "target objective and behavior evidence are available for domain-owner review"

    return {
        "role_id": role.get("role_id"),
        "source_juror_id": role.get("source_juror_id"),
        "perspective": perspective,
        "judgment": status,
        "rationale": rationale,
        "missing_evidence": missing_evidence,
        "activation_authority": False,
        "model_backed": False,
        "provider_called": False,
    }


def build_program_evidence_adjudication(
    *,
    adjudicator_verification_path: Path,
    manifest_path: Path,
    behavior_results_path: Path | None = None,
    behavior_episode_path: Path | None = None,
    runtime_episode_path: Path | None = None,
    oracle_report_path: Path | None = None,
    activation_packet_path: Path | None = None,
    generation_fitness_results_path: Path | None = None,
    generation_traceability_path: Path | None = None,
) -> dict[str, Any]:
    """Judge program evidence with the verified deterministic program adjudicator."""

    adjudicator_verification = _load_expected_sidecar(
        adjudicator_verification_path,
        key="program_adjudicator_verification",
        label="program adjudicator verification",
    )
    if (
        adjudicator_verification.get("status") != "verified"
        or adjudicator_verification.get("approved_for_program_evidence_adjudication")
        is not True
    ):
        raise ProgramMetaAdjudicationError(
            "program adjudicator verification must be verified before evidence adjudication"
        )
    formation_ref_ok, formation_ref_detail, formation = _load_hash_bound_ref(
        adjudicator_verification.get("program_adjudicator_formation"),
        expected_schema=PROGRAM_ADJUDICATOR_FORMATION_SCHEMA,
        label="program adjudicator formation ref",
    )
    if not formation_ref_ok or formation is None:
        raise ProgramMetaAdjudicationError(
            "program adjudicator verification must hash-bind a valid formation sidecar: "
            + formation_ref_detail
        )

    manifest = load_program_manifest(manifest_path)
    manifest_text = _manifest_text(manifest)
    if runtime_episode_path is not None and (
        behavior_results_path is not None or behavior_episode_path is not None
    ):
        raise ProgramMetaAdjudicationError(
            "runtime_episode cannot be combined with explicit behavior_results or behavior_episode evidence"
        )
    behavior_path = (
        _default_existing_path(
            manifest_path,
            explicit_path=behavior_results_path,
            default_name="behavior_results.json",
        )
        if runtime_episode_path is None
        else None
    )
    behavior_episode_ref = (
        _default_existing_path(
            manifest_path,
            explicit_path=behavior_episode_path,
            default_name="behavior_episode.json",
        )
        if runtime_episode_path is None
        else None
    )
    behavior_payload: dict[str, Any] | None = None
    behavior_ref: dict[str, Any] | None = None
    if behavior_path is not None:
        behavior_payload = _load_expected_sidecar(
            behavior_path, key="behavior_results", label="behavior results"
        )
        _validate_behavior_results_contract(
            payload=behavior_payload, path=behavior_path, manifest=manifest
        )
        behavior_ref = _artifact_ref(
            behavior_path, schema_version="program-behavior-results-v1"
        )
    elif behavior_episode_ref is not None:
        behavior_payload = _load_expected_sidecar(
            behavior_episode_ref, key="behavior_episode", label="behavior episode"
        )
        _validate_behavior_episode_contract(
            payload=behavior_payload, path=behavior_episode_ref, manifest=manifest
        )
        behavior_ref = _artifact_ref(
            behavior_episode_ref, schema_version="program-behavior-episode-v1"
        )

    runtime_episode_ref = None
    runtime_episode_file = None
    if runtime_episode_path is not None:
        runtime_episode_file = runtime_episode_path.expanduser().resolve()
    elif behavior_payload is None:
        runtime_episode_file = _default_existing_path(
            manifest_path,
            explicit_path=None,
            default_name="runtime_episode.json",
        )
    if runtime_episode_file is not None:
        runtime_episode = _load_expected_sidecar(
            runtime_episode_file, key="runtime_episode", label="runtime episode"
        )
        _validate_runtime_episode_sidecar(
            manifest_path=manifest_path,
            runtime_episode_path=runtime_episode_file,
            runtime_episode=runtime_episode,
        )
        runtime_episode_ref = _artifact_ref(
            runtime_episode_file, schema_version=PROGRAM_RUNTIME_EPISODE_SCHEMA
        )
        if behavior_payload is None:
            runtime_behavior_path = (
                runtime_episode_file.parent / "behavior_results.json"
            )
            behavior_payload = _load_expected_sidecar(
                runtime_behavior_path,
                key="behavior_results",
                label="runtime behavior results",
            )
            behavior_ref = _artifact_ref(
                runtime_behavior_path, schema_version="program-behavior-results-v1"
            )

    resolved_oracle_report_path = _default_existing_path(
        manifest_path,
        explicit_path=oracle_report_path,
        default_name="program_oracle_report.json",
    )
    oracle_report = None
    oracle_ref = None
    if resolved_oracle_report_path is not None:
        oracle_report = _load_expected_sidecar(
            resolved_oracle_report_path, key="oracle_report", label="oracle report"
        )
        oracle_ref = _artifact_ref(
            resolved_oracle_report_path,
            schema_version="program-oracle-evidence-report-v1",
        )

    resolved_activation_packet_path = _default_existing_path(
        manifest_path,
        explicit_path=activation_packet_path,
        default_name="activation_packet.json",
    )
    activation_packet = None
    activation_ref = None
    if resolved_activation_packet_path is not None:
        activation_packet = _load_expected_sidecar(
            resolved_activation_packet_path,
            key="activation_packet",
            label="activation packet",
        )
        activation_ref = _artifact_ref(
            resolved_activation_packet_path,
            schema_version="generated-cognition-program-production-activation-packet-v1",
        )

    resolved_generation_fitness_results_path = _default_existing_path(
        manifest_path,
        explicit_path=generation_fitness_results_path,
        default_name="generation_fitness_results.json",
    )
    generation_fitness_results = None
    generation_fitness_results_ref = None
    if resolved_generation_fitness_results_path is not None:
        generation_fitness_results = _load_expected_sidecar(
            resolved_generation_fitness_results_path,
            key="generation_fitness_results",
            label="generation fitness results",
        )
        generation_fitness_results_ref = _artifact_ref(
            resolved_generation_fitness_results_path,
            schema_version="gen-fitness-results-v1",
        )

    resolved_generation_traceability_path = _default_existing_path(
        manifest_path,
        explicit_path=generation_traceability_path,
        default_name="generation_traceability.json",
    )
    generation_traceability_ref = None
    if resolved_generation_traceability_path is not None:
        _load_expected_sidecar(
            resolved_generation_traceability_path,
            key="generation_traceability",
            label="generation traceability",
        )
        generation_traceability_ref = _artifact_ref(
            resolved_generation_traceability_path,
            schema_version="gen-traceability-v1",
        )

    adjudicator = _safe_mapping(formation.get("program_adjudicator"))
    roles = [
        dict(role)
        for role in _safe_list(adjudicator.get("roles"))
        if isinstance(role, Mapping)
    ]
    summary = _behavior_summary(behavior_payload)
    role_judgments = [
        _role_judgment(
            role=role,
            manifest_text=manifest_text,
            behavior_summary=summary,
            oracle_report=oracle_report,
            activation_packet=activation_packet,
            generation_fitness_results=generation_fitness_results,
        )
        for role in roles
    ]
    judgment_counts: dict[str, int] = {}
    missing_evidence = sorted(
        {
            str(item)
            for judgment in role_judgments
            for item in _safe_list(judgment.get("missing_evidence"))
        }
    )
    for judgment in role_judgments:
        key = str(judgment.get("judgment"))
        judgment_counts[key] = judgment_counts.get(key, 0) + 1
    blocking_judgments = [
        judgment
        for judgment in role_judgments
        if judgment.get("judgment") in {"withhold", "needs_more_evidence"}
    ]
    ready_for_domain_decision = behavior_ref is not None and not blocking_judgments
    recommendation = (
        "ready_for_domain_decision_not_activation"
        if ready_for_domain_decision
        else "revise_or_collect_missing_evidence"
    )
    return {
        "schema_version": PROGRAM_EVIDENCE_ADJUDICATION_SCHEMA,
        "status": "evidence_adjudicated",
        "authority": "program_evidence_adjudication_evidence_only_non_authoritative",
        "identity": _identity_from_manifest(manifest),
        "manifest": _artifact_ref(
            manifest_path, schema_version=manifest.get("schema_version")
        ),
        "program_adjudicator_verification": _artifact_ref(
            adjudicator_verification_path,
            schema_version=PROGRAM_ADJUDICATOR_VERIFICATION_SCHEMA,
        ),
        "program_adjudicator_formation": adjudicator_verification.get(
            "program_adjudicator_formation"
        ),
        "evidence_refs": {
            "behavior": behavior_ref,
            "runtime_episode": runtime_episode_ref,
            "oracle_report": oracle_ref,
            "activation_packet": activation_ref,
            "generation_traceability": generation_traceability_ref,
            "generation_fitness_results": generation_fitness_results_ref,
        },
        "behavior_summary": summary,
        "role_judgments": role_judgments,
        "aggregate": {
            "recommendation": recommendation,
            "ready_for_domain_decision": ready_for_domain_decision,
            "activation_approved": False,
            "judgment_counts": judgment_counts,
            "missing_evidence": missing_evidence,
            "blocking_perspectives": [
                str(judgment.get("perspective")) for judgment in blocking_judgments
            ],
        },
        "next_required_action": (
            "write_adjudication_behavior_trace"
            if ready_for_domain_decision
            else "collect_missing_evidence_or_revise_candidate"
        ),
        "notes": [
            "This sidecar adjudicates evidence only; it is not production activation.",
            "Rollout still requires domain/governance authority and canonical binding.",
        ],
        "non_authority": dict(_NON_AUTHORITY),
        "effect": dict(_EFFECT),
    }


def write_program_evidence_adjudication(
    adjudication: Mapping[str, Any], out_path: Path
) -> dict[str, Any]:
    if adjudication.get("schema_version") != PROGRAM_EVIDENCE_ADJUDICATION_SCHEMA:
        raise ProgramMetaAdjudicationError(
            "program evidence adjudication schema_version must be "
            + PROGRAM_EVIDENCE_ADJUDICATION_SCHEMA
        )
    payload = dict(adjudication)
    out = _prepare_guarded_sidecar_output(
        out_path,
        payload=payload,
        artifact_label="program evidence adjudication",
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_json_text(payload), encoding="utf-8")
    return payload


def build_program_adjudication_behavior_trace(
    *,
    evidence_adjudication_path: Path,
    adjudicator_delegation_path: Path | None = None,
    decision_record_path: Path | None = None,
) -> dict[str, Any]:
    """Build a local behavior trace for later explicit Oracle/Postgres publication."""

    adjudication = _load_expected_sidecar(
        evidence_adjudication_path,
        key="program_evidence_adjudication",
        label="program evidence adjudication",
    )
    if adjudication.get("status") != "evidence_adjudicated":
        raise ProgramMetaAdjudicationError(
            "program evidence adjudication must be evidence_adjudicated before tracing"
        )
    aggregate = _safe_mapping(adjudication.get("aggregate"))
    role_judgments = [
        dict(item)
        for item in _safe_list(adjudication.get("role_judgments"))
        if isinstance(item, Mapping)
    ]
    delegation = None
    delegation_ref = None
    if adjudicator_delegation_path is not None:
        delegation = _load_expected_sidecar(
            adjudicator_delegation_path,
            key="program_adjudicator_delegation",
            label="program adjudicator delegation",
        )
        delegation_ref = _artifact_ref(
            adjudicator_delegation_path,
            schema_version=PROGRAM_ADJUDICATOR_DELEGATION_SCHEMA,
        )
    decision_record = None
    decision_ref = None
    if decision_record_path is not None:
        decision_record = _load_expected_sidecar(
            decision_record_path,
            key="decision_record",
            label="program promotion decision record",
        )
        decision_ref = _artifact_ref(
            decision_record_path,
            schema_version="program-promotion-decision-record-v1",
        )
    delegation_generated_adjudicator = _safe_mapping(
        _safe_mapping(delegation or {}).get("generated_program_adjudicator")
    )
    decision_delegation = _safe_mapping(
        _safe_mapping(decision_record or {}).get("adjudicator_delegation")
    )
    trace_events = [
        {
            "event": "program_evidence_adjudicated",
            "status": adjudication.get("status"),
            "recommendation": aggregate.get("recommendation"),
            "ready_for_domain_decision": aggregate.get("ready_for_domain_decision"),
        }
    ]
    if delegation is not None:
        trace_events.append(
            {
                "event": "dspx_meta_adjudicator_delegated_generated_program_adjudicator",
                "status": delegation.get("status"),
                "delegated_by": _safe_mapping(
                    delegation.get("dspx_meta_adjudicator")
                ).get("id"),
                "generated_program_adjudicator": delegation_generated_adjudicator.get(
                    "id"
                ),
                "approved_to_decide": delegation_generated_adjudicator.get(
                    "approved_to_decide"
                )
                is True,
            }
        )
    if decision_record is not None:
        trace_events.append(
            {
                "event": "generated_program_adjudicator_decided",
                "status": decision_record.get("status"),
                "outcome": decision_record.get("outcome"),
                "decided_by": decision_record.get("decided_by"),
                "delegated_by": decision_delegation.get("decided_by"),
                "promotion_state_after_decision": decision_record.get(
                    "promotion_state_after_decision"
                ),
            }
        )
    trace_events.append(
        {
            "event": "authority_boundary_preserved",
            "activation_approved": False,
            "shared_oracle_write_performed": False,
        }
    )
    linked_artifacts = {
        "manifest": _safe_mapping(adjudication.get("manifest")),
        "program_adjudicator_verification": _safe_mapping(
            adjudication.get("program_adjudicator_verification")
        ),
        "program_adjudicator_formation": _safe_mapping(
            adjudication.get("program_adjudicator_formation")
        ),
        "evidence_refs": _safe_mapping(adjudication.get("evidence_refs")),
    }
    if delegation_ref is not None:
        linked_artifacts["program_adjudicator_delegation"] = delegation_ref
    if decision_ref is not None:
        linked_artifacts["generated_program_adjudicator_decision"] = decision_ref
    return {
        "schema_version": PROGRAM_ADJUDICATION_BEHAVIOR_TRACE_SCHEMA,
        "status": "trace_ready_for_publication_preflight",
        "authority": "adjudication_behavior_trace_empirical_memory_only_non_authoritative",
        "identity": _safe_mapping(adjudication.get("identity")),
        "source_adjudication": _artifact_ref(
            evidence_adjudication_path,
            schema_version=PROGRAM_EVIDENCE_ADJUDICATION_SCHEMA,
        ),
        "linked_artifacts": linked_artifacts,
        "trace_events": trace_events,
        "judging_behavior": {
            "adjudicator_id": "program_adjudicator_from_verified_meta_jury_v1",
            "meta_adjudicator_id": "dspx_meta_adjudicator_v1",
            "generated_program_adjudicator_id": delegation_generated_adjudicator.get(
                "id"
            ),
            "generated_program_decision_outcome": _safe_mapping(
                decision_record or {}
            ).get("outcome"),
            "mode": "deterministic_contract_check",
            "role_judgment_count": len(role_judgments),
            "judgment_counts": _safe_mapping(aggregate.get("judgment_counts")),
            "missing_evidence": _safe_list(aggregate.get("missing_evidence")),
        },
        "oracle_postgres_publication": {
            "publication_label": "adjudication_behavior_trace",
            "shared_oracle_write_performed": False,
            "eligible_for_publication_preflight": True,
            "redaction_status": "not_reviewed",
            "retention_class": "retained_when_published",
            "authority_ref_required": False,
            "activation_authority": False,
        },
        "gepa_improvement_lane": {
            "candidate_example_schema": "program-adjudication-gepa-example-v1",
            "eligible_after_publication_and_labeling": True,
            "requires_later_domain_outcome_label": True,
            "activation_authority": False,
        },
        "non_authority": dict(_NON_AUTHORITY),
        "effect": dict(_EFFECT),
    }


def write_program_adjudication_behavior_trace(
    trace: Mapping[str, Any], out_path: Path
) -> dict[str, Any]:
    if trace.get("schema_version") != PROGRAM_ADJUDICATION_BEHAVIOR_TRACE_SCHEMA:
        raise ProgramMetaAdjudicationError(
            "program adjudication behavior trace schema_version must be "
            + PROGRAM_ADJUDICATION_BEHAVIOR_TRACE_SCHEMA
        )
    payload = dict(trace)
    out = _prepare_guarded_sidecar_output(
        out_path,
        payload=payload,
        artifact_label="program adjudication behavior trace",
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_json_text(payload), encoding="utf-8")
    return payload


def build_program_meta_adjudication_plan(
    *,
    manifest_path: Path,
    behavior_results_path: Path | None = None,
    behavior_episode_path: Path | None = None,
    runtime_episode_path: Path | None = None,
    oracle_report_path: Path | None = None,
    oracle_publication_receipt_path: Path | None = None,
    jury_results_path: Path | None = None,
    review_path: Path | None = None,
    decision_record_path: Path | None = None,
    activation_packet_path: Path | None = None,
    generation_target_contract_path: Path | None = None,
    generation_fitness_suite_path: Path | None = None,
    generation_gate_preflight_path: Path | None = None,
    generation_traceability_path: Path | None = None,
    generation_fitness_results_path: Path | None = None,
    program_adjudicator_delegation_path: Path | None = None,
    program_evidence_adjudication_path: Path | None = None,
) -> dict[str, Any]:
    """Build a local meta-adjudication plan without model calls or authority effects."""

    try:
        manifest = load_program_manifest(manifest_path)
    except ProgramRefinementError as exc:
        raise ProgramMetaAdjudicationError(str(exc)) from exc

    sidecars: dict[str, dict[str, Any]] = {}

    def record_sidecar(key: str, explicit_path: Path | None = None) -> None:
        sidecars[key] = _sidecar_status(
            manifest_path, key=key, explicit_path=explicit_path
        )

    record_sidecar("behavior_results", behavior_results_path)
    record_sidecar("behavior_episode", behavior_episode_path)
    record_sidecar("runtime_episode", runtime_episode_path)
    record_sidecar("oracle_report", oracle_report_path)
    record_sidecar("oracle_publication_receipt", oracle_publication_receipt_path)
    record_sidecar("jury_results", jury_results_path)
    record_sidecar("review", review_path)
    record_sidecar("decision_record", decision_record_path)
    record_sidecar("activation_packet", activation_packet_path)
    record_sidecar("generation_target_contract", generation_target_contract_path)
    record_sidecar("generation_fitness_suite", generation_fitness_suite_path)
    record_sidecar("generation_gate_preflight", generation_gate_preflight_path)
    record_sidecar("generation_traceability", generation_traceability_path)
    record_sidecar("generation_fitness_results", generation_fitness_results_path)
    record_sidecar("target_profile")
    record_sidecar("jury_requirements")
    record_sidecar("meta_jury_selection")
    record_sidecar("jury_verification")
    record_sidecar("program_adjudicator_formation")
    record_sidecar("program_adjudicator_verification")
    record_sidecar(
        "program_adjudicator_delegation", program_adjudicator_delegation_path
    )
    sidecars["program_evidence_adjudication"] = _sidecar_status(
        manifest_path,
        key="program_evidence_adjudication",
        explicit_path=program_evidence_adjudication_path,
        sibling_sidecars=sidecars,
    )
    record_sidecar("adjudication_behavior_trace")
    record_sidecar("adjudication_gepa_example")
    profile = _target_profile(
        manifest,
        manifest_path=manifest_path,
        target_fidelity_sidecars={
            key: sidecars[key]
            for key in (
                "generation_target_contract",
                "generation_fitness_suite",
                "generation_gate_preflight",
                "generation_traceability",
                "generation_fitness_results",
            )
        },
    )
    requirements = _jury_requirements(profile)
    missing = _missing_evidence(sidecars)
    return {
        "schema_version": PROGRAM_META_ADJUDICATION_PLAN_SCHEMA,
        "status": "planned_not_executed",
        "lifecycle_state": "meta_adjudication_plan_ready",
        "authority": "local_meta_adjudication_plan_evidence_only_non_authoritative",
        "identity": _identity_from_manifest(manifest),
        "manifest": {
            "path": str(manifest_path.expanduser().resolve()),
            "sha256": _sha256_file(manifest_path.expanduser().resolve()),
            "schema_version": manifest.get("schema_version"),
        },
        "target_profile": profile,
        "jury_requirements": requirements,
        "sidecars": sidecars,
        "missing_evidence": missing,
        "next_commands": _next_commands(manifest_path, sidecars),
        "oracle_postgres_behavior_memory": {
            "intended_label": "adjudication_behavior_trace",
            "publication_allowed_by_this_plan": False,
            "requires_explicit_publication_preflight": True,
            "activation_authority": False,
        },
        "gepa_improvement_lane": {
            "eligible_after_trace_publication": True,
            "optimized_artifact_kind": "versioned_judging_policy_or_prompt",
            "activation_authority": False,
            "requires_curated_train_validation_examples": True,
        },
        "non_authority": dict(_NON_AUTHORITY),
        "effect": dict(_EFFECT),
    }


def build_program_adjudication_gepa_example(
    *,
    trace_path: Path,
    outcome_label: str | None = None,
    feedback: str | None = None,
) -> dict[str, Any]:
    """Build a deterministic GEPA example from an adjudication behavior trace."""

    trace = _load_expected_sidecar(
        trace_path, key="adjudication_behavior_trace", label="adjudication trace"
    )
    if trace.get("status") != "trace_ready_for_publication_preflight":
        raise ProgramMetaAdjudicationError(
            "adjudication trace must be trace_ready_for_publication_preflight"
        )
    linked_artifacts = _safe_mapping(trace.get("linked_artifacts"))
    evidence_refs = _safe_mapping(linked_artifacts.get("evidence_refs"))
    judging_behavior = _safe_mapping(trace.get("judging_behavior"))
    trace_events = [
        dict(item)
        for item in _safe_list(trace.get("trace_events"))
        if isinstance(item, Mapping)
    ]
    primary_event = trace_events[0] if trace_events else {}
    label = _first_text(outcome_label, "pending_domain_outcome")
    feedback_text = _first_text(
        feedback,
        "Await later human/domain outcome before using this example for GEPA training.",
    )
    trainable = label != "pending_domain_outcome"
    return {
        "schema_version": PROGRAM_ADJUDICATION_GEPA_EXAMPLE_SCHEMA,
        "status": "curated_pending_outcome_label"
        if not trainable
        else "curated_with_outcome_label",
        "authority": "adjudication_gepa_example_optimization_input_only_non_authoritative",
        "identity": _safe_mapping(trace.get("identity")),
        "source_trace": _artifact_ref(
            trace_path, schema_version=PROGRAM_ADJUDICATION_BEHAVIOR_TRACE_SCHEMA
        ),
        "input": {
            "manifest": _safe_mapping(linked_artifacts.get("manifest")),
            "program_adjudicator_verification": _safe_mapping(
                linked_artifacts.get("program_adjudicator_verification")
            ),
            "program_adjudicator_formation": _safe_mapping(
                linked_artifacts.get("program_adjudicator_formation")
            ),
            "program_adjudicator_delegation": _safe_mapping(
                linked_artifacts.get("program_adjudicator_delegation")
            ),
            "generated_program_adjudicator_decision": _safe_mapping(
                linked_artifacts.get("generated_program_adjudicator_decision")
            ),
            "evidence_refs": evidence_refs,
            "judging_behavior": judging_behavior,
        },
        "expected_output": {
            "recommendation": primary_event.get("recommendation"),
            "ready_for_domain_decision": primary_event.get("ready_for_domain_decision"),
            "activation_authority": False,
            "missing_evidence": _safe_list(judging_behavior.get("missing_evidence")),
        },
        "label": {
            "outcome_label": label,
            "label_source": "operator_or_domain_outcome" if trainable else "pending",
            "feedback": feedback_text,
            "usable_for_gepa_training": trainable,
            "usable_for_gepa_validation": trainable,
        },
        "metric_hint": {
            "score_field": "judgment_quality_score",
            "feedback_field": "feedback",
            "optimize_for": [
                "risk_detection",
                "authority_boundary_preservation",
                "missing_evidence_precision",
                "domain_outcome_alignment",
            ],
        },
        "gepa_improvement_lane": {
            "candidate_module": "EvidenceAdjudicationModule",
            "requires_train_validation_split": True,
            "requires_multiple_labeled_examples": True,
            "activation_authority": False,
        },
        "non_authority": dict(_NON_AUTHORITY),
        "effect": dict(_EFFECT),
    }


def write_program_adjudication_gepa_example(
    example: Mapping[str, Any], out_path: Path
) -> dict[str, Any]:
    if example.get("schema_version") != PROGRAM_ADJUDICATION_GEPA_EXAMPLE_SCHEMA:
        raise ProgramMetaAdjudicationError(
            "program adjudication GEPA example schema_version must be "
            + PROGRAM_ADJUDICATION_GEPA_EXAMPLE_SCHEMA
        )
    payload = dict(example)
    out = _prepare_guarded_sidecar_output(
        out_path,
        payload=payload,
        artifact_label="program adjudication GEPA example",
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_json_text(payload), encoding="utf-8")
    return payload


def write_program_meta_adjudication_plan(
    plan: Mapping[str, Any], out_path: Path
) -> dict[str, Any]:
    if plan.get("schema_version") != PROGRAM_META_ADJUDICATION_PLAN_SCHEMA:
        raise ProgramMetaAdjudicationError(
            "meta-adjudication plan schema_version must be "
            + PROGRAM_META_ADJUDICATION_PLAN_SCHEMA
        )
    payload = dict(plan)
    out = _prepare_guarded_sidecar_output(
        out_path,
        payload=payload,
        artifact_label="meta-adjudication plan",
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_json_text(payload), encoding="utf-8")
    return payload
