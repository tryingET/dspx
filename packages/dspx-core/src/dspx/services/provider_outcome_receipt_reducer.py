# summary: "Fail-closed state reduction for retained provider outcome receipt journals."
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

from dspx.services.provider_outcome_receipt_contract import (
    EmpiricalDisposition,
    ProviderOutcomeConsumerError,
    ReceiptProjection,
    SemanticOutcome,
    VerifiedJournal,
)
from dspx.services.provider_outcome_receipt_identity import verify_owner_artifact
from dspx.services.provider_outcome_receipt_journal import load_verified_journal

_TERMINALS = frozenset(
    {
        "pre_transport_failed",
        "remote_http_error_final",
        "provider_response_completed",
        "provider_response_failed",
        "provider_response_incomplete",
        "outcome_unresolved",
    }
)


@dataclass(frozen=True, slots=True)
class VerifiedReceiptChain:
    journal: VerifiedJournal
    terminal: str
    request_acknowledged: bool
    external_effect_possible: bool


@dataclass(frozen=True, slots=True)
class ReducedProviderOutcome:
    terminal: str
    request_acknowledged: bool
    external_effect_possible: bool
    empirical_disposition: EmpiricalDisposition
    reason: str


def _reject(reason: str, *, effect_possible: bool) -> NoReturn:
    raise ProviderOutcomeConsumerError(reason, effect_possible=effect_possible)


def verify_receipt_chain(journal: VerifiedJournal) -> VerifiedReceiptChain:
    phase = "absent"
    return_phase: str | None = None
    gate_ordinal = 0
    effect_possible = False
    acknowledged = False
    response_status: int | None = None
    response_id: str | None = None
    protocol_terminal: str | None = None
    protocol_seen: set[tuple[str, str | None]] = set()
    terminal: str | None = None

    for index, envelope in enumerate(journal.events):
        event = envelope.event
        kind = event.kind
        if terminal is not None:
            _reject("event_after_terminal", effect_possible=effect_possible)
        if kind == "wrapper_request_accepted":
            if index != 0 or phase != "absent":
                _reject("wrapper_event_order_drift", effect_possible=effect_possible)
            phase = "wrapper"
            continue
        if phase == "absent":
            _reject("wrapper_event_missing", effect_possible=True)
        if kind == "transport_gate_entered":
            ordinal = event.gate_ordinal or 0
            if ordinal != gate_ordinal + 1:
                _reject("gate_ordinal_drift", effect_possible=True)
            if ordinal == 1:
                if phase != "wrapper":
                    _reject("first_gate_order_drift", effect_possible=effect_possible)
                phase = "gate_one"
            else:
                if not effect_possible or phase not in {
                    "pending",
                    "transport",
                    "response",
                }:
                    _reject("retry_gate_order_drift", effect_possible=True)
                return_phase = phase
                phase = "retry_gate"
            gate_ordinal = ordinal
            continue
        if kind == "retry_blocked_before_transport":
            if (
                phase != "retry_gate"
                or event.gate_ordinal != gate_ordinal
                or return_phase is None
            ):
                _reject("retry_block_order_drift", effect_possible=True)
            phase = return_phase
            return_phase = None
            continue
        if kind == "pre_transport_failed":
            if effect_possible or phase not in {"wrapper", "gate_one"}:
                _reject("pre_transport_terminal_order_drift", effect_possible=True)
            terminal = kind
            phase = "terminal"
            continue
        if kind == "transport_effect_pending":
            if phase != "gate_one" or event.gate_ordinal != 1:
                _reject("effect_pending_order_drift", effect_possible=True)
            effect_possible = True
            phase = "pending"
            continue
        if kind == "transport_entered":
            if phase != "pending" or event.gate_ordinal != 1:
                _reject("transport_entry_order_drift", effect_possible=True)
            phase = "transport"
            continue
        if kind == "http_response_observed":
            if phase != "transport" or event.gate_ordinal != 1:
                _reject("http_response_order_drift", effect_possible=True)
            acknowledged = True
            response_status = event.status_class
            phase = "response"
            continue
        if kind == "parsed_protocol_event_observed":
            if phase != "response" or not acknowledged:
                _reject("protocol_event_order_drift", effect_possible=True)
            key = (event.protocol_event or "", event.response_id_sha256)
            if key in protocol_seen:
                _reject("duplicate_protocol_event", effect_possible=True)
            if (
                event.response_id_sha256 is not None
                and response_id is not None
                and event.response_id_sha256 != response_id
            ):
                _reject("protocol_response_identity_drift", effect_possible=True)
            failure_terminals = {
                "error",
                "response.error",
                "response.failed",
                "response.incomplete",
            }
            if protocol_terminal in failure_terminals or (
                event.protocol_event == "response.completed"
                and protocol_terminal is not None
                and protocol_terminal != "response.completed"
            ):
                _reject("contradictory_protocol_terminal", effect_possible=True)
            protocol_seen.add(key)
            if event.response_id_sha256 is not None:
                response_id = event.response_id_sha256
                protocol_terminal = event.protocol_event
            continue
        if kind == "remote_http_error_final":
            if (
                phase != "response"
                or response_status is None
                or response_status == 2
                or event.status_class != response_status
            ):
                _reject("remote_http_terminal_order_drift", effect_possible=True)
            terminal = kind
            phase = "terminal"
            continue
        if kind == "provider_response_completed":
            if (
                phase != "response"
                or response_status != 2
                or event.status_class != response_status
                or response_id is None
                or event.response_id_sha256 != response_id
                or protocol_terminal != "response.completed"
            ):
                _reject("provider_completed_terminal_drift", effect_possible=True)
            terminal = kind
            phase = "terminal"
            continue
        if kind == "provider_response_failed":
            allowed = {"error", "response.error", "response.failed"}
            if event.error_class == "provider_refusal":
                allowed.add("response.completed")
            if (
                phase != "response"
                or response_status is None
                or event.status_class != response_status
                or response_id is None
                or event.response_id_sha256 != response_id
                or protocol_terminal not in allowed
            ):
                _reject("provider_failed_terminal_drift", effect_possible=True)
            terminal = kind
            phase = "terminal"
            continue
        if kind == "provider_response_incomplete":
            if (
                phase != "response"
                or response_status is None
                or event.status_class != response_status
                or response_id is None
                or event.response_id_sha256 != response_id
                or protocol_terminal != "response.incomplete"
            ):
                _reject("provider_incomplete_terminal_drift", effect_possible=True)
            terminal = kind
            phase = "terminal"
            continue
        if kind == "outcome_unresolved":
            if not effect_possible or phase not in {"pending", "transport", "response"}:
                _reject("unresolved_terminal_order_drift", effect_possible=True)
            if (
                event.status_class is not None
                and response_status is not None
                and event.status_class != response_status
            ) or (
                event.response_id_sha256 is not None
                and response_id is not None
                and event.response_id_sha256 != response_id
            ):
                _reject("unresolved_terminal_binding_drift", effect_possible=True)
            terminal = kind
            phase = "terminal"
            continue
        _reject("unknown_state_transition", effect_possible=True)

    if terminal is None:
        _reject(
            "effect_capable_chain_open"
            if effect_possible
            else "pre_effect_chain_incomplete",
            effect_possible=effect_possible,
        )
    if journal.events[-1].event.kind not in _TERMINALS:
        _reject("terminal_not_last", effect_possible=effect_possible)
    return VerifiedReceiptChain(journal, terminal, acknowledged, effect_possible)


