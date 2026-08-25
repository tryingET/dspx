"""Soomfon-only dspy-lm-auth call custody and closed provider evidence."""

from __future__ import annotations

import os
import stat
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, NoReturn, TypeVar

from dspx.services.provider_outcome_receipt_contract import (
    ProviderOutcomeConsumerError,
    ReceiptReservation,
    VerifiedJournal,
    canonical_json,
    sha256,
)
from dspx.services.provider_outcome_receipt_identity import (
    VerifiedOwnerArtifact,
)
from dspx.services.provider_outcome_receipt_journal import (
    ReceiptJournal,
    load_verified_journal,
)
from dspx.services.provider_outcome_receipt_journal_fd import (
    load_verified_journal_fd,
)
from dspx.services.soomfon_evaluation_contract import CONTRACT_PREPARATION_TASK_ID
from dspx.services.provider_outcome_receipt_reducer import (
    reduce_verified_chain,
    verify_receipt_chain,
)
from dspx.services.soomfon_evaluation_owner import (
    AUTH_PROVIDER as AUTH_PROVIDER,
    CREDENTIAL_MODE as CREDENTIAL_MODE,
    ENDPOINT_ORIGIN_SHA256,
    MAX_SUITE_LOGICAL_CALLS as MAX_SUITE_LOGICAL_CALLS,
    OBSERVED_MODEL as OBSERVED_MODEL,
    OWNER_CANDIDATE_INSTALLED_PAYLOAD_SHA256 as OWNER_CANDIDATE_INSTALLED_PAYLOAD_SHA256,
    OWNER_CANDIDATE_WHEEL_SHA256 as OWNER_CANDIDATE_WHEEL_SHA256,
    REASONING_EFFORT as REASONING_EFFORT,
    REQUESTED_MODEL as REQUESTED_MODEL,
    REQUESTED_ROUTE,
    RESOLVED_MODEL as RESOLVED_MODEL,
    RESOLVED_ROUTE,
    SOOMFON_OWNER_SOURCE as SOOMFON_OWNER_SOURCE,
    TIMEOUT_SECONDS as TIMEOUT_SECONDS,
    VerifiedSoomfonOwner as VerifiedSoomfonOwner,
    expected_owner_dependency_identity,
    expected_owner_source_identity,
    owner_authorization_identity as owner_authorization_identity,
    verify_loaded_soomfon_owner as verify_loaded_soomfon_owner,
    verify_soomfon_owner_source as verify_soomfon_owner_source,
)

_MODE_SIGNATURES: dict[str, tuple[str, str]] = {
    "simple": ("DefinePersona", "AnswerSimple"),
    "elaborate": ("DefinePersona", "AnswerElaborate"),
    "researched": ("DefinePersona", "AnswerResearched"),
    "deep-research": ("DefinePersona", "SynthesizeDeepResearch"),
    "socratic": ("DefinePersona", "GuideSocratically"),
    "bloom": ("DefinePersona", "TeachWithBloom"),
}
_SHA256_RE = __import__("re").compile(r"^[0-9a-f]{64}$")
_CLOSED_RETAINED_JOURNAL_REASONS = frozenset(
    {
        "journal_parent_fd_invalid",
        "journal_parent_posture_drift",
        "retained_journal_read_failed",
        "retained_journal_member_name_drift",
        "retained_journal_member_posture_drift",
        "retained_journal_acceptance_drift",
        "retained_journal_count_drift",
        "retained_journal_binding_drift",
        "retained_journal_member_identity_drift",
        "retained_journal_parent_identity_drift",
    }
)
T = TypeVar("T")


def logical_signature_name(signature: type[Any], *, mode: str) -> str:
    if mode not in _MODE_SIGNATURES:
        _reject("unknown_mode")
    outputs = set(getattr(signature, "output_fields", {}))
    if outputs == {"persona"}:
        return "DefinePersona"
    if "response" in outputs and outputs <= {"reasoning", "response"}:
        return _MODE_SIGNATURES[mode][1]
    _reject("logical_signature_shape_drift")


class SoomfonProviderError(RuntimeError):
    """Fixed-message Soomfon provider-custody rejection."""

    def __init__(
        self, reason: str, message: str = "Soomfon provider custody rejected"
    ) -> None:
        super().__init__(message)
        self.reason = reason


def _reject(
    reason: str, message: str = "Soomfon provider custody rejected"
) -> NoReturn:
    raise SoomfonProviderError(reason, message)


def _private_directory(path: Path) -> Path:
    try:
        info = path.lstat()
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise SoomfonProviderError("journal_parent_unavailable") from exc
    if (
        path.is_symlink()
        or not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) != 0o700
        or resolved != path.absolute()
    ):
        _reject("journal_parent_posture_drift")
    return resolved


def _fd_private_directory_members(
    directory_fd: int,
) -> tuple[int, list[tuple[Path, os.stat_result]], os.stat_result, os.stat_result]:
    """Open an independently positioned fd for stable member verification."""

    if isinstance(directory_fd, bool) or not isinstance(directory_fd, int):
        _reject("journal_parent_fd_invalid")
    verification_fd = -1
    flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
    try:
        parent_info = os.fstat(directory_fd)
        verification_fd = os.open(".", flags, dir_fd=directory_fd)
        verification_info = os.fstat(verification_fd)
        names = sorted(os.listdir(verification_fd))
    except OSError as exc:
        if verification_fd >= 0:
            os.close(verification_fd)
        raise SoomfonProviderError("retained_journal_read_failed") from exc
    if (
        not stat.S_ISDIR(parent_info.st_mode)
        or parent_info.st_uid != os.geteuid()
        or stat.S_IMODE(parent_info.st_mode) != 0o700
        or not _same_inode(parent_info, verification_info)
    ):
        os.close(verification_fd)
        _reject("journal_parent_posture_drift")
    members: list[tuple[Path, os.stat_result]] = []
    try:
        for name in names:
            if not name or name in {".", ".."} or "/" in name:
                _reject("retained_journal_member_name_drift")
            try:
                info = os.stat(name, dir_fd=verification_fd, follow_symlinks=False)
            except OSError as exc:
                raise SoomfonProviderError("retained_journal_read_failed") from exc
            if (
                not stat.S_ISDIR(info.st_mode)
                or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o700
            ):
                _reject("retained_journal_member_posture_drift")
            members.append((Path(f"/proc/self/fd/{verification_fd}") / name, info))
    except BaseException:
        os.close(verification_fd)
        raise
    return verification_fd, members, parent_info, verification_info


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


def _revalidate_fd_directory_members(
    directory_fd: int, expected: list[tuple[Path, os.stat_result]]
) -> None:
    recheck_fd = -1
    try:
        recheck_fd, observed, _parent, _verification = _fd_private_directory_members(
            directory_fd
        )
        if [path.name for path, _info in observed] != [
            path.name for path, _info in expected
        ] or any(
            not _same_inode(expected_info, observed_info)
            for (_expected_path, expected_info), (_observed_path, observed_info) in zip(
                expected, observed, strict=True
            )
        ):
            _reject("retained_journal_member_identity_drift")
    finally:
        if recheck_fd >= 0:
            os.close(recheck_fd)


def closed_retained_journal_reason(exc: BaseException) -> str:
    """Reduce retained-verification failures to a non-sensitive closed reason."""

    if (
        isinstance(exc, SoomfonProviderError)
        and exc.reason in _CLOSED_RETAINED_JOURNAL_REASONS
    ):
        return exc.reason
    return "retained_journal_verification_failed"


def _load_fd_anchored_journal(
    parent_fd: int, name: str, expected_info: os.stat_result
) -> VerifiedJournal:
    flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
    journal_fd = -1
    try:
        lexical_before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        journal_fd = os.open(name, flags, dir_fd=parent_fd)
        opened_before = os.fstat(journal_fd)
        if not _same_inode(expected_info, lexical_before) or not _same_inode(
            lexical_before, opened_before
        ):
            _reject("retained_journal_member_identity_drift")
        journal = load_verified_journal_fd(journal_fd)
        opened_after = os.fstat(journal_fd)
        lexical_after = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if not _same_inode(opened_before, opened_after) or not _same_inode(
            opened_after, lexical_after
        ):
            _reject("retained_journal_member_identity_drift")
        return journal
    except SoomfonProviderError:
        raise
    except OSError as exc:
        raise SoomfonProviderError("retained_journal_read_failed") from exc
    finally:
        if journal_fd >= 0:
            os.close(journal_fd)


def _journal_projection_digest(journal: VerifiedJournal) -> str:
    return sha256(
        canonical_json(
            {
                "reservation_id": journal.reservation.reservation_id,
                "event_sha256": [event.digest for event in journal.events],
                "artifact_verification": journal.artifact_verification,
            }
        )
    )


class SoomfonCallCustodian:
    """Exactly two ordered sync LM calls with one owner receipt journal each."""

    def __init__(
        self,
        *,
        journal_parent: Path,
        artifact: VerifiedOwnerArtifact,
        execution_task_id: int,
        contract_sha256: str,
        mode: str,
        ledger_sha256: str,
        authority_revalidator: Callable[[], None],
    ) -> None:
        if mode not in _MODE_SIGNATURES:
            _reject("unknown_mode")
        if (
            type(artifact) is not VerifiedOwnerArtifact
            or isinstance(execution_task_id, bool)
            or not isinstance(execution_task_id, int)
            or execution_task_id <= CONTRACT_PREPARATION_TASK_ID
            or _SHA256_RE.fullmatch(contract_sha256) is None
            or _SHA256_RE.fullmatch(ledger_sha256) is None
            or not callable(authority_revalidator)
        ):
            _reject("call_custody_identity_drift")
        artifact.revalidate()
        self._journal_parent = _private_directory(journal_parent)
        self._artifact = artifact
        self._execution_task_id = execution_task_id
        self._contract_sha256 = contract_sha256
        self._mode = mode
        self._ledger_sha256 = ledger_sha256
        self._authority_revalidator = authority_revalidator
        self._records: list[dict[str, object]] = []
        self._terminal = False

    def _reservation(
        self, ordinal: int, semantic_request_sha256: str
    ) -> ReceiptReservation:
        logical = sha256(
            b"dspx-soomfon-logical-request-v1\0"
            + canonical_json(
                {
                    "contract_sha256": self._contract_sha256,
                    "mode": self._mode,
                    "ordinal": ordinal,
                    "execution_task_id": self._execution_task_id,
                }
            )
        )
        gate = sha256(
            b"dspx-soomfon-transport-gate-v1\0"
            + canonical_json({"logical_request_id": logical, "gate_ordinal": 1})
        )
        process = sha256(
            b"dspx-soomfon-process-v1\0"
            + canonical_json(
                {
                    "contract_sha256": self._contract_sha256,
                    "ledger_sha256": self._ledger_sha256,
                    "mode": self._mode,
                }
            )
        )
        return ReceiptReservation(
            consumer_task_id=self._execution_task_id,
            ledger_sha256=self._ledger_sha256,
            process_id=process,
            case_id=self._mode,
            logical_request_id=logical,
            transport_gate_id=gate,
            semantic_request_sha256=semantic_request_sha256,
            contract_sha256=self._contract_sha256,
            mode="sync",
            requested_route=REQUESTED_ROUTE,
            resolved_route=RESOLVED_ROUTE,
            endpoint_origin_sha256=ENDPOINT_ORIGIN_SHA256,
            source_identity=self._artifact.source_identity,
            dependency_identity=self._artifact.dependency_identity,
        )

    def _record_rejection(
        self,
        *,
        ordinal: int,
        signature_name: str,
        reason: str,
        effect_possible: bool,
        journal: VerifiedJournal | None,
    ) -> None:
        self._records.append(
            {
                "call_ordinal": ordinal,
                "signature_name": signature_name,
                "reservation_id": (
                    journal.reservation.reservation_id if journal is not None else None
                ),
                "journal_sha256": (
                    _journal_projection_digest(journal) if journal is not None else None
                ),
                "provider_outcome_receipt": "rejected",
                "request_acknowledged": None,
                "external_effect_possible": effect_possible,
                "producer_terminal": None,
                "empirical_disposition": (
                    "effect_indeterminate" if effect_possible else "error"
                ),
                "reason": reason,
            }
        )
        self._terminal = True

    def invoke(
        self,
        *,
        signature_name: str,
        semantic_request_sha256: str,
        invoke: Callable[[object], T],
    ) -> T:
        ordinal = len(self._records) + 1
        expected = _MODE_SIGNATURES[self._mode]
        if (
            self._terminal
            or ordinal > 2
            or signature_name != expected[ordinal - 1]
            or _SHA256_RE.fullmatch(semantic_request_sha256) is None
        ):
            _reject("logical_call_order_drift")
        try:
            self._authority_revalidator()
        except BaseException:
            self._terminal = True
            raise SoomfonProviderError("canonical_authority_invalid") from None
        self._artifact.revalidate()
        reservation = self._reservation(ordinal, semantic_request_sha256)
        root = self._journal_parent / f"{ordinal:02d}-{reservation.logical_request_id}"
        journal = ReceiptJournal.create(root, reservation, self._artifact)
        receipt = journal.provider_receipt()
        result: T
        invocation_error: BaseException | None = None
        try:
            result = invoke(receipt)
        except BaseException as exc:
            invocation_error = exc
        loaded: VerifiedJournal | None = None
        chain_effect_possible = False
        try:
            loaded = journal.load_verified()
            chain = verify_receipt_chain(loaded)
            chain_effect_possible = chain.external_effect_possible
            reduced = reduce_verified_chain(chain)
            if (
                loaded.artifact_verification not in {"accepted_exact", "fixture_only"}
                or reduced.terminal != "provider_response_completed"
                or reduced.request_acknowledged is not True
                or reduced.external_effect_possible is not True
                or reduced.reason != "attributable_completion_not_evaluated"
            ):
                raise ProviderOutcomeConsumerError(
                    "attributable_completion_required",
                    effect_possible=reduced.external_effect_possible,
                )
            self._artifact.revalidate()
        except ProviderOutcomeConsumerError as exc:
            self._record_rejection(
                ordinal=ordinal,
                signature_name=signature_name,
                reason=exc.reason,
                effect_possible=exc.effect_possible or chain_effect_possible,
                journal=loaded,
            )
            raise SoomfonProviderError(
                "receipt_chain_rejected", "Soomfon provider receipt rejected"
            ) from None
        self._records.append(
            {
                "call_ordinal": ordinal,
                "signature_name": signature_name,
                "reservation_id": reservation.reservation_id,
                "journal_sha256": _journal_projection_digest(loaded),
                "provider_outcome_receipt": "accepted",
                "request_acknowledged": True,
                "external_effect_possible": True,
                "producer_terminal": "provider_response_completed",
                "empirical_disposition": "not_evaluated",
                "reason": "attributable_completion_not_evaluated",
            }
        )
        if invocation_error is not None:
            self._terminal = True
            raise SoomfonProviderError(
                "provider_invocation_failed", "Soomfon provider invocation failed"
            ) from None
        return result

    def evidence(self) -> dict[str, Any]:
        verification = "accepted_exact" if self._artifact.accepted else "fixture_only"
        return {
            "schema_version": "soomfon-provider-outcome-evidence-v1",
            "artifact_verification": verification,
            "logical_call_total": len(self._records),
            "maximum_logical_calls": 2,
            "maximum_provider_transports": 2,
            "sync_only": True,
            "fallback_allowed": False,
            "health_probe_allowed": False,
            "retry_count": 0,
            "call_records": [dict(item) for item in self._records],
        }

    def finalize(self) -> dict[str, Any]:
        if self._terminal or len(self._records) != 2:
            _reject("logical_call_count_incomplete")
        evidence = self.evidence()
        validate_soomfon_provider_evidence(evidence, mode=self._mode)
        return evidence


