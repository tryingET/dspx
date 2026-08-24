# summary: "Verifier-local exact reservation, marker, event-chain, and projection checks."
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from dspx.services.program_oracle_semantic_artifacts_v11 import ConsumedAttempt
from dspx.services.program_oracle_semantic_gate4_contract_v11 import (
    EXPECTED_ENDPOINT_ORIGIN_SHA256,
    REQUESTED_ROUTE,
    RESOLVED_ROUTE,
)
from dspx.services.program_oracle_semantic_gate5_semantics_v11 import VerifierCase
from dspx.services.provider_outcome_receipt_contract import (
    ProviderOutcomeConsumerError,
    ReceiptProjection,
    ReceiptReservation,
    SemanticOutcome,
    VerifiedJournal,
)
from dspx.services.provider_outcome_receipt_identity import VerifiedOwnerArtifact
import dspx.services.provider_outcome_receipt_journal as journal_module
from dspx.services.provider_outcome_receipt_reducer import (
    reduce_verified_chain,
    verify_receipt_chain,
)

_LOGICAL_DOMAIN = b"dspx-oracle-semantic-v11-logical-request-v1\0"
_GATE_DOMAIN = b"dspx-oracle-semantic-v11-transport-gate-v1\0"
_PROCESS_DOMAIN = b"dspx-oracle-semantic-v11-process-v1\0"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _domain(domain: bytes, value: Mapping[str, Any]) -> str:
    return _sha(domain + _canonical(dict(value)))


def expected_reservation(
    attempt: ConsumedAttempt,
    case: VerifierCase,
    semantic_request_sha256: str,
    artifact: VerifiedOwnerArtifact,
) -> ReceiptReservation:
    ledger = attempt.ledger
    logical = _domain(
        _LOGICAL_DOMAIN,
        {
            "live_task_id": attempt.binding.live_task_id,
            "state_root_identity_sha256": attempt.binding.state_root_identity_sha256,
            "contract_sha256": ledger["contract_sha256"],
            "ledger_sha256": attempt.ledger_sha256,
            "case_id": case.case_id,
            "case_ordinal": case.case_ordinal,
        },
    )
    process = _domain(
        _PROCESS_DOMAIN,
        {
            "live_task_id": attempt.binding.live_task_id,
            "state_root_identity_sha256": attempt.binding.state_root_identity_sha256,
            "ledger_sha256": attempt.ledger_sha256,
            "process_identity_sha256": ledger["process_identity_sha256"],
        },
    )
    return ReceiptReservation(
        consumer_task_id=attempt.binding.live_task_id,
        ledger_sha256=attempt.ledger_sha256,
        process_id=process,
        case_id=case.case_id,
        logical_request_id=logical,
        transport_gate_id=_domain(
            _GATE_DOMAIN, {"logical_request_id": logical, "gate_ordinal": 1}
        ),
        semantic_request_sha256=semantic_request_sha256,
        contract_sha256=ledger["contract_sha256"],
        mode="sync",
        requested_route=REQUESTED_ROUTE,
        resolved_route=RESOLVED_ROUTE,
        endpoint_origin_sha256=EXPECTED_ENDPOINT_ORIGIN_SHA256,
        source_identity=artifact.source_identity,
        dependency_identity=artifact.dependency_identity,
    )


def _rejected(reason: str, effect: bool) -> ReceiptProjection:
    return ReceiptProjection(
        "rejected",
        None,
        effect,
        None,
        "effect_indeterminate" if effect else "error",
        reason,
    )


def _payload(
    projection: ReceiptProjection,
    *,
    observed_model: str | None,
    reservation_sha256: str,
    terminal_event_sha256: str | None,
    journal_present: bool,
    admitted: bool,
    delegations: int,
    clean: bool,
) -> dict[str, Any]:
    return {
        "provider_outcome": projection.payload(),
        "observed_model": observed_model,
        "reservation_sha256": reservation_sha256,
        "terminal_event_sha256": terminal_event_sha256,
        "journal_present": journal_present,
        "invocation_admitted": admitted,
        "effect_capable_delegations": delegations,
        "clean_terminal_order_proven": clean,
    }


def _read_exact(
    root: Path, expected: ReceiptReservation
) -> tuple[ReceiptReservation, tuple[Any, ...], str, str | None, bool, bool]:
    journal_module._require_private(root, directory=True)
    members = {path.name for path in root.iterdir()}
    unknown = members - {"reservation.json", "events", "poisoned.json", "inflight.json"}
    markers = members & {"poisoned.json", "inflight.json"}
    if (
        unknown
        or "reservation.json" not in members
        or "events" not in members
        or len(markers) > 1
    ):
        raise ProviderOutcomeConsumerError(
            "ambiguous_journal_members", effect_possible=True
        )
    wrapper = journal_module._decode_mapping(
        journal_module._read_private(root / "reservation.json"), "reservation_invalid"
    )
    reservation_raw = wrapper.get("reservation")
    if (
        set(wrapper)
        != {"schema_version", "reservation_id", "artifact_verification", "reservation"}
        or wrapper.get("schema_version") != "dspx-provider-outcome-consumption-v1"
        or not isinstance(reservation_raw, Mapping)
    ):
        raise ProviderOutcomeConsumerError("reservation_schema_drift")
    observed = journal_module._reservation_from_payload(reservation_raw)
    if (
        observed.payload() != expected.payload()
        or wrapper.get("reservation_id") != observed.reservation_id
    ):
        raise ProviderOutcomeConsumerError(
            "reservation_exact_field_drift", effect_possible=True
        )
    events_root = root / "events"
    journal_module._require_private(events_root, directory=True)
    event_members = sorted(events_root.iterdir(), key=lambda item: item.name)
    envelopes: list[Any] = []
    previous: str | None = None
    for sequence, member in enumerate(event_members):
        if member.name != f"{sequence:06d}.json":
            raise ProviderOutcomeConsumerError(
                "event_sequence_drift", effect_possible=True
            )
        envelope = journal_module._validate_envelope(
            journal_module._read_private(member), observed, sequence, previous
        )
        envelopes.append(envelope)
        previous = envelope.digest

    marker_name = next(iter(markers), None)
    marker_effect = False
    marker_valid = True
    if marker_name is not None:
        marker = journal_module._decode_mapping(
            journal_module._read_private(root / marker_name), "journal_marker_invalid"
        )
        if marker_name == "poisoned.json":
            marker_valid = (
                set(marker) == {"schema_version", "effect_possible"}
                and marker.get("schema_version") == "dspx-provider-outcome-poison-v1"
                and isinstance(marker.get("effect_possible"), bool)
            )
        else:
            sequence = marker.get("sequence")
            lawful_sequences = {len(envelopes)}
            if envelopes:
                lawful_sequences.add(len(envelopes) - 1)
            marker_valid = (
                set(marker) == {"schema_version", "sequence", "effect_possible"}
                and marker.get("schema_version") == "dspx-provider-outcome-inflight-v1"
                and not isinstance(sequence, bool)
                and isinstance(sequence, int)
                and sequence in lawful_sequences
                and isinstance(marker.get("effect_possible"), bool)
            )
        effect = marker.get("effect_possible")
        marker_effect = effect if isinstance(effect, bool) else True
    return (
        observed,
        tuple(envelopes),
        cast(str, wrapper.get("artifact_verification")),
        marker_name,
        marker_effect,
        marker_valid,
    )


def inspect_journal(
    root: Path,
    *,
    expected: ReceiptReservation,
    artifact: VerifiedOwnerArtifact,
    semantic_outcome: SemanticOutcome,
) -> dict[str, Any]:
    expected_digest = _sha(_canonical(expected.payload()))
    if not root.exists() and not root.is_symlink():
        return _payload(
            _rejected("receipt_preparation_failed_before_effect", False),
            observed_model=None,
            reservation_sha256=expected_digest,
            terminal_event_sha256=None,
            journal_present=False,
            admitted=False,
            delegations=0,
            clean=False,
        )
    try:
        observed, envelopes, verification, marker, marker_effect, marker_valid = (
            _read_exact(root, expected)
        )
    except (OSError, ProviderOutcomeConsumerError):
        return _payload(
            _rejected("retained_reservation_or_event_drift", True),
            observed_model=None,
            reservation_sha256=expected_digest,
            terminal_event_sha256=None,
            journal_present=True,
            admitted=False,
            delegations=0,
            clean=False,
        )
    events = [item.event for item in envelopes]
    admitted = bool(events and events[0].kind == "wrapper_request_accepted")
    delegations = sum(event.kind == "transport_entered" for event in events)
    effect = (
        (marker is not None and not marker_valid)
        or marker_effect
        or any(
            event.kind
            in {
                "transport_effect_pending",
                "transport_entered",
                "http_response_observed",
                "parsed_protocol_event_observed",
                "remote_http_error_final",
                "provider_response_completed",
                "provider_response_failed",
                "provider_response_incomplete",
                "outcome_unresolved",
            }
            for event in events
        )
    )
    if marker is not None:
        reason = (
            "journal_marker_invalid"
            if not marker_valid
            else "journal_poisoned"
            if marker == "poisoned.json"
            else "journal_inflight"
        )
        return _payload(
            _rejected(reason, effect),
            observed_model=None,
            reservation_sha256=expected_digest,
            terminal_event_sha256=None,
            journal_present=True,
            admitted=admitted,
            delegations=delegations,
            clean=False,
        )
    gates = [
        event.gate_ordinal for event in events if event.kind == "transport_gate_entered"
    ]
    if (
        sum(event.kind == "wrapper_request_accepted" for event in events) != 1
        or gates not in ([], [1])
        or delegations > 1
        or any(event.kind == "retry_blocked_before_transport" for event in events)
    ):
        return _payload(
            _rejected("one_delegation_custody_drift", effect),
            observed_model=None,
            reservation_sha256=expected_digest,
            terminal_event_sha256=None,
            journal_present=True,
            admitted=admitted,
            delegations=delegations,
            clean=False,
        )
    if verification != "accepted_exact" or not artifact.accepted:
        return _payload(
            _rejected("fixture_journal_not_accepted", effect),
            observed_model=None,
            reservation_sha256=expected_digest,
            terminal_event_sha256=None,
            journal_present=True,
            admitted=admitted,
            delegations=delegations,
            clean=False,
        )
    try:
        chain = verify_receipt_chain(
            VerifiedJournal(observed, envelopes, "accepted_exact")
        )
        reduced = reduce_verified_chain(chain, semantic_outcome=semantic_outcome)
    except ProviderOutcomeConsumerError as exc:
        return _payload(
            _rejected(exc.reason, exc.effect_possible),
            observed_model=None,
            reservation_sha256=expected_digest,
            terminal_event_sha256=None,
            journal_present=True,
            admitted=admitted,
            delegations=delegations,
            clean=False,
        )
    projection = ReceiptProjection(
        "accepted",
        reduced.request_acknowledged,
        reduced.external_effect_possible,
        reduced.terminal,
        reduced.empirical_disposition,
        reduced.reason,
    )
    model = (
        envelopes[-1].event.observed_model
        if reduced.terminal == "provider_response_completed"
        else None
    )
    return _payload(
        projection,
        observed_model=model,
        reservation_sha256=expected_digest,
        terminal_event_sha256=envelopes[-1].digest,
        journal_present=True,
        admitted=admitted,
        delegations=delegations,
        clean=True,
    )
