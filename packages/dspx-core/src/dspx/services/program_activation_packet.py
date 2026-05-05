from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

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
    "jury_results": "program-jury-results-v1",
    "refined_review": "program-promotion-review-refined-v1",
    "decision_record": "program-promotion-decision-record-v1",
    "promotion_plan": "program-promotion-plan-v1",
}

_FORBIDDEN_OUTPUT_NAMES = {
    "manifest.json",
    "manifest.json.meta.json",
    "promotion_review.json",
    "promotion_adjudication_request.json",
    "promotion_decision_template.json",
    "promotion_review_refined.json",
    "promotion_decision_record.json",
    "promotion_plan.json",
    "jury_results.json",
    "behavior_results.json",
    "oracle_evidence.json",
    "execution_episode.json",
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
        return
    mismatched = _identity_mismatch(candidate_identity, artifact_identity)
    if mismatched:
        raise ProgramActivationPacketError(
            f"{label} identity does not match candidate identity: "
            + ", ".join(mismatched)
        )


def _behavior_refs(root: Path) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for name, schema in (
        ("behavior_results.json", "program-behavior-results-v1"),
        ("behavior_episode.json", "program-behavior-episode-v1"),
    ):
        ref = _artifact_ref(root / name, schema_version=schema)
        if ref is not None:
            refs.append(ref)
    return refs


def _receipt_ref(manifest_path: Path) -> dict[str, Any] | None:
    return _artifact_ref(
        Path(str(manifest_path.expanduser().resolve()) + ".meta.json"),
        schema_version="dspx-run-receipt-v1",
    )


def _decision_outcome(decision_record: Mapping[str, Any] | None) -> str | None:
    if decision_record is None:
        return None
    outcome = str(decision_record.get("outcome") or "").strip()
    return outcome or None


def _status_and_missing(
    *,
    behavior_refs: list[dict[str, Any]],
    oracle_report: Mapping[str, Any] | None,
    jury_results: Mapping[str, Any] | None,
    refined_review: Mapping[str, Any] | None,
    decision_record: Mapping[str, Any] | None,
    canonical_binding_ref: str | None,
    rollback_plan: str | None,
) -> tuple[str, list[str], str]:
    missing: list[str] = []
    if not behavior_refs:
        missing.append("behavior_evidence")
    if oracle_report is None:
        missing.append("oracle_report")
    if jury_results is None:
        missing.append("jury_results")
    if refined_review is None:
        missing.append("refined_promotion_review")
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
    return "ready_for_rollout_preflight", [], "run_owner_approved_rollout_preflight"


def build_generated_program_activation_packet(
    *,
    manifest_path: Path,
    owning_domain: str,
    activation_target: str,
    authority_owner: str,
    oracle_report_path: Path | None = None,
    jury_results_path: Path | None = None,
    review_path: Path | None = None,
    decision_record_path: Path | None = None,
    promotion_plan_path: Path | None = None,
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

    _validate_artifact_identity(identity, jury_results, label="jury_results")
    _validate_artifact_identity(identity, refined_review, label="refined_review")
    _validate_artifact_identity(identity, decision_record, label="decision_record")
    _validate_artifact_identity(identity, promotion_plan, label="promotion_plan")

    behavior_refs = _behavior_refs(root)
    receipt = _receipt_ref(manifest_path)
    status, missing, next_action = _status_and_missing(
        behavior_refs=behavior_refs,
        oracle_report=oracle_report,
        jury_results=jury_results,
        refined_review=refined_review,
        decision_record=decision_record,
        canonical_binding_ref=canonical_binding_ref,
        rollback_plan=rollback_plan,
    )

    return {
        "schema_version": ACTIVATION_PACKET_SCHEMA,
        "transition_type": TRANSITION_TYPE,
        "status": status,
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
            "refined_review": review_ref,
            "decision_record": decision_ref,
            "promotion_plan": promotion_plan_ref,
        },
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
        "boundary_checks": {
            "mlflow_approval_authority": False,
            "oracle_promotion_authority": False,
            "jury_promotion_authority": False,
            "dspx_activation_authority": False,
            "requires_domain_governing_body": True,
            "requires_canonical_binding_before_rollout": True,
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

    out_path = out_path.expanduser().resolve()
    if out_path.name in _FORBIDDEN_OUTPUT_NAMES:
        raise ProgramActivationPacketError(
            f"activation packet must not overwrite {out_path.name}"
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(packet)
    out_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload
