# summary: "Soomfon-only AK-5070 exact-status provider receipt contract."
from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any, Literal, Mapping, cast

from dspx.services.provider_outcome_receipt_contract import (
    ERROR_CLASSES,
    EVENT_KINDS,
    MAX_EVENT_BYTES as MAX_EVENT_BYTES,
    MAX_EVENTS as MAX_EVENTS,
    PROTOCOL_EVENTS,
    EmpiricalDisposition,
    ProtocolEventKind,
    ProviderOutcomeConsumerError,
    ReceiptErrorClass,
    ReceiptEventKind,
    ReceiptReservation,
    SemanticOutcome as SemanticOutcome,
    _bounded_model,
    _sha256,
    canonical_json,
    sha256,
)

# Exact AK-5070 owner API. Frozen V11 EVENT_FIELDS remains seven fields elsewhere.
EVENT_FIELDS = (
    "kind",
    "gate_ordinal",
    "status_class",
    "status_code",
    "error_class",
    "protocol_event",
    "response_id_sha256",
    "observed_model",
)
EVENT_FIELDS_V2 = EVENT_FIELDS


@dataclass(frozen=True, slots=True)
class ClosedOwnerEvent:
    kind: ReceiptEventKind
    gate_ordinal: int | None = None
    status_class: int | None = None
    status_code: int | None = None
    error_class: ReceiptErrorClass | None = None
    protocol_event: ProtocolEventKind | None = None
    response_id_sha256: str | None = None
    observed_model: str | None = None

    @classmethod
    def from_owner(cls, event: object, *, exact_type: type[Any]) -> "ClosedOwnerEvent":
        if type(event) is not exact_type:
            raise ProviderOutcomeConsumerError("alternate_owner_event_type")
        try:
            field_names = tuple(field.name for field in fields(exact_type))
        except TypeError as exc:
            raise ProviderOutcomeConsumerError("owner_event_not_dataclass") from exc
        if field_names != EVENT_FIELDS:
            raise ProviderOutcomeConsumerError("owner_event_schema_drift")
        return cls.from_mapping({name: getattr(event, name) for name in EVENT_FIELDS})

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ClosedOwnerEvent":
        if set(value) != set(EVENT_FIELDS):
            raise ProviderOutcomeConsumerError("owner_event_schema_drift")
        kind = value.get("kind")
        gate = value.get("gate_ordinal")
        status = value.get("status_class")
        status_code = value.get("status_code")
        error = value.get("error_class")
        protocol = value.get("protocol_event")
        response_hash = value.get("response_id_sha256")
        model = value.get("observed_model")
        if kind not in EVENT_KINDS:
            raise ProviderOutcomeConsumerError("unknown_event_kind")
        if gate is not None and (
            isinstance(gate, bool) or not isinstance(gate, int) or gate < 1
        ):
            raise ProviderOutcomeConsumerError("invalid_gate_ordinal")
        if status is not None and (
            isinstance(status, bool)
            or not isinstance(status, int)
            or status not in range(1, 6)
        ):
            raise ProviderOutcomeConsumerError("invalid_status_class")
        if status_code is not None and (
            isinstance(status_code, bool)
            or not isinstance(status_code, int)
            or not 100 <= status_code <= 599
        ):
            raise ProviderOutcomeConsumerError("invalid_status_code")
        if (status is None) != (status_code is None):
            raise ProviderOutcomeConsumerError("status_class_code_pair_drift")
        if status_code is not None and status != status_code // 100:
            raise ProviderOutcomeConsumerError("status_class_code_mismatch")
        if error is not None and error not in ERROR_CLASSES:
            raise ProviderOutcomeConsumerError("unknown_error_class")
        if protocol is not None and protocol not in PROTOCOL_EVENTS:
            raise ProviderOutcomeConsumerError("unknown_protocol_event")
        if response_hash is not None:
            response_hash = _sha256(response_hash, "response_id_sha256")
        event_value = cls(
            kind=cast(ReceiptEventKind, kind),
            gate_ordinal=cast(int | None, gate),
            status_class=cast(int | None, status),
            status_code=cast(int | None, status_code),
            error_class=cast(ReceiptErrorClass | None, error),
            protocol_event=cast(ProtocolEventKind | None, protocol),
            response_id_sha256=response_hash,
            observed_model=_bounded_model(model),
        )
        event_value._validate_shape()
        return event_value

    @property
    def uses_status_code_field(self) -> bool:
        return True

    def _validate_shape(self) -> None:
        present = {name for name in EVENT_FIELDS[1:] if getattr(self, name) is not None}
        allowed: dict[str, set[str]] = {
            "wrapper_request_accepted": set(),
            "pre_transport_failed": {"error_class"},
            "transport_gate_entered": {"gate_ordinal"},
            "retry_blocked_before_transport": {"gate_ordinal", "error_class"},
            "transport_effect_pending": {"gate_ordinal"},
            "transport_entered": {"gate_ordinal"},
            "http_response_observed": {
                "gate_ordinal",
                "status_class",
                "status_code",
            },
            "parsed_protocol_event_observed": {
                "protocol_event",
                "response_id_sha256",
            },
            "remote_http_error_final": {
                "status_class",
                "status_code",
                "error_class",
            },
            "provider_response_completed": {
                "status_class",
                "status_code",
                "response_id_sha256",
                "observed_model",
            },
            "provider_response_failed": {
                "status_class",
                "status_code",
                "error_class",
                "response_id_sha256",
            },
            "provider_response_incomplete": {
                "status_class",
                "status_code",
                "error_class",
                "response_id_sha256",
            },
            "outcome_unresolved": {
                "status_class",
                "status_code",
                "error_class",
                "response_id_sha256",
            },
        }
        required: dict[str, set[str]] = {
            "pre_transport_failed": {"error_class"},
            "transport_gate_entered": {"gate_ordinal"},
            "retry_blocked_before_transport": {"gate_ordinal", "error_class"},
            "transport_effect_pending": {"gate_ordinal"},
            "transport_entered": {"gate_ordinal"},
            "http_response_observed": {
                "gate_ordinal",
                "status_class",
                "status_code",
            },
            "parsed_protocol_event_observed": {"protocol_event"},
            "remote_http_error_final": {
                "status_class",
                "status_code",
                "error_class",
            },
            "provider_response_completed": {
                "status_class",
                "status_code",
                "response_id_sha256",
            },
            "provider_response_failed": {
                "status_class",
                "status_code",
                "error_class",
                "response_id_sha256",
            },
            "provider_response_incomplete": {
                "status_class",
                "status_code",
                "error_class",
                "response_id_sha256",
            },
            "outcome_unresolved": {"error_class"},
        }
        if not required.get(self.kind, set()).issubset(present) or not present.issubset(
            allowed[self.kind]
        ):
            raise ProviderOutcomeConsumerError("event_field_shape_drift")
        if (
            self.kind == "retry_blocked_before_transport"
            and self.error_class != "retry_blocked"
        ):
            raise ProviderOutcomeConsumerError("retry_event_class_drift")
        if self.kind == "remote_http_error_final" and (
            self.error_class != "remote_http_status" or self.status_class == 2
        ):
            raise ProviderOutcomeConsumerError("remote_http_terminal_drift")
        if (
            self.kind == "provider_response_incomplete"
            and self.error_class != "provider_incomplete"
        ):
            raise ProviderOutcomeConsumerError("provider_incomplete_terminal_drift")
        if self.kind == "provider_response_failed" and self.error_class not in {
            "provider_failed",
            "provider_refusal",
        }:
            raise ProviderOutcomeConsumerError("provider_failed_terminal_drift")

    def payload(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in EVENT_FIELDS}


