# summary: "Closed DSPx consumer contracts for provider outcome receipt custody."
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, fields
from typing import Any, Literal, Mapping, cast

ReceiptEventKind = Literal[
    "wrapper_request_accepted",
    "pre_transport_failed",
    "transport_gate_entered",
    "retry_blocked_before_transport",
    "transport_effect_pending",
    "transport_entered",
    "http_response_observed",
    "parsed_protocol_event_observed",
    "remote_http_error_final",
    "provider_response_completed",
    "provider_response_failed",
    "provider_response_incomplete",
    "outcome_unresolved",
]
ReceiptErrorClass = Literal[
    "callback_posture",
    "concurrent_request",
    "pre_transport_validation",
    "provider_failed",
    "provider_incomplete",
    "provider_refusal",
    "receipt_invalid",
    "receipt_persistence",
    "remote_http_status",
    "request_identity_mismatch",
    "retry_blocked",
    "sanitization_rejected",
    "transport_exception",
    "transport_exception_unknown",
    "transport_timeout",
]
ProtocolEventKind = Literal[
    "error",
    "response.completed",
    "response.error",
    "response.failed",
    "response.incomplete",
]
SemanticOutcome = Literal["not_evaluated", "semantic_error", "score_miss", "score_pass"]
EmpiricalDisposition = Literal[
    "not_evaluated", "effect_indeterminate", "error", "failed", "passed"
]

EVENT_KINDS = frozenset(ReceiptEventKind.__args__)
ERROR_CLASSES = frozenset(ReceiptErrorClass.__args__)
PROTOCOL_EVENTS = frozenset(ProtocolEventKind.__args__)
EVENT_FIELDS = (
    "kind",
    "gate_ordinal",
    "status_class",
    "error_class",
    "protocol_event",
    "response_id_sha256",
    "observed_model",
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
MAX_EVENT_BYTES = 16 * 1024
MAX_EVENTS = 64

_RESERVATION_DOMAIN = b"dspx-provider-outcome-reservation-v1\0"


class ProviderOutcomeConsumerError(ValueError):
    """Fixed-message consumer rejection with a closed reason."""

    def __init__(
        self,
        reason: str,
        *,
        effect_possible: bool = False,
        message: str = "provider outcome receipt rejected",
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.effect_possible = effect_possible


def canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ProviderOutcomeConsumerError("non_canonical_value") from exc


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _bounded_id(value: Any, name: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise ProviderOutcomeConsumerError(f"invalid_{name}")
    return value


def _sha256(value: Any, name: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise ProviderOutcomeConsumerError(f"invalid_{name}")
    return value


def _bounded_model(value: Any) -> str | None:
    if value is None:
        return None
    if (
        not isinstance(value, str)
        or not value
        or len(value.encode("utf-8")) > 128
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise ProviderOutcomeConsumerError("invalid_observed_model")
    return value


def _closed_identity(value: Mapping[str, Any], name: str) -> dict[str, Any]:
    if name == "source_identity":
        module_names = {
            "package_init",
            "lm",
            "codex_stream",
            "codex_stream_support",
            "outcome_receipt",
            "outcome_receipt_state",
            "outcome_receipt_runtime",
            "outcome_receipt_transport",
        }
        modules = value.get("module_sha256")
        if (
            set(value)
            != {"owner", "version", "commit", "tree", "lock_sha256", "module_sha256"}
            or value.get("owner") != "tryinget-dspy-lm-auth"
            or not isinstance(value.get("version"), str)
            or not ID_RE.fullmatch(value["version"])
            or not isinstance(value.get("commit"), str)
            or not re.fullmatch(r"[0-9a-f]{40}", value["commit"])
            or not isinstance(value.get("tree"), str)
            or not re.fullmatch(r"[0-9a-f]{40}", value["tree"])
            or not isinstance(modules, Mapping)
            or set(modules) != module_names
        ):
            raise ProviderOutcomeConsumerError("invalid_source_identity")
        closed_modules = {
            key: _sha256(modules[key], f"source_module_{key}")
            for key in sorted(module_names)
        }
        return {
            "owner": value["owner"],
            "version": value["version"],
            "commit": value["commit"],
            "tree": value["tree"],
            "lock_sha256": _sha256(value.get("lock_sha256"), "source_lock_sha256"),
            "module_sha256": closed_modules,
        }
    if name == "dependency_identity":
        dependency_names = {"dspy", "litellm", "httpx", "httpcore"}
        entry_keys = {
            "version",
            "locked_wheel_sha256",
            "payload_count",
            "payload_sha256",
            "record_sha256",
        }
        if set(value) != dependency_names:
            raise ProviderOutcomeConsumerError("invalid_dependency_identity")
        closed_dependencies: dict[str, Any] = {}
        for key in sorted(dependency_names):
            entry = value.get(key)
            if (
                not isinstance(entry, Mapping)
                or set(entry) != entry_keys
                or not isinstance(entry.get("version"), str)
                or not ID_RE.fullmatch(entry["version"])
                or isinstance(entry.get("payload_count"), bool)
                or not isinstance(entry.get("payload_count"), int)
                or not 1 <= entry["payload_count"] <= 100_000
            ):
                raise ProviderOutcomeConsumerError("invalid_dependency_identity")
            closed_dependencies[key] = {
                "version": entry["version"],
                "locked_wheel_sha256": _sha256(
                    entry.get("locked_wheel_sha256"), f"{key}_wheel_sha256"
                ),
                "payload_count": entry["payload_count"],
                "payload_sha256": _sha256(
                    entry.get("payload_sha256"), f"{key}_payload_sha256"
                ),
                "record_sha256": _sha256(
                    entry.get("record_sha256"), f"{key}_record_sha256"
                ),
            }
        return closed_dependencies
    raise ProviderOutcomeConsumerError("unknown_identity_kind")


@dataclass(frozen=True, slots=True)
class ReceiptReservation:
    consumer_task_id: int
    ledger_sha256: str
    process_id: str
    case_id: str
    logical_request_id: str
    transport_gate_id: str
    semantic_request_sha256: str
    contract_sha256: str
    mode: Literal["sync", "async"]
    requested_route: str
    resolved_route: str
    endpoint_origin_sha256: str
    source_identity: Mapping[str, Any]
    dependency_identity: Mapping[str, Any]

    def payload(self) -> dict[str, Any]:
        if (
            isinstance(self.consumer_task_id, bool)
            or not isinstance(self.consumer_task_id, int)
            or self.consumer_task_id < 1
        ):
            raise ProviderOutcomeConsumerError("invalid_consumer_task_id")
        if self.mode not in {"sync", "async"}:
            raise ProviderOutcomeConsumerError("invalid_mode")
        payload = {
            "schema_version": "dspx-provider-outcome-reservation-v1",
            "consumer_task_id": self.consumer_task_id,
            "ledger_sha256": _sha256(self.ledger_sha256, "ledger_sha256"),
            "process_id": _bounded_id(self.process_id, "process_id"),
            "case_id": _bounded_id(self.case_id, "case_id"),
            "logical_request_id": _bounded_id(
                self.logical_request_id, "logical_request_id"
            ),
            "transport_gate_id": _bounded_id(
                self.transport_gate_id, "transport_gate_id"
            ),
            "semantic_request_sha256": _sha256(
                self.semantic_request_sha256, "semantic_request_sha256"
            ),
            "contract_sha256": _sha256(self.contract_sha256, "contract_sha256"),
            "mode": self.mode,
            "requested_route": _bounded_id(self.requested_route, "requested_route"),
            "resolved_route": _bounded_id(self.resolved_route, "resolved_route"),
            "endpoint_origin_sha256": _sha256(
                self.endpoint_origin_sha256, "endpoint_origin_sha256"
            ),
            "source_identity": _closed_identity(
                self.source_identity, "source_identity"
            ),
            "dependency_identity": _closed_identity(
                self.dependency_identity, "dependency_identity"
            ),
        }
        if len(canonical_json(payload)) > MAX_EVENT_BYTES:
            raise ProviderOutcomeConsumerError("reservation_too_large")
        return payload

    @property
    def reservation_id(self) -> str:
        return sha256(_RESERVATION_DOMAIN + canonical_json(self.payload()))


@dataclass(frozen=True, slots=True)
class ClosedOwnerEvent:
    kind: ReceiptEventKind
    gate_ordinal: int | None = None
    status_class: int | None = None
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
        values = {name: getattr(event, name) for name in EVENT_FIELDS}
        return cls.from_mapping(values)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ClosedOwnerEvent":
        if set(value) != set(EVENT_FIELDS):
            raise ProviderOutcomeConsumerError("owner_event_schema_drift")
        kind = value.get("kind")
        gate = value.get("gate_ordinal")
        status = value.get("status_class")
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
            error_class=cast(ReceiptErrorClass | None, error),
            protocol_event=cast(ProtocolEventKind | None, protocol),
            response_id_sha256=response_hash,
            observed_model=_bounded_model(model),
        )
        event_value._validate_shape()
        return event_value

    def _validate_shape(self) -> None:
        present = {name for name in EVENT_FIELDS[1:] if getattr(self, name) is not None}
        allowed: dict[str, set[str]] = {
            "wrapper_request_accepted": set(),
            "pre_transport_failed": {"error_class"},
            "transport_gate_entered": {"gate_ordinal"},
            "retry_blocked_before_transport": {"gate_ordinal", "error_class"},
            "transport_effect_pending": {"gate_ordinal"},
            "transport_entered": {"gate_ordinal"},
            "http_response_observed": {"gate_ordinal", "status_class"},
            "parsed_protocol_event_observed": {
                "protocol_event",
                "response_id_sha256",
            },
            "remote_http_error_final": {"status_class", "error_class"},
            "provider_response_completed": {
                "status_class",
                "response_id_sha256",
                "observed_model",
            },
            "provider_response_failed": {
                "status_class",
                "error_class",
                "response_id_sha256",
            },
            "provider_response_incomplete": {
                "status_class",
                "error_class",
                "response_id_sha256",
            },
            "outcome_unresolved": {
                "status_class",
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
            "http_response_observed": {"gate_ordinal", "status_class"},
            "parsed_protocol_event_observed": {"protocol_event"},
            "remote_http_error_final": {"status_class", "error_class"},
            "provider_response_completed": {"status_class", "response_id_sha256"},
            "provider_response_failed": {
                "status_class",
                "error_class",
                "response_id_sha256",
            },
            "provider_response_incomplete": {
                "status_class",
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
        "schema_version": "dspx-provider-outcome-consumption-event-v1",
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
    empirical_disposition: EmpiricalDisposition
    reason: str

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": "dspx-provider-outcome-projection-v1",
            "provider_outcome_receipt": self.provider_outcome_receipt,
            "request_acknowledged": self.request_acknowledged,
            "external_effect_possible": self.external_effect_possible,
            "producer_terminal": self.producer_terminal,
            "empirical_disposition": self.empirical_disposition,
            "reason": self.reason,
            "fixture_only": True,
            "v11_authorized": False,
            "live_execution_authorized": False,
        }
