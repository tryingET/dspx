from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

PROGRAM_EXTERNAL_AUTHORITY_EXPORT_PREFLIGHT_SCHEMA = (
    "program-external-authority-export-preflight-v1"
)
PROGRAM_MANIFEST_SCHEMA = "program-candidate-assembly-v1"
PROGRAM_PROMOTION_DECISION_RECORD_SCHEMA = "program-promotion-decision-record-v1"
PROGRAM_REFINEMENT_CANDIDATE_COMPARISON_SCHEMA = (
    "program-refinement-candidate-comparison-v1"
)
TARGET_SYSTEM = "agent_kernel"
TARGET_CONTRACT = "ak_task_evidence_attachment"

_EXTERNAL_APPLY_BLOCKING_REASONS = [
    "external_apply_not_implemented",
    "target_contract_not_bound_to_ak_runtime",
]

_ALLOWED_NON_PROMOTE_DECISION_OUTCOMES = {
    "withhold",
    "reject",
    "request_more_evidence",
}
_REQUIRED_FALSE_DECISION_NON_AUTHORITY_FLAGS = (
    "automatic_promotion",
    "oracle_ranking",
    "oracle_pruning",
    "oracle_promotion",
    "program_mutation",
    "refined_review_mutation",
    "new_candidate_generation",
    "governance_authority",
    "external_mutation",
)
_REQUIRED_FALSE_COMPARISON_NON_AUTHORITY_FLAGS = (
    "oracle_ranking",
    "oracle_pruning",
    "oracle_promotion",
    "winner_selection",
    "automatic_promotion",
    "program_mutation",
    "new_candidate_generation",
    "governance_authority",
    "external_mutation",
)


