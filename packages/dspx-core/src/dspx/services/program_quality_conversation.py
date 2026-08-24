# summary: "Proposes intent-native quality criteria through the Sol Codex model role."
# read_when:
#   - "Changing conversational intent-to-quality prompting or model execution."

from __future__ import annotations

import json
import math
from typing import Any, Mapping, Sequence

from dspx.provider_contract import (
    EffectDisposition,
    Provider,
    ProviderMessage,
    ProviderRequest,
)
from dspx.model_roles import create_role_lm, resolve_model_role
from dspx.redaction import sanitize_diagnostic_text
from dspx.services.program_intent import ProgramIntent
from dspx.services.program_intent_normalization import (
    normalize_program_intent_from_prompt,
)
from dspx.services.program_oracle_secret_policy import (
    ProgramOracleSecretPolicyError,
    validate_publisher_assertion_no_secret,
)
from dspx.services.program_quality_contract import (
    PROGRAM_QUALITY_PROPOSAL_SCHEMA,
    ProgramQualityConversationError,
    canonical_json,
    identity_for,
    parse_model_payload,
    set_quality_proposal_decision,
    sha256_text,
    validate_quality_proposal,
    write_accepted_program_intent,
    write_quality_proposal,
)

_MAX_INTENT_CHARS = 20_000
_MAX_FEEDBACK_TURNS = 8
_MAX_FEEDBACK_CHARS = 2_000
_MAX_FEEDBACK_TOTAL_CHARS = 8_000
_MAX_HISTORY_TURNS = 8
_USAGE_KEYS = {
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "prompt_tokens",
    "completion_tokens",
}


def _reject_secret_shaped_text(value: str, *, label: str) -> None:
    try:
        validate_publisher_assertion_no_secret(value)
    except ProgramOracleSecretPolicyError as exc:
        raise ProgramQualityConversationError(
            f"{label} appears to contain secret-shaped content; remove credentials before using a provider-backed conversation"
        ) from exc


def _bounded_feedback(feedback: Sequence[str]) -> list[str]:
    cleaned = [str(item).strip() for item in feedback if str(item).strip()]
    if len(cleaned) > _MAX_FEEDBACK_TURNS:
        raise ProgramQualityConversationError(
            f"quality conversation supports at most {_MAX_FEEDBACK_TURNS} feedback turns"
        )
    if any(len(item) > _MAX_FEEDBACK_CHARS for item in cleaned):
        raise ProgramQualityConversationError(
            f"quality feedback may not exceed {_MAX_FEEDBACK_CHARS} characters per turn"
        )
    if sum(len(item) for item in cleaned) > _MAX_FEEDBACK_TOTAL_CHARS:
        raise ProgramQualityConversationError(
            f"quality feedback may not exceed {_MAX_FEEDBACK_TOTAL_CHARS} total characters"
        )
    for item in cleaned:
        _reject_secret_shaped_text(item, label="quality feedback")
    return cleaned


def _history_entries(
    history: Sequence[Mapping[str, Any]], *, expected_intent_sha256: str
) -> list[dict[str, Any]]:
    if len(history) > _MAX_HISTORY_TURNS:
        raise ProgramQualityConversationError(
            f"quality conversation history may contain at most {_MAX_HISTORY_TURNS} proposals"
        )
    entries: list[dict[str, Any]] = []
    for index, item in enumerate(history):
        validated = validate_quality_proposal(
            item,
            allowed_statuses={
                "proposed_pending_acceptance",
                "accepted_for_program_generation",
                "rejected",
            },
        )
        intent = validated["intent"]
        if intent.get("text_sha256") != expected_intent_sha256:
            raise ProgramQualityConversationError(
                f"quality conversation history turn {index} belongs to a different intent"
            )
        conversation = validated["conversation"]
        if (
            conversation.get("turn") != index + 1
            or conversation.get("history") != entries
        ):
            raise ProgramQualityConversationError(
                f"quality conversation history turn {index} does not extend the preceding lineage"
            )
        _reject_secret_shaped_text(
            canonical_json(validated), label="quality conversation history"
        )
        entries.append(
            {
                "turn": index + 1,
                "intent_sha256": expected_intent_sha256,
                "envelope_sha256": validated["identity"]["envelope_sha256"],
                "proposal_sha256": validated["identity"]["proposal_sha256"],
                "proposal": validated["proposal"],
            }
        )
    return entries


