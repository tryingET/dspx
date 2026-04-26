from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from dspx.services.program_refinement import (
    ProgramRefinementError,
    load_program_behavior_results,
    load_program_manifest,
    load_program_oracle_report,
    validate_program_oracle_report_non_authority,
)

PROGRAM_PROMOTION_REVIEW_REFINED_SCHEMA = "program-promotion-review-refined-v1"
PROGRAM_PROMOTION_REVIEW_SCHEMA = "program-promotion-review-v1"
PROGRAM_PROMOTION_ADJUDICATION_REQUEST_SCHEMA = (
    "program-promotion-adjudication-request-v1"
)
PROGRAM_PROMOTION_DECISION_SCHEMA = "program-promotion-decision-v1"
PROGRAM_REFINEMENT_PROPOSAL_SCHEMA = "program-refinement-proposal-v1"

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

_REFINED_PACKET_NON_AUTHORITY = {
    "local_review_packet_only": True,
    "automatic_promotion": False,
    "oracle_ranking": False,
    "oracle_pruning": False,
    "oracle_promotion": False,
    "program_mutation": False,
    "new_candidate_generation": False,
    "promotion_authority": False,
    "governance_authority": False,
    "external_mutation": False,
}


class ProgramPromotionRefinementError(ValueError):
    """Raised when promotion-review refinement inputs are malformed."""


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    source = path.expanduser().resolve()
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProgramPromotionRefinementError(f"{label} not found: {source}") from exc
    except json.JSONDecodeError as exc:
        raise ProgramPromotionRefinementError(
            f"{label} must be valid JSON: {source}"
        ) from exc
    if not isinstance(payload, dict):
        raise ProgramPromotionRefinementError(
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


def _manifest_root(manifest_path: Path) -> Path:
    return manifest_path.expanduser().resolve().parent


def _surface_path(
    manifest: Mapping[str, Any], manifest_path: Path, *, kind: str, default: str
) -> Path:
    candidate_assembly = _safe_mapping(manifest.get("candidate_assembly"))
    for surface in _safe_list(candidate_assembly.get("surfaces")):
        if not isinstance(surface, Mapping) or surface.get("kind") != kind:
            continue
        raw_path = _first_text(surface.get("path"))
        if raw_path:
            path = Path(raw_path)
            if not path.is_absolute():
                path = _manifest_root(manifest_path) / path
            return path
    return _manifest_root(manifest_path) / default


def _validate_schema(
    payload: Mapping[str, Any], *, label: str, expected_schema: str
) -> None:
    if payload.get("schema_version") != expected_schema:
        raise ProgramPromotionRefinementError(
            f"{label} schema_version must be {expected_schema}"
        )


def _identity_matches(left: Mapping[str, Any], right: Mapping[str, str | None]) -> bool:
    for key in (
        "receipt_bundle_id",
        "episode_id",
        "assembly_id",
        "candidate_id",
        "request_id",
    ):
        wanted = right.get(key)
        actual = left.get(key)
        if wanted and actual and actual == wanted:
            return True
    return False


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
        raise ProgramPromotionRefinementError(
            f"{label} identity does not match manifest identity: "
            + ", ".join(sorted(mismatches))
        )
    missing = [
        key
        for key, expected_value in expected.items()
        if expected_value and not actual.get(key)
    ]
    if missing:
        raise ProgramPromotionRefinementError(
            f"{label} identity is missing manifest identity fields: "
            + ", ".join(sorted(missing))
        )


def _validate_oracle_report_identity(
    report: Mapping[str, Any], identity: Mapping[str, str | None]
) -> tuple[dict[str, Any] | None, bool]:
    records = [
        item for item in _safe_list(report.get("records")) if isinstance(item, Mapping)
    ]
    if not records:
        return None, False
    for record in records:
        record_identity = _safe_mapping(record.get("identity"))
        if _identity_matches(record_identity, identity):
            return dict(record), True
    raise ProgramPromotionRefinementError(
        "program Oracle evidence report does not contain a record matching manifest identity"
    )


def _load_refinement_proposal(path: Path) -> dict[str, Any]:
    proposal = _load_json_object(path, label="program refinement proposal")
    _validate_schema(
        proposal,
        label="program refinement proposal",
        expected_schema=PROGRAM_REFINEMENT_PROPOSAL_SCHEMA,
    )
    non_authority = _safe_mapping(proposal.get("non_authority"))
    if non_authority.get("proposal_only") is not True:
        raise ProgramPromotionRefinementError(
            "program refinement proposal must be proposal-only"
        )
    invalid = [
        key
        for key in _REQUIRED_FALSE_PROPOSAL_NON_AUTHORITY_FLAGS
        if non_authority.get(key) is not False
    ]
    if invalid:
        raise ProgramPromotionRefinementError(
            "program refinement proposal widens non-authority flags: "
            + ", ".join(invalid)
        )
    return proposal


def _behavior_summary(behavior: Mapping[str, Any] | None) -> dict[str, Any]:
    return _safe_mapping(behavior.get("summary")) if behavior is not None else {}


def _promotion_policy(review: Mapping[str, Any]) -> dict[str, Any]:
    return _safe_mapping(review.get("promotion_policy"))


def _evidence_requirement_status(
    review: Mapping[str, Any], requirement_name: str
) -> str | None:
    for raw in _safe_list(review.get("evidence_requirements")):
        if not isinstance(raw, Mapping):
            continue
        if raw.get("name") == requirement_name:
            return _first_text(raw.get("status"))
    return None


def _missing_required_evidence(
    *,
    review: Mapping[str, Any],
    behavior_present: bool,
    oracle_matched: bool,
    proposal_present: bool,
) -> list[str]:
    policy = _promotion_policy(review)
    missing: list[str] = []
    if (
        bool(policy.get("requires_behavioral_evaluation", True))
        and not behavior_present
    ):
        missing.append("no_behavioral_evaluation_episode")
    if not oracle_matched and behavior_present:
        missing.append("no_matching_oracle_program_evidence_report_record")
    if not proposal_present:
        missing.append("no_program_refinement_proposal")
    if bool(policy.get("requires_jury_execution", True)):
        jury_status = _evidence_requirement_status(
            review, "model_jury_execution_episode"
        )
        if jury_status != "satisfied_by_current_model_jury_episode":
            missing.append("no_model_jury_execution_episode")
    if bool(policy.get("requires_adjudicator_decision", True)):
        decision = _safe_mapping(review.get("decision"))
        if decision.get("status") != "decided" or not decision.get("outcome"):
            missing.append("no_promotion_adjudicator_decision")
    return missing


def _status_for_packet(
    *, behavior_present: bool, oracle_matched: bool, proposal: Mapping[str, Any]
) -> str:
    if (
        not behavior_present
        or proposal.get("status") == "insufficient_behavior_evidence"
    ):
        return "insufficient_behavior_evidence"
    if not oracle_matched:
        return "needs_more_evidence"
    return "review_packet_ready"


def _load_original_promotion_artifacts(
    manifest: Mapping[str, Any], manifest_path: Path
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Path]]:
    paths = {
        "original_promotion_review_path": _surface_path(
            manifest,
            manifest_path,
            kind="promotion_review",
            default="promotion_review.json",
        ),
        "original_promotion_adjudication_request_path": _surface_path(
            manifest,
            manifest_path,
            kind="promotion_adjudication_request",
            default="promotion_adjudication_request.json",
        ),
        "original_promotion_decision_template_path": _surface_path(
            manifest,
            manifest_path,
            kind="promotion_decision_template",
            default="promotion_decision_template.json",
        ),
    }
    review = _load_json_object(
        paths["original_promotion_review_path"], label="original promotion review"
    )
    request = _load_json_object(
        paths["original_promotion_adjudication_request_path"],
        label="original promotion adjudication request",
    )
    decision_template = _load_json_object(
        paths["original_promotion_decision_template_path"],
        label="original promotion decision template",
    )
    _validate_schema(
        review,
        label="original promotion review",
        expected_schema=PROGRAM_PROMOTION_REVIEW_SCHEMA,
    )
    _validate_schema(
        request,
        label="original promotion adjudication request",
        expected_schema=PROGRAM_PROMOTION_ADJUDICATION_REQUEST_SCHEMA,
    )
    _validate_schema(
        decision_template,
        label="original promotion decision template",
        expected_schema=PROGRAM_PROMOTION_DECISION_SCHEMA,
    )
    if review.get("promotion_state") != "not_promoted":
        raise ProgramPromotionRefinementError(
            "original promotion review must keep promotion_state not_promoted"
        )
    if request.get("decision_record_template") != decision_template:
        raise ProgramPromotionRefinementError(
            "original promotion adjudication request decision template does not match original promotion decision template"
        )
    return review, request, decision_template, paths