class ProgramExternalAuthorityExportError(ValueError):
    """Raised when an external-authority export preflight input is invalid."""


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    source = path.expanduser().resolve()
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProgramExternalAuthorityExportError(
            f"{label} not found: {source}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ProgramExternalAuthorityExportError(
            f"{label} must be valid JSON: {source}"
        ) from exc
    if not isinstance(payload, dict):
        raise ProgramExternalAuthorityExportError(
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


def _sha256_payload(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _json_text(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


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


def _validate_program_manifest(manifest: Mapping[str, Any], path: Path) -> None:
    if manifest.get("schema_version") != PROGRAM_MANIFEST_SCHEMA:
        raise ProgramExternalAuthorityExportError(
            f"program manifest schema_version must be {PROGRAM_MANIFEST_SCHEMA}: {path}"
        )
    candidate = _safe_mapping(manifest.get("candidate_assembly"))
    if candidate.get("artifact_kind") != "program":
        raise ProgramExternalAuthorityExportError(
            f"program manifest artifact_kind must be program: {path}"
        )
    identity = _identity_from_manifest(manifest)
    if not any(identity.values()):
        raise ProgramExternalAuthorityExportError(
            "program manifest does not expose request/candidate/assembly/episode/receipt identity"
        )


def _manifest_agent_kernel_refs(manifest: Mapping[str, Any]) -> list[str]:
    promotion_review = _safe_mapping(manifest.get("program_promotion_review"))
    external_authority = _safe_mapping(promotion_review.get("external_authority"))
    refs: list[str] = []
    for raw_ref in _safe_list(external_authority.get("refs")):
        if not isinstance(raw_ref, Mapping):
            continue
        system = str(raw_ref.get("system") or raw_ref.get("adapter") or "").strip()
        if system and system != TARGET_SYSTEM:
            continue
        ref = _first_text(raw_ref.get("ref"), raw_ref.get("id"))
        if ref is not None:
            refs.append(ref)
    return refs


def _identity_mismatches(
    actual: Mapping[str, Any], expected: Mapping[str, str | None]
) -> list[str]:
    return [
        key
        for key, expected_value in expected.items()
        if expected_value is not None
        and actual.get(key) is not None
        and actual.get(key) != expected_value
    ]


def _identity_missing(
    actual: Mapping[str, Any], expected: Mapping[str, str | None]
) -> list[str]:
    return [
        key
        for key, expected_value in expected.items()
        if expected_value and not actual.get(key)
    ]


def _assert_identity_matches_manifest(
    actual: Mapping[str, Any], expected: Mapping[str, str | None], *, label: str
) -> None:
    mismatches = _identity_mismatches(actual, expected)
    if mismatches:
        raise ProgramExternalAuthorityExportError(
            f"{label} identity does not match manifest identity: "
            + ", ".join(sorted(mismatches))
        )
    missing = _identity_missing(actual, expected)
    if missing:
        raise ProgramExternalAuthorityExportError(
            f"{label} identity is missing manifest identity fields: "
            + ", ".join(sorted(missing))
        )


def _identity_exactly_matches(
    actual: Mapping[str, Any], expected: Mapping[str, str | None]
) -> bool:
    if not actual:
        return False
    for key, expected_value in expected.items():
        if expected_value is not None and actual.get(key) != expected_value:
            return False
    return True


def _assert_false_flags(
    non_authority: Mapping[str, Any], required_false: tuple[str, ...], *, label: str
) -> None:
    invalid = [key for key in required_false if non_authority.get(key) is not False]
    if invalid:
        raise ProgramExternalAuthorityExportError(
            f"{label} widens non-authority flags: " + ", ".join(invalid)
        )


def _load_optional_decision_record(
    path: Path | None, *, manifest_identity: Mapping[str, str | None]
) -> tuple[dict[str, Any] | None, Path | None]:
    if path is None:
        return None, None
    source = path.expanduser().resolve()
    record = _load_json_object(source, label="program promotion decision record")
    if record.get("schema_version") != PROGRAM_PROMOTION_DECISION_RECORD_SCHEMA:
        raise ProgramExternalAuthorityExportError(
            "program promotion decision record schema_version must be "
            + PROGRAM_PROMOTION_DECISION_RECORD_SCHEMA
        )
    if record.get("status") != "recorded":
        raise ProgramExternalAuthorityExportError(
            "program promotion decision record must have status recorded"
        )
    _assert_identity_matches_manifest(
        _safe_mapping(record.get("identity")),
        manifest_identity,
        label="program promotion decision record",
    )
    non_authority = _safe_mapping(record.get("non_authority"))
    if non_authority.get("local_decision_record_only") is not True:
        raise ProgramExternalAuthorityExportError(
            "program promotion decision record must be local-only"
        )
    _assert_false_flags(
        non_authority,
        _REQUIRED_FALSE_DECISION_NON_AUTHORITY_FLAGS,
        label="program promotion decision record",
    )
    if record.get("promotion_state_after_decision") != "not_promoted":
        raise ProgramExternalAuthorityExportError(
            "program promotion decision record promotion_state_after_decision must be not_promoted"
        )
    if record.get("outcome") not in _ALLOWED_NON_PROMOTE_DECISION_OUTCOMES:
        raise ProgramExternalAuthorityExportError(
            "program promotion decision record outcome must be non-promoting"
        )
    return record, source


def _load_optional_comparison(
    path: Path | None, *, manifest_identity: Mapping[str, str | None]
) -> tuple[dict[str, Any] | None, Path | None, bool]:
    if path is None:
        return None, None, False
    source = path.expanduser().resolve()
    comparison = _load_json_object(
        source, label="program refinement candidate comparison"
    )
    if (
        comparison.get("schema_version")
        != PROGRAM_REFINEMENT_CANDIDATE_COMPARISON_SCHEMA
    ):
        raise ProgramExternalAuthorityExportError(
            "program refinement candidate comparison schema_version must be "
            + PROGRAM_REFINEMENT_CANDIDATE_COMPARISON_SCHEMA
        )
    source_matches = _identity_exactly_matches(
        _safe_mapping(comparison.get("source_identity")), manifest_identity
    )
    candidate_matches = _identity_exactly_matches(
        _safe_mapping(comparison.get("candidate_identity")), manifest_identity
    )
    mentions_identity = source_matches or candidate_matches
    if not mentions_identity:
        raise ProgramExternalAuthorityExportError(
            "program refinement candidate comparison must mention manifest identity as source_identity or candidate_identity"
        )
    non_authority = _safe_mapping(comparison.get("non_authority"))
    if non_authority.get("local_comparison_only") is not True:
        raise ProgramExternalAuthorityExportError(
            "program refinement candidate comparison must be local-only"
        )
    _assert_false_flags(
        non_authority,
        _REQUIRED_FALSE_COMPARISON_NON_AUTHORITY_FLAGS,
        label="program refinement candidate comparison",
    )
    return comparison, source, mentions_identity


def _promotion_not_applied(
    manifest: Mapping[str, Any], decision_record: Mapping[str, Any] | None
) -> bool:
    promotion_review = _safe_mapping(manifest.get("program_promotion_review"))
    decision_effect = _safe_mapping(
        decision_record.get("effect") if decision_record is not None else None
    )
    return (
        promotion_review.get("promotion_state") == "not_promoted"
        and (
            decision_record is None
            or decision_record.get("promotion_state_after_decision") == "not_promoted"
        )
        and (
            decision_record is None
            or decision_record.get("outcome") in _ALLOWED_NON_PROMOTE_DECISION_OUTCOMES
        )
        and decision_effect.get("external_authority_mutated", False) is False
        and decision_effect.get("governance_mutated", False) is False
    )


def _status_for_preflight(
    *,
    target_ref_matches_manifest: bool,
    decision_record_present: bool,
    comparison_present: bool,
    promotion_not_applied: bool,
) -> str:
    if (
        target_ref_matches_manifest
        and decision_record_present
        and comparison_present
        and promotion_not_applied
    ):
        return "ready_not_applied"
    return "incomplete_preflight"


def _blocking_reasons(
    *,
    target_ref_matches_manifest: bool,
    decision_record_present: bool,
    comparison_present: bool,
    promotion_not_applied: bool,
) -> list[str]:
    reasons: list[str] = []
    if not target_ref_matches_manifest:
        reasons.append("target_ref_not_declared_in_manifest_external_authority_refs")
    if not decision_record_present:
        reasons.append("missing_decision_record")
    if not comparison_present:
        reasons.append("missing_candidate_comparison")
    if not promotion_not_applied:
        reasons.append("promotion_already_applied_or_state_not_not_promoted")
    return reasons


def _artifact_hashes_fingerprint(artifact_hashes: Mapping[str, str | None]) -> str:
    seed = {key: value for key, value in sorted(artifact_hashes.items()) if value}
    return _sha256_payload(seed)


def _export_id(*, external_ref: str, artifact_hashes: Mapping[str, str | None]) -> str:
    seed = {
        "schema_version": PROGRAM_EXTERNAL_AUTHORITY_EXPORT_PREFLIGHT_SCHEMA,
        "target_system": TARGET_SYSTEM,
        "target_contract": TARGET_CONTRACT,
        "external_ref": external_ref,
        "artifact_hashes": {
            key: value for key, value in sorted(artifact_hashes.items()) if value
        },
    }
    return "prog-ext-export-" + _sha256_payload(seed)[:16]


def build_program_external_authority_export_preflight(
    *,
    manifest_path: Path,
    external_ref: str,
    decision_record_path: Path | None = None,
    comparison_path: Path | None = None,
) -> dict[str, Any]:
    """Build a local external-authority export preflight packet without AK mutation."""

    manifest_file = manifest_path.expanduser().resolve()
    normalized_external_ref = str(external_ref or "").strip()
    if not normalized_external_ref:
        raise ProgramExternalAuthorityExportError(
            "external authority export preflight requires --external-ref"
        )

    manifest = _load_json_object(manifest_file, label="program manifest")
    _validate_program_manifest(manifest, manifest_file)
    identity = _identity_from_manifest(manifest)
    manifest_hash = _sha256_file(manifest_file)
    decision_record, decision_file = _load_optional_decision_record(
        decision_record_path,
        manifest_identity=identity,
    )
    comparison, comparison_file, comparison_mentions_identity = (
        _load_optional_comparison(
            comparison_path,
            manifest_identity=identity,
        )
    )
    decision_hash = _sha256_file(decision_file) if decision_file is not None else None
    comparison_hash = (
        _sha256_file(comparison_file) if comparison_file is not None else None
    )
    artifact_hashes = {
        "manifest_sha256": manifest_hash,
        "decision_record_sha256": decision_hash,
        "comparison_sha256": comparison_hash,
    }
    export_id = _export_id(
        external_ref=normalized_external_ref,
        artifact_hashes=artifact_hashes,
    )
    declared_refs = _manifest_agent_kernel_refs(manifest)
    target_ref_matches_manifest = normalized_external_ref in declared_refs
    decision_record_present = decision_record is not None
    comparison_present = comparison is not None
    promotion_not_applied = _promotion_not_applied(manifest, decision_record)
    blocking_reasons = _blocking_reasons(
        target_ref_matches_manifest=target_ref_matches_manifest,
        decision_record_present=decision_record_present,
        comparison_present=comparison_present,
        promotion_not_applied=promotion_not_applied,
    )
    status = _status_for_preflight(
        target_ref_matches_manifest=target_ref_matches_manifest,
        decision_record_present=decision_record_present,
        comparison_present=comparison_present,
        promotion_not_applied=promotion_not_applied,
    )
    evidence_refs: list[dict[str, Any]] = [
        {
            "kind": "program_manifest",
            "path": str(manifest_file),
            "sha256": manifest_hash,
        }
    ]
    if decision_file is not None:
        evidence_refs.append(
            {
                "kind": "promotion_decision_record",
                "path": str(decision_file),
                "sha256": decision_hash,
            }
        )
    if comparison_file is not None:
        evidence_refs.append(
            {
                "kind": "candidate_comparison",
                "path": str(comparison_file),
                "sha256": comparison_hash,
            }
        )

    return {
        "schema_version": PROGRAM_EXTERNAL_AUTHORITY_EXPORT_PREFLIGHT_SCHEMA,
        "status": status,
        "target": {
            "system": TARGET_SYSTEM,
            "external_ref": normalized_external_ref,
            "target_contract": TARGET_CONTRACT,
            "mutation_supported": False,
            "apply_command_available": False,
        },
        "export_id": export_id,
        "created_from": {
            "manifest_path": str(manifest_file),
            "manifest_schema_version": manifest.get("schema_version"),
            "decision_record_path": str(decision_file)
            if decision_file is not None
            else None,
            "decision_record_schema_version": decision_record.get("schema_version")
            if decision_record is not None
            else None,
            "comparison_path": str(comparison_file)
            if comparison_file is not None
            else None,
            "comparison_schema_version": comparison.get("schema_version")
            if comparison is not None
            else None,
        },
        "identity": identity,
        "artifact_hashes": artifact_hashes,
        "preflight": {
            "manifest_valid": True,
            "target_ref_present": True,
            "target_ref_matches_manifest_external_authority_refs": target_ref_matches_manifest,
            "decision_record_present": decision_record_present,
            "decision_record_identity_matches_manifest": decision_record_present,
            "comparison_present": comparison_present,
            "comparison_mentions_manifest_identity": comparison_mentions_identity,
            "promotion_not_applied": promotion_not_applied,
            "external_mutation_supported": False,
            "external_mutation_requested": False,
            "ready_for_future_apply": False,
            "blocking_reasons": blocking_reasons,
            "external_apply_blocking_reasons": list(_EXTERNAL_APPLY_BLOCKING_REASONS),
        },
        "planned_payload": {
            "kind": TARGET_CONTRACT,
            "target_ref": normalized_external_ref,
            "evidence_refs": evidence_refs,
            "summary": "Local DSPx candidate evidence export is preflighted but not applied.",
        },
        "idempotency": {
            "export_id": export_id,
            "target_ref": normalized_external_ref,
            "artifact_hashes_fingerprint": _artifact_hashes_fingerprint(
                artifact_hashes
            ),
            "safe_to_recompute": True,
            "repeated_preflight_same_inputs_same_export_id": True,
            "external_duplicate_check_performed": False,
            "external_duplicate_check_reason": "AK was not called.",
        },
        "effect": {
            "local_preflight_written": False,
            "external_authority_mutated": False,
            "ak_called": False,
            "governance_mutated": False,
            "program_files_mutated": False,
            "promotion_state_changed": False,
        },
        "non_authority": {
            "preflight_only": True,
            "planned_not_exported": True,
            "external_apply": False,
            "agent_kernel_mutation": False,
            "governance_authority": False,
            "promotion_authority": False,
            "oracle_authority": False,
            "winner_selection": False,
            "automatic_promotion": False,
        },
        "failure_model": {
            "states": [
                "planned",
                "attempted",
                "applied",
                "partial",
                "failed",
                "rolled_back",
            ],
            "current_state": "planned",
            "apply_receipt_required_for_state_change": True,
        },
        "notes": [
            "This packet is a local preflight/export plan only.",
            "No AK command was invoked.",
            "No external authority was mutated.",
            "A future apply command must bind an exact AK target contract, perform external duplicate checks, and emit an apply receipt.",
        ],
    }


def write_program_external_authority_export_preflight(
    packet: Mapping[str, Any], out_path: Path
) -> dict[str, Any]:
    """Write a local export preflight packet and return the written payload."""

    target = out_path.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(packet)
    effect = _safe_mapping(payload.get("effect"))
    effect["local_preflight_written"] = True
    payload["effect"] = effect
    target.write_text(_json_text(payload), encoding="utf-8")
    return payload
