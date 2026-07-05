from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from dspx.services.artifact_boundary import prepare_sidecar_output_path
from dspx.services.program_promotion_decision import (
    ProgramPromotionDecisionError,
    validate_program_promotion_decision_record_contract,
)

PROGRAM_EXTERNAL_AUTHORITY_EXPORT_PREFLIGHT_SCHEMA = (
    "program-external-authority-export-preflight-v1"
)
PROGRAM_MANIFEST_SCHEMA = "program-candidate-assembly-v1"
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
    try:
        validate_program_promotion_decision_record_contract(
            record,
            expected_identities=[manifest_identity],
            require_non_promoting=True,
        )
    except ProgramPromotionDecisionError as exc:
        raise ProgramExternalAuthorityExportError(str(exc)) from exc
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


def validate_program_external_authority_export_preflight_contract(
    export_preflight: Mapping[str, Any],
    *,
    expected_identities: list[Mapping[str, Any]],
    valid_manifest_hashes: set[str],
    decision_record_sha256: str | None = None,
    comparison_sha256: str | None = None,
) -> None:
    """Validate a local export preflight before a final consumer summarizes it."""

    if (
        export_preflight.get("schema_version")
        != PROGRAM_EXTERNAL_AUTHORITY_EXPORT_PREFLIGHT_SCHEMA
    ):
        raise ProgramExternalAuthorityExportError(
            "external authority export preflight schema_version must be "
            + PROGRAM_EXTERNAL_AUTHORITY_EXPORT_PREFLIGHT_SCHEMA
        )
    if export_preflight.get("status") not in {
        "ready_not_applied",
        "incomplete_preflight",
    }:
        raise ProgramExternalAuthorityExportError(
            "external authority export preflight status must be ready_not_applied or incomplete_preflight"
        )

    identity = _safe_mapping(export_preflight.get("identity"))
    if not any(
        _identity_exactly_matches(identity, expected)
        for expected in expected_identities
    ):
        raise ProgramExternalAuthorityExportError(
            "external authority export preflight identity does not match candidate identity or candidate/source identity"
        )

    preflight = _safe_mapping(export_preflight.get("preflight"))
    if preflight.get("ready_for_future_apply") is not False:
        raise ProgramExternalAuthorityExportError(
            "external authority export preflight must keep ready_for_future_apply false"
        )
    if preflight.get("external_mutation_requested") is not False:
        raise ProgramExternalAuthorityExportError(
            "external authority export preflight must record external_mutation_requested false"
        )

    target = _safe_mapping(export_preflight.get("target"))
    if target.get("system") != TARGET_SYSTEM:
        raise ProgramExternalAuthorityExportError(
            "external authority export preflight target system must be agent_kernel"
        )
    if target.get("target_contract") != TARGET_CONTRACT:
        raise ProgramExternalAuthorityExportError(
            "external authority export preflight target_contract must be "
            + TARGET_CONTRACT
        )
    if target.get("mutation_supported") is not False:
        raise ProgramExternalAuthorityExportError(
            "external authority export preflight target must keep mutation_supported false"
        )
    if target.get("apply_command_available") is not False:
        raise ProgramExternalAuthorityExportError(
            "external authority export preflight target must keep apply_command_available false"
        )

    effect = _safe_mapping(export_preflight.get("effect"))
    for key in (
        "external_authority_mutated",
        "ak_called",
        "governance_mutated",
        "program_files_mutated",
        "promotion_state_changed",
    ):
        if effect.get(key) is not False:
            raise ProgramExternalAuthorityExportError(
                f"external authority export preflight must record {key} false"
            )

    non_authority = _safe_mapping(export_preflight.get("non_authority"))
    if non_authority.get("preflight_only") is not True:
        raise ProgramExternalAuthorityExportError(
            "external authority export preflight must be preflight-only"
        )
    if non_authority.get("planned_not_exported") is not True:
        raise ProgramExternalAuthorityExportError(
            "external authority export preflight must be planned_not_exported"
        )
    _assert_false_flags(
        non_authority,
        (
            "external_apply",
            "agent_kernel_mutation",
            "governance_authority",
            "promotion_authority",
            "oracle_authority",
            "winner_selection",
            "automatic_promotion",
        ),
        label="external authority export preflight",
    )

    artifact_hashes = _safe_mapping(export_preflight.get("artifact_hashes"))
    manifest_sha256 = _first_text(artifact_hashes.get("manifest_sha256"))
    if manifest_sha256 not in valid_manifest_hashes:
        raise ProgramExternalAuthorityExportError(
            "external authority export preflight manifest_sha256 does not match current manifest or candidate/source manifest"
        )
    for field, expected_hash, label in (
        ("decision_record_sha256", decision_record_sha256, "decision record"),
        ("comparison_sha256", comparison_sha256, "comparison"),
    ):
        if expected_hash is not None and artifact_hashes.get(field) != expected_hash:
            raise ProgramExternalAuthorityExportError(
                f"external authority export preflight {field} does not match supplied {label}"
            )

    external_ref = _first_text(target.get("external_ref"))
    export_id = _first_text(export_preflight.get("export_id"))
    expected_export_id = _export_id(
        external_ref=external_ref or "",
        artifact_hashes={
            "manifest_sha256": manifest_sha256,
            "decision_record_sha256": _first_text(
                artifact_hashes.get("decision_record_sha256")
            ),
            "comparison_sha256": _first_text(artifact_hashes.get("comparison_sha256")),
        },
    )
    if external_ref is None or export_id != expected_export_id:
        raise ProgramExternalAuthorityExportError(
            "external authority export preflight export_id does not match target/artifact hashes"
        )
    idempotency = _safe_mapping(export_preflight.get("idempotency"))
    if idempotency.get("export_id") != export_id:
        raise ProgramExternalAuthorityExportError(
            "external authority export preflight idempotency export_id mismatch"
        )
    if idempotency.get("target_ref") != external_ref:
        raise ProgramExternalAuthorityExportError(
            "external authority export preflight idempotency target_ref mismatch"
        )
    if idempotency.get("artifact_hashes_fingerprint") != _artifact_hashes_fingerprint(
        artifact_hashes
    ):
        raise ProgramExternalAuthorityExportError(
            "external authority export preflight idempotency fingerprint mismatch"
        )
    if idempotency.get("safe_to_recompute") is not True:
        raise ProgramExternalAuthorityExportError(
            "external authority export preflight must be safe_to_recompute"
        )
    if idempotency.get("external_duplicate_check_performed") is not False:
        raise ProgramExternalAuthorityExportError(
            "external authority export preflight must not claim an external duplicate check"
        )

    refs_by_kind: dict[str, Mapping[str, Any]] = {}
    planned_payload = _safe_mapping(export_preflight.get("planned_payload"))
    if planned_payload.get("kind") != TARGET_CONTRACT:
        raise ProgramExternalAuthorityExportError(
            "external authority export preflight planned_payload kind must be "
            + TARGET_CONTRACT
        )
    if planned_payload.get("target_ref") != external_ref:
        raise ProgramExternalAuthorityExportError(
            "external authority export preflight planned_payload target_ref mismatch"
        )
    for ref in _safe_list(planned_payload.get("evidence_refs")):
        if not isinstance(ref, Mapping):
            raise ProgramExternalAuthorityExportError(
                "external authority export preflight evidence refs must be objects"
            )
        kind = _first_text(ref.get("kind"))
        raw_path = _first_text(ref.get("path"))
        expected_hash = _first_text(ref.get("sha256"))
        if kind is None or raw_path is None or expected_hash is None:
            raise ProgramExternalAuthorityExportError(
                "external authority export preflight evidence refs must include kind, path, and sha256"
            )
        path = Path(raw_path).expanduser().resolve()
        if not path.exists():
            raise ProgramExternalAuthorityExportError(
                f"external authority export preflight evidence ref is missing: {path}"
            )
        actual_hash = _sha256_file(path)
        if actual_hash != expected_hash:
            raise ProgramExternalAuthorityExportError(
                "external authority export preflight evidence ref hash mismatch: "
                f"{path}"
            )
        refs_by_kind[kind] = ref

    expected_refs = {
        "program_manifest": manifest_sha256,
        "promotion_decision_record": _first_text(
            artifact_hashes.get("decision_record_sha256")
        ),
        "candidate_comparison": _first_text(artifact_hashes.get("comparison_sha256")),
    }
    if export_preflight.get("status") == "ready_not_applied":
        for kind, expected_hash in expected_refs.items():
            if expected_hash is None or kind not in refs_by_kind:
                raise ProgramExternalAuthorityExportError(
                    f"external authority export preflight is missing {kind} evidence ref"
                )
    for kind, expected_hash in expected_refs.items():
        if expected_hash is None:
            continue
        ref = refs_by_kind.get(kind)
        if ref is None:
            continue
        if ref.get("sha256") != expected_hash:
            raise ProgramExternalAuthorityExportError(
                f"external authority export preflight {kind} evidence ref hash mismatch"
            )
    manifest_ref = refs_by_kind.get("program_manifest")
    if manifest_ref is None or manifest_ref.get("sha256") != manifest_sha256:
        raise ProgramExternalAuthorityExportError(
            "external authority export preflight program_manifest ref does not match manifest_sha256"
        )


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

    payload = dict(packet)
    try:
        target = prepare_sidecar_output_path(
            out_path,
            payload=payload,
            artifact_label="external authority export preflight",
            payload_artifact_root_policy="forbid",
        )
    except ValueError as exc:
        raise ProgramExternalAuthorityExportError(str(exc)) from exc
    target.parent.mkdir(parents=True, exist_ok=True)
    effect = _safe_mapping(payload.get("effect"))
    effect["local_preflight_written"] = True
    payload["effect"] = effect
    target.write_text(_json_text(payload), encoding="utf-8")
    return payload
