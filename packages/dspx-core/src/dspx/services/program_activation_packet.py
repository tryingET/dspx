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
    "oracle_publication_receipt": "program-oracle-shared-publication-receipt-v1",
    "candidate_state": "program-candidate-state-v1",
    "obsidian_review_adapter_receipt": "dspy-pdf-transition-review-adapter-receipt-v1",
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


def _decision_outcome(decision_record: Mapping[str, Any] | None) -> str | None:
    if decision_record is None:
        return None
    outcome = str(decision_record.get("outcome") or "").strip()
    return outcome or None


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


def _validate_activation_evidence_boundaries(
    *,
    jury_results: Mapping[str, Any] | None,
    refined_review: Mapping[str, Any] | None,
    decision_record: Mapping[str, Any] | None,
    promotion_plan: Mapping[str, Any] | None,
) -> None:
    if jury_results is not None:
        _validate_non_authority_false(
            jury_results,
            label="jury_results",
            keys=(
                "automatic_promotion",
                "winner_selection",
                "candidate_ranking",
                "oracle_ranking",
                "oracle_pruning",
                "oracle_promotion",
                "promotion_authority",
                "governance_authority",
                "external_mutation",
            ),
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
    identity: Mapping[str, Any], receipt: Mapping[str, Any] | None
) -> None:
    if receipt is None:
        return
    if receipt.get("status") != "published":
        raise ProgramActivationPacketError(
            "oracle_publication_receipt status must be published"
        )
    _validate_artifact_identity(
        identity,
        receipt,
        label="oracle_publication_receipt",
    )
    effect = _safe_mapping(receipt.get("effect"))
    if effect.get("shared_oracle_mutated") is not True:
        raise ProgramActivationPacketError(
            "oracle_publication_receipt must record shared_oracle_mutated true"
        )
    for key in (
        "ak_called",
        "governance_mutated",
        "mlflow_mutated",
        "program_files_mutated",
        "promotion_state_changed",
    ):
        if effect.get(key) is not False:
            raise ProgramActivationPacketError(
                f"oracle_publication_receipt must record {key} false"
            )
    non_authority = _safe_mapping(receipt.get("non_authority"))
    invalid = [
        key
        for key in (
            "oracle_authority",
            "promotion_authority",
            "governance_authority",
            "agent_kernel_mutation",
            "winner_selection",
            "automatic_promotion",
        )
        if non_authority.get(key) is not False
    ]
    if invalid:
        raise ProgramActivationPacketError(
            "oracle_publication_receipt widens non-authority flags: "
            + ", ".join(invalid)
        )


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
        if not _identity_mismatch(identity, record_identity):
            matched_keys = [
                key
                for key, value in identity.items()
                if value not in {None, ""} and record_identity.get(key) == value
            ]
            if matched_keys:
                return
    raise ProgramActivationPacketError(
        "oracle_report does not contain a record matching candidate identity"
    )


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


def _validate_candidate_state(
    identity: Mapping[str, Any], candidate_state: Mapping[str, Any] | None
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
        if expected and actual and expected != actual:
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
    refined_review: Mapping[str, Any] | None,
    decision_record: Mapping[str, Any] | None,
    canonical_binding_ref: str | None,
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
    if jury_results is None:
        blockers.append("jury_results")
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
    else:
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
    refined_review: Mapping[str, Any] | None,
    decision_record: Mapping[str, Any] | None,
    canonical_binding_ref: str | None,
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
    if jury_results is None:
        missing.append("jury_results")
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
    return (
        "ready_for_canonical_binding_verification",
        [],
        "verify_canonical_binding_ref_before_rollout_preflight",
    )


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
    oracle_publication_receipt_path: Path | None = None,
    candidate_state_path: Path | None = None,
    obsidian_review_adapter_receipt_path: Path | None = None,
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
    obsidian_review_adapter_receipt, obsidian_review_adapter_receipt_ref = (
        _load_optional_artifact(
            obsidian_review_adapter_receipt_path,
            label="obsidian_review_adapter_receipt",
        )
    )

    _validate_artifact_identity(identity, jury_results, label="jury_results")
    _validate_artifact_identity(identity, refined_review, label="refined_review")
    _validate_artifact_identity(identity, decision_record, label="decision_record")
    _validate_artifact_identity(identity, promotion_plan, label="promotion_plan")
    _validate_activation_evidence_boundaries(
        jury_results=jury_results,
        refined_review=refined_review,
        decision_record=decision_record,
        promotion_plan=promotion_plan,
    )
    _validate_decision_authority_owner(
        decision_record,
        authority_owner=normalized_authority_owner,
    )
    _validate_oracle_report_identity(identity, oracle_report)
    _validate_oracle_publication_receipt(identity, oracle_publication_receipt)
    _validate_candidate_state(identity, candidate_state)
    _validate_obsidian_review_adapter_receipt(
        obsidian_review_adapter_receipt,
        candidate_state_ref=candidate_state_ref,
    )

    behavior_refs = _behavior_refs(root, manifest)
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
        refined_review=refined_review,
        decision_record=decision_record,
        canonical_binding_ref=canonical_binding_ref,
        rollout_owner=rollout_owner,
        rollback_plan=rollback_plan,
        require_obsidian_review_adapter=require_obsidian_review_adapter,
        target_review_admission=target_review_admission,
    )
    remaining_activation_blockers = _remaining_activation_blockers(
        behavior_refs=behavior_refs,
        oracle_report=oracle_report,
        jury_results=jury_results,
        refined_review=refined_review,
        decision_record=decision_record,
        canonical_binding_ref=canonical_binding_ref,
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
            "refined_review": review_ref,
            "decision_record": decision_ref,
            "promotion_plan": promotion_plan_ref,
            "oracle_publication_receipt": _oracle_publication_ref(
                oracle_publication_receipt_ref,
                oracle_publication_receipt,
            ),
            "candidate_state": candidate_state_ref,
            "obsidian_review_adapter_receipt": obsidian_review_adapter_receipt_ref,
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