def verify_retained_soomfon_journals(
    journal_parent: Path | int,
    evidence: Mapping[str, Any],
    *,
    mode: str,
    execution_task_id: int,
    contract_sha256: str,
    expected_marker_sha256: str,
) -> None:
    validated = validate_soomfon_provider_evidence(evidence, mode=mode)
    if (
        validated["artifact_verification"] != "accepted_exact"
        or validated["logical_call_total"] != 2
    ):
        _reject("retained_journal_acceptance_drift")
    parent_fd: int | None = None
    verification_fd: int | None = None
    initial_parent_info: os.stat_result | None = None
    initial_verification_info: os.stat_result | None = None
    initial_member_info: list[os.stat_result] = []
    if isinstance(journal_parent, bool):
        _reject("journal_parent_fd_invalid")
    if isinstance(journal_parent, int):
        parent_fd = journal_parent
        (
            verification_fd,
            anchored_members,
            initial_parent_info,
            initial_verification_info,
        ) = _fd_private_directory_members(parent_fd)
        members = [path for path, _info in anchored_members]
        initial_member_info = [info for _path, info in anchored_members]
    else:
        parent = _private_directory(journal_parent)
        try:
            members = sorted(parent.iterdir(), key=lambda item: item.name)
        except OSError as exc:
            raise SoomfonProviderError("retained_journal_read_failed") from exc
    try:
        if len(members) != 2:
            _reject("retained_journal_count_drift")
        source_identity = expected_owner_source_identity()
        dependency_identity = expected_owner_dependency_identity()
        for ordinal, (path, record) in enumerate(
            zip(members, validated["call_records"], strict=True), start=1
        ):
            journal = (
                _load_fd_anchored_journal(
                    verification_fd,
                    path.name,
                    initial_member_info[ordinal - 1],
                )
                if verification_fd is not None
                else load_verified_journal(path)
            )
            chain = verify_receipt_chain(journal)
            reduced = reduce_verified_chain(chain)
            reservation = journal.reservation
            if (
                path.name != f"{ordinal:02d}-{reservation.logical_request_id}"
                or journal.artifact_verification != "accepted_exact"
                or reservation.consumer_task_id != execution_task_id
                or reservation.contract_sha256 != contract_sha256
                or reservation.ledger_sha256 != expected_marker_sha256
                or reservation.case_id != mode
                or reservation.mode != "sync"
                or reservation.requested_route != REQUESTED_ROUTE
                or reservation.resolved_route != RESOLVED_ROUTE
                or reservation.endpoint_origin_sha256 != ENDPOINT_ORIGIN_SHA256
                or reservation.source_identity != source_identity
                or reservation.dependency_identity != dependency_identity
                or record["call_ordinal"] != ordinal
                or record["signature_name"] != _MODE_SIGNATURES[mode][ordinal - 1]
                or record["reservation_id"] != reservation.reservation_id
                or record["journal_sha256"] != _journal_projection_digest(journal)
                or reduced.terminal != "provider_response_completed"
                or reduced.request_acknowledged is not True
                or reduced.external_effect_possible is not True
            ):
                _reject("retained_journal_binding_drift")
        if parent_fd is not None and verification_fd is not None:
            _revalidate_fd_directory_members(
                verification_fd,
                list(zip(members, initial_member_info, strict=True)),
            )
            try:
                final_parent_info = os.fstat(parent_fd)
                final_verification_info = os.fstat(verification_fd)
            except OSError as exc:
                raise SoomfonProviderError("retained_journal_read_failed") from exc
            if (
                initial_parent_info is None
                or initial_verification_info is None
                or not _same_inode(initial_parent_info, final_parent_info)
                or not _same_inode(initial_verification_info, final_verification_info)
                or not _same_inode(final_parent_info, final_verification_info)
            ):
                _reject("retained_journal_parent_identity_drift")
    finally:
        if verification_fd is not None:
            os.close(verification_fd)


