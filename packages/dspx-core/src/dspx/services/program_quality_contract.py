# summary: "Validates and safely publishes conversational program-quality proposal contracts."
# read_when:
#   - "Changing quality proposal schema, acceptance binding, or output publication."

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

from dspx.services.artifact_boundary import atomic_publish_bytes
from dspx.services.program_intent import ProgramIntent
from dspx.services.program_oracle_secret_policy import (
    ProgramOracleSecretPolicyError,
    validate_publisher_assertion_no_secret,
)
from dspx.services.program_quality_evaluation import normalize_quality_criteria

PROGRAM_QUALITY_PROPOSAL_SCHEMA = "program-quality-criteria-proposal-v1"
MAX_RESPONSE_CHARS = 40_000
_REQUIRED_MODEL_KEYS = {
    "metric",
    "quality_criteria",
    "rationale",
    "clarifying_questions",
}
_REQUIRED_CRITERION_KEYS = {
    "id",
    "output_field",
    "evaluator",
    "required_concept_groups",
    "forbidden_concepts",
    "min_score",
}
_BASE_ENVELOPE_KEYS = {
    "schema_version",
    "status",
    "intent",
    "conversation",
    "proposal",
    "candidate_intent",
    "model_role",
    "model_execution",
    "effect",
    "non_authority",
    "identity",
}


class ProgramQualityConversationError(ValueError):
    """Raised when quality proposal generation or validation fails closed."""


def canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _strip_json_fence(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        if len(lines) >= 2:
            return "\n".join(lines[1:-1]).strip()
    return text


def _decode_one_json_object(raw: str) -> object:
    text = _strip_json_fence(raw)
    try:
        return json.loads(text)
    except json.JSONDecodeError as direct_error:
        start = text.find("{")
        if start < 0:
            raise ProgramQualityConversationError(
                "quality proposal model response must contain one JSON object"
            ) from direct_error
        try:
            payload, end = json.JSONDecoder().raw_decode(text[start:])
        except json.JSONDecodeError as exc:
            raise ProgramQualityConversationError(
                "quality proposal model response must contain one JSON object"
            ) from exc
        trailing = text[start + end :].strip()
        if "{" in trailing or "}" in trailing:
            raise ProgramQualityConversationError(
                "quality proposal model response contains multiple JSON objects"
            )
        return payload


def parse_model_payload(raw: str, *, outputs: list[str]) -> dict[str, Any]:
    if not raw.strip() or len(raw) > MAX_RESPONSE_CHARS:
        raise ProgramQualityConversationError(
            "quality proposal model response is empty or exceeds the size limit"
        )
    payload = _decode_one_json_object(raw)
    if not isinstance(payload, dict):
        raise ProgramQualityConversationError(
            "quality proposal model response must be a JSON object"
        )
    payload_map = {str(key): item for key, item in payload.items()}
    if set(payload_map) != _REQUIRED_MODEL_KEYS:
        missing = sorted(_REQUIRED_MODEL_KEYS - set(payload_map))
        unknown = sorted(set(payload_map) - _REQUIRED_MODEL_KEYS)
        raise ProgramQualityConversationError(
            f"quality proposal fields mismatch; missing={missing}, unknown={unknown}"
        )
    metric = payload_map["metric"]
    if not isinstance(metric, str) or metric != "concept_coverage":
        raise ProgramQualityConversationError(
            "quality proposal metric must be concept_coverage for the v1 evaluator"
        )
    raw_criteria = payload_map["quality_criteria"]
    if not isinstance(raw_criteria, list) or not raw_criteria:
        raise ProgramQualityConversationError(
            "quality proposal quality_criteria must be a non-empty list"
        )
    for index, criterion in enumerate(raw_criteria):
        if not isinstance(criterion, Mapping):
            raise ProgramQualityConversationError(
                f"quality criterion {index} must be an object"
            )
        criterion_map = {str(key): item for key, item in criterion.items()}
        if set(criterion_map) != _REQUIRED_CRITERION_KEYS:
            raise ProgramQualityConversationError(
                f"quality criterion {index} must contain exactly {sorted(_REQUIRED_CRITERION_KEYS)}"
            )
        for field in ("id", "output_field", "evaluator"):
            if not isinstance(criterion_map[field], str):
                raise ProgramQualityConversationError(
                    f"quality criterion {index}.{field} must be a string"
                )
        if not isinstance(criterion_map["forbidden_concepts"], list):
            raise ProgramQualityConversationError(
                f"quality criterion {index}.forbidden_concepts must be a list"
            )
        min_score = criterion_map["min_score"]
        if isinstance(min_score, bool) or not isinstance(min_score, (int, float)):
            raise ProgramQualityConversationError(
                f"quality criterion {index}.min_score must be a number"
            )
    try:
        criteria = normalize_quality_criteria(raw_criteria, outputs=outputs)
    except ValueError as exc:
        raise ProgramQualityConversationError(
            f"quality proposal criteria are invalid: {exc}"
        ) from exc
    if not criteria:
        raise ProgramQualityConversationError(
            "quality proposal must include at least one quality criterion"
        )
    rationale = payload_map["rationale"]
    if not isinstance(rationale, str) or not rationale.strip():
        raise ProgramQualityConversationError(
            "quality proposal rationale must be a non-empty string"
        )
    rationale = rationale.strip()
    if len(rationale) > 4_000:
        raise ProgramQualityConversationError(
            "quality proposal rationale exceeds 4000 characters"
        )
    raw_questions = payload_map["clarifying_questions"]
    if not isinstance(raw_questions, list) or len(raw_questions) > 10:
        raise ProgramQualityConversationError(
            "quality proposal clarifying_questions must be a list of at most 10 strings"
        )
    questions: list[str] = []
    for item in raw_questions:
        if not isinstance(item, str):
            raise ProgramQualityConversationError(
                "quality proposal clarifying_questions must contain only strings"
            )
        if item.strip():
            questions.append(item.strip())
    if any(len(item) > 500 for item in questions):
        raise ProgramQualityConversationError(
            "quality proposal clarifying questions may not exceed 500 characters"
        )
    return {
        "metric": metric,
        "quality_criteria": criteria,
        "rationale": rationale,
        "clarifying_questions": questions,
    }


def _mapping(payload: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise ProgramQualityConversationError(
            f"quality proposal envelope section {key!r} is missing or invalid"
        )
    return dict(value)


def identity_for(payload: Mapping[str, Any]) -> dict[str, str]:
    intent = _mapping(payload, "intent")
    proposal = _mapping(payload, "proposal")
    candidate = _mapping(payload, "candidate_intent")
    execution = _mapping(payload, "model_execution")
    envelope = dict(payload)
    envelope.pop("identity", None)
    return {
        "intent_sha256": str(intent.get("text_sha256") or ""),
        "proposal_sha256": sha256_text(canonical_json(proposal)),
        "candidate_intent_sha256": sha256_text(canonical_json(candidate)),
        "model_response_sha256": str(execution.get("response_sha256") or ""),
        "envelope_sha256": sha256_text(canonical_json(envelope)),
    }


def _derived_pending_envelope_sha256(payload: Mapping[str, Any]) -> str:
    pending = dict(payload)
    pending.pop("decision", None)
    pending["status"] = "proposed_pending_acceptance"
    candidate = _mapping(pending, "candidate_intent")
    options = dict(candidate.get("options") or {})
    provenance = dict(options.get("quality_proposal") or {})
    provenance["accepted"] = False
    options["quality_proposal"] = provenance
    candidate["options"] = options
    pending["candidate_intent"] = ProgramIntent.model_validate(candidate).model_dump(
        mode="json"
    )
    return identity_for(pending)["envelope_sha256"]


def validate_quality_proposal(
    payload: Mapping[str, Any], *, allowed_statuses: set[str]
) -> dict[str, Any]:
    if payload.get("schema_version") != PROGRAM_QUALITY_PROPOSAL_SCHEMA:
        raise ProgramQualityConversationError("quality proposal schema mismatch")
    status = str(payload.get("status") or "")
    if status not in allowed_statuses:
        raise ProgramQualityConversationError(
            f"quality proposal status must be one of {sorted(allowed_statuses)}"
        )
    expected_keys = set(_BASE_ENVELOPE_KEYS)
    if status in {"accepted_for_program_generation", "rejected"}:
        expected_keys.add("decision")
    if set(payload) != expected_keys:
        raise ProgramQualityConversationError(
            "quality proposal envelope fields do not match its lifecycle status"
        )
    proposal = _mapping(payload, "proposal")
    candidate = _mapping(payload, "candidate_intent")
    role = _mapping(payload, "model_role")
    execution = _mapping(payload, "model_execution")
    effect = _mapping(payload, "effect")
    non_authority = _mapping(payload, "non_authority")
    intent = _mapping(payload, "intent")
    conversation = _mapping(payload, "conversation")
    validated_candidate = ProgramIntent.model_validate(candidate).model_dump(
        mode="json"
    )
    validated_proposal = parse_model_payload(
        canonical_json(proposal), outputs=validated_candidate["outputs"]
    )
    if validated_candidate["metric"] != validated_proposal["metric"]:
        raise ProgramQualityConversationError(
            "quality proposal metric does not match candidate intent"
        )
    if (
        validated_candidate["quality_criteria"]
        != validated_proposal["quality_criteria"]
    ):
        raise ProgramQualityConversationError(
            "quality proposal criteria do not match candidate intent"
        )
    quality_provenance = validated_candidate.get("options", {}).get(
        "quality_proposal", {}
    )
    intent_sha256 = str(intent.get("text_sha256") or "")
    if (
        not isinstance(quality_provenance, Mapping)
        or quality_provenance.get("intent_sha256") != intent_sha256
        or not intent_sha256
    ):
        raise ProgramQualityConversationError(
            "quality proposal intent and candidate provenance hashes do not match"
        )
    feedback = conversation.get("feedback")
    history = conversation.get("history")
    turn = conversation.get("turn")
    if (
        not isinstance(feedback, list)
        or not all(isinstance(item, str) for item in feedback)
        or not isinstance(history, list)
        or turn != len(history) + 1
    ):
        raise ProgramQualityConversationError(
            "quality proposal conversation chronology is invalid"
        )
    for index, entry in enumerate(history):
        if not isinstance(entry, Mapping):
            raise ProgramQualityConversationError(
                f"quality proposal history entry {index} is invalid"
            )
        entry_map = {str(key): item for key, item in entry.items()}
        if set(entry_map) != {
            "turn",
            "intent_sha256",
            "envelope_sha256",
            "proposal_sha256",
            "proposal",
        }:
            raise ProgramQualityConversationError(
                f"quality proposal history entry {index} is invalid"
            )
        if (
            entry_map.get("turn") != index + 1
            or entry_map.get("intent_sha256") != intent_sha256
            or entry_map.get("proposal_sha256")
            != sha256_text(canonical_json(_mapping(entry_map, "proposal")))
            or not isinstance(entry_map.get("envelope_sha256"), str)
            or len(str(entry_map.get("envelope_sha256"))) != 64
        ):
            raise ProgramQualityConversationError(
                f"quality proposal history entry {index} lineage mismatch"
            )
    accepted_flag = (
        quality_provenance.get("accepted")
        if isinstance(quality_provenance, Mapping)
        else None
    )
    decision = payload.get("decision")
    if status == "proposed_pending_acceptance":
        if decision is not None or accepted_flag is not False:
            raise ProgramQualityConversationError(
                "pending quality proposal has inconsistent decision state"
            )
    else:
        if not isinstance(decision, Mapping):
            raise ProgramQualityConversationError(
                "decided quality proposal is missing decision evidence"
            )
        expected_outcome = (
            "accept" if status == "accepted_for_program_generation" else "reject"
        )
        if (
            decision.get("outcome") != expected_outcome
            or decision.get("local_generation_consent")
            is not (expected_outcome == "accept")
            or decision.get("program_generated") is not False
            or decision.get("external_authority_mutated") is not False
            or not isinstance(decision.get("source_envelope_sha256"), str)
            or len(str(decision.get("source_envelope_sha256"))) != 64
            or decision.get("source_envelope_sha256")
            != _derived_pending_envelope_sha256(payload)
            or accepted_flag is not (expected_outcome == "accept")
        ):
            raise ProgramQualityConversationError(
                "quality proposal decision evidence is inconsistent with status"
            )
    if (
        role.get("model") != "codex/gpt-5.6-sol"
        or role.get("reasoning_effort") != "high"
    ):
        raise ProgramQualityConversationError("quality proposal model role mismatch")
    if execution.get("status") != "completed" or not execution.get("response_sha256"):
        raise ProgramQualityConversationError(
            "quality proposal model execution evidence is incomplete"
        )
    required_effect = {
        "model_call_performed": True,
        "program_generated": False,
        "candidate_transitioned": False,
        "external_authority_mutated": False,
    }
    if any(effect.get(key) is not value for key, value in required_effect.items()):
        raise ProgramQualityConversationError(
            "quality proposal effect posture mismatch"
        )
    if any(
        non_authority.get(key) is not False
        for key in (
            "model_proposal_is_decision",
            "proposal_is_promotion",
            "proposal_is_activation",
        )
    ):
        raise ProgramQualityConversationError(
            "quality proposal non-authority posture mismatch"
        )
    normalized_payload = {
        **dict(payload),
        "proposal": validated_proposal,
        "candidate_intent": validated_candidate,
    }
    try:
        validate_publisher_assertion_no_secret(canonical_json(normalized_payload))
    except ProgramOracleSecretPolicyError as exc:
        raise ProgramQualityConversationError(
            "quality proposal envelope appears to contain secret-shaped content"
        ) from exc
    expected_identity = identity_for(normalized_payload)
    identity = payload.get("identity")
    if not isinstance(identity, Mapping) or dict(identity) != expected_identity:
        raise ProgramQualityConversationError(
            "quality proposal identity binding mismatch"
        )
    return {
        **normalized_payload,
        "identity": expected_identity,
    }


def set_quality_proposal_decision(
    payload: Mapping[str, Any], *, decision: str
) -> dict[str, Any]:
    current = validate_quality_proposal(
        payload, allowed_statuses={"proposed_pending_acceptance"}
    )
    normalized = str(decision or "").strip().lower()
    source_envelope_sha256 = current["identity"]["envelope_sha256"]
    if normalized not in {"accept", "reject"}:
        raise ProgramQualityConversationError("decision must be accept or reject")
    current["status"] = (
        "accepted_for_program_generation" if normalized == "accept" else "rejected"
    )
    if normalized == "accept":
        candidate = dict(current["candidate_intent"])
        options = dict(candidate.get("options") or {})
        provenance = dict(options.get("quality_proposal") or {})
        provenance["accepted"] = True
        options["quality_proposal"] = provenance
        candidate["options"] = options
        current["candidate_intent"] = ProgramIntent.model_validate(
            candidate
        ).model_dump(mode="json")
    current["decision"] = {
        "outcome": normalized,
        "local_generation_consent": normalized == "accept",
        "source_envelope_sha256": source_envelope_sha256,
        "program_generated": False,
        "external_authority_mutated": False,
    }
    current["identity"] = identity_for(current)
    return validate_quality_proposal(
        current,
        allowed_statuses={"accepted_for_program_generation", "rejected"},
    )


def _target(path: Path) -> Path:
    return Path(os.path.abspath(path.expanduser()))


def _require_fresh(path: Path, *, label: str) -> None:
    if os.path.lexists(path):
        raise ProgramQualityConversationError(f"{label} output already exists: {path}")


def _publish(payload: Mapping[str, Any], target: Path, *, label: str) -> Path:
    content = (
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    atomic_publish_bytes(
        target,
        content,
        label=label,
        precommit=lambda: _require_fresh(target, label=label),
        error_type=ProgramQualityConversationError,
        replace_existing=False,
    )
    return target


def write_quality_proposal(payload: Mapping[str, Any], out: Path) -> Path:
    validated = validate_quality_proposal(
        payload,
        allowed_statuses={
            "proposed_pending_acceptance",
            "accepted_for_program_generation",
            "rejected",
        },
    )
    return _publish(validated, _target(out), label="quality proposal")


def write_accepted_program_intent(payload: Mapping[str, Any], out: Path) -> Path:
    validated = validate_quality_proposal(
        payload, allowed_statuses={"accepted_for_program_generation"}
    )
    candidate = ProgramIntent.model_validate(validated["candidate_intent"]).model_dump(
        mode="json"
    )
    if candidate["options"]["quality_proposal"].get("accepted") is not True:
        raise ProgramQualityConversationError(
            "accepted proposal candidate intent is missing accepted provenance"
        )
    return _publish(candidate, _target(out), label="accepted program intent")
