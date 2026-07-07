from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Mapping

from dspx.services.artifact_boundary import prepare_sidecar_output_path
from dspx.services.program_artifact_names import PROTECTED_PROGRAM_ARTIFACT_NAMES
from dspx.services.program_external_authority_export import (
    ProgramExternalAuthorityExportError,
    validate_program_external_authority_export_preflight_contract,
)
from dspx.services.program_evidence_adjudication_validation import (
    validate_program_evidence_adjudication_contract,
)
from dspx.services.program_jury_result_validation import (
    validate_program_jury_results_contract,
)
from dspx.services.program_model_jury_validation import (
    PROGRAM_MODEL_JURY_RESULTS_SCHEMA,
    validate_program_model_jury_results_contract,
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

ACTIVATION_PACKET_SCHEMA = "generated-cognition-program-production-activation-packet-v1"
TRANSITION_TYPE = "generated-cognition-program.production_activation"
GOVERNANCE_BOUNDARY_REF = (
    "~/ai-society/holdingco/governance-kernel/docs/core/definitions/"
    "generated-dspy-program-promotion-governance.md"
)
TRANSITION_PASSPORT_REF = (
    "~/ai-society/holdingco/governance-kernel/docs/core/definitions/"
    "transition-passports/generated-cognition-program-production-activation.md"
)

_EXPECTED_SCHEMAS = {
    "oracle_report": "program-oracle-evidence-report-v1",
    "jury_results": "program-jury-results-v2",
    "model_jury_results": PROGRAM_MODEL_JURY_RESULTS_SCHEMA,
    "refined_review": "program-promotion-review-refined-v1",
    "decision_record": "program-promotion-decision-record-v1",
    "promotion_plan": "program-promotion-plan-v1",
    "oracle_publication_preflight": "program-oracle-shared-publication-preflight-v1",
    "oracle_publication_receipt": "program-oracle-shared-publication-receipt-v1",
    "candidate_state": "program-candidate-state-v1",
    "obsidian_review_adapter_receipt": "dspy-pdf-transition-review-adapter-receipt-v1",
    "canonical_binding_verification": "program-canonical-binding-verification-v1",
    "external_authority_export_preflight": "program-external-authority-export-preflight-v1",
    "generation_fitness_results": "gen-fitness-results-v1",
    "program_evidence_adjudication": "program-evidence-adjudication-v1",
    "runtime_episode": PROGRAM_RUNTIME_EPISODE_SCHEMA,
}

CANONICAL_BINDING_VERIFICATION_SCHEMA = "program-canonical-binding-verification-v1"
_AK_DECISION_REF_RE = re.compile(r"^ak://decision/(?P<id>[0-9]+)#accepted$")

_ACTIVATION_PACKET_PROTECTED_OUTPUT_NAMES = {
    *PROTECTED_PROGRAM_ARTIFACT_NAMES,
    "promotion_decision_record.json",
    "promotion_plan.json",
    "jury_results.json",
    "model_jury_results.json",
}

_NON_AUTHORITY = {
    "activation_packet_only": True,
    "program_activation_applied": False,
    "automatic_promotion": False,
    "oracle_ranking": False,
    "oracle_pruning": False,
    "oracle_promotion": False,
    "jury_promotion_authority": False,
    "mlflow_approval_authority": False,
    "governance_authority": False,
    "external_mutation": False,
}

_EFFECT = {
    "activation_packet_written": True,
    "program_files_mutated": False,
    "oracle_index_mutated": False,
    "mlflow_mutated": False,
    "ak_mutated": False,
    "external_authority_mutated": False,
    "production_activation_applied": False,
}


class ProgramActivationPacketError(ValueError):
    """Raised when activation packet inputs are malformed."""


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    source = path.expanduser().resolve()
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProgramActivationPacketError(f"{label} not found: {source}") from exc
    except json.JSONDecodeError as exc:
        raise ProgramActivationPacketError(
            f"{label} must be valid JSON: {source}"
        ) from exc
    if not isinstance(payload, dict):
        raise ProgramActivationPacketError(
            f"{label} must contain a JSON object: {source}"
        )
    return payload


def _safe_mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items()}


def _safe_list(value: object) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _first_text(*values: object) -> str | None:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return None


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
            execution_episode.get("episode_id"),
            receipt_bundle.get("episode_id"),
        ),
        "receipt_bundle_id": _first_text(receipt_bundle.get("receipt_bundle_id")),
    }