def validate_soomfon_provider_evidence(
    value: Mapping[str, Any], *, mode: str
) -> dict[str, Any]:
    if mode not in _MODE_SIGNATURES:
        _reject("provider_evidence_mode_drift")
    expected_keys = {
        "schema_version",
        "artifact_verification",
        "logical_call_total",
        "maximum_logical_calls",
        "maximum_provider_transports",
        "sync_only",
        "fallback_allowed",
        "health_probe_allowed",
        "retry_count",
        "call_records",
    }
    records = value.get("call_records")
    total = value.get("logical_call_total")
    if (
        set(value) != expected_keys
        or value.get("schema_version") != "soomfon-provider-outcome-evidence-v1"
        or value.get("artifact_verification") not in {"accepted_exact", "fixture_only"}
        or isinstance(total, bool)
        or not isinstance(total, int)
        or not isinstance(records, list)
        or total != len(records)
        or not 0 <= total <= 2
        or value.get("maximum_logical_calls") != 2
        or value.get("maximum_provider_transports") != 2
        or value.get("sync_only") is not True
        or value.get("fallback_allowed") is not False
        or value.get("health_probe_allowed") is not False
        or value.get("retry_count") != 0
    ):
        _reject("provider_evidence_shape_drift")
    record_keys = {
        "call_ordinal",
        "signature_name",
        "reservation_id",
        "journal_sha256",
        "provider_outcome_receipt",
        "request_acknowledged",
        "external_effect_possible",
        "producer_terminal",
        "empirical_disposition",
        "reason",
    }
    terminal_seen = False
    for ordinal, raw in enumerate(records, start=1):
        if not isinstance(raw, Mapping) or set(raw) != record_keys:
            _reject("provider_call_record_shape_drift")
        accepted = raw.get("provider_outcome_receipt") == "accepted"
        if (
            raw.get("call_ordinal") != ordinal
            or raw.get("signature_name") != _MODE_SIGNATURES[mode][ordinal - 1]
            or raw.get("provider_outcome_receipt") not in {"accepted", "rejected"}
            or not isinstance(raw.get("external_effect_possible"), bool)
            or not isinstance(raw.get("reason"), str)
            or not raw.get("reason")
            or terminal_seen
        ):
            _reject("provider_call_record_identity_drift")
        for key in ("reservation_id", "journal_sha256"):
            value_hash = raw.get(key)
            if value_hash is not None and (
                not isinstance(value_hash, str)
                or _SHA256_RE.fullmatch(value_hash) is None
            ):
                _reject("provider_call_record_hash_drift")
        if accepted:
            if (
                raw.get("request_acknowledged") is not True
                or raw.get("external_effect_possible") is not True
                or raw.get("producer_terminal") != "provider_response_completed"
                or raw.get("empirical_disposition") != "not_evaluated"
                or raw.get("reason") != "attributable_completion_not_evaluated"
                or raw.get("reservation_id") is None
                or raw.get("journal_sha256") is None
            ):
                _reject("provider_attributable_completion_drift")
        else:
            if (
                raw.get("request_acknowledged") is not None
                or raw.get("producer_terminal") is not None
                or raw.get("empirical_disposition")
                not in {"error", "effect_indeterminate"}
            ):
                _reject("provider_rejection_projection_drift")
            terminal_seen = True
    return dict(value)