def _prompt(
    *,
    objective: str,
    inputs: list[str],
    outputs: list[str],
    feedback: Sequence[str],
    history: Sequence[Mapping[str, Any]],
) -> str:
    return (
        "You design measurable quality criteria for a DSPy program before the "
        "program is generated. Return only one JSON object with exactly these keys: "
        "metric, quality_criteria, rationale, clarifying_questions. metric must be "
        "concept_coverage. quality_criteria must be a non-empty list. Every item must "
        "contain exactly id, output_field, evaluator, required_concept_groups, "
        "forbidden_concepts, min_score. evaluator must be concept_coverage. "
        f"output_field must be one of {json.dumps(outputs)}. ids must be lowercase. "
        "Use at most 20 criteria. required_concept_groups must contain 1-20 synonym "
        "groups, and every group must contain 1-10 short terms. forbidden_concepts "
        "must contain at most 50 short terms. Satisfying one term in each group should "
        "demonstrate the desired behavior. min_score is between 0 "
        "and 1. Prefer intended outcomes over writing style. Use clarifying_questions "
        "only for material unresolved ambiguity. When feedback refers to an earlier "
        "criterion, revise the supplied prior proposal rather than starting over.\n\n"
        f"Program objective:\n{objective}\n\n"
        f"Inferred input fields: {json.dumps(inputs)}\n"
        f"Inferred output fields: {json.dumps(outputs)}\n"
        f"Prior validated proposals: {json.dumps(list(history), ensure_ascii=False)}\n"
        f"Conversation feedback: {json.dumps(list(feedback), ensure_ascii=False)}"
    )


def _safe_usage(value: object) -> dict[str, int | float]:
    if not isinstance(value, Mapping):
        return {}
    mapping = {str(key): item for key, item in value.items()}
    result: dict[str, int | float] = {}
    for key in _USAGE_KEYS:
        item = mapping.get(key)
        if (
            isinstance(item, (int, float))
            and not isinstance(item, bool)
            and math.isfinite(float(item))
            and item >= 0
        ):
            result[key] = item
    return result


