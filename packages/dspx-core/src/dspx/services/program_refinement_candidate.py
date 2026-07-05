from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from dspx.services.program_intent import ProgramIntent
from dspx.services.program_promotion_decision import (
    ProgramPromotionDecisionError,
    validate_program_promotion_decision_record_contract,
)
from dspx.services.program_refinement import load_program_manifest
from dspx.services.program_service import materialize_program_from_intent

PROGRAM_REFINEMENT_CANDIDATE_RESULT_SCHEMA = "program-refinement-candidate-result-v1"
PROGRAM_REFINEMENT_PROPOSAL_SCHEMA = "program-refinement-proposal-v1"

_ALLOWED_DECISION_OUTCOMES_FOR_SECOND_CANDIDATE = {"request_more_evidence"}
_REQUIRED_FALSE_PROPOSAL_NON_AUTHORITY_FLAGS = (
    "applies_changes",
    "generates_candidate",
    "oracle_ranking",
    "oracle_pruning",
    "oracle_promotion",
    "promotion_authority",
    "governance_authority",
    "external_mutation",
)


class ProgramRefinementCandidateError(ValueError):
    """Raised when a second-candidate refinement request is invalid."""


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    source = path.expanduser().resolve()
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProgramRefinementCandidateError(f"{label} not found: {source}") from exc
    except json.JSONDecodeError as exc:
        raise ProgramRefinementCandidateError(
            f"{label} must be valid JSON: {source}"
        ) from exc
    if not isinstance(payload, dict):
        raise ProgramRefinementCandidateError(
            f"{label} must contain a JSON object: {source}"
        )
    return payload


def _safe_mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items()}


def _safe_list(value: object) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _first_text(*values: object) -> str | None:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return None


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


def _assert_identity_matches(
    actual: Mapping[str, Any], expected: Mapping[str, str | None], *, label: str
) -> None:
    mismatches = [
        key
        for key, expected_value in expected.items()
        if expected_value is not None
        and actual.get(key) is not None
        and actual.get(key) != expected_value
    ]
    if mismatches:
        raise ProgramRefinementCandidateError(
            f"{label} identity does not match source manifest identity: "
            + ", ".join(sorted(mismatches))
        )
    missing = [
        key
        for key, expected_value in expected.items()
        if expected_value and not actual.get(key)
    ]
    if missing:
        raise ProgramRefinementCandidateError(
            f"{label} identity is missing source manifest identity fields: "
            + ", ".join(sorted(missing))
        )


def load_program_refinement_proposal(path: Path) -> dict[str, Any]:
    """Load a non-authoritative refinement proposal for candidate generation."""

    proposal = _load_json_object(path, label="program refinement proposal")
    if proposal.get("schema_version") != PROGRAM_REFINEMENT_PROPOSAL_SCHEMA:
        raise ProgramRefinementCandidateError(
            "program refinement proposal schema_version must be "
            + PROGRAM_REFINEMENT_PROPOSAL_SCHEMA
        )
    if proposal.get("status") != "proposed":
        raise ProgramRefinementCandidateError(
            "second-candidate generation requires a proposed refinement"
        )
    non_authority = _safe_mapping(proposal.get("non_authority"))
    if non_authority.get("proposal_only") is not True:
        raise ProgramRefinementCandidateError(
            "program refinement proposal must be proposal-only"
        )
    invalid = [
        key
        for key in _REQUIRED_FALSE_PROPOSAL_NON_AUTHORITY_FLAGS
        if non_authority.get(key) is not False
    ]
    if invalid:
        raise ProgramRefinementCandidateError(
            "program refinement proposal widens non-authority flags: "
            + ", ".join(invalid)
        )
    return proposal


def load_program_promotion_decision_record(
    path: Path,
    *,
    expected_identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Load a local decision record for explicit second-candidate generation."""

    decision = _load_json_object(path, label="program promotion decision record")
    try:
        validate_program_promotion_decision_record_contract(
            decision,
            expected_identities=[expected_identity] if expected_identity else None,
            require_non_promoting=True,
        )
    except ProgramPromotionDecisionError as exc:
        raise ProgramRefinementCandidateError(str(exc)) from exc

    outcome = str(decision.get("outcome") or "").strip()
    if outcome not in _ALLOWED_DECISION_OUTCOMES_FOR_SECOND_CANDIDATE:
        allowed = ", ".join(sorted(_ALLOWED_DECISION_OUTCOMES_FOR_SECOND_CANDIDATE))
        raise ProgramRefinementCandidateError(
            "second-candidate generation requires decision outcome: " + allowed
        )
    return decision


def _proposal_patch(proposal: Mapping[str, Any]) -> dict[str, Any]:
    bounded_refinement = _safe_mapping(proposal.get("bounded_refinement"))
    return _safe_mapping(bounded_refinement.get("next_candidate_intent_patch"))


def _append_unique(existing: list[str], additions: list[str]) -> list[str]:
    result = list(existing)
    seen = {item for item in result}
    for item in additions:
        if item not in seen:
            result.append(item)
            seen.add(item)
    return result


def build_refined_program_intent_payload(
    *,
    manifest: Mapping[str, Any],
    proposal: Mapping[str, Any],
    decision: Mapping[str, Any],
    source_identity: Mapping[str, str | None],
    manifest_path: Path,
    refinement_proposal_path: Path,
    decision_record_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Apply the bounded proposal patch to the source intent payload."""

    source_intent = _safe_mapping(manifest.get("intent"))
    if not source_intent:
        raise ProgramRefinementCandidateError("source manifest is missing intent")
    patch = _proposal_patch(proposal)
    constraints_added = _string_list(patch.get("constraints"))
    if not constraints_added:
        raise ProgramRefinementCandidateError(
            "second-candidate generation requires bounded intent patch constraints"
        )

    next_intent = dict(source_intent)
    next_intent["constraints"] = _append_unique(
        _string_list(source_intent.get("constraints")), constraints_added
    )
    options = _safe_mapping(source_intent.get("options"))
    options["refinement_lineage"] = {
        "schema_version": "program-refinement-candidate-lineage-v1",
        "source_identity": dict(source_identity),
        "source_manifest_path": str(manifest_path),
        "refinement_proposal_path": str(refinement_proposal_path),
        "refinement_proposal_id": proposal.get("proposal_id"),
        "decision_record_path": str(decision_record_path),
        "decision_outcome": decision.get("outcome"),
        "decision_record_status": decision.get("status"),
        "authority": "local_refinement_lineage_only_non_authoritative",
    }
    next_intent["options"] = options
    applied_patch = {
        "allowed_patch_fields": ["constraints"],
        "constraints_added": constraints_added,
        "ignored_patch_fields": sorted(set(patch) - {"constraints"}),
    }
    ProgramIntent.model_validate(next_intent)
    return next_intent, applied_patch


def materialize_refinement_candidate(
    *,
    manifest_path: Path,
    refinement_proposal_path: Path,
    decision_record_path: Path,
    outdir: Path,
) -> dict[str, Any]:
    """Materialize one explicit second candidate from a local request-more-evidence path."""

    manifest_path = manifest_path.expanduser().resolve()
    refinement_proposal_path = refinement_proposal_path.expanduser().resolve()
    decision_record_path = decision_record_path.expanduser().resolve()
    outdir = outdir.expanduser().resolve()

    manifest = load_program_manifest(manifest_path)
    proposal = load_program_refinement_proposal(refinement_proposal_path)
    source_identity = _identity_from_manifest(manifest)
    decision = load_program_promotion_decision_record(
        decision_record_path,
        expected_identity=source_identity,
    )
    _assert_identity_matches(
        _safe_mapping(proposal.get("identity")),
        source_identity,
        label="program refinement proposal",
    )
    _assert_identity_matches(
        _safe_mapping(decision.get("identity")),
        source_identity,
        label="program promotion decision record",
    )

    next_intent_payload, applied_patch = build_refined_program_intent_payload(
        manifest=manifest,
        proposal=proposal,
        decision=decision,
        source_identity=source_identity,
        manifest_path=manifest_path,
        refinement_proposal_path=refinement_proposal_path,
        decision_record_path=decision_record_path,
    )
    next_intent = ProgramIntent.model_validate(next_intent_payload)
    source_intent = _safe_mapping(manifest.get("request")).get("intent_source")
    intent_source_path = (
        Path(str(source_intent)).expanduser().resolve()
        if isinstance(source_intent, str) and source_intent.strip()
        else None
    )
    artifact = materialize_program_from_intent(
        next_intent,
        outdir=outdir,
        intent_source=intent_source_path,
    )
    candidate_manifest_path = Path(artifact.root_path) / "manifest.json"
    return {
        "schema_version": PROGRAM_REFINEMENT_CANDIDATE_RESULT_SCHEMA,
        "status": "materialized",
        "created_from": {
            "manifest_path": str(manifest_path),
            "refinement_proposal_path": str(refinement_proposal_path),
            "decision_record_path": str(decision_record_path),
        },
        "source_identity": dict(source_identity),
        "decision": {
            "outcome": decision.get("outcome"),
            "promotion_state_after_decision": decision.get(
                "promotion_state_after_decision"
            ),
        },
        "applied_patch": applied_patch,
        "candidate": {
            "root_path": artifact.root_path,
            "manifest_path": str(candidate_manifest_path),
            "request_id": artifact.metadata.get("request_id"),
            "candidate_id": artifact.metadata.get("candidate_id"),
            "assembly_id": artifact.metadata.get("assembly_id"),
            "episode_id": artifact.metadata.get("episode_id"),
            "receipt_bundle_id": artifact.metadata.get("receipt_bundle_id"),
        },
        "effect": {
            "local_second_candidate_generated": True,
            "source_program_files_mutated": False,
            "refinement_proposal_mutated": False,
            "decision_record_mutated": False,
            "external_authority_mutated": False,
            "governance_mutated": False,
        },
        "non_authority": {
            "local_candidate_generation_only": True,
            "automatic_promotion": False,
            "oracle_ranking": False,
            "oracle_pruning": False,
            "oracle_promotion": False,
            "external_authority_export": False,
            "governance_authority": False,
            "external_mutation": False,
        },
        "notes": [
            "This command materializes one explicit local second candidate from a request-more-evidence decision record.",
            "It does not mutate the source candidate, proposal, decision record, governance, AK, Oracle authority, or external authority.",
        ],
    }