def reduce_verified_chain(
    chain: VerifiedReceiptChain,
    *,
    semantic_outcome: SemanticOutcome = "not_evaluated",
) -> ReducedProviderOutcome:
    terminal = chain.terminal
    disposition: EmpiricalDisposition
    if terminal == "outcome_unresolved":
        disposition, reason = "effect_indeterminate", "producer_outcome_unresolved"
    elif terminal in {
        "pre_transport_failed",
        "remote_http_error_final",
        "provider_response_failed",
        "provider_response_incomplete",
    }:
        disposition, reason = "error", terminal
    elif terminal == "provider_response_completed":
        disposition_map: dict[SemanticOutcome, EmpiricalDisposition] = {
            "not_evaluated": "not_evaluated",
            "semantic_error": "error",
            "score_miss": "failed",
            "score_pass": "passed",
        }
        reason_map = {
            "not_evaluated": "attributable_completion_not_evaluated",
            "semantic_error": "attributable_completion_semantic_error",
            "score_miss": "attributable_completion_score_miss",
            "score_pass": "attributable_completion_score_pass",
        }
        try:
            disposition, reason = (
                disposition_map[semantic_outcome],
                reason_map[semantic_outcome],
            )
        except KeyError as exc:
            raise ProviderOutcomeConsumerError("unknown_semantic_outcome") from exc
    else:  # pragma: no cover
        raise ProviderOutcomeConsumerError("unknown_terminal_projection")
    return ReducedProviderOutcome(
        terminal,
        chain.request_acknowledged,
        chain.external_effect_possible,
        disposition,
        reason,
    )


def _rejected(reason: str, effect_possible: bool) -> ReceiptProjection:
    return ReceiptProjection(
        provider_outcome_receipt="rejected",
        request_acknowledged=None,
        external_effect_possible=effect_possible,
        producer_terminal=None,
        empirical_disposition="effect_indeterminate" if effect_possible else "error",
        reason=reason,
    )


def reduce_journal(
    root: Path,
    *,
    owner_source_root: Path | None = None,
    event_type: type[Any] | None = None,
    receipt_type: type[Any] | None = None,
    semantic_outcome: SemanticOutcome = "not_evaluated",
) -> ReceiptProjection:
    try:
        journal = load_verified_journal(root)
        chain = verify_receipt_chain(journal)
    except ProviderOutcomeConsumerError as exc:
        return _rejected(exc.reason, exc.effect_possible)
    if journal.artifact_verification != "accepted_exact":
        return _rejected("fixture_journal_not_accepted", chain.external_effect_possible)
    if owner_source_root is None or event_type is None or receipt_type is None:
        return _rejected(
            "accepted_owner_artifact_required", chain.external_effect_possible
        )
    try:
        artifact = verify_owner_artifact(owner_source_root, event_type, receipt_type)
        if (
            journal.reservation.source_identity != artifact.source_identity
            or journal.reservation.dependency_identity != artifact.dependency_identity
        ):
            raise ProviderOutcomeConsumerError("retained_owner_identity_drift")
    except ProviderOutcomeConsumerError as exc:
        return _rejected(exc.reason, chain.external_effect_possible)
    reduced = reduce_verified_chain(chain, semantic_outcome=semantic_outcome)
    return ReceiptProjection(
        provider_outcome_receipt="accepted",
        request_acknowledged=reduced.request_acknowledged,
        external_effect_possible=reduced.external_effect_possible,
        producer_terminal=reduced.terminal,
        empirical_disposition=reduced.empirical_disposition,
        reason=reduced.reason,
    )