def propose_program_quality_criteria(
    intent: str,
    *,
    feedback: Sequence[str] = (),
    history: Sequence[Mapping[str, Any]] = (),
    lm: Provider | None = None,
) -> dict[str, Any]:
    """Propose a validated quality contract before program materialization."""

    objective = str(intent or "").strip()
    if not objective or len(objective) > _MAX_INTENT_CHARS:
        raise ProgramQualityConversationError(
            "program intent must contain 1-20000 characters"
        )
    _reject_secret_shaped_text(objective, label="program intent")
    cleaned_feedback = _bounded_feedback(feedback)
    intent_sha256 = sha256_text(objective)
    history_entries = _history_entries(history, expected_intent_sha256=intent_sha256)
    normalization = normalize_program_intent_from_prompt(objective)
    raw_intent = normalization.get("normalized_intent")
    if not isinstance(raw_intent, Mapping):
        raise ProgramQualityConversationError(
            "intent normalization did not produce a normalized intent"
        )
    draft = ProgramIntent.model_validate(dict(raw_intent))
    injected_lm = lm is not None
    if lm is None:
        create_role_lm("quality_criteria")
        raise AssertionError("removed model role unexpectedly returned")
    active_provider = lm
    normalized_error: ProgramQualityConversationError | None = None
    try:
        response = active_provider.invoke(
            ProviderRequest(
                model=active_provider.model,
                messages=(
                    ProviderMessage(
                        role="user",
                        text=_prompt(
                            objective=draft.objective,
                            inputs=draft.inputs,
                            outputs=draft.outputs,
                            feedback=cleaned_feedback,
                            history=history_entries,
                        ),
                    ),
                ),
            )
        )
    except Exception as exc:
        diagnostic = sanitize_diagnostic_text(str(exc))
        normalized_error = ProgramQualityConversationError(
            f"quality proposal model call failed: {type(exc).__name__}: {diagnostic}"
        )
    if normalized_error is not None:
        raise normalized_error from None
    if response.effect_disposition is not EffectDisposition.COMPLETED_SUCCESS:
        raise ProgramQualityConversationError(
            "quality proposal model call did not complete successfully: "
            f"{response.effect_disposition.value}"
        )
    raw_output = response.text
    stripped_output = raw_output.strip()
    response_json_extraction = (
        "direct_object"
        if stripped_output.startswith("{")
        else "fenced_or_wrapped_object"
    )
    proposal = parse_model_payload(raw_output, outputs=draft.outputs)
    _reject_secret_shaped_text(
        canonical_json(proposal), label="quality proposal model output"
    )
    candidate_payload = draft.model_dump(mode="json")
    candidate_payload["metric"] = proposal["metric"]
    candidate_payload["quality_criteria"] = proposal["quality_criteria"]
    options = dict(candidate_payload.get("options") or {})
    options["quality_proposal"] = {
        "schema_version": PROGRAM_QUALITY_PROPOSAL_SCHEMA,
        "intent_sha256": intent_sha256,
        "feedback_turns": len(cleaned_feedback),
        "accepted": False,
    }
    candidate_payload["options"] = options
    candidate = ProgramIntent.model_validate(candidate_payload).model_dump(mode="json")
    role = resolve_model_role("quality_criteria")
    reported_model_raw = str(response.model or "")
    reported_model_sanitized = sanitize_diagnostic_text(reported_model_raw)
    reported_model = (
        reported_model_sanitized
        if reported_model_sanitized == reported_model_raw
        else "[REDACTED]"
    )
    payload: dict[str, Any] = {
        "schema_version": PROGRAM_QUALITY_PROPOSAL_SCHEMA,
        "status": "proposed_pending_acceptance",
        "intent": {
            "text_sha256": intent_sha256,
            "normalization_schema_version": normalization.get("schema_version"),
            "inputs": draft.inputs,
            "outputs": draft.outputs,
        },
        "conversation": {
            "feedback": cleaned_feedback,
            "turn": len(history_entries) + 1,
            "history": history_entries,
        },
        "proposal": proposal,
        "candidate_intent": candidate,
        "model_role": role.evidence_descriptor(),
        "model_execution": {
            "status": "completed",
            "execution_mode": "injected_test_double"
            if injected_lm
            else "provider_backed",
            "requested_model": role.model,
            "reported_model": reported_model,
            "reasoning_effort": role.reasoning_effort,
            "usage": _safe_usage(response.usage),
            "response_sha256": sha256_text(raw_output),
            "json_extraction": response_json_extraction,
        },
        "effect": {
            "model_call_performed": True,
            "program_generated": False,
            "candidate_transitioned": False,
            "external_authority_mutated": False,
        },
        "non_authority": {
            "model_proposal_is_decision": False,
            "proposal_is_promotion": False,
            "proposal_is_activation": False,
        },
    }
    payload["identity"] = identity_for(payload)
    return validate_quality_proposal(
        payload, allowed_statuses={"proposed_pending_acceptance"}
    )


__all__ = [
    "PROGRAM_QUALITY_PROPOSAL_SCHEMA",
    "ProgramQualityConversationError",
    "propose_program_quality_criteria",
    "set_quality_proposal_decision",
    "write_accepted_program_intent",
    "write_quality_proposal",
]