def load_program_promotion_inputs(
    *, manifest_path: Path, oracle_report_path: Path, refinement_proposal_path: Path
) -> dict[str, Any]:
    """Load and validate all existing evidence for local promotion-review refinement."""

    manifest_path = manifest_path.expanduser().resolve()
    oracle_report_path = oracle_report_path.expanduser().resolve()
    refinement_proposal_path = refinement_proposal_path.expanduser().resolve()
    try:
        manifest = load_program_manifest(manifest_path)
        behavior, behavior_path, behavior_hash = load_program_behavior_results(
            manifest,
            manifest_path,
        )
        report = load_program_oracle_report(oracle_report_path)
        validate_program_oracle_report_non_authority(report)
    except ProgramRefinementError as exc:
        raise ProgramPromotionRefinementError(str(exc)) from exc
    identity = _identity_from_manifest(manifest)
    oracle_record, oracle_matched = _validate_oracle_report_identity(report, identity)
    proposal = _load_refinement_proposal(refinement_proposal_path)
    proposal_identity = _safe_mapping(proposal.get("identity"))
    _assert_identity_matches(
        proposal_identity, identity, label="program refinement proposal"
    )
    review, request, decision_template, promotion_paths = (
        _load_original_promotion_artifacts(
            manifest,
            manifest_path,
        )
    )
    return {
        "manifest_path": manifest_path,
        "manifest": manifest,
        "identity": identity,
        "behavior": behavior,
        "behavior_path": behavior_path,
        "behavior_hash": behavior_hash,
        "oracle_report_path": oracle_report_path,
        "oracle_report": report,
        "oracle_record": oracle_record,
        "oracle_matched": oracle_matched,
        "refinement_proposal_path": refinement_proposal_path,
        "refinement_proposal": proposal,
        "promotion_review": review,
        "promotion_adjudication_request": request,
        "promotion_decision_template": decision_template,
        "promotion_paths": promotion_paths,
    }