def _manifest_surfaces(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    candidate = _safe_mapping(manifest.get("candidate_assembly"))
    surfaces: list[dict[str, Any]] = []
    for surface in _safe_list(candidate.get("surfaces")):
        if isinstance(surface, Mapping):
            surfaces.append({str(key): item for key, item in surface.items()})
    return surfaces


def _artifact_ref(
    path: Path | None, *, schema_version: str | None = None
) -> dict[str, Any] | None:
    if path is None:
        return None
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        return None
    return {
        "path": str(resolved),
        "sha256": _sha256_file(resolved),
        **({"schema_version": schema_version} if schema_version else {}),
    }


def _load_optional_artifact(
    path: Path | None,
    *,
    label: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if path is None:
        return None, None
    payload = _load_json_object(path, label=label)
    expected_schema = _EXPECTED_SCHEMAS[label]
    if payload.get("schema_version") != expected_schema:
        raise ProgramActivationPacketError(
            f"{label} schema_version must be {expected_schema}"
        )
    return payload, _artifact_ref(path, schema_version=expected_schema)


def _validate_non_authority_false(
    payload: Mapping[str, Any], *, label: str, keys: tuple[str, ...]
) -> None:
    non_authority = _safe_mapping(payload.get("non_authority"))
    invalid = [key for key in keys if non_authority.get(key) is not False]
    if invalid:
        raise ProgramActivationPacketError(
            f"{label} widens non-authority flags: " + ", ".join(invalid)
        )


def _identity_mismatch(
    candidate_identity: Mapping[str, Any],
    artifact_identity: Mapping[str, Any],
) -> list[str]:
    mismatched: list[str] = []
    for key, candidate_value in candidate_identity.items():
        artifact_value = artifact_identity.get(key)
        if artifact_value in {None, ""} or candidate_value in {None, ""}:
            continue
        if str(artifact_value) != str(candidate_value):
            mismatched.append(key)
    return mismatched


def _missing_identity_keys(
    candidate_identity: Mapping[str, Any],
    artifact_identity: Mapping[str, Any],
) -> list[str]:
    return [
        key
        for key, candidate_value in candidate_identity.items()
        if candidate_value not in {None, ""}
        and artifact_identity.get(key) in {None, ""}
    ]


def _validate_artifact_identity(
    candidate_identity: Mapping[str, Any],
    artifact: Mapping[str, Any] | None,
    *,
    label: str,
) -> None:
    if artifact is None:
        return
    artifact_identity = _safe_mapping(artifact.get("identity"))
    if not artifact_identity:
        raise ProgramActivationPacketError(f"{label} missing identity object")
    missing = _missing_identity_keys(candidate_identity, artifact_identity)
    if missing:
        raise ProgramActivationPacketError(
            f"{label} identity is incomplete for candidate identity: "
            + ", ".join(missing)
        )
    mismatched = _identity_mismatch(candidate_identity, artifact_identity)
    if mismatched:
        raise ProgramActivationPacketError(
            f"{label} identity does not match candidate identity: "
            + ", ".join(mismatched)
        )


def _declared_behavior_result_hashes(manifest: Mapping[str, Any]) -> dict[str, str]:
    request = _safe_mapping(manifest.get("request"))
    execution_episode = _safe_mapping(manifest.get("execution_episode"))
    behavior_results = _safe_mapping(execution_episode.get("behavior_results"))
    receipt_bundle = _safe_mapping(manifest.get("receipt_bundle"))
    receipt_evidence = _safe_mapping(receipt_bundle.get("evidence"))
    hashes: dict[str, str] = {}
    for label, value in (
        ("request.behavior_results_hash", request.get("behavior_results_hash")),
        (
            "execution_episode.behavior_results.content_hash",
            behavior_results.get("content_hash"),
        ),
        (
            "receipt_bundle.evidence.behavior_results_hash",
            receipt_evidence.get("behavior_results_hash"),
        ),
    ):
        text = _first_text(value)
        if text:
            hashes[label] = text
    candidate = _safe_mapping(manifest.get("candidate_assembly"))
    for surface in _safe_list(candidate.get("surfaces")):
        if (
            not isinstance(surface, Mapping)
            or surface.get("kind") != "behavior_results"
        ):
            continue
        text = _first_text(surface.get("content_hash"))
        if text:
            hashes["candidate_assembly.surfaces.behavior_results.content_hash"] = text
    return hashes


def _declared_behavior_episode_hashes(manifest: Mapping[str, Any]) -> dict[str, str]:
    request = _safe_mapping(manifest.get("request"))
    execution_episode = _safe_mapping(manifest.get("execution_episode"))
    orchestration = _safe_mapping(execution_episode.get("behavior_orchestration"))
    episode_artifact = _safe_mapping(manifest.get("behavior_episode_artifact"))
    receipt_bundle = _safe_mapping(manifest.get("receipt_bundle"))
    receipt_evidence = _safe_mapping(receipt_bundle.get("evidence"))
    hashes: dict[str, str] = {}
    for label, value in (
        ("request.behavior_episode_hash", request.get("behavior_episode_hash")),
        (
            "execution_episode.behavior_orchestration.result_hash",
            orchestration.get("result_hash"),
        ),
        (
            "manifest.behavior_episode_artifact.content_hash",
            episode_artifact.get("content_hash"),
        ),
        (
            "receipt_bundle.evidence.behavior_episode_hash",
            receipt_evidence.get("behavior_episode_hash"),
        ),
    ):
        text = _first_text(value)
        if text:
            hashes[label] = text
    candidate = _safe_mapping(manifest.get("candidate_assembly"))
    for surface in _safe_list(candidate.get("surfaces")):
        if (
            not isinstance(surface, Mapping)
            or surface.get("kind") != "behavior_episode"
        ):
            continue
        text = _first_text(surface.get("content_hash"))
        if text:
            hashes["candidate_assembly.surfaces.behavior_episode.content_hash"] = text
    return hashes


def _validate_declared_hashes(
    *,
    actual_hash: str,
    declared_hashes: Mapping[str, str],
    label: str,
) -> None:
    mismatched = [
        name
        for name, declared_hash in declared_hashes.items()
        if declared_hash != actual_hash
    ]
    if mismatched:
        raise ProgramActivationPacketError(
            f"{label} hash does not match manifest declaration(s): "
            + ", ".join(sorted(mismatched))
        )


def _behavior_refs(root: Path, manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for name, schema, declared_hashes in (
        (
            "behavior_results.json",
            "program-behavior-results-v1",
            _declared_behavior_result_hashes(manifest),
        ),
        (
            "behavior_episode.json",
            "program-behavior-episode-v1",
            _declared_behavior_episode_hashes(manifest),
        ),
    ):
        path = root / name
        if not path.exists():
            continue
        payload = _load_json_object(path, label=name)
        if payload.get("schema_version") != schema:
            raise ProgramActivationPacketError(
                f"{name} schema_version must be {schema}"
            )
        actual_hash = _sha256_file(path)
        _validate_declared_hashes(
            actual_hash=actual_hash,
            declared_hashes=declared_hashes,
            label=name,
        )
        ref = _artifact_ref(path, schema_version=schema)
        if ref is not None:
            refs.append(ref)
    return refs


def _receipt_ref(manifest_path: Path) -> dict[str, Any] | None:
    return _artifact_ref(
        Path(str(manifest_path.expanduser().resolve()) + ".meta.json"),
        schema_version="dspx-run-receipt-v1",
    )


def _first_ref_hash_by_schema(
    refs: list[dict[str, Any]], *, schema_version: str
) -> str | None:
    for ref in refs:
        if ref.get("schema_version") == schema_version:
            return _first_text(ref.get("sha256"))
    return None


def _decision_outcome(decision_record: Mapping[str, Any] | None) -> str | None:
    if decision_record is None:
        return None
    outcome = str(decision_record.get("outcome") or "").strip()
    return outcome or None


def _decision_record_ref(path: Path | None) -> dict[str, Any] | None:
    return _artifact_ref(path, schema_version="program-promotion-decision-record-v1")


def _validate_decision_authority_owner(
    decision_record: Mapping[str, Any] | None, *, authority_owner: str
) -> None:
    if decision_record is None:
        return
    decided_by = str(decision_record.get("decided_by") or "").strip()
    if decided_by != authority_owner:
        raise ProgramActivationPacketError(
            "decision_record decided_by must match activation authority_owner"
        )


def _validate_jury_results_artifact_binding(
    jury_results: Mapping[str, Any],
    *,
    manifest_path: Path,
    manifest_hash: str,
) -> None:
    validate_program_jury_results_contract(
        jury_results,
        valid_manifest_refs={manifest_path: manifest_hash},
        label="jury_results",
        error_type=ProgramActivationPacketError,
        outside_root_message="outside the activation manifest root",
        manifest_mismatch_message=(
            "jury_results manifest sha256 does not match activation manifest"
        ),
    )


def _validate_activation_evidence_boundaries(
    *,
    manifest_path: Path,
    manifest_hash: str,
    jury_results: Mapping[str, Any] | None,
    model_jury_results: Mapping[str, Any] | None,
    refined_review: Mapping[str, Any] | None,
    decision_record: Mapping[str, Any] | None,
    promotion_plan: Mapping[str, Any] | None,
) -> None:
    if jury_results is not None:
        _validate_jury_results_artifact_binding(
            jury_results,
            manifest_path=manifest_path,
            manifest_hash=manifest_hash,
        )
    if model_jury_results is not None:
        validate_program_model_jury_results_contract(
            model_jury_results,
            label="model_jury_results",
            error_type=ProgramActivationPacketError,
            valid_manifest_refs={manifest_path: manifest_hash},
        )
    if refined_review is not None:
        _validate_non_authority_false(
            refined_review,
            label="refined_review",
            keys=(
                "automatic_promotion",
                "oracle_ranking",
                "oracle_pruning",
                "oracle_promotion",
                "program_mutation",
                "new_candidate_generation",
                "promotion_authority",
                "governance_authority",
                "external_mutation",
            ),
        )
    if decision_record is not None:
        _validate_non_authority_false(
            decision_record,
            label="decision_record",
            keys=(
                "automatic_promotion",
                "oracle_ranking",
                "oracle_pruning",
                "oracle_promotion",
                "program_mutation",
                "refined_review_mutation",
                "new_candidate_generation",
                "governance_authority",
                "external_mutation",
            ),
        )
    if promotion_plan is not None:
        _validate_non_authority_false(
            promotion_plan,
            label="promotion_plan",
            keys=(
                "automatic_promotion",
                "apply_promotion",
                "external_authority_export",
                "oracle_ranking",
                "oracle_pruning",
                "oracle_promotion",
                "winner_selection",
                "governance_authority",
                "external_mutation",
            ),
        )


def _validate_oracle_publication_receipt(
    identity: Mapping[str, Any],
    receipt: Mapping[str, Any] | None,
    *,
    preflight: Mapping[str, Any] | None = None,
    preflight_ref: Mapping[str, Any] | None = None,
) -> None:
    if receipt is None:
        return
    try:
        validate_program_oracle_publication_receipt_contract(
            receipt,
            expected_identities=(identity,),
            preflight=preflight,
            preflight_sha256=_first_text((preflight_ref or {}).get("sha256")),
        )
    except ProgramOraclePublicationError as exc:
        raise ProgramActivationPacketError(str(exc)) from exc


def _parse_ak_decision_ref(canonical_binding_ref: str) -> int:
    match = _AK_DECISION_REF_RE.fullmatch(str(canonical_binding_ref or "").strip())
    if match is None:
        raise ProgramActivationPacketError(
            "canonical_binding_ref must match ak://decision/<id>#accepted"
        )
    return int(match.group("id"))


def _ak_decision_payload(envelope: Mapping[str, Any]) -> Mapping[str, Any]:
    decision = envelope.get("decision")
    if isinstance(decision, Mapping):
        return decision
    return envelope


def _validate_canonical_binding_verification(
    *,
    verification: Mapping[str, Any] | None,
    canonical_binding_ref: str | None,
    decision_record_ref: Mapping[str, Any] | None,
) -> None:
    if verification is None:
        return
    if not str(canonical_binding_ref or "").strip():
        raise ProgramActivationPacketError(
            "canonical_binding_verification requires canonical_binding_ref"
        )
    if verification.get("status") != "verified":
        raise ProgramActivationPacketError(
            "canonical_binding_verification status must be verified"
        )
    if verification.get("canonical_binding_ref") != canonical_binding_ref:
        raise ProgramActivationPacketError(
            "canonical_binding_verification canonical_binding_ref does not match"
        )
    if verification.get("binding_kind") != "ak_decision":
        raise ProgramActivationPacketError(
            "canonical_binding_verification binding_kind must be ak_decision"
        )
    if verification.get("ak_decision_outcome") != "accepted":
        raise ProgramActivationPacketError(
            "canonical_binding_verification ak_decision_outcome must be accepted"
        )
    if verification.get("ak_decision_state") not in {"adr_recorded", "unblocked"}:
        raise ProgramActivationPacketError(
            "canonical_binding_verification ak_decision_state must be adr_recorded or unblocked"
        )
    if decision_record_ref is not None:
        expected_hash = _strip_sha256_prefix(decision_record_ref.get("sha256"))
        actual_hash = _strip_sha256_prefix(verification.get("decision_record_sha256"))
        if expected_hash and not actual_hash:
            raise ProgramActivationPacketError(
                "canonical_binding_verification decision_record_sha256 is required"
            )
        if expected_hash and actual_hash != expected_hash:
            raise ProgramActivationPacketError(
                "canonical_binding_verification decision_record_sha256 does not match"
            )


def _canonical_binding_verified(verification: Mapping[str, Any] | None) -> bool:
    return (
        verification is not None
        and verification.get("schema_version") == CANONICAL_BINDING_VERIFICATION_SCHEMA
        and verification.get("status") == "verified"
    )


def _canonical_binding_created_from(
    decision_record_path: Path, decision_record: Mapping[str, Any]
) -> dict[str, Any]:
    created_from = _safe_mapping(decision_record.get("created_from"))
    result: dict[str, Any] = {"decision_record_path": str(decision_record_path)}
    refined_review_path_text = _first_text(created_from.get("refined_review_path"))
    if refined_review_path_text is None:
        return result
    refined_review_path = Path(refined_review_path_text).expanduser().resolve()
    result["refined_review_path"] = str(refined_review_path)
    try:
        refined_review = _load_json_object(refined_review_path, label="refined_review")
    except ProgramActivationPacketError:
        return result
    review_created_from = _safe_mapping(refined_review.get("created_from"))
    manifest_path_text = _first_text(review_created_from.get("manifest_path"))
    if manifest_path_text is not None:
        result["manifest_path"] = str(Path(manifest_path_text).expanduser().resolve())
    return result


def build_canonical_binding_verification(
    *,
    canonical_binding_ref: str,
    decision_record_path: Path,
    ak_bin: Path | str = "ak",
    ak_db: Path | None = None,
    timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    normalized_ref = str(canonical_binding_ref or "").strip()
    decision_id = _parse_ak_decision_ref(normalized_ref)
    decision_record_path = decision_record_path.expanduser().resolve()
    decision_record = _load_json_object(decision_record_path, label="decision_record")
    if decision_record.get("schema_version") != "program-promotion-decision-record-v1":
        raise ProgramActivationPacketError(
            "decision_record schema_version must be program-promotion-decision-record-v1"
        )
    created_from = _safe_mapping(decision_record.get("created_from"))
    if created_from.get("ak_decision_ref") != normalized_ref:
        raise ProgramActivationPacketError(
            "decision_record created_from.ak_decision_ref must match canonical_binding_ref"
        )
    if decision_record.get("outcome") != "promote":
        raise ProgramActivationPacketError("decision_record outcome must be promote")

    command = [
        str(Path(ak_bin).expanduser()),
        "decision",
        "get",
        str(decision_id),
        "-F",
        "json",
    ]
    if ak_db is not None:
        command.extend(["--db", str(ak_db.expanduser())])
    try:
        proc = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as exc:
        raise ProgramActivationPacketError(
            f"canonical binding verification could not read AK decision {decision_id}: {exc}"
        ) from exc
    if proc.returncode != 0:
        raise ProgramActivationPacketError(
            "canonical binding verification AK lookup failed: " + proc.stderr.strip()
        )
    try:
        envelope = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ProgramActivationPacketError(
            "canonical binding verification AK lookup did not return JSON"
        ) from exc
    if not isinstance(envelope, Mapping):
        raise ProgramActivationPacketError(
            "canonical binding verification AK lookup must return a JSON object"
        )
    decision = _ak_decision_payload(envelope)
    if int(decision.get("id") or -1) != decision_id:
        raise ProgramActivationPacketError("AK decision id does not match binding ref")
    if decision.get("outcome") != "accepted":
        raise ProgramActivationPacketError("AK decision outcome must be accepted")
    if decision.get("state") not in {"adr_recorded", "unblocked"}:
        raise ProgramActivationPacketError(
            "AK decision state must be adr_recorded or unblocked"
        )
    if decision.get("adr_ref") != created_from.get("decision_doc"):
        raise ProgramActivationPacketError(
            "AK decision adr_ref must match decision_record created_from.decision_doc"
        )

    return {
        "schema_version": CANONICAL_BINDING_VERIFICATION_SCHEMA,
        "status": "verified",
        "canonical_binding_ref": normalized_ref,
        "binding_kind": "ak_decision",
        "decision_id": decision_id,
        "created_from": _canonical_binding_created_from(
            decision_record_path, decision_record
        ),
        "decision_record": _decision_record_ref(decision_record_path),
        "decision_record_sha256": _sha256_file(decision_record_path),
        "ak_decision_state": decision.get("state"),
        "ak_decision_outcome": decision.get("outcome"),
        "ak_decision_title": decision.get("title"),
        "ak_decision_rfc_ref": decision.get("rfc_ref"),
        "ak_decision_adr_ref": decision.get("adr_ref"),
        "ak_decision_evidence_ref": decision.get("evidence_ref"),
        "authority_owner": decision_record.get("decided_by"),
        "effect": {
            "ak_read_only": True,
            "ak_mutated": False,
            "program_files_mutated": False,
            "external_authority_mutated": False,
            "production_activation_applied": False,
        },
        "non_authority": {
            "binding_verification_only": True,
            "production_activation_authority": False,
            "rollout_preflight_authority": False,
            "external_mutation": False,
        },
    }


def write_canonical_binding_verification(
    verification: Mapping[str, Any], out_path: Path
) -> dict[str, Any]:
    payload = dict(verification)
    try:
        out_path = prepare_sidecar_output_path(
            out_path,
            payload=payload,
            artifact_label="canonical binding verification",
            protected_names=_ACTIVATION_PACKET_PROTECTED_OUTPUT_NAMES,
            payload_artifact_root_policy="forbid",
        )
    except ValueError as exc:
        raise ProgramActivationPacketError(str(exc)) from exc
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload


def _validate_oracle_report_identity(
    identity: Mapping[str, Any], oracle_report: Mapping[str, Any] | None
) -> None:
    if oracle_report is None:
        return
    records = _safe_list(oracle_report.get("records"))
    for record in records:
        if not isinstance(record, Mapping):
            continue
        record_identity = _safe_mapping(record.get("identity"))
        if not record_identity:
            continue
        if _missing_identity_keys(identity, record_identity):
            continue
        if not _identity_mismatch(identity, record_identity):
            return
    raise ProgramActivationPacketError(
        "oracle_report does not contain a record matching candidate identity"
    )


def _validate_oracle_publication_preflight(
    identity: Mapping[str, Any],
    preflight_packet: Mapping[str, Any] | None,
    *,
    manifest_path: Path,
    manifest_hash: str,
    preflight_ref: Mapping[str, Any] | None = None,
) -> None:
    if preflight_packet is None:
        return
    preflight_identity = _safe_mapping(preflight_packet.get("identity"))
    if not preflight_identity:
        raise ProgramActivationPacketError(
            "oracle_publication_preflight missing identity object"
        )
    if preflight_identity != dict(identity):
        raise ProgramActivationPacketError(
            "oracle_publication_preflight identity does not match candidate identity"
        )
    try:
        validate_program_oracle_publication_preflight_contract(
            preflight_packet,
            expected_manifest_path=manifest_path,
            expected_manifest_hash=manifest_hash,
            preflight_path=Path(str(preflight_ref.get("path")))
            if preflight_ref and preflight_ref.get("path")
            else None,
        )
    except ProgramOraclePublicationError as exc:
        raise ProgramActivationPacketError(
            "oracle_publication_preflight " + str(exc)
        ) from exc


def _oracle_publication_preflight_ref(
    preflight_ref: dict[str, Any] | None,
    preflight_packet: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if preflight_ref is None or preflight_packet is None:
        return None
    publication = _safe_mapping(preflight_packet.get("publication"))
    checks = _safe_mapping(preflight_packet.get("preflight"))
    effect = _safe_mapping(preflight_packet.get("effect"))
    return {
        **preflight_ref,
        "publication_id": preflight_packet.get("publication_id"),
        "publication_label": publication.get("publication_label"),
        "publication_label_class": publication.get("publication_label_class"),
        "authority_ref": publication.get("authority_ref"),
        "retention_class": publication.get("retention_class"),
        "ready_for_shared_publication": checks.get("ready_for_shared_publication")
        is True,
        "runtime_trace_semantics_valid": checks.get("runtime_trace_semantics_valid")
        is True,
        "runtime_trace_hash_match": checks.get("runtime_trace_hash_match") is True,
        "blocking_reasons": _safe_list(checks.get("blocking_reasons")),
        "preflight_only": True,
        "activation_authority": False,
        "promotion_authority": False,
        "shared_oracle_mutated": effect.get("shared_oracle_mutated") is True,
    }


def _oracle_publication_ref(
    receipt_ref: dict[str, Any] | None,
    receipt: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if receipt_ref is None or receipt is None:
        return None
    publication = _safe_mapping(receipt.get("publication"))
    effect = _safe_mapping(receipt.get("effect"))
    return {
        **receipt_ref,
        "publication_id": receipt.get("publication_id"),
        "run_id": receipt.get("run_id"),
        "publication_label": publication.get("publication_label"),
        "publication_label_class": publication.get("publication_label_class"),
        "authority_ref": publication.get("authority_ref"),
        "retention_class": publication.get("retention_class"),
        "evidence_only": True,
        "activation_authority": False,
        "promotion_authority": False,
        "shared_oracle_mutated": effect.get("shared_oracle_mutated") is True,
    }


def _strip_sha256_prefix(value: object) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return text.removeprefix("sha256:")


def _runtime_episode_ref(
    artifact_ref: Mapping[str, Any] | None,
    runtime_episode: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if artifact_ref is None or runtime_episode is None:
        return None
    artifact_hashes = _safe_mapping(runtime_episode.get("artifact_hashes"))
    return {
        **dict(artifact_ref),
        "status": runtime_episode.get("status"),
        "runtime_episode_id": runtime_episode.get("runtime_episode_id"),
        "contract_mode": runtime_episode.get("contract_mode"),
        "source_manifest_sha256": artifact_hashes.get("source_manifest_sha256"),
        "runtime_inputs_sha256": artifact_hashes.get("runtime_inputs_sha256"),
        "behavior_results_sha256": artifact_hashes.get("behavior_results_sha256"),
        "program_runtime_traces_sha256": artifact_hashes.get(
            "program_runtime_traces_sha256"
        ),
        "oracle_evidence_sha256": artifact_hashes.get("oracle_evidence_sha256"),
        "evidence_only": True,
        "activation_authority": False,
        "promotion_authority": False,
        "shared_oracle_mutated": False,
    }


def _candidate_state_publication_refs(
    candidate_state: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if candidate_state is None:
        return {
            "candidate_state_present": False,
            "preflight_present": False,
            "preflight_publication_id": None,
            "receipt_present": False,
            "receipt_publication_id": None,
        }
    evidence = _safe_mapping(candidate_state.get("evidence_state"))
    shared = _safe_mapping(candidate_state.get("shared_oracle_publication"))
    state_preflight = _safe_mapping(evidence.get("oracle_publication_preflight"))
    state_receipt = _safe_mapping(evidence.get("oracle_publication_receipt"))
    return {
        "candidate_state_present": True,
        "preflight_present": state_preflight.get("present") is True
        or shared.get("preflight_present") is True,
        "preflight_ready": shared.get("preflight_ready") is True,
        "preflight_publication_id": state_preflight.get("publication_id"),
        "receipt_present": state_receipt.get("present") is True
        or shared.get("evidence_ref_present") is True,
        "receipt_publication_id": state_receipt.get("publication_id"),
    }


def _oracle_publication_alignment_summary(
    *,
    candidate_state: Mapping[str, Any] | None,
    oracle_publication_preflight: Mapping[str, Any] | None,
    oracle_publication_receipt: Mapping[str, Any] | None,
) -> dict[str, Any]:
    candidate_refs = _candidate_state_publication_refs(candidate_state)
    preflight_publication_id = (
        oracle_publication_preflight.get("publication_id")
        if oracle_publication_preflight is not None
        else None
    )
    receipt_publication_id = (
        oracle_publication_receipt.get("publication_id")
        if oracle_publication_receipt is not None
        else None
    )
    supplied_ids = [
        value for value in (preflight_publication_id, receipt_publication_id) if value
    ]
    candidate_ids = [
        value
        for value in (
            candidate_refs.get("preflight_publication_id"),
            candidate_refs.get("receipt_publication_id"),
        )
        if value
    ]
    unique_ids = set(supplied_ids + candidate_ids)
    return {
        "candidate_state_present": candidate_refs["candidate_state_present"],
        "candidate_state_preflight_present": candidate_refs["preflight_present"],
        "candidate_state_receipt_present": candidate_refs["receipt_present"],
        "preflight_ref_supplied": oracle_publication_preflight is not None,
        "receipt_ref_supplied": oracle_publication_receipt is not None,
        "preflight_publication_id": preflight_publication_id,
        "receipt_publication_id": receipt_publication_id,
        "candidate_state_preflight_publication_id": candidate_refs.get(
            "preflight_publication_id"
        ),
        "candidate_state_receipt_publication_id": candidate_refs.get(
            "receipt_publication_id"
        ),
        "publication_ids_aligned": len(unique_ids) <= 1,
        "evidence_only": True,
        "activation_authority": False,
        "promotion_authority": False,
    }


def _validate_export_preflight_artifact_hashes(
    export_preflight: Mapping[str, Any],
    *,
    manifest_path: Path,
    decision_record_path: Path | None,
) -> None:
    artifact_hashes = _safe_mapping(export_preflight.get("artifact_hashes"))
    manifest_hash = _sha256_file(manifest_path)
    if artifact_hashes.get("manifest_sha256") != manifest_hash:
        raise ProgramActivationPacketError(
            "external authority export preflight manifest_sha256 does not match current manifest"
        )
    if decision_record_path is not None:
        decision_hash = _sha256_file(decision_record_path)
        if artifact_hashes.get("decision_record_sha256") != decision_hash:
            raise ProgramActivationPacketError(
                "external authority export preflight decision_record_sha256 does not match supplied decision record"
            )
    planned_payload = _safe_mapping(export_preflight.get("planned_payload"))
    refs_by_kind: dict[str, Mapping[str, Any]] = {}
    for ref in _safe_list(planned_payload.get("evidence_refs")):
        if not isinstance(ref, Mapping):
            raise ProgramActivationPacketError(
                "external authority export preflight evidence refs must be objects"
            )
        kind = _first_text(ref.get("kind"))
        raw_path = _first_text(ref.get("path"))
        expected_hash = _first_text(ref.get("sha256"))
        if kind is None or raw_path is None or expected_hash is None:
            raise ProgramActivationPacketError(
                "external authority export preflight evidence refs must include kind, path, and sha256"
            )
        path = Path(raw_path).expanduser().resolve()
        if not path.exists():
            raise ProgramActivationPacketError(
                f"external authority export preflight evidence ref is missing: {path}"
            )
        actual_hash = _sha256_file(path)
        if actual_hash != expected_hash:
            raise ProgramActivationPacketError(
                "external authority export preflight evidence ref hash mismatch: "
                f"{path}"
            )
        refs_by_kind[kind] = ref
        if ref.get("kind") == "program_manifest" and actual_hash != manifest_hash:
            raise ProgramActivationPacketError(
                "external authority export preflight program_manifest ref does not match current manifest"
            )

    expected_refs = {
        "program_manifest": artifact_hashes.get("manifest_sha256"),
        "promotion_decision_record": artifact_hashes.get("decision_record_sha256"),
        "candidate_comparison": artifact_hashes.get("comparison_sha256"),
    }
    if export_preflight.get("status") == "ready_not_applied":
        for kind, expected_hash in expected_refs.items():
            if expected_hash is None or kind not in refs_by_kind:
                raise ProgramActivationPacketError(
                    f"external authority export preflight is missing {kind} evidence ref"
                )
    for kind, expected_hash in expected_refs.items():
        if expected_hash is None or kind not in refs_by_kind:
            continue
        if refs_by_kind[kind].get("sha256") != expected_hash:
            raise ProgramActivationPacketError(
                f"external authority export preflight {kind} evidence ref hash mismatch"
            )


def _validate_external_authority_export_preflight(
    candidate_identity: Mapping[str, Any],
    export_preflight: Mapping[str, Any] | None,
    *,
    manifest_path: Path,
    decision_record_path: Path | None,
) -> None:
    if export_preflight is None:
        return
    try:
        validate_program_external_authority_export_preflight_contract(
            export_preflight,
            expected_identities=[candidate_identity],
            valid_manifest_hashes={_sha256_file(manifest_path)},
            decision_record_sha256=_sha256_file(decision_record_path)
            if decision_record_path is not None
            else None,
        )
    except ProgramExternalAuthorityExportError as exc:
        raise ProgramActivationPacketError(str(exc)) from exc


def _external_authority_export_preflight_ref(
    artifact_ref: Mapping[str, Any] | None,
    export_preflight: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if artifact_ref is None or export_preflight is None:
        return None
    target = _safe_mapping(export_preflight.get("target"))
    preflight = _safe_mapping(export_preflight.get("preflight"))
    return {
        **dict(artifact_ref),
        "status": export_preflight.get("status"),
        "export_id": export_preflight.get("export_id"),
        "target_system": target.get("system"),
        "target_contract": target.get("target_contract"),
        "external_ref": target.get("external_ref"),
        "ready_for_future_apply": preflight.get("ready_for_future_apply") is True,
        "blocking_reasons": _safe_list(preflight.get("blocking_reasons")),
        "external_apply_blocking_reasons": _safe_list(
            preflight.get("external_apply_blocking_reasons")
        ),
        "preflight_only": _safe_mapping(export_preflight.get("non_authority")).get(
            "preflight_only"
        )
        is True,
        "planned_not_exported": _safe_mapping(
            export_preflight.get("non_authority")
        ).get("planned_not_exported")
        is True,
    }


def _validate_candidate_state_publication_alignment(
    *,
    candidate_state: Mapping[str, Any] | None,
    oracle_publication_preflight: Mapping[str, Any] | None,
    oracle_publication_receipt: Mapping[str, Any] | None,
) -> None:
    if (
        oracle_publication_preflight is not None
        and oracle_publication_receipt is not None
        and oracle_publication_preflight.get("publication_id")
        != oracle_publication_receipt.get("publication_id")
    ):
        raise ProgramActivationPacketError(
            "oracle_publication_preflight/receipt publication_id mismatch"
        )
    if candidate_state is None:
        return
    evidence = _safe_mapping(candidate_state.get("evidence_state"))
    shared = _safe_mapping(candidate_state.get("shared_oracle_publication"))
    state_preflight = _safe_mapping(evidence.get("oracle_publication_preflight"))
    state_receipt = _safe_mapping(evidence.get("oracle_publication_receipt"))

    state_preflight_present = state_preflight.get("present") is True
    shared_preflight_present = shared.get("preflight_present") is True
    if oracle_publication_preflight is None:
        if state_preflight_present or shared_preflight_present:
            raise ProgramActivationPacketError(
                "candidate_state references oracle_publication_preflight but activation packet omitted it"
            )
    else:
        if not state_preflight_present or not shared_preflight_present:
            raise ProgramActivationPacketError(
                "candidate_state must include supplied oracle_publication_preflight"
            )
        if state_preflight.get("publication_id") != oracle_publication_preflight.get(
            "publication_id"
        ):
            raise ProgramActivationPacketError(
                "candidate_state oracle_publication_preflight publication_id does not match supplied preflight"
            )
        if shared.get("preflight_ready") is not True:
            raise ProgramActivationPacketError(
                "candidate_state shared_oracle_publication.preflight_ready must be true"
            )

    state_receipt_present = state_receipt.get("present") is True
    shared_receipt_present = shared.get("evidence_ref_present") is True
    if oracle_publication_receipt is None:
        if state_receipt_present or shared_receipt_present:
            raise ProgramActivationPacketError(
                "candidate_state references oracle_publication_receipt but activation packet omitted it"
            )
    else:
        if not state_receipt_present or not shared_receipt_present:
            raise ProgramActivationPacketError(
                "candidate_state must include supplied oracle_publication_receipt"
            )
        if state_receipt.get("publication_id") != oracle_publication_receipt.get(
            "publication_id"
        ):
            raise ProgramActivationPacketError(
                "candidate_state oracle_publication_receipt publication_id does not match supplied receipt"
            )


def _validate_candidate_state(
    identity: Mapping[str, Any],
    candidate_state: Mapping[str, Any] | None,
    *,
    current_manifest_sha256: str,
) -> None:
    if candidate_state is None:
        return
    state_identity = _safe_mapping(candidate_state.get("candidate_identity"))
    if not state_identity:
        raise ProgramActivationPacketError("candidate_state missing candidate_identity")
    mismatched = _identity_mismatch(identity, state_identity)
    if mismatched:
        raise ProgramActivationPacketError(
            "candidate_state identity does not match candidate identity: "
            + ", ".join(mismatched)
        )
    artifact_hashes = _safe_mapping(candidate_state.get("artifact_hashes"))
    if artifact_hashes.get("manifest_sha256") != current_manifest_sha256:
        raise ProgramActivationPacketError(
            "candidate_state manifest_sha256 does not match current manifest"
        )
    _validate_non_authority_false(
        candidate_state,
        label="candidate_state",
        keys=(
            "agent_kernel_mutation",
            "apply_promotion",
            "automatic_promotion",
            "external_apply",
            "governance_authority",
            "oracle_authority",
            "promotion_authority",
            "winner_selection",
        ),
    )
    target_fidelity = _safe_mapping(candidate_state.get("target_fidelity_state"))
    if target_fidelity:
        if target_fidelity.get("production_or_domain_activation_allowed") is not False:
            raise ProgramActivationPacketError(
                "candidate_state target_fidelity_state must record "
                "production_or_domain_activation_allowed false"
            )
        if target_fidelity.get("canonical_mutation_allowed") is not False:
            raise ProgramActivationPacketError(
                "candidate_state target_fidelity_state must record "
                "canonical_mutation_allowed false"
            )
        judgment = _safe_mapping(
            target_fidelity.get("target_protocol_fidelity_judgment")
        )
        if judgment.get("present") is not True:
            raise ProgramActivationPacketError(
                "candidate_state target_fidelity_state must include present "
                "target_protocol_fidelity_judgment"
            )
        if judgment.get("blocking") is not False:
            raise ProgramActivationPacketError(
                "candidate_state target_protocol_fidelity_judgment must record "
                "blocking false"
            )
        if judgment.get("judgment") != "supports_domain_review":
            raise ProgramActivationPacketError(
                "candidate_state target_protocol_fidelity_judgment must be "
                "supports_domain_review"
            )


def _validate_candidate_state_runtime_episode_alignment(
    *,
    candidate_state: Mapping[str, Any] | None,
    runtime_episode_ref: Mapping[str, Any] | None,
) -> None:
    if candidate_state is None:
        return
    artifact_hashes = _safe_mapping(candidate_state.get("artifact_hashes"))
    runtime_hash = _first_text(artifact_hashes.get("runtime_episode_sha256"))
    evidence = _safe_mapping(candidate_state.get("evidence_state"))
    runtime_summary = _safe_mapping(evidence.get("runtime_episode"))
    created_from = _safe_mapping(candidate_state.get("created_from"))
    runtime_path = _first_text(created_from.get("runtime_episode_path"))
    runtime_present = runtime_summary.get("present") is True or runtime_hash is not None
    if runtime_present and runtime_episode_ref is None:
        raise ProgramActivationPacketError(
            "candidate_state references runtime_episode but activation packet omitted it"
        )
    if runtime_present and runtime_path is None:
        raise ProgramActivationPacketError(
            "candidate_state runtime_episode_path is required when runtime episode evidence is present"
        )
    if runtime_episode_ref is not None:
        supplied_hash = _first_text(runtime_episode_ref.get("sha256"))
        supplied_path = _first_text(runtime_episode_ref.get("path"))
        if runtime_hash and runtime_hash != supplied_hash:
            raise ProgramActivationPacketError(
                "candidate_state runtime_episode hash does not match supplied runtime episode"
            )
        if runtime_path is not None and supplied_path is not None:
            if (
                Path(runtime_path).expanduser().resolve()
                != Path(supplied_path).expanduser().resolve()
            ):
                raise ProgramActivationPacketError(
                    "candidate_state runtime_episode_path does not match supplied runtime episode"
                )
        if runtime_summary.get("present") is True:
            summary_checks = {
                "sha256": supplied_hash,
                "status": runtime_episode_ref.get("status"),
                "runtime_episode_id": runtime_episode_ref.get("runtime_episode_id"),
                "contract_mode": runtime_episode_ref.get("contract_mode"),
                "source_manifest_sha256": runtime_episode_ref.get(
                    "source_manifest_sha256"
                ),
                "runtime_inputs_sha256": runtime_episode_ref.get(
                    "runtime_inputs_sha256"
                ),
                "behavior_results_sha256": runtime_episode_ref.get(
                    "behavior_results_sha256"
                ),
                "program_runtime_traces_sha256": runtime_episode_ref.get(
                    "program_runtime_traces_sha256"
                ),
                "oracle_evidence_sha256": runtime_episode_ref.get(
                    "oracle_evidence_sha256"
                ),
            }
            for key, expected in summary_checks.items():
                if runtime_summary.get(key) != expected:
                    raise ProgramActivationPacketError(
                        "candidate_state runtime_episode summary does not match supplied runtime episode: "
                        f"{key}"
                    )
            if runtime_summary.get("activation_authority") is not False:
                raise ProgramActivationPacketError(
                    "candidate_state runtime_episode summary must deny activation authority"
                )
            if runtime_summary.get("promotion_authority") is not False:
                raise ProgramActivationPacketError(
                    "candidate_state runtime_episode summary must deny promotion authority"
                )


def _validate_candidate_state_target_adjudication_alignment(
    *,
    candidate_state: Mapping[str, Any] | None,
    program_evidence_adjudication_ref: Mapping[str, Any] | None,
    generation_fitness_results_ref: Mapping[str, Any] | None,
) -> None:
    if candidate_state is None:
        return
    artifact_hashes = _safe_mapping(candidate_state.get("artifact_hashes"))
    adjudication_hash = artifact_hashes.get("program_evidence_adjudication_sha256")
    if adjudication_hash and program_evidence_adjudication_ref is None:
        raise ProgramActivationPacketError(
            "candidate_state references program_evidence_adjudication but activation packet omitted it"
        )
    if program_evidence_adjudication_ref is not None:
        supplied_hash = program_evidence_adjudication_ref.get("sha256")
        if adjudication_hash and adjudication_hash != supplied_hash:
            raise ProgramActivationPacketError(
                "candidate_state program_evidence_adjudication hash does not match supplied adjudication"
            )
    fitness_hash = artifact_hashes.get("generation_fitness_results_sha256")
    if fitness_hash and generation_fitness_results_ref is None:
        raise ProgramActivationPacketError(
            "candidate_state references generation_fitness_results but activation packet omitted it"
        )
    if generation_fitness_results_ref is not None:
        supplied_fitness_hash = generation_fitness_results_ref.get("sha256")
        if fitness_hash and fitness_hash != supplied_fitness_hash:
            raise ProgramActivationPacketError(
                "candidate_state generation_fitness_results hash does not match supplied fitness results"
            )


def _validate_obsidian_review_adapter_receipt(
    receipt: Mapping[str, Any] | None,
    *,
    candidate_state_ref: Mapping[str, Any] | None,
) -> None:
    if receipt is None:
        return
    if receipt.get("status") != "materialized":
        raise ProgramActivationPacketError(
            "obsidian_review_adapter_receipt status must be materialized"
        )
    for key in (
        "canonical_mutation_performed",
        "wiki_mutation_performed",
        "atlas_mutation_performed",
        "zotero_mutation_performed",
        "source_package_mutation_performed",
        "puzzle_register_mutation_performed",
        "external_mutation_performed",
    ):
        if receipt.get(key) is not False:
            raise ProgramActivationPacketError(
                f"obsidian_review_adapter_receipt must record {key} false"
            )
    if receipt.get("obsidian_review_adapter_materialization_allowed") is not True:
        raise ProgramActivationPacketError(
            "obsidian_review_adapter_receipt must record "
            "obsidian_review_adapter_materialization_allowed true"
        )
    if candidate_state_ref is not None:
        expected = _strip_sha256_prefix(candidate_state_ref.get("sha256"))
        actual = _strip_sha256_prefix(receipt.get("program_candidate_state_hash"))
        if expected and not actual:
            raise ProgramActivationPacketError(
                "obsidian_review_adapter_receipt program_candidate_state_hash is required"
            )
        if expected and actual != expected:
            raise ProgramActivationPacketError(
                "obsidian_review_adapter_receipt program_candidate_state_hash "
                "does not match candidate_state"
            )


def _target_review_admission(
    *,
    candidate_state: Mapping[str, Any] | None,
    candidate_state_ref: dict[str, Any] | None,
    obsidian_receipt: Mapping[str, Any] | None,
    obsidian_receipt_ref: dict[str, Any] | None,
) -> dict[str, Any]:
    target_fidelity = _safe_mapping(
        (candidate_state or {}).get("target_fidelity_state")
    )
    target_judgment = _safe_mapping(
        target_fidelity.get("target_protocol_fidelity_judgment")
    )
    blockers: list[str] = []
    if candidate_state is None:
        blockers.append("target_aware_candidate_state_missing")
    elif target_fidelity:
        if (
            target_fidelity.get("obsidian_review_adapter_materialization_allowed")
            is not True
        ):
            blockers.append("obsidian_review_adapter_materialization_not_allowed")
        if target_fidelity.get("production_or_domain_activation_allowed") is not False:
            blockers.append("candidate_state_does_not_deny_domain_activation")
        if target_fidelity.get("canonical_mutation_allowed") is not False:
            blockers.append("candidate_state_does_not_deny_canonical_mutation")
        if target_judgment.get("present") is not True:
            blockers.append("target_protocol_fidelity_judgment_missing")
        if target_judgment.get("blocking") is not False:
            blockers.append("target_protocol_fidelity_judgment_blocking")
        if target_judgment.get("judgment") != "supports_domain_review":
            blockers.append("target_protocol_fidelity_judgment_not_supported")
    else:
        blockers.append("target_fidelity_state_missing")
    if obsidian_receipt is None:
        blockers.append("obsidian_review_adapter_receipt_missing")

    return {
        "candidate_state": candidate_state_ref,
        "obsidian_review_adapter_receipt": obsidian_receipt_ref,
        "target_protocol_fidelity_judgment": target_judgment.get("judgment"),
        "review_adapter_materialization_allowed": target_fidelity.get(
            "obsidian_review_adapter_materialization_allowed"
        )
        is True,
        "review_packet_materialized": obsidian_receipt is not None,
        "review_only": True,
        "production_activation_authority": False,
        "canonical_mutation_authority": False,
        "canonical_mutation_allowed": target_fidelity.get("canonical_mutation_allowed")
        is True,
        "status": "review_admitted" if not blockers else "blocked",
        "blockers": blockers,
    }


def _remaining_activation_blockers(
    *,
    behavior_refs: list[dict[str, Any]],
    oracle_report: Mapping[str, Any] | None,
    jury_results: Mapping[str, Any] | None,
    model_jury_results: Mapping[str, Any] | None,
    refined_review: Mapping[str, Any] | None,
    decision_record: Mapping[str, Any] | None,
    canonical_binding_ref: str | None,
    canonical_binding_verification: Mapping[str, Any] | None,
    rollout_owner: str | None,
    rollback_plan: str | None,
    require_obsidian_review_adapter: bool,
    target_review_admission: Mapping[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if not behavior_refs:
        blockers.append("behavior_evidence")
    if oracle_report is None:
        blockers.append("oracle_report")
    if jury_results is None and model_jury_results is None:
        blockers.append("jury_evidence")
    if refined_review is None:
        blockers.append("refined_promotion_review")
    if require_obsidian_review_adapter:
        blockers.extend(
            str(item) for item in _safe_list(target_review_admission.get("blockers"))
        )
    if decision_record is None:
        blockers.append("domain_decision_record")
    elif _decision_outcome(decision_record) != "promote":
        blockers.append("decision_outcome_not_promote")
    if not str(canonical_binding_ref or "").strip():
        blockers.append("canonical_binding_ref")
    elif not _canonical_binding_verified(canonical_binding_verification):
        blockers.append("canonical_binding_verification")
    if not str(rollout_owner or "").strip():
        blockers.append("rollout_owner")
    if not str(rollback_plan or "").strip():
        blockers.append("rollback_plan")
    return list(dict.fromkeys(blockers))


def _status_and_missing(
    *,
    behavior_refs: list[dict[str, Any]],
    oracle_report: Mapping[str, Any] | None,
    jury_results: Mapping[str, Any] | None,
    model_jury_results: Mapping[str, Any] | None,
    refined_review: Mapping[str, Any] | None,
    decision_record: Mapping[str, Any] | None,
    canonical_binding_ref: str | None,
    canonical_binding_verification: Mapping[str, Any] | None,
    rollout_owner: str | None,
    rollback_plan: str | None,
    require_obsidian_review_adapter: bool,
    target_review_admission: Mapping[str, Any],
) -> tuple[str, list[str], str]:
    missing: list[str] = []
    if not behavior_refs:
        missing.append("behavior_evidence")
    if oracle_report is None:
        missing.append("oracle_report")
    if jury_results is None and model_jury_results is None:
        missing.append("jury_evidence")
    if refined_review is None:
        missing.append("refined_promotion_review")
    if require_obsidian_review_adapter:
        missing.extend(
            str(item) for item in _safe_list(target_review_admission.get("blockers"))
        )
    if not str(rollout_owner or "").strip():
        missing.append("rollout_owner")
    if not str(rollback_plan or "").strip():
        missing.append("rollback_plan")
    if missing:
        return "blocked", missing, "collect_missing_evidence"

    outcome = _decision_outcome(decision_record)
    if decision_record is None:
        return "ready_for_domain_adjudication", [], "record_domain_decision"
    if outcome != "promote":
        return "blocked", ["decision_outcome_not_promote"], "resolve_decision_outcome"
    if not str(canonical_binding_ref or "").strip():
        return (
            "ready_for_canonical_binding",
            [],
            "bind_decision_into_ak_or_current_authority",
        )
    if not _canonical_binding_verified(canonical_binding_verification):
        return (
            "ready_for_canonical_binding_verification",
            [],
            "verify_canonical_binding_ref_before_rollout_preflight",
        )
    return "ready_for_rollout_preflight", [], "run_owner_approved_rollout_preflight"


def build_generated_program_activation_packet(
    *,
    manifest_path: Path,
    owning_domain: str,
    activation_target: str,
    authority_owner: str,
    oracle_report_path: Path | None = None,
    jury_results_path: Path | None = None,
    model_jury_results_path: Path | None = None,
    review_path: Path | None = None,
    decision_record_path: Path | None = None,
    promotion_plan_path: Path | None = None,
    oracle_publication_preflight_path: Path | None = None,
    oracle_publication_receipt_path: Path | None = None,
    candidate_state_path: Path | None = None,
    generation_fitness_results_path: Path | None = None,
    program_evidence_adjudication_path: Path | None = None,
    external_authority_export_preflight_path: Path | None = None,
    obsidian_review_adapter_receipt_path: Path | None = None,
    canonical_binding_verification_path: Path | None = None,
    runtime_episode_path: Path | None = None,
    require_obsidian_review_adapter: bool = False,
    canonical_binding_ref: str | None = None,
    rollout_owner: str | None = None,
    rollback_plan: str | None = None,
) -> dict[str, Any]:
    """Build a non-authoritative activation evidence packet for domain review."""

    normalized_owning_domain = str(owning_domain or "").strip()
    normalized_activation_target = str(activation_target or "").strip()
    normalized_authority_owner = str(authority_owner or "").strip()
    if not normalized_owning_domain:
        raise ProgramActivationPacketError("activation packet requires owning_domain")
    if not normalized_activation_target:
        raise ProgramActivationPacketError(
            "activation packet requires activation_target"
        )
    if not normalized_authority_owner:
        raise ProgramActivationPacketError("activation packet requires authority_owner")

    manifest_path = manifest_path.expanduser().resolve()
    manifest = _load_json_object(manifest_path, label="program manifest")
    if manifest.get("schema_version") != "program-candidate-assembly-v1":
        raise ProgramActivationPacketError(
            "program manifest schema_version must be program-candidate-assembly-v1"
        )
    manifest_ref = _artifact_ref(
        manifest_path, schema_version="program-candidate-assembly-v1"
    )
    assert manifest_ref is not None
    root = manifest_path.parent
    identity = _identity_from_manifest(manifest)

    oracle_report, oracle_ref = _load_optional_artifact(
        oracle_report_path,
        label="oracle_report",
    )
    jury_results, jury_ref = _load_optional_artifact(
        jury_results_path,
        label="jury_results",
    )
    model_jury_results, model_jury_ref = _load_optional_artifact(
        model_jury_results_path,
        label="model_jury_results",
    )
    refined_review, review_ref = _load_optional_artifact(
        review_path,
        label="refined_review",
    )
    decision_record, decision_ref = _load_optional_artifact(
        decision_record_path,
        label="decision_record",
    )
    promotion_plan, promotion_plan_ref = _load_optional_artifact(
        promotion_plan_path,
        label="promotion_plan",
    )
    oracle_publication_preflight, oracle_publication_preflight_ref = (
        _load_optional_artifact(
            oracle_publication_preflight_path,
            label="oracle_publication_preflight",
        )
    )
    oracle_publication_receipt, oracle_publication_receipt_ref = (
        _load_optional_artifact(
            oracle_publication_receipt_path,
            label="oracle_publication_receipt",
        )
    )
    candidate_state, candidate_state_ref = _load_optional_artifact(
        candidate_state_path,
        label="candidate_state",
    )
    generation_fitness_results, generation_fitness_results_ref = (
        _load_optional_artifact(
            generation_fitness_results_path,
            label="generation_fitness_results",
        )
    )
    program_evidence_adjudication, program_evidence_adjudication_ref = (
        _load_optional_artifact(
            program_evidence_adjudication_path,
            label="program_evidence_adjudication",
        )
    )
    external_authority_export_preflight, external_authority_export_preflight_ref = (
        _load_optional_artifact(
            external_authority_export_preflight_path,
            label="external_authority_export_preflight",
        )
    )
    obsidian_review_adapter_receipt, obsidian_review_adapter_receipt_ref = (
        _load_optional_artifact(
            obsidian_review_adapter_receipt_path,
            label="obsidian_review_adapter_receipt",
        )
    )
    canonical_binding_verification, canonical_binding_verification_ref = (
        _load_optional_artifact(
            canonical_binding_verification_path,
            label="canonical_binding_verification",
        )
    )
    runtime_episode, runtime_episode_ref = _load_optional_artifact(
        runtime_episode_path,
        label="runtime_episode",
    )

    _validate_artifact_identity(identity, jury_results, label="jury_results")
    _validate_artifact_identity(
        identity, model_jury_results, label="model_jury_results"
    )
    _validate_artifact_identity(identity, refined_review, label="refined_review")
    _validate_artifact_identity(identity, decision_record, label="decision_record")
    _validate_artifact_identity(identity, promotion_plan, label="promotion_plan")
    _validate_activation_evidence_boundaries(
        manifest_path=manifest_path,
        manifest_hash=str(manifest_ref["sha256"]),
        jury_results=jury_results,
        model_jury_results=model_jury_results,
        refined_review=refined_review,
        decision_record=decision_record,
        promotion_plan=promotion_plan,
    )
    _validate_decision_authority_owner(
        decision_record,
        authority_owner=normalized_authority_owner,
    )
    _validate_oracle_report_identity(identity, oracle_report)
    _validate_oracle_publication_preflight(
        identity,
        oracle_publication_preflight,
        manifest_path=manifest_path,
        manifest_hash=str(manifest_ref["sha256"]),
        preflight_ref=oracle_publication_preflight_ref,
    )
    _validate_oracle_publication_receipt(
        identity,
        oracle_publication_receipt,
        preflight=oracle_publication_preflight,
        preflight_ref=oracle_publication_preflight_ref,
    )
    _validate_candidate_state(
        identity,
        candidate_state,
        current_manifest_sha256=str(manifest_ref["sha256"]),
    )
    if runtime_episode is not None:
        if runtime_episode_path is None:
            raise ProgramActivationPacketError("runtime_episode path is required")
        runtime_episode_resolved = runtime_episode_path.expanduser().resolve()
        validate_program_runtime_episode_contract(
            runtime_episode,
            runtime_episode_path=runtime_episode_resolved,
            expected_manifest_path=manifest_path,
            expected_manifest=manifest,
            expected_manifest_sha256=str(manifest_ref["sha256"]),
            error_type=ProgramActivationPacketError,
        )
    behavior_refs = _behavior_refs(root, manifest)
    validate_program_evidence_adjudication_contract(
        program_evidence_adjudication,
        expected_identity=identity,
        current_manifest_path=manifest_path,
        current_manifest_hash=str(manifest_ref["sha256"]),
        behavior_results_hash=_first_ref_hash_by_schema(
            behavior_refs,
            schema_version="program-behavior-results-v1",
        ),
        behavior_episode_hash=_first_ref_hash_by_schema(
            behavior_refs,
            schema_version="program-behavior-episode-v1",
        ),
        oracle_report_hash=_first_text((oracle_ref or {}).get("sha256")),
        activation_packet_hash=None,
        generation_fitness_results_hash=_first_text(
            (generation_fitness_results_ref or {}).get("sha256")
        ),
        error_type=ProgramActivationPacketError,
    )
    _validate_candidate_state_target_adjudication_alignment(
        candidate_state=candidate_state,
        program_evidence_adjudication_ref=program_evidence_adjudication_ref,
        generation_fitness_results_ref=generation_fitness_results_ref,
    )
    _validate_candidate_state_runtime_episode_alignment(
        candidate_state=candidate_state,
        runtime_episode_ref=_runtime_episode_ref(runtime_episode_ref, runtime_episode),
    )
    _validate_external_authority_export_preflight(
        identity,
        external_authority_export_preflight,
        manifest_path=manifest_path,
        decision_record_path=decision_record_path,
    )
    _validate_candidate_state_publication_alignment(
        candidate_state=candidate_state,
        oracle_publication_preflight=oracle_publication_preflight,
        oracle_publication_receipt=oracle_publication_receipt,
    )
    decision_ref_for_binding = (
        _decision_record_ref(decision_record_path)
        if decision_record_path is not None
        else None
    )
    _validate_canonical_binding_verification(
        verification=canonical_binding_verification,
        canonical_binding_ref=canonical_binding_ref,
        decision_record_ref=decision_ref_for_binding,
    )
    _validate_obsidian_review_adapter_receipt(
        obsidian_review_adapter_receipt,
        candidate_state_ref=candidate_state_ref,
    )

    receipt = _receipt_ref(manifest_path)
    target_review_admission = _target_review_admission(
        candidate_state=candidate_state,
        candidate_state_ref=candidate_state_ref,
        obsidian_receipt=obsidian_review_adapter_receipt,
        obsidian_receipt_ref=obsidian_review_adapter_receipt_ref,
    )
    status, missing, next_action = _status_and_missing(
        behavior_refs=behavior_refs,
        oracle_report=oracle_report,
        jury_results=jury_results,
        model_jury_results=model_jury_results,
        refined_review=refined_review,
        decision_record=decision_record,
        canonical_binding_ref=canonical_binding_ref,
        canonical_binding_verification=canonical_binding_verification,
        rollout_owner=rollout_owner,
        rollback_plan=rollback_plan,
        require_obsidian_review_adapter=require_obsidian_review_adapter,
        target_review_admission=target_review_admission,
    )
    remaining_activation_blockers = _remaining_activation_blockers(
        behavior_refs=behavior_refs,
        oracle_report=oracle_report,
        jury_results=jury_results,
        model_jury_results=model_jury_results,
        refined_review=refined_review,
        decision_record=decision_record,
        canonical_binding_ref=canonical_binding_ref,
        canonical_binding_verification=canonical_binding_verification,
        rollout_owner=rollout_owner,
        rollback_plan=rollback_plan,
        require_obsidian_review_adapter=require_obsidian_review_adapter,
        target_review_admission=target_review_admission,
    )

    return {
        "schema_version": ACTIVATION_PACKET_SCHEMA,
        "transition_type": TRANSITION_TYPE,
        "status": status,
        "status_kind": "advisory_evidence_packet_status_not_authority_state",
        "next_required_action": next_action,
        "governance_boundary_ref": GOVERNANCE_BOUNDARY_REF,
        "transition_passport_ref": TRANSITION_PASSPORT_REF,
        "owning_domain": normalized_owning_domain,
        "activation_target": normalized_activation_target,
        "authority_owner": normalized_authority_owner,
        "rollout_owner": str(rollout_owner or "").strip() or None,
        "rollback_plan": str(rollback_plan or "").strip() or None,
        "canonical_binding_ref": str(canonical_binding_ref or "").strip() or None,
        "identity": identity,
        "candidate": {
            "manifest": manifest_ref,
            "receipt": receipt,
            "surface_count": len(_manifest_surfaces(manifest)),
            "surfaces": _manifest_surfaces(manifest),
        },
        "evidence": {
            "behavior": behavior_refs,
            "oracle_report": oracle_ref,
            "jury_results": jury_ref,
            "model_jury_results": model_jury_ref,
            "refined_review": review_ref,
            "decision_record": decision_ref,
            "promotion_plan": promotion_plan_ref,
            "oracle_publication_preflight": _oracle_publication_preflight_ref(
                oracle_publication_preflight_ref,
                oracle_publication_preflight,
            ),
            "oracle_publication_receipt": _oracle_publication_ref(
                oracle_publication_receipt_ref,
                oracle_publication_receipt,
            ),
            "candidate_state": candidate_state_ref,
            "generation_fitness_results": generation_fitness_results_ref,
            "program_evidence_adjudication": program_evidence_adjudication_ref,
            "external_authority_export_preflight": _external_authority_export_preflight_ref(
                external_authority_export_preflight_ref,
                external_authority_export_preflight,
            ),
            "obsidian_review_adapter_receipt": obsidian_review_adapter_receipt_ref,
            "canonical_binding_verification": canonical_binding_verification_ref,
            "runtime_episode": _runtime_episode_ref(
                runtime_episode_ref,
                runtime_episode,
            ),
        },
        "evidence_alignment": {
            "oracle_publication": _oracle_publication_alignment_summary(
                candidate_state=candidate_state,
                oracle_publication_preflight=oracle_publication_preflight,
                oracle_publication_receipt=oracle_publication_receipt,
            )
        },
        "target_review_admission": target_review_admission,
        "decision": {
            "outcome": _decision_outcome(decision_record),
            "promotion_state_after_decision": (decision_record or {}).get(
                "promotion_state_after_decision"
            )
            if decision_record is not None
            else None,
            "decided_by": (decision_record or {}).get("decided_by")
            if decision_record is not None
            else None,
        },
        "missing_required_evidence": missing,
        "remaining_activation_blockers": remaining_activation_blockers,
        "boundary_checks": {
            "mlflow_approval_authority": False,
            "oracle_promotion_authority": False,
            "oracle_publication_activation_authority": False,
            "jury_promotion_authority": False,
            "dspx_activation_authority": False,
            "requires_domain_governing_body": True,
            "requires_rollout_owner_before_rollout": True,
            "requires_rollback_plan_before_rollout": True,
            "requires_canonical_binding_before_rollout": True,
            "requires_obsidian_review_adapter_when_requested": require_obsidian_review_adapter,
        },
        "effect": dict(_EFFECT),
        "non_authority": dict(_NON_AUTHORITY),
        "notes": [
            "This packet is generated-program activation evidence only.",
            "It does not activate, deploy, promote, mutate AK, mutate governance, mutate MLflow, or mutate Oracle indexes.",
            "The owning domain or delegated governing body remains the judging authority for concrete activation.",
        ],
    }


def write_generated_program_activation_packet(
    packet: Mapping[str, Any],
    out_path: Path,
) -> dict[str, Any]:
    """Write an activation evidence packet without mutating source artifacts."""

    payload = dict(packet)
    try:
        out_path = prepare_sidecar_output_path(
            out_path,
            payload=payload,
            artifact_label="activation packet",
            protected_names=_ACTIVATION_PACKET_PROTECTED_OUTPUT_NAMES,
            payload_artifact_root_policy="forbid",
        )
    except ValueError as exc:
        raise ProgramActivationPacketError(str(exc)) from exc
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload
