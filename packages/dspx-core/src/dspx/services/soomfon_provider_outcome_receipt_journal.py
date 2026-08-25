# summary: "Private no-replace Soomfon v2 exact-status receipt journal."
from __future__ import annotations

import json
import os
import stat
import threading
from pathlib import Path
from typing import Any, Literal, Mapping, cast

from dspx.services.soomfon_provider_outcome_receipt_contract import (
    MAX_EVENT_BYTES,
    MAX_EVENTS,
    ClosedOwnerEvent,
    JournalEnvelope,
    ProviderOutcomeConsumerError,
    ReceiptReservation,
    VerifiedJournal,
    canonical_json,
    event_envelope_payload,
    sha256,
)
from dspx.services.soomfon_provider_outcome_receipt_identity import (
    VerifiedOwnerArtifact,
)

_RESERVATION_NAME = "reservation.json"
_EVENTS_NAME = "events"
_POISON_NAME = "poisoned.json"
_INFLIGHT_NAME = "inflight.json"
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
_EFFECT_KINDS = frozenset(
    {
        "transport_effect_pending",
        "transport_entered",
        "http_response_observed",
        "parsed_protocol_event_observed",
        *_TERMINALS - {"pre_transport_failed"},
    }
)


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        fd = os.open(path, flags)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError as exc:
        raise ProviderOutcomeConsumerError("directory_sync_failed") from exc


def _write_file(path: Path, raw: bytes, *, sync_parent: bool = True) -> None:
    if not raw or len(raw) > MAX_EVENT_BYTES:
        raise ProviderOutcomeConsumerError("journal_member_size_drift")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags, 0o600)
        try:
            os.fchmod(fd, 0o600)
            view = memoryview(raw)
            while view:
                written = os.write(fd, view)
                if written <= 0:
                    raise OSError("short write")
                view = view[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
        if sync_parent:
            _fsync_directory(path.parent)
    except FileExistsError as exc:
        raise ProviderOutcomeConsumerError("journal_member_exists") from exc
    except ProviderOutcomeConsumerError:
        raise
    except OSError as exc:
        raise ProviderOutcomeConsumerError("journal_persistence_failed") from exc


def _write_poison(root: Path, effect_possible: bool) -> None:
    raw = canonical_json(
        {
            "schema_version": "dspx-provider-outcome-poison-v1",
            "effect_possible": effect_possible,
        }
    )
    path = root / _POISON_NAME
    if path.exists() or path.is_symlink():
        return
    try:
        _write_file(path, raw)
    except BaseException:
        return


def _write_inflight(root: Path, sequence: int, effect_possible: bool) -> None:
    _write_file(
        root / _INFLIGHT_NAME,
        canonical_json(
            {
                "schema_version": "dspx-provider-outcome-inflight-v1",
                "sequence": sequence,
                "effect_possible": effect_possible,
            }
        ),
    )


def _clear_inflight(root: Path) -> None:
    try:
        (root / _INFLIGHT_NAME).unlink()
        _fsync_directory(root)
    except OSError as exc:
        raise ProviderOutcomeConsumerError("inflight_cleanup_failed") from exc


def _require_private(path: Path, *, directory: bool) -> None:
    try:
        info = path.lstat()
    except OSError as exc:
        raise ProviderOutcomeConsumerError("journal_member_missing") from exc
    expected = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if (
        not expected
        or path.is_symlink()
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != (0o700 if directory else 0o600)
        or (not directory and info.st_nlink != 1)
    ):
        raise ProviderOutcomeConsumerError("journal_member_posture_drift")


def _read_private(path: Path) -> bytes:
    _require_private(path, directory=False)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ProviderOutcomeConsumerError("journal_read_failed") from exc
    if not raw or len(raw) > MAX_EVENT_BYTES:
        raise ProviderOutcomeConsumerError("journal_member_size_drift")
    return raw


def _decode_mapping(raw: bytes, reason: str) -> Mapping[str, Any]:
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise ProviderOutcomeConsumerError(reason, effect_possible=True) from exc
    if not isinstance(value, Mapping) or canonical_json(value) != raw:
        raise ProviderOutcomeConsumerError(reason, effect_possible=True)
    return value


def _reservation_from_payload(value: Mapping[str, Any]) -> ReceiptReservation:
    keys = {
        "schema_version",
        "consumer_task_id",
        "ledger_sha256",
        "process_id",
        "case_id",
        "logical_request_id",
        "transport_gate_id",
        "semantic_request_sha256",
        "contract_sha256",
        "mode",
        "requested_route",
        "resolved_route",
        "endpoint_origin_sha256",
        "source_identity",
        "dependency_identity",
    }
    if (
        set(value) != keys
        or value.get("schema_version") != "dspx-provider-outcome-reservation-v1"
    ):
        raise ProviderOutcomeConsumerError("reservation_schema_drift")
    reservation = ReceiptReservation(
        consumer_task_id=cast(int, value["consumer_task_id"]),
        ledger_sha256=cast(str, value["ledger_sha256"]),
        process_id=cast(str, value["process_id"]),
        case_id=cast(str, value["case_id"]),
        logical_request_id=cast(str, value["logical_request_id"]),
        transport_gate_id=cast(str, value["transport_gate_id"]),
        semantic_request_sha256=cast(str, value["semantic_request_sha256"]),
        contract_sha256=cast(str, value["contract_sha256"]),
        mode=cast(Literal["sync", "async"], value["mode"]),
        requested_route=cast(str, value["requested_route"]),
        resolved_route=cast(str, value["resolved_route"]),
        endpoint_origin_sha256=cast(str, value["endpoint_origin_sha256"]),
        source_identity=cast(Mapping[str, Any], value["source_identity"]),
        dependency_identity=cast(Mapping[str, Any], value["dependency_identity"]),
    )
    if reservation.payload() != value:
        raise ProviderOutcomeConsumerError("reservation_schema_drift")
    return reservation


def _validate_envelope(
    raw: bytes,
    reservation: ReceiptReservation,
    sequence: int,
    previous: str | None,
) -> JournalEnvelope:
    value = _decode_mapping(raw, "event_envelope_invalid")
    keys = {
        "schema_version",
        "reservation_id",
        "sequence",
        "previous_event_sha256",
        "producer",
        "source_identity_sha256",
        "dependency_identity_sha256",
        "event",
    }
    event_raw = value.get("event")
    if set(value) != keys or not isinstance(event_raw, Mapping):
        raise ProviderOutcomeConsumerError(
            "event_envelope_schema_drift", effect_possible=True
        )
    try:
        event = ClosedOwnerEvent.from_mapping(event_raw)
    except ProviderOutcomeConsumerError as exc:
        raise ProviderOutcomeConsumerError(exc.reason, effect_possible=True) from exc
    if value != event_envelope_payload(reservation, sequence, previous, event):
        raise ProviderOutcomeConsumerError(
            "event_envelope_binding_drift", effect_possible=True
        )
    return JournalEnvelope(sequence, previous, event, raw, sha256(raw))


class ReceiptJournal:
    """Consumer-owned journal; only the paired owner receipt sees its sink."""

    def __init__(
        self,
        root: Path,
        reservation: ReceiptReservation,
        artifact: VerifiedOwnerArtifact,
    ) -> None:
        self._root = root
        self._events = root / _EVENTS_NAME
        self._reservation = reservation
        self._artifact = artifact
        self._lock = threading.Lock()
        self._next_sequence = 0
        self._previous: str | None = None
        self._terminal_seen = False
        self._poisoned = False
        self._effect_possible = False
        self._receipt_issued = False

    @classmethod
    def create(
        cls,
        root: Path,
        reservation: ReceiptReservation,
        artifact: VerifiedOwnerArtifact,
    ) -> "ReceiptJournal":
        artifact.revalidate()
        if (
            reservation.source_identity != artifact.source_identity
            or reservation.dependency_identity != artifact.dependency_identity
        ):
            raise ProviderOutcomeConsumerError("reservation_artifact_identity_drift")
        target = root.expanduser()
        try:
            if target.is_symlink() or not target.parent.resolve(strict=True).is_dir():
                raise ProviderOutcomeConsumerError("journal_root_posture_drift")
            os.mkdir(target, 0o700)
            os.chmod(target, 0o700)
            os.mkdir(target / _EVENTS_NAME, 0o700)
            os.chmod(target / _EVENTS_NAME, 0o700)
            _fsync_directory(target)
            _fsync_directory(target.parent)
        except FileExistsError as exc:
            raise ProviderOutcomeConsumerError("journal_root_exists") from exc
        except ProviderOutcomeConsumerError:
            raise
        except OSError as exc:
            raise ProviderOutcomeConsumerError("journal_root_create_failed") from exc
        wrapper = {
            "schema_version": "dspx-soomfon-provider-outcome-consumption-v2",
            "reservation_id": reservation.reservation_id,
            "artifact_verification": (
                "accepted_exact" if artifact.accepted else "fixture_only"
            ),
            "reservation": reservation.payload(),
        }
        _write_file(target / _RESERVATION_NAME, canonical_json(wrapper))
        return cls(target, reservation, artifact)

    def provider_receipt(self) -> object:
        if not self._lock.acquire(blocking=False):
            raise ProviderOutcomeConsumerError("concurrent_receipt_issue")
        try:
            if self._poisoned or self._receipt_issued:
                raise ProviderOutcomeConsumerError("receipt_capability_already_issued")
            self._artifact.revalidate()
            sink = self._append_owner_event
            try:
                receipt = self._artifact.receipt_type(
                    logical_request_id=self._reservation.logical_request_id,
                    semantic_request_sha256=self._reservation.semantic_request_sha256,
                    sink=sink,
                )
            except BaseException:
                self._poisoned = True
                _write_poison(self._root, False)
                raise
            if (
                type(receipt) is not self._artifact.receipt_type
                or getattr(receipt, "logical_request_id", None)
                != self._reservation.logical_request_id
                or getattr(receipt, "semantic_request_sha256", None)
                != self._reservation.semantic_request_sha256
                or getattr(receipt, "sink", None) is not sink
            ):
                self._poisoned = True
                _write_poison(self._root, False)
                raise ProviderOutcomeConsumerError("owner_receipt_capability_drift")
            self._receipt_issued = True
            return receipt
        finally:
            self._lock.release()

    def _append_owner_event(self, owner_event: object) -> None:
        if not self._lock.acquire(blocking=False):
            self._poisoned = True
            _write_poison(self._root, self._effect_possible)
            raise ProviderOutcomeConsumerError(
                "concurrent_sink_invocation", effect_possible=self._effect_possible
            )
        try:
            if self._poisoned or not self._receipt_issued:
                raise ProviderOutcomeConsumerError(
                    "journal_not_writable", effect_possible=self._effect_possible
                )
            if self._terminal_seen or self._next_sequence >= MAX_EVENTS:
                self._poisoned = True
                _write_poison(self._root, self._effect_possible)
                raise ProviderOutcomeConsumerError(
                    "event_after_terminal"
                    if self._terminal_seen
                    else "event_budget_exceeded",
                    effect_possible=self._effect_possible,
                )
            possible = self._effect_possible
            try:
                self._artifact.revalidate()
                event = ClosedOwnerEvent.from_owner(
                    owner_event, exact_type=self._artifact.event_type
                )
                possible = possible or event.kind in _EFFECT_KINDS
                raw = canonical_json(
                    event_envelope_payload(
                        self._reservation,
                        self._next_sequence,
                        self._previous,
                        event,
                    )
                )
            except BaseException:
                self._poisoned = True
                _write_poison(self._root, possible)
                raise
            try:
                _write_inflight(self._root, self._next_sequence, possible)
            except BaseException:
                self._poisoned = True
                _write_poison(self._root, possible)
                raise
            try:
                _write_file(self._events / f"{self._next_sequence:06d}.json", raw)
                _clear_inflight(self._root)
            except BaseException:
                self._poisoned = True
                raise
            self._previous = sha256(raw)
            self._next_sequence += 1
            self._effect_possible = possible
            self._terminal_seen = event.kind in _TERMINALS
        finally:
            self._lock.release()

    def load_verified(self) -> VerifiedJournal:
        if self._poisoned:
            raise ProviderOutcomeConsumerError(
                "journal_poisoned", effect_possible=self._effect_possible
            )
        return load_verified_journal(self._root)


def load_verified_journal(root: Path) -> VerifiedJournal:
    target = root.expanduser()
    _require_private(target, directory=True)
    try:
        members_by_name = {path.name: path for path in target.iterdir()}
    except OSError as exc:
        raise ProviderOutcomeConsumerError(
            "journal_read_failed", effect_possible=True
        ) from exc
    marker_name = next(
        (name for name in (_POISON_NAME, _INFLIGHT_NAME) if name in members_by_name),
        None,
    )
    if marker_name is not None:
        marker = _decode_mapping(
            _read_private(members_by_name[marker_name]), "journal_marker_invalid"
        )
        effect = marker.get("effect_possible")
        if not isinstance(effect, bool):
            effect = True
        raise ProviderOutcomeConsumerError(
            "journal_poisoned" if marker_name == _POISON_NAME else "journal_inflight",
            effect_possible=effect,
        )
    if set(members_by_name) != {_RESERVATION_NAME, _EVENTS_NAME}:
        raise ProviderOutcomeConsumerError(
            "unexpected_journal_member", effect_possible=True
        )
    events_dir = members_by_name[_EVENTS_NAME]
    _require_private(events_dir, directory=True)
    try:
        event_members = sorted(events_dir.iterdir(), key=lambda path: path.name)
    except OSError as exc:
        raise ProviderOutcomeConsumerError(
            "journal_read_failed", effect_possible=True
        ) from exc
    if len(event_members) > MAX_EVENTS:
        raise ProviderOutcomeConsumerError(
            "event_budget_exceeded", effect_possible=True
        )
    try:
        wrapper = _decode_mapping(
            _read_private(members_by_name[_RESERVATION_NAME]), "reservation_invalid"
        )
        reservation_raw = wrapper.get("reservation")
        artifact_verification = wrapper.get("artifact_verification")
        if (
            set(wrapper)
            != {
                "schema_version",
                "reservation_id",
                "artifact_verification",
                "reservation",
            }
            or wrapper.get("schema_version")
            != "dspx-soomfon-provider-outcome-consumption-v2"
            or artifact_verification not in {"accepted_exact", "fixture_only"}
            or not isinstance(reservation_raw, Mapping)
        ):
            raise ProviderOutcomeConsumerError("reservation_schema_drift")
        reservation = _reservation_from_payload(reservation_raw)
        if wrapper.get("reservation_id") != reservation.reservation_id:
            raise ProviderOutcomeConsumerError("reservation_identity_drift")
    except ProviderOutcomeConsumerError as exc:
        raise ProviderOutcomeConsumerError(
            exc.reason, effect_possible=bool(event_members)
        ) from exc
    envelopes: list[JournalEnvelope] = []
    previous: str | None = None
    for sequence, path in enumerate(event_members):
        if path.name != f"{sequence:06d}.json":
            raise ProviderOutcomeConsumerError(
                "event_sequence_drift", effect_possible=True
            )
        try:
            raw = _read_private(path)
            envelope = _validate_envelope(raw, reservation, sequence, previous)
        except ProviderOutcomeConsumerError as exc:
            raise ProviderOutcomeConsumerError(
                exc.reason, effect_possible=True
            ) from exc
        envelopes.append(envelope)
        previous = envelope.digest
    return VerifiedJournal(
        reservation,
        tuple(envelopes),
        cast(Literal["accepted_exact", "fixture_only"], artifact_verification),
    )
