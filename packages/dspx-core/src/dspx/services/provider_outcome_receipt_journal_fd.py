# summary: "Descriptor-native verification for retained provider outcome journals."
from __future__ import annotations

import os
import stat
from collections.abc import Mapping
from typing import Literal, cast

from dspx.services.provider_outcome_receipt_contract import (
    MAX_EVENT_BYTES,
    MAX_EVENTS,
    JournalEnvelope,
    ProviderOutcomeConsumerError,
    VerifiedJournal,
)
from dspx.services.provider_outcome_receipt_journal import (
    _EVENTS_NAME,
    _INFLIGHT_NAME,
    _POISON_NAME,
    _RESERVATION_NAME,
    _decode_mapping,
    _reservation_from_payload,
    _validate_envelope,
)


def _same_inode(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        left.st_dev,
        left.st_ino,
        left.st_mode,
        left.st_uid,
        left.st_nlink,
        left.st_size,
        left.st_mtime_ns,
        left.st_ctime_ns,
    ) == (
        right.st_dev,
        right.st_ino,
        right.st_mode,
        right.st_uid,
        right.st_nlink,
        right.st_size,
        right.st_mtime_ns,
        right.st_ctime_ns,
    )


def _require_private_directory(info: os.stat_result) -> None:
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise ProviderOutcomeConsumerError("journal_member_posture_drift")


def _open_directory_at(parent_fd: int, name: str) -> tuple[int, os.stat_result]:
    flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
    fd = -1
    try:
        lexical = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        fd = os.open(name, flags, dir_fd=parent_fd)
        opened = os.fstat(fd)
    except OSError as exc:
        if fd >= 0:
            os.close(fd)
        raise ProviderOutcomeConsumerError("journal_member_missing") from exc
    try:
        _require_private_directory(lexical)
        if not _same_inode(lexical, opened):
            raise ProviderOutcomeConsumerError("journal_member_posture_drift")
    except BaseException:
        os.close(fd)
        raise
    return fd, lexical


def _read_file_at(parent_fd: int, name: str) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = -1
    try:
        lexical = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        fd = os.open(name, flags, dir_fd=parent_fd)
        before = os.fstat(fd)
        raw = os.read(fd, MAX_EVENT_BYTES + 1)
        after = os.fstat(fd)
        final = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as exc:
        raise ProviderOutcomeConsumerError("journal_read_failed") from exc
    finally:
        if fd >= 0:
            os.close(fd)
    if (
        not stat.S_ISREG(lexical.st_mode)
        or lexical.st_uid != os.geteuid()
        or stat.S_IMODE(lexical.st_mode) != 0o600
        or lexical.st_nlink != 1
        or not _same_inode(lexical, before)
        or not _same_inode(before, after)
        or not _same_inode(after, final)
        or (lexical.st_nlink, lexical.st_size, lexical.st_mtime_ns)
        != (before.st_nlink, before.st_size, before.st_mtime_ns)
        or (before.st_nlink, before.st_size, before.st_mtime_ns)
        != (after.st_nlink, after.st_size, after.st_mtime_ns)
        or (after.st_nlink, after.st_size, after.st_mtime_ns)
        != (final.st_nlink, final.st_size, final.st_mtime_ns)
        or len(raw) != before.st_size
        or not raw
        or len(raw) > MAX_EVENT_BYTES
    ):
        raise ProviderOutcomeConsumerError("journal_member_posture_drift")
    return raw


def _list_directory_at(directory_fd: int) -> tuple[str, ...]:
    positioned_fd, _info = _open_directory_at(directory_fd, ".")
    try:
        return tuple(sorted(os.listdir(positioned_fd)))
    except OSError as exc:
        raise ProviderOutcomeConsumerError(
            "journal_read_failed", effect_possible=True
        ) from exc
    finally:
        os.close(positioned_fd)


def load_verified_journal_fd(root_fd: int) -> VerifiedJournal:
    """Load one retained journal without converting its authoritative fd to a path."""

    if isinstance(root_fd, bool) or not isinstance(root_fd, int):
        raise ProviderOutcomeConsumerError("journal_member_posture_drift")
    verification_fd = -1
    events_fd = -1
    try:
        root_info = os.fstat(root_fd)
        _require_private_directory(root_info)
        verification_fd, verification_info = _open_directory_at(root_fd, ".")
        if not _same_inode(root_info, verification_info):
            raise ProviderOutcomeConsumerError("journal_member_posture_drift")
        names = set(_list_directory_at(verification_fd))
        marker_name = next(
            (name for name in (_POISON_NAME, _INFLIGHT_NAME) if name in names), None
        )
        if marker_name is not None:
            marker = _decode_mapping(
                _read_file_at(verification_fd, marker_name), "journal_marker_invalid"
            )
            effect = marker.get("effect_possible")
            raise ProviderOutcomeConsumerError(
                "journal_poisoned"
                if marker_name == _POISON_NAME
                else "journal_inflight",
                effect_possible=effect if isinstance(effect, bool) else True,
            )
        if names != {_RESERVATION_NAME, _EVENTS_NAME}:
            raise ProviderOutcomeConsumerError(
                "unexpected_journal_member", effect_possible=True
            )
        events_fd, events_info = _open_directory_at(verification_fd, _EVENTS_NAME)
        event_names = list(_list_directory_at(events_fd))
        if len(event_names) > MAX_EVENTS:
            raise ProviderOutcomeConsumerError(
                "event_budget_exceeded", effect_possible=True
            )
        try:
            reservation_bytes = _read_file_at(verification_fd, _RESERVATION_NAME)
            wrapper = _decode_mapping(reservation_bytes, "reservation_invalid")
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
                != "dspx-provider-outcome-consumption-v1"
                or artifact_verification not in {"accepted_exact", "fixture_only"}
                or not isinstance(reservation_raw, Mapping)
            ):
                raise ProviderOutcomeConsumerError("reservation_schema_drift")
            reservation = _reservation_from_payload(reservation_raw)
            if wrapper.get("reservation_id") != reservation.reservation_id:
                raise ProviderOutcomeConsumerError("reservation_identity_drift")
        except ProviderOutcomeConsumerError as exc:
            raise ProviderOutcomeConsumerError(
                exc.reason, effect_possible=bool(event_names)
            ) from exc
        envelopes: list[JournalEnvelope] = []
        event_bytes: list[bytes] = []
        previous: str | None = None
        for sequence, name in enumerate(event_names):
            if name != f"{sequence:06d}.json":
                raise ProviderOutcomeConsumerError(
                    "event_sequence_drift", effect_possible=True
                )
            try:
                raw = _read_file_at(events_fd, name)
                envelope = _validate_envelope(raw, reservation, sequence, previous)
            except ProviderOutcomeConsumerError as exc:
                raise ProviderOutcomeConsumerError(
                    exc.reason, effect_possible=True
                ) from exc
            envelopes.append(envelope)
            event_bytes.append(raw)
            previous = envelope.digest
        try:
            if (
                set(_list_directory_at(verification_fd)) != names
                or list(_list_directory_at(events_fd)) != event_names
                or _read_file_at(verification_fd, _RESERVATION_NAME)
                != reservation_bytes
                or any(
                    _read_file_at(events_fd, name) != expected
                    for name, expected in zip(event_names, event_bytes, strict=True)
                )
                or not _same_inode(events_info, os.fstat(events_fd))
                or not _same_inode(root_info, os.fstat(root_fd))
                or not _same_inode(verification_info, os.fstat(verification_fd))
            ):
                raise ProviderOutcomeConsumerError(
                    "journal_member_posture_drift", effect_possible=True
                )
        except ProviderOutcomeConsumerError as exc:
            raise ProviderOutcomeConsumerError(
                exc.reason, effect_possible=bool(event_names)
            ) from exc
        return VerifiedJournal(
            reservation,
            tuple(envelopes),
            cast(Literal["accepted_exact", "fixture_only"], artifact_verification),
        )
    finally:
        try:
            if events_fd >= 0:
                os.close(events_fd)
        finally:
            if verification_fd >= 0:
                os.close(verification_fd)


__all__ = ["load_verified_journal_fd"]