@dataclass(frozen=True, slots=True)
class JournalEnvelope:
    sequence: int
    previous_event_sha256: str | None
    event: ClosedOwnerEvent
    raw: bytes
    digest: str


@dataclass(frozen=True, slots=True)
class VerifiedJournal:
    reservation: ReceiptReservation
    events: tuple[JournalEnvelope, ...]
    artifact_verification: Literal["accepted_exact", "fixture_only"]


def event_envelope_payload(
    reservation: ReceiptReservation,
    sequence: int,
    previous: str | None,
    event: ClosedOwnerEvent,
) -> dict[str, Any]:
    identity = reservation.source_identity
    producer = {
        key: identity.get(key) for key in ("owner", "version", "commit", "tree")
    }
    if not all(isinstance(value, str) and value for value in producer.values()):
        raise ProviderOutcomeConsumerError("producer_identity_drift")
    return {
        "schema_version": "dspx-soomfon-provider-outcome-consumption-event-v2",
        "reservation_id": reservation.reservation_id,
        "sequence": sequence,
        "previous_event_sha256": previous,
        "producer": producer,
        "source_identity_sha256": sha256(canonical_json(reservation.source_identity)),
        "dependency_identity_sha256": sha256(
            canonical_json(reservation.dependency_identity)
        ),
        "event": event.payload(),
    }


@dataclass(frozen=True, slots=True)
class ReceiptProjection:
    provider_outcome_receipt: Literal["accepted", "rejected"]
    request_acknowledged: bool | None
    external_effect_possible: bool
    producer_terminal: str | None
    status_class: int | None
    status_code: int | None
    empirical_disposition: EmpiricalDisposition
    reason: str

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": "dspx-soomfon-provider-outcome-projection-v2",
            "provider_outcome_receipt": self.provider_outcome_receipt,
            "request_acknowledged": self.request_acknowledged,
            "external_effect_possible": self.external_effect_possible,
            "producer_terminal": self.producer_terminal,
            "status_class": self.status_class,
            "status_code": self.status_code,
            "empirical_disposition": self.empirical_disposition,
            "reason": self.reason,
            "fixture_only": True,
            "v11_authorized": False,
            "live_execution_authorized": False,
        }