def validate_promotion_refinement_inputs(inputs: Mapping[str, Any]) -> None:
    """Validate cross-input consistency for a loaded promotion refinement packet."""

    report = _safe_mapping(inputs.get("oracle_report"))
    proposal = _safe_mapping(inputs.get("refinement_proposal"))
    review = _safe_mapping(inputs.get("promotion_review"))
    if report.get("schema_version") != "program-oracle-evidence-report-v1":
        raise ProgramPromotionRefinementError(
            "program Oracle evidence report schema_version must be program-oracle-evidence-report-v1"
        )
    if proposal.get("schema_version") != PROGRAM_REFINEMENT_PROPOSAL_SCHEMA:
        raise ProgramPromotionRefinementError(
            "program refinement proposal schema_version must be "
            + PROGRAM_REFINEMENT_PROPOSAL_SCHEMA
        )
    if review.get("promotion_state") != "not_promoted":
        raise ProgramPromotionRefinementError(
            "promotion review refinement requires an unpromoted original shell"
        )


def build_program_promotion_refinement(
    *, manifest_path: Path, oracle_report_path: Path, refinement_proposal_path: Path
) -> dict[str, Any]:
    """Build a local non-authoritative refined promotion-review packet."""

    inputs = load_program_promotion_inputs(
        manifest_path=manifest_path,
        oracle_report_path=oracle_report_path,
        refinement_proposal_path=refinement_proposal_path,
    )
    validate_promotion_refinement_inputs(inputs)

    identity = _safe_mapping(inputs["identity"])
    behavior = inputs.get("behavior")
    behavior_present = isinstance(behavior, Mapping)
    behavior_summary = _behavior_summary(
        behavior if isinstance(behavior, Mapping) else None
    )
    report = _safe_mapping(inputs.get("oracle_report"))
    proposal = _safe_mapping(inputs.get("refinement_proposal"))
    review = _safe_mapping(inputs.get("promotion_review"))
    request = _safe_mapping(inputs.get("promotion_adjudication_request"))
    promotion_paths = _safe_mapping(inputs.get("promotion_paths"))
    oracle_matched = bool(inputs.get("oracle_matched"))
    missing = _missing_required_evidence(
        review=review,
        behavior_present=behavior_present,
        oracle_matched=oracle_matched,
        proposal_present=True,
    )
    model_jury_missing = "no_model_jury_execution_episode" in missing
    adjudicator_missing = "no_promotion_adjudicator_decision" in missing
    ready_for_adjudicator_review = not missing
    adjudication_status = (
        "ready_for_adjudicator_review"
        if ready_for_adjudicator_review
        else "not_ready_missing_required_evidence"
    )
    behavior_path = inputs.get("behavior_path")
    behavior_path_text = (
        str(Path(behavior_path).resolve())
        if isinstance(behavior_path, Path) and behavior_path.exists()
        else None
    )
    packet = {
        "schema_version": PROGRAM_PROMOTION_REVIEW_REFINED_SCHEMA,
        "status": _status_for_packet(
            behavior_present=behavior_present,
            oracle_matched=oracle_matched,
            proposal=proposal,
        ),
        "promotion_state": "not_promoted",
        "candidate_status": str(review.get("candidate_status") or "exploratory"),
        "identity": identity,
        "created_from": {
            "manifest_path": str(Path(inputs["manifest_path"]).resolve()),
            "behavior_results_path": behavior_path_text,
            "oracle_report_path": str(Path(inputs["oracle_report_path"]).resolve()),
            "refinement_proposal_path": str(
                Path(inputs["refinement_proposal_path"]).resolve()
            ),
            "original_promotion_review_path": str(
                Path(promotion_paths["original_promotion_review_path"]).resolve()
            ),
            "original_promotion_adjudication_request_path": str(
                Path(
                    promotion_paths["original_promotion_adjudication_request_path"]
                ).resolve()
            ),
            "original_promotion_decision_template_path": str(
                Path(
                    promotion_paths["original_promotion_decision_template_path"]
                ).resolve()
            ),
        },
        "evidence_summary": {
            "behavior": {
                "present": behavior_present,
                "status": str(
                    behavior_summary.get("status") or "insufficient_behavior_evidence"
                ),
                "example_count": int(behavior_summary.get("total") or 0),
                "status_counts": _safe_mapping(behavior_summary.get("status_counts")),
            },
            "oracle_report": {
                "present": True,
                "status": report.get("status"),
                "total_records": int(report.get("total_records") or 0),
                "record_matched": oracle_matched,
            },
            "refinement_proposal": {
                "present": True,
                "status": proposal.get("status"),
                "proposal_id": proposal.get("proposal_id"),
            },
        },
        "review_readiness": {
            "behavior_evidence_present": behavior_present,
            "oracle_report_present": True,
            "refinement_proposal_present": True,
            "model_jury_execution_present": not model_jury_missing,
            "adjudicator_decision_present": not adjudicator_missing,
            "ready_for_adjudicator_review": ready_for_adjudicator_review,
            "missing_required_evidence": missing,
        },
        "promotion_review_delta": {
            "behavioral_evaluation_episode": "satisfied_by_current_behavior_episode"
            if behavior_present
            else "missing_behavior_evidence",
            "oracle_interpretation": "satisfied_by_explicit_oracle_report"
            if oracle_matched
            else "explicit_oracle_report_without_matching_record",
            "bounded_refinement_proposal": "available_non_authoritative",
            "promotion_authority": "unchanged_required_adjudicator",
        },
        "adjudication_packet": {
            "status": adjudication_status,
            "decision_question": request.get("decision_question"),
            "original_allowed_outcomes": list(request.get("allowed_outcomes") or []),
            "local_packet_recommended_review_outcomes": [
                "withhold",
                "reject",
                "request_more_evidence",
            ],
            "forbidden_outcomes_without_explicit_adjudicator": ["promote"],
            "evidence_refs": [
                "manifest.json",
                "promotion_review.json",
                "promotion_adjudication_request.json",
                "promotion_decision_template.json",
                *(["behavior_results.json"] if behavior_present else []),
                "oracle_report",
                "refinement_proposal",
            ],
        },
        "non_authority": dict(_REFINED_PACKET_NON_AUTHORITY),
        "notes": [
            "This is a local promotion-review evidence packet only.",
            "It consumes existing behavior evidence, an explicit Oracle report, and an explicit refinement proposal without mutating generated program artifacts.",
            "Promotion remains unavailable without an explicit adjudicator decision and any other required local evidence.",
            "Oracle interpretation remains non-authoritative and cannot rank, prune, promote, or block candidates.",
        ],
    }
    return packet


def write_program_promotion_refinement(
    packet: Mapping[str, Any], out_path: Path
) -> dict[str, Any]:
    """Write the refined local promotion-review packet and return its payload."""

    out_path = out_path.expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(packet)
    out_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload
