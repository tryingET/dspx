# summary: "Strict Gate-4 provider-outcome journal inspection and marker precedence."
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from dspx.services.program_oracle_semantic_identity_v11 import (
    assert_exact_reservation,
)
from dspx.services.program_oracle_semantic_gate4_contract_v11 import (
    SemanticV11Error,
    canonical,
    sha256,
)
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

_TERMINALS = {
    "pre_transport_failed",
    "remote_http_error_final",
    "provider_response_completed",
    "provider_response_failed",
    "provider_response_incomplete",
    "outcome_unresolved",
}


@dataclass(frozen=True, slots=True)
class JournalInspection:
    projection: ReceiptProjection
    observed_model: str | None
    reservation_sha256: str
    terminal_event_sha256: str | None
    journal_present: bool
    invocation_admitted: bool
    effect_capable_delegations: int
    clean_terminal_order_proven: bool

    def diagnostic_payload(self) -> dict[str, Any]:
        return {
            "provider_outcome": self.projection.payload(),
            "observed_model": self.observed_model,
            "reservation_sha256": self.reservation_sha256,
            "terminal_event_sha256": self.terminal_event_sha256,
            "journal_present": self.journal_present,
            "invocation_admitted": self.invocation_admitted,
            "effect_capable_delegations": self.effect_capable_delegations,
            "clean_terminal_order_proven": self.clean_terminal_order_proven,
            "fixture_only": True,
            "v11_authorized": False,
            "live_execution_authorized": False,
        }


def _rejected(reason: str, effect_possible: bool) -> ReceiptProjection:
    return ReceiptProjection(
        provider_outcome_receipt="rejected",
        request_acknowledged=None,
        external_effect_possible=effect_possible,
        producer_terminal=None,
        empirical_disposition="effect_indeterminate" if effect_possible else "error",
        reason=reason,
    )


def _read_reservation(root: Path) -> tuple[ReceiptReservation, str]:
    try:
        wrapper = journal_module._decode_mapping(
            journal_module._read_private(root / "reservation.json"),
            "reservation_invalid",
        )
        raw = wrapper.get("reservation")
        if (
            set(wrapper)
            != {
                "schema_version",
                "reservation_id",
                "artifact_verification",
                "reservation",
            }
            or wrapper.get("schema_version") != "dspx-provider-outcome-consumption-v1"
            or wrapper.get("artifact_verification")
            not in {"accepted_exact", "fixture_only"}
            or not isinstance(raw, Mapping)
        ):
            raise ProviderOutcomeConsumerError("reservation_schema_drift")
        reservation = journal_module._reservation_from_payload(raw)
        if wrapper.get("reservation_id") != reservation.reservation_id:
            raise ProviderOutcomeConsumerError("reservation_identity_drift")
        return reservation, cast(str, wrapper["artifact_verification"])
    except OSError as exc:
        raise ProviderOutcomeConsumerError("reservation_invalid") from exc


def _read_envelopes(root: Path, reservation: ReceiptReservation) -> tuple[Any, ...]:
    events_root = root / "events"
    journal_module._require_private(events_root, directory=True)
    try:
        members = sorted(events_root.iterdir(), key=lambda item: item.name)
    except OSError as exc:
        raise ProviderOutcomeConsumerError(
            "journal_read_failed", effect_possible=True
        ) from exc
    envelopes = []
    previous: str | None = None
    for sequence, member in enumerate(members):
        if member.name != f"{sequence:06d}.json":
            raise ProviderOutcomeConsumerError(
                "event_sequence_drift", effect_possible=True
            )
        raw = journal_module._read_private(member)
        envelope = journal_module._validate_envelope(
            raw, reservation, sequence, previous
        )
        envelopes.append(envelope)
        previous = envelope.digest
    return tuple(envelopes)


def _marker_effect(root: Path, members: set[str]) -> tuple[str | None, bool]:
    marker_names = members & {"poisoned.json", "inflight.json"}
    if not marker_names:
        return None, False
    if len(marker_names) != 1:
        return "ambiguous_journal_markers", True
    name = next(iter(marker_names))
    try:
        marker = journal_module._decode_mapping(
            journal_module._read_private(root / name), "journal_marker_invalid"
        )
    except ProviderOutcomeConsumerError:
        return "journal_marker_invalid", True
    effect = marker.get("effect_possible")
    effect_value = effect if isinstance(effect, bool) else True
    if name == "poisoned.json":
        valid = (
            set(marker) == {"schema_version", "effect_possible"}
            and marker.get("schema_version") == "dspx-provider-outcome-poison-v1"
            and isinstance(effect, bool)
        )
        return (
            "journal_poisoned" if valid else "journal_marker_invalid",
            effect_value if valid else True,
        )
    try:
        event_names = sorted(path.name for path in (root / "events").iterdir())
    except OSError:
        return "journal_marker_invalid", True
    if event_names != [f"{index:06d}.json" for index in range(len(event_names))]:
        return "journal_marker_invalid", True
    sequence = marker.get("sequence")
    lawful = {len(event_names)}
    if event_names:
        lawful.add(len(event_names) - 1)
    valid = (
        set(marker) == {"schema_version", "sequence", "effect_possible"}
        and marker.get("schema_version") == "dspx-provider-outcome-inflight-v1"
        and not isinstance(sequence, bool)
        and isinstance(sequence, int)
        and sequence in lawful
        and isinstance(effect, bool)
    )
    return (
        "journal_inflight" if valid else "journal_marker_invalid",
        effect_value if valid else True,
    )


def inspect_journal(
    root: Path,
    *,
    expected: ReceiptReservation,
    artifact: VerifiedOwnerArtifact,
    semantic_outcome: SemanticOutcome,
) -> JournalInspection:
    """Strictly inspect a journal; poison/inflight never preserves a terminal."""

    expected_digest = sha256(canonical(expected.payload()))
    if not root.exists() and not root.is_symlink():
        return JournalInspection(
            _rejected("receipt_preparation_failed_before_effect", False),
            None,
            expected_digest,
            None,
            False,
            False,
            0,
            False,
        )
    try:
        journal_module._require_private(root, directory=True)
        members = {path.name for path in root.iterdir()}
    except (OSError, ProviderOutcomeConsumerError):
        return JournalInspection(
            _rejected("journal_root_invalid", True),
            None,
            expected_digest,
            None,
            True,
            False,
            0,
            False,
        )
    marker_reason, marker_effect = _marker_effect(root, members)
    try:
        retained_event_present = any((root / "events").iterdir())
    except OSError:
        retained_event_present = "events" in members
    unknown = members - {"reservation.json", "events", "poisoned.json", "inflight.json"}
    if unknown or "events" not in members:
        return JournalInspection(
            _rejected("unexpected_journal_member", True),
            None,
            expected_digest,
            None,
            True,
            False,
            0,
            False,
        )
    try:
        observed, artifact_verification = _read_reservation(root)
        assert_exact_reservation(observed, expected)
        envelopes = _read_envelopes(root, observed)
    except (ProviderOutcomeConsumerError, SemanticV11Error):
        return JournalInspection(
            _rejected(
                "retained_reservation_or_event_drift",
                bool(marker_effect or retained_event_present),
            ),
            None,
            expected_digest,
            None,
            True,
            False,
            0,
            False,
        )
    events = [envelope.event for envelope in envelopes]
    admitted = bool(events and events[0].kind == "wrapper_request_accepted")
    delegations = sum(event.kind == "transport_entered" for event in events)
    gates = [
        event.gate_ordinal for event in events if event.kind == "transport_gate_entered"
    ]
    one_delegation = (
        sum(event.kind == "wrapper_request_accepted" for event in events) == 1
        and gates in ([], [1])
        and delegations <= 1
        and not any(event.kind == "retry_blocked_before_transport" for event in events)
    )
    effect_from_events = any(
        event.kind
        in {
            "transport_effect_pending",
            "transport_entered",
            "http_response_observed",
            "parsed_protocol_event_observed",
            *(_TERMINALS - {"pre_transport_failed"}),
        }
        for event in events
    )
    if marker_reason is not None:
        return JournalInspection(
            _rejected(marker_reason, marker_effect or effect_from_events),
            None,
            expected_digest,
            None,
            True,
            admitted,
            delegations,
            False,
        )
    if not one_delegation:
        return JournalInspection(
            _rejected("one_delegation_custody_drift", effect_from_events),
            None,
            expected_digest,
            None,
            True,
            admitted,
            delegations,
            False,
        )
    if artifact_verification != "accepted_exact" or not artifact.accepted:
        return JournalInspection(
            _rejected("fixture_journal_not_accepted", effect_from_events),
            None,
            expected_digest,
            None,
            True,
            admitted,
            delegations,
            False,
        )
    journal = VerifiedJournal(observed, envelopes, "accepted_exact")
    try:
        chain = verify_receipt_chain(journal)
        reduced = reduce_verified_chain(chain, semantic_outcome=semantic_outcome)
    except ProviderOutcomeConsumerError as exc:
        return JournalInspection(
            _rejected(exc.reason, exc.effect_possible),
            None,
            expected_digest,
            None,
            True,
            admitted,
            delegations,
            False,
        )
    terminal_envelope = envelopes[-1]
    observed_model = (
        terminal_envelope.event.observed_model
        if chain.terminal == "provider_response_completed"
        else None
    )
    projection = ReceiptProjection(
        provider_outcome_receipt="accepted",
        request_acknowledged=reduced.request_acknowledged,
        external_effect_possible=reduced.external_effect_possible,
        producer_terminal=reduced.terminal,
        empirical_disposition=reduced.empirical_disposition,
        reason=reduced.reason,
    )
    return JournalInspection(
        projection,
        observed_model,
        expected_digest,
        terminal_envelope.digest,
        True,
        admitted,
        delegations,
        True,
    )


def inspect_fixture_journal(
    root: Path,
    *,
    expected: ReceiptReservation,
    artifact: VerifiedOwnerArtifact,
    semantic_outcome: SemanticOutcome = "not_evaluated",
) -> dict[str, Any]:
    """Authority-false hostile-test diagnostic over the production inspector."""

    return inspect_journal(
        root,
        expected=expected,
        artifact=artifact,
        semantic_outcome=semantic_outcome,
    ).diagnostic_payload()
