# summary: "Task-bound private state construction for receipt-bound semantic v11."
from __future__ import annotations

import json
import os
import re
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from dspx.services.program_oracle_semantic_contract_v11 import (
    BoundContractCase,
    CASE_ORDER,
    CONTRACT_SHA256,
    SemanticV11Error,
    assert_sha256,
    canonical,
    sha256,
)
from dspx.services.program_oracle_semantic_result_v11 import (
    VerifiedSemanticResult,
    semantic_error_result,
)
from dspx.services.program_oracle_semantic_gate4_v11 import Gate4AuthorityCapability
from dspx.services.provider_outcome_receipt_contract import (
    ProviderOutcomeConsumerError,
    ReceiptProjection,
    VerifiedJournal,
)
from dspx.services.provider_outcome_receipt_identity import VerifiedOwnerArtifact
import dspx.services.provider_outcome_receipt_journal as receipt_journal_module
from dspx.services.provider_outcome_receipt_journal import ReceiptJournal
from dspx.services.provider_outcome_receipt_reducer import (
    reduce_verified_chain,
    verify_receipt_chain,
)

LEDGER_SCHEMA = "dspx-oracle-semantic-v11-ledger-v1"
RESULT_SCHEMA = "dspx-oracle-semantic-v11-result-v1"
VERIFICATION_SCHEMA = "dspx-oracle-semantic-v11-verification-v1"
REQUIRED_LIVE_COMPLETION_KIND = "oracle_semantic_v11_live_execution"
FORBIDDEN_TASK_IDS = frozenset({4643})
LEDGER_NAME = "ledger.json"
RESULT_NAME = "evaluation-result.json"
VERIFICATION_NAME = "independent-verification.json"
ATTEMPT_TERMINAL_NAME = "attempt-terminal.json"
ATTEMPT_TERMINAL_SCHEMA = RESULT_SCHEMA
PROVIDER_OUTCOMES_NAME = "provider-outcomes"
CASE_CUSTODY_NAME = "case-custody"
CASE_CUSTODY_SCHEMA = "dspx-oracle-semantic-v11-case-custody-v1"
MAX_RETAINED_BYTES = 1_500_000
LEDGER_KEYS = {
    "schema_version",
    "live_task_id",
    "ledger_namespace",
    "ledger_key",
    "artifact_key",
    "status",
    "maximum_evaluation_processes",
    "retry_allowed",
    "process_identity_sha256",
    "candidate_commit",
    "candidate_tree",
    "candidate_source_manifest_sha256",
    "contract_sha256",
    "candidate_review_sha256",
    "live_gate_sha256",
    "authority_snapshot_sha256",
    "live_authorized",
}


_TASK_BINDING_TOKEN = object()


class TaskBinding:
    """Opaque canonical task-to-state derivation; direct construction is forbidden."""

    __slots__ = (
        "live_task_id",
        "ledger_namespace",
        "ledger_key",
        "artifact_key",
        "_sealed",
    )

    live_task_id: int
    ledger_namespace: str
    ledger_key: str
    artifact_key: str
    _sealed: bool

    def __init__(
        self,
        *,
        live_task_id: int,
        ledger_namespace: str,
        ledger_key: str,
        artifact_key: str,
        token: object,
    ) -> None:
        if token is not _TASK_BINDING_TOKEN:
            raise TypeError("TaskBinding is created by the canonical factory")
        object.__setattr__(self, "live_task_id", live_task_id)
        object.__setattr__(self, "ledger_namespace", ledger_namespace)
        object.__setattr__(self, "ledger_key", ledger_key)
        object.__setattr__(self, "artifact_key", artifact_key)
        object.__setattr__(self, "_sealed", True)

    def __setattr__(self, name: str, value: Any) -> None:
        if getattr(self, "_sealed", False):
            raise TypeError("TaskBinding is immutable")
        object.__setattr__(self, name, value)

    def __eq__(self, other: object) -> bool:
        return type(other) is TaskBinding and self.payload() == other.payload()

    @classmethod
    def create(cls, live_task_id: int, completion_kind: str) -> "TaskBinding":
        if cls is not TaskBinding or (
            isinstance(live_task_id, bool)
            or not isinstance(live_task_id, int)
            or live_task_id <= 0
            or live_task_id in FORBIDDEN_TASK_IDS
            or completion_kind != REQUIRED_LIVE_COMPLETION_KIND
        ):
            raise SemanticV11Error("future live task binding rejected")
        return cls(
            live_task_id=live_task_id,
            ledger_namespace=(
                f"dspx/oracle-semantic-analysis-evaluations/AK-{live_task_id}/v11"
            ),
            ledger_key=f"AK-{live_task_id}:oracle-semantic-analysis-v11:one-process",
            artifact_key=(
                f"oracle-semantic-analysis-evaluations/AK-{live_task_id}/v11/attempt"
            ),
            token=_TASK_BINDING_TOKEN,
        )

    def require_canonical(self) -> None:
        if type(self) is not TaskBinding:
            raise SemanticV11Error("task binding type drift")
        expected = TaskBinding.create(self.live_task_id, REQUIRED_LIVE_COMPLETION_KIND)
        if self.payload() != expected.payload():
            raise SemanticV11Error("task binding canonical drift")

    def payload(self) -> dict[str, Any]:
        return {
            "live_task_id": self.live_task_id,
            "ledger_namespace": self.ledger_namespace,
            "ledger_key": self.ledger_key,
            "artifact_key": self.artifact_key,
        }


_ATTEMPT_TOKEN = object()


class ConsumedAttempt:
    """Opaque consumed-attempt handle; live effect capability stays sealed."""

    __slots__ = (
        "binding",
        "attempt_root",
        "ledger_sha256",
        "_ledger_raw",
        "_authority",
        "_terminal_digests",
        "_sealed",
    )
    binding: TaskBinding
    attempt_root: Path
    ledger_sha256: str
    _ledger_raw: bytes
    _authority: Gate4AuthorityCapability | None
    _terminal_digests: dict[int, str]
    _sealed: bool

    def __init__(
        self,
        *,
        binding: TaskBinding,
        attempt_root: Path,
        ledger_raw: bytes,
        authority: Gate4AuthorityCapability | None,
        token: object,
    ) -> None:
        if token is not _ATTEMPT_TOKEN:
            raise TypeError("ConsumedAttempt is created by task-state custody")
        if type(binding) is not TaskBinding:
            raise SemanticV11Error("consumed task binding type drift")
        binding.require_canonical()
        if authority is not None and type(authority) is not Gate4AuthorityCapability:
            raise SemanticV11Error("consumed Gate-4 authority type drift")
        object.__setattr__(self, "binding", binding)
        object.__setattr__(self, "attempt_root", attempt_root)
        object.__setattr__(self, "ledger_sha256", sha256(ledger_raw))
        object.__setattr__(self, "_ledger_raw", ledger_raw)
        object.__setattr__(self, "_authority", authority)
        object.__setattr__(self, "_terminal_digests", {})
        object.__setattr__(self, "_sealed", True)

    def __setattr__(self, name: str, value: Any) -> None:
        if getattr(self, "_sealed", False):
            raise TypeError("ConsumedAttempt is immutable")
        object.__setattr__(self, name, value)

    @property
    def ledger(self) -> Mapping[str, Any]:
        value = json.loads(self._ledger_raw)
        if not isinstance(value, Mapping):  # pragma: no cover - constructor invariant
            raise SemanticV11Error("consumed ledger schema drift")
        return dict(value)

    @property
    def live_authorized(self) -> bool:
        return type(self._authority) is Gate4AuthorityCapability

    def require_current_process(self) -> None:
        if type(self) is not ConsumedAttempt:
            raise SemanticV11Error("consumed-attempt capability type drift")
        self.binding.require_canonical()
        ledger = self.ledger
        if ledger.get("process_identity_sha256") != current_process_identity_sha256():
            raise SemanticV11Error("consumed process custody drift")
        path = self.attempt_root / LEDGER_NAME
        _require_private(path, directory=False)
        try:
            retained = path.read_bytes()
        except OSError as exc:
            raise SemanticV11Error("consumed ledger invalid") from exc
        if retained != self._ledger_raw or sha256(retained) != self.ledger_sha256:
            raise SemanticV11Error("consumed ledger bytes drift")

    def require_live(self) -> None:
        """Revalidate opaque authority, ledger, and process custody before effect."""

        if type(self) is not ConsumedAttempt:
            raise SemanticV11Error("consumed-attempt capability type drift")
        authority = self._authority
        if type(authority) is not Gate4AuthorityCapability:
            raise SemanticV11Error("canonical Gate-4 capability required")
        authority.require_current()
        ledger = self.ledger
        if (
            authority.live_task_id != self.binding.live_task_id
            or authority.contract_sha256 != ledger.get("contract_sha256")
            or authority.candidate_review_sha256
            != ledger.get("candidate_review_sha256")
            or authority.live_gate_sha256 != ledger.get("live_gate_sha256")
            or authority.authority_snapshot_sha256
            != ledger.get("authority_snapshot_sha256")
        ):
            raise SemanticV11Error("consumed Gate-4 authority binding drift")
        self.require_current_process()

    def _record_terminal_digest(self, case_ordinal: int, digest: str) -> None:
        self.require_live()
        expected = len(self._terminal_digests) + 1
        if case_ordinal != expected or case_ordinal in self._terminal_digests:
            raise SemanticV11Error("case terminal in-memory order drift")
        self._terminal_digests[case_ordinal] = assert_sha256(
            digest, "case_terminal_sha256"
        )

    def _require_terminal_digest(self, case_ordinal: int, digest: str) -> None:
        self.require_live()
        if self._terminal_digests.get(case_ordinal) != assert_sha256(
            digest, "case_terminal_sha256"
        ):
            raise SemanticV11Error("case terminal in-memory custody drift")


_BOOT_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


def current_process_identity_sha256() -> str:
    """Derive a domain-separated process digest without retaining account IDs."""

    pid = os.getpid()
    try:
        boot_id = (
            Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip()
        )
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
        tail = raw[raw.rfind(")") + 2 :].split()
        start_ticks = int(tail[19])
    except (OSError, UnicodeError, ValueError, IndexError) as exc:
        raise SemanticV11Error("process identity is unavailable") from exc
    if not _BOOT_ID_RE.fullmatch(boot_id) or start_ticks <= 0:
        raise SemanticV11Error("process identity value drift")
    return sha256(
        b"dspx-oracle-semantic-v11-process-identity-v1\0"
        + canonical(
            {
                "pid": pid,
                "uid": os.getuid(),
                "boot_id": boot_id,
                "proc_start_ticks": start_ticks,
            }
        )
    )


def _require_private(path: Path, *, directory: bool) -> None:
    try:
        info = path.lstat()
    except OSError as exc:
        raise SemanticV11Error("private state member missing") from exc
    expected = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    expected_mode = 0o700 if directory else 0o600
    if (
        not expected
        or stat.S_ISLNK(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != expected_mode
        or (not directory and info.st_nlink != 1)
    ):
        raise SemanticV11Error("private state posture drift")


def _read_private_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    _require_private(path, directory=False)
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SemanticV11Error(f"{label} invalid") from exc
    if (
        not isinstance(value, Mapping)
        or not raw
        or len(raw) > MAX_RETAINED_BYTES
        or canonical(value) != raw
    ):
        raise SemanticV11Error(f"{label} canonical drift")
    return dict(value), raw


def _fsync_directory(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError as exc:
        raise SemanticV11Error("directory sync failed") from exc


def write_exclusive(path: Path, payload: Mapping[str, Any]) -> bytes:
    raw = canonical(dict(payload))
    if not raw or len(raw) > MAX_RETAINED_BYTES:
        raise SemanticV11Error("retained payload size drift")
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
        _fsync_directory(path.parent)
    except FileExistsError as exc:
        raise SemanticV11Error("retained member already exists") from exc
    except SemanticV11Error:
        raise
    except OSError as exc:
        raise SemanticV11Error("retained member write failed") from exc
    return raw


def _write_pre_effect_setup_terminal(
    attempt: ConsumedAttempt, next_case: BoundContractCase | None = None
) -> dict[str, Any]:
    """Terminalize a proven post-entry failure before the next provider effect."""

    attempt.require_live()
    records = load_case_custody(attempt)
    if next_case is None:
        if records:
            raise SemanticV11Error("initial setup terminal after case custody")
        next_case_id = None
        next_case_ordinal = None
    else:
        next_case.require_canonical()
        expected = {
            name
            for ordinal in range(1, next_case.case_ordinal)
            for name in (
                f"{ordinal:02d}-reserved.json",
                f"{ordinal:02d}-terminal.json",
            )
        }
        if set(records) != expected:
            raise SemanticV11Error("next-case setup terminal custody drift")
        next_case_id = next_case.case_id
        next_case_ordinal = next_case.case_ordinal
    payload = {
        "schema_version": ATTEMPT_TERMINAL_SCHEMA,
        "kind": "pre_effect_setup_failed",
        "live_task_id": attempt.binding.live_task_id,
        "next_case_id": next_case_id,
        "next_case_ordinal": next_case_ordinal,
        "external_effect_possible": False,
        "empirical_gate": "error",
        "reason": "post_entry_setup_failed_before_provider_effect",
    }
    write_exclusive(attempt.attempt_root / ATTEMPT_TERMINAL_NAME, payload)
    return payload


def load_pre_effect_setup_terminal(attempt: ConsumedAttempt) -> dict[str, Any] | None:
    path = attempt.attempt_root / ATTEMPT_TERMINAL_NAME
    if not path.exists() and not path.is_symlink():
        return None
    payload, _ = _read_private_json(path, "attempt setup terminal")
    next_ordinal = payload.get("next_case_ordinal")
    next_case_id = payload.get("next_case_id")
    if next_ordinal is None:
        valid_next = next_case_id is None
    else:
        valid_next = (
            not isinstance(next_ordinal, bool)
            and isinstance(next_ordinal, int)
            and 1 <= next_ordinal <= len(CASE_ORDER)
            and next_case_id == CASE_ORDER[next_ordinal - 1]
        )
    if not valid_next or payload != {
        "schema_version": ATTEMPT_TERMINAL_SCHEMA,
        "kind": "pre_effect_setup_failed",
        "live_task_id": attempt.binding.live_task_id,
        "next_case_id": next_case_id,
        "next_case_ordinal": next_ordinal,
        "external_effect_possible": False,
        "empirical_gate": "error",
        "reason": "post_entry_setup_failed_before_provider_effect",
    }:
        raise SemanticV11Error("attempt setup terminal drift")
    return payload


def load_case_custody(attempt: ConsumedAttempt) -> dict[str, dict[str, Any]]:
    root = attempt.attempt_root / CASE_CUSTODY_NAME
    _require_private(root, directory=True)
    records: dict[str, dict[str, Any]] = {}
    try:
        paths = sorted(root.iterdir())
    except OSError as exc:
        raise SemanticV11Error("case custody listing failed") from exc
    for path in paths:
        if not re.fullmatch(r"0[1-4]-(?:reserved|terminal)\.json", path.name):
            raise SemanticV11Error("unexpected case custody member")
        payload, _ = _read_private_json(path, "case custody record")
        if payload.get("schema_version") != CASE_CUSTODY_SCHEMA:
            raise SemanticV11Error("case custody schema drift")
        records[path.name] = payload
    return records


def validate_retained_semantic_result(
    case: BoundContractCase, value: object
) -> dict[str, Any]:
    """Re-score retained bounded facts against the exact canonical case."""

    if type(case) is not BoundContractCase or not isinstance(value, Mapping):
        raise SemanticV11Error("retained semantic result capability drift")
    case.require_canonical()
    semantic = dict(value)
    if (
        set(semantic) != {"case_id", "outcome", "analysis", "score", "analysis_sha256"}
        or semantic.get("case_id") != case.case_id
    ):
        raise SemanticV11Error("retained semantic result schema drift")
    outcome = semantic.get("outcome")
    if outcome == "semantic_error":
        if any(
            semantic.get(key) is not None
            for key in ("analysis", "score", "analysis_sha256")
        ):
            raise SemanticV11Error("retained semantic error custody drift")
        return semantic
    analysis = semantic.get("analysis")
    score = semantic.get("score")
    if not isinstance(analysis, Mapping) or not isinstance(score, Mapping):
        raise SemanticV11Error("retained semantic score custody drift")
    expected_score = case.score(analysis)
    expected_outcome = (
        "score_pass" if expected_score.get("status") == "passed" else "score_miss"
    )
    if (
        outcome != expected_outcome
        or canonical(score) != canonical(expected_score)
        or semantic.get("analysis_sha256") != sha256(canonical(analysis))
    ):
        raise SemanticV11Error("retained semantic score derivation drift")
    return semantic


def reserve_case(
    attempt: ConsumedAttempt,
    *,
    case: BoundContractCase,
    logical_request_id: str,
    semantic_request_sha256: str,
    reservation_sha256: str,
) -> None:
    """Durably admit only the next fixed case before receipt creation."""

    attempt.require_live()
    if type(case) is not BoundContractCase:
        raise SemanticV11Error("bound contract case required")
    case.require_canonical()
    case_id = case.case_id
    case_ordinal = case.case_ordinal
    if attempt.ledger.get("contract_sha256") != case.contract_sha256:
        raise SemanticV11Error("case custody contract digest drift")
    logical = assert_sha256(logical_request_id, "logical_request_id")
    request_digest = assert_sha256(semantic_request_sha256, "semantic_request_sha256")
    reservation_digest = assert_sha256(reservation_sha256, "reservation_sha256")
    records = load_case_custody(attempt)
    expected: set[str] = set()
    for ordinal in range(1, case_ordinal):
        expected.update(
            {f"{ordinal:02d}-reserved.json", f"{ordinal:02d}-terminal.json"}
        )
        terminal = records.get(f"{ordinal:02d}-terminal.json")
        semantic = terminal.get("semantic_result") if terminal is not None else None
        prior_case = case.case_at(ordinal)
        retained_semantic = validate_retained_semantic_result(prior_case, semantic)
        if (
            retained_semantic.get("outcome") != "score_pass"
            or terminal is None
            or terminal.get("semantic_result_sha256")
            != sha256(canonical(retained_semantic))
        ):
            raise SemanticV11Error("prior semantic result custody drift")
        if (
            terminal is None
            or terminal.get("case_id") != CASE_ORDER[ordinal - 1]
            or terminal.get("case_ordinal") != ordinal
            or terminal.get("empirical_disposition") != "passed"
            or terminal.get("semantic_outcome") != "score_pass"
        ):
            raise SemanticV11Error("prior case did not permit continuation")
        attempt._require_terminal_digest(ordinal, sha256(canonical(terminal)))
    if set(records) != expected:
        raise SemanticV11Error("case custody order/stop drift")
    payload = {
        "schema_version": CASE_CUSTODY_SCHEMA,
        "kind": "reserved",
        "live_task_id": attempt.binding.live_task_id,
        "case_id": case_id,
        "case_ordinal": case_ordinal,
        "logical_request_id": logical,
        "semantic_request_sha256": request_digest,
        "reservation_sha256": reservation_digest,
    }
    write_exclusive(
        attempt.attempt_root / CASE_CUSTODY_NAME / f"{case_ordinal:02d}-reserved.json",
        payload,
    )


def _record_case_pre_effect_failure(
    attempt: ConsumedAttempt, case: BoundContractCase
) -> dict[str, Any]:
    """Close a reserved case when receipt preparation failed before LM entry."""

    attempt.require_live()
    case.require_canonical()
    records = load_case_custody(attempt)
    expected = {
        name
        for ordinal in range(1, case.case_ordinal)
        for name in (
            f"{ordinal:02d}-reserved.json",
            f"{ordinal:02d}-terminal.json",
        )
    }
    reserved_name = f"{case.case_ordinal:02d}-reserved.json"
    expected.add(reserved_name)
    reserved = records.get(reserved_name)
    if (
        set(records) != expected
        or reserved is None
        or reserved.get("case_id") != case.case_id
        or reserved.get("case_ordinal") != case.case_ordinal
    ):
        raise SemanticV11Error("reserved pre-effect failure custody drift")
    semantic = semantic_error_result(case).payload()
    payload = {
        "schema_version": CASE_CUSTODY_SCHEMA,
        "kind": "terminal",
        "live_task_id": attempt.binding.live_task_id,
        "case_id": case.case_id,
        "case_ordinal": case.case_ordinal,
        "semantic_outcome": "semantic_error",
        "semantic_result": semantic,
        "semantic_result_sha256": sha256(canonical(semantic)),
        "observed_model": None,
        "provider_outcome_receipt": "rejected",
        "request_acknowledged": None,
        "external_effect_possible": False,
        "producer_terminal": None,
        "empirical_disposition": "error",
        "reason": "receipt_preparation_failed_before_effect",
    }
    raw = write_exclusive(
        attempt.attempt_root
        / CASE_CUSTODY_NAME
        / f"{case.case_ordinal:02d}-terminal.json",
        payload,
    )
    attempt._record_terminal_digest(case.case_ordinal, sha256(raw))
    return payload


def _load_terminal_preserving_journal(journal: ReceiptJournal) -> VerifiedJournal:
    """Recover a valid durable terminal when only a later callback poisoned writes."""

    try:
        return journal.load_verified()
    except ProviderOutcomeConsumerError as original:
        if type(journal) is not ReceiptJournal:
            raise
        root = journal._root
        try:
            members = {path.name: path for path in root.iterdir()}
            if set(members) != {"reservation.json", "events", "poisoned.json"}:
                raise ProviderOutcomeConsumerError(
                    "terminal_recovery_member_drift", effect_possible=True
                )
            poison = receipt_journal_module._decode_mapping(
                receipt_journal_module._read_private(members["poisoned.json"]),
                "terminal_recovery_poison_invalid",
            )
            if poison != {
                "schema_version": "dspx-provider-outcome-poison-v1",
                "effect_possible": True,
            }:
                raise ProviderOutcomeConsumerError(
                    "terminal_recovery_poison_drift", effect_possible=True
                )
            wrapper = receipt_journal_module._decode_mapping(
                receipt_journal_module._read_private(members["reservation.json"]),
                "terminal_recovery_reservation_invalid",
            )
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
                or wrapper.get("reservation_id") != journal._reservation.reservation_id
                or wrapper.get("artifact_verification") != "accepted_exact"
                or wrapper.get("reservation") != journal._reservation.payload()
            ):
                raise ProviderOutcomeConsumerError(
                    "terminal_recovery_reservation_drift", effect_possible=True
                )
            events_dir = members["events"]
            receipt_journal_module._require_private(events_dir, directory=True)
            paths = sorted(events_dir.iterdir(), key=lambda path: path.name)
            if not paths:
                raise ProviderOutcomeConsumerError(
                    "terminal_recovery_event_missing", effect_possible=True
                )
            envelopes = []
            previous: str | None = None
            for sequence, path in enumerate(paths):
                if path.name != f"{sequence:06d}.json":
                    raise ProviderOutcomeConsumerError(
                        "terminal_recovery_sequence_drift", effect_possible=True
                    )
                raw = receipt_journal_module._read_private(path)
                envelope = receipt_journal_module._validate_envelope(
                    raw, journal._reservation, sequence, previous
                )
                envelopes.append(envelope)
                previous = envelope.digest
            recovered = VerifiedJournal(
                journal._reservation, tuple(envelopes), "accepted_exact"
            )
            chain = verify_receipt_chain(recovered)
            if chain.terminal is None or envelopes[-1].event.kind != chain.terminal:
                raise ProviderOutcomeConsumerError(
                    "terminal_recovery_missing_terminal", effect_possible=True
                )
            return recovered
        except (OSError, ProviderOutcomeConsumerError) as recovery_error:
            raise original from recovery_error


def record_case_terminal(
    attempt: ConsumedAttempt,
    *,
    case: BoundContractCase,
    semantic_result: VerifiedSemanticResult,
    journal: ReceiptJournal,
    artifact: VerifiedOwnerArtifact,
) -> ReceiptProjection:
    """Derive and retain terminal custody from the exact journal, never caller facts."""

    attempt.require_live()
    if type(case) is not BoundContractCase:
        raise SemanticV11Error("bound contract case required")
    case.require_canonical()
    case_id = case.case_id
    case_ordinal = case.case_ordinal
    if (
        type(journal) is not ReceiptJournal
        or type(artifact) is not VerifiedOwnerArtifact
        or artifact.accepted is not True
        or type(semantic_result) is not VerifiedSemanticResult
        or semantic_result._case is not case
        or semantic_result.case_id != case_id
    ):
        raise SemanticV11Error("case terminal identity/capability drift")
    semantic_payload = semantic_result.payload()
    semantic_outcome = semantic_result.outcome
    artifact.revalidate()
    reservation = journal._reservation
    if (
        reservation.consumer_task_id != attempt.binding.live_task_id
        or reservation.ledger_sha256 != attempt.ledger_sha256
        or reservation.case_id != case_id
        or reservation.contract_sha256 != case.contract_sha256
        or reservation.source_identity != artifact.source_identity
        or reservation.dependency_identity != artifact.dependency_identity
    ):
        raise SemanticV11Error("case terminal journal binding drift")
    records = load_case_custody(attempt)
    expected = {
        name
        for ordinal in range(1, case_ordinal)
        for name in (f"{ordinal:02d}-reserved.json", f"{ordinal:02d}-terminal.json")
    }
    reserved_name = f"{case_ordinal:02d}-reserved.json"
    expected.add(reserved_name)
    reserved = records.get(reserved_name)
    if (
        set(records) != expected
        or reserved is None
        or reserved.get("logical_request_id") != reservation.logical_request_id
        or reserved.get("semantic_request_sha256")
        != reservation.semantic_request_sha256
        or reserved.get("reservation_sha256")
        != sha256(canonical(reservation.payload()))
    ):
        raise SemanticV11Error("case terminal order/reservation drift")
    try:
        retained = _load_terminal_preserving_journal(journal)
        if retained.artifact_verification != "accepted_exact":
            raise ProviderOutcomeConsumerError(
                "fixture_journal_not_accepted", effect_possible=True
            )
        chain = verify_receipt_chain(retained)
        terminal_model = retained.events[-1].event.observed_model
        if chain.terminal == "provider_response_completed" and (
            not isinstance(terminal_model, str)
            or not terminal_model
            or len(terminal_model.encode("utf-8")) > 128
            or any(ord(char) < 32 or ord(char) == 127 for char in terminal_model)
        ):
            semantic_outcome = "semantic_error"
        elif chain.terminal != "provider_response_completed":
            terminal_model = None
        reduced = reduce_verified_chain(chain, semantic_outcome=semantic_outcome)
        projection = ReceiptProjection(
            provider_outcome_receipt="accepted",
            request_acknowledged=reduced.request_acknowledged,
            external_effect_possible=reduced.external_effect_possible,
            producer_terminal=reduced.terminal,
            empirical_disposition=reduced.empirical_disposition,
            reason=reduced.reason,
        )
    except ProviderOutcomeConsumerError as exc:
        terminal_model = None
        projection = ReceiptProjection(
            provider_outcome_receipt="rejected",
            request_acknowledged=None,
            external_effect_possible=exc.effect_possible,
            producer_terminal=None,
            empirical_disposition=(
                "effect_indeterminate" if exc.effect_possible else "error"
            ),
            reason=exc.reason,
        )
    if projection.empirical_disposition == "not_evaluated":
        raise SemanticV11Error("case terminal semantic disposition unresolved")
    if semantic_outcome != semantic_result.outcome:
        semantic_payload = {
            "case_id": case_id,
            "outcome": semantic_outcome,
            "analysis": None,
            "score": None,
            "analysis_sha256": None,
        }
    semantic_result_sha256 = sha256(canonical(semantic_payload))
    facts = {
        "provider_outcome_receipt": projection.provider_outcome_receipt,
        "request_acknowledged": projection.request_acknowledged,
        "external_effect_possible": projection.external_effect_possible,
        "producer_terminal": projection.producer_terminal,
        "empirical_disposition": projection.empirical_disposition,
        "reason": projection.reason,
    }
    reason = projection.reason
    if (
        not reason
        or len(reason.encode("utf-8")) > 128
        or any(ord(char) < 32 or ord(char) == 127 for char in reason)
    ):
        raise SemanticV11Error("case terminal reason drift")
    payload = {
        "schema_version": CASE_CUSTODY_SCHEMA,
        "kind": "terminal",
        "live_task_id": attempt.binding.live_task_id,
        "case_id": case_id,
        "case_ordinal": case_ordinal,
        "semantic_outcome": semantic_outcome,
        "semantic_result": semantic_payload,
        "semantic_result_sha256": semantic_result_sha256,
        "observed_model": terminal_model,
        **facts,
    }
    raw = write_exclusive(
        attempt.attempt_root / CASE_CUSTODY_NAME / f"{case_ordinal:02d}-terminal.json",
        payload,
    )
    attempt._record_terminal_digest(case_ordinal, sha256(raw))
    return projection


def _derived_paths(state_root: Path, binding: TaskBinding) -> tuple[Path, Path, Path]:
    if type(binding) is not TaskBinding:
        raise SemanticV11Error("task binding type drift")
    binding.require_canonical()
    task_root = (
        state_root
        / "oracle-semantic-analysis-evaluations"
        / f"AK-{binding.live_task_id}"
    )
    version_root = task_root / "v11"
    return task_root, version_root, version_root / "attempt"


def assert_attempt_absent(state_root: Path, binding: TaskBinding) -> None:
    """Absence-only preflight. It never creates a path."""

    if type(binding) is not TaskBinding:
        raise SemanticV11Error("task binding type drift")
    binding.require_canonical()

    root = state_root.expanduser()
    _require_private(root, directory=True)
    for path in _derived_paths(root, binding):
        if path.exists() or path.is_symlink():
            raise SemanticV11Error("task-bound attempt already exists")


def _mkdir_exclusive(path: Path) -> None:
    try:
        os.mkdir(path, 0o700)
        os.chmod(path, 0o700)
        _fsync_directory(path)
        _fsync_directory(path.parent)
    except FileExistsError as exc:
        raise SemanticV11Error("task-bound state collision") from exc
    except SemanticV11Error:
        raise
    except OSError as exc:
        raise SemanticV11Error("task-bound directory creation failed") from exc


def _consume_attempt(
    state_root: Path,
    binding: TaskBinding,
    *,
    authority: Gate4AuthorityCapability | None,
    contract_sha256: str,
    candidate_review_sha256: str,
    live_gate_sha256: str,
    authority_snapshot_sha256: str,
    candidate_commit: str,
    candidate_tree: str,
    candidate_source_manifest_sha256: str,
) -> ConsumedAttempt:
    binding.require_canonical()
    process_digest = current_process_identity_sha256()
    root = state_root.expanduser()
    assert_attempt_absent(root, binding)
    namespace = root / "oracle-semantic-analysis-evaluations"
    if namespace.exists() or namespace.is_symlink():
        _require_private(namespace, directory=True)
    else:
        _mkdir_exclusive(namespace)
    task_root, version_root, attempt = _derived_paths(root, binding)
    _mkdir_exclusive(task_root)
    _mkdir_exclusive(version_root)
    _mkdir_exclusive(attempt)
    _mkdir_exclusive(attempt / PROVIDER_OUTCOMES_NAME)
    _mkdir_exclusive(attempt / CASE_CUSTODY_NAME)
    ledger = {
        "schema_version": LEDGER_SCHEMA,
        "live_task_id": binding.live_task_id,
        "ledger_namespace": binding.ledger_namespace,
        "ledger_key": binding.ledger_key,
        "artifact_key": binding.artifact_key,
        "status": "consumed",
        "maximum_evaluation_processes": 1,
        "retry_allowed": False,
        "process_identity_sha256": process_digest,
        "candidate_commit": candidate_commit,
        "candidate_tree": candidate_tree,
        "candidate_source_manifest_sha256": assert_sha256(
            candidate_source_manifest_sha256,
            "candidate_source_manifest_sha256",
        ),
        "contract_sha256": assert_sha256(contract_sha256, "contract_sha256"),
        "candidate_review_sha256": assert_sha256(
            candidate_review_sha256, "candidate_review_sha256"
        ),
        "live_gate_sha256": assert_sha256(live_gate_sha256, "live_gate_sha256"),
        "authority_snapshot_sha256": assert_sha256(
            authority_snapshot_sha256, "authority_snapshot_sha256"
        ),
        "live_authorized": authority is not None,
    }
    raw = write_exclusive(attempt / LEDGER_NAME, ledger)
    return ConsumedAttempt(
        binding=binding,
        attempt_root=attempt,
        ledger_raw=raw,
        authority=authority,
        token=_ATTEMPT_TOKEN,
    )


def consume_attempt(
    state_root: Path, authority: Gate4AuthorityCapability
) -> ConsumedAttempt:
    """Spend canonical AK-backed authority and durably consume one live process."""

    if type(authority) is not Gate4AuthorityCapability:
        raise SemanticV11Error("canonical Gate-4 capability required")
    authority.require_current()
    binding = TaskBinding.create(authority.live_task_id, REQUIRED_LIVE_COMPLETION_KIND)
    authority.claim_for_entry()
    return _consume_attempt(
        state_root,
        binding,
        authority=authority,
        contract_sha256=authority.contract_sha256,
        candidate_review_sha256=authority.candidate_review_sha256,
        live_gate_sha256=authority.live_gate_sha256,
        authority_snapshot_sha256=authority.authority_snapshot_sha256,
        candidate_commit=authority.candidate_commit,
        candidate_tree=authority.candidate_tree,
        candidate_source_manifest_sha256=(authority.candidate_source_manifest_sha256),
    )


def consume_fixture_attempt(state_root: Path, binding: TaskBinding) -> ConsumedAttempt:
    """Create authority-false provider-free custody; it cannot pass require_live()."""

    if type(binding) is not TaskBinding:
        raise SemanticV11Error("task binding type drift")
    fixture = sha256(
        canonical({"fixture_only": True, "task_binding": binding.payload()})
    )
    return _consume_attempt(
        state_root,
        binding,
        authority=None,
        contract_sha256=CONTRACT_SHA256,
        candidate_review_sha256=fixture,
        live_gate_sha256=fixture,
        authority_snapshot_sha256=fixture,
        candidate_commit="0" * 40,
        candidate_tree="0" * 40,
        candidate_source_manifest_sha256=fixture,
    )


def load_consumed_attempt(
    state_root: Path,
    binding: TaskBinding,
    *,
    require_current_process: bool = True,
    authority: Gate4AuthorityCapability | None = None,
) -> ConsumedAttempt:
    if type(binding) is not TaskBinding:
        raise SemanticV11Error("task binding type drift")
    binding.require_canonical()
    if authority is not None and type(authority) is not Gate4AuthorityCapability:
        raise SemanticV11Error("canonical Gate-4 capability type drift")
    _, _, attempt = _derived_paths(state_root.expanduser(), binding)
    _require_private(attempt, directory=True)
    _require_private(attempt / PROVIDER_OUTCOMES_NAME, directory=True)
    _require_private(attempt / CASE_CUSTODY_NAME, directory=True)
    path = attempt / LEDGER_NAME
    _require_private(path, directory=False)
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SemanticV11Error("consumed ledger invalid") from exc
    if not isinstance(value, Mapping) or canonical(value) != raw:
        raise SemanticV11Error("consumed ledger canonical drift")
    ledger = dict(value)
    if (
        set(ledger) != LEDGER_KEYS
        or ledger.get("schema_version") != LEDGER_SCHEMA
        or ledger.get("live_task_id") != binding.live_task_id
        or ledger.get("ledger_namespace") != binding.ledger_namespace
        or ledger.get("ledger_key") != binding.ledger_key
        or ledger.get("artifact_key") != binding.artifact_key
        or ledger.get("status") != "consumed"
        or ledger.get("maximum_evaluation_processes") != 1
        or ledger.get("retry_allowed") is not False
        or not isinstance(ledger.get("live_authorized"), bool)
    ):
        raise SemanticV11Error("consumed ledger binding drift")
    for key in (
        "process_identity_sha256",
        "candidate_source_manifest_sha256",
        "contract_sha256",
        "candidate_review_sha256",
        "live_gate_sha256",
        "authority_snapshot_sha256",
    ):
        assert_sha256(ledger.get(key), key)
    if (
        not isinstance(ledger["candidate_commit"], str)
        or not re.fullmatch(r"[0-9a-f]{40}", ledger["candidate_commit"])
        or not isinstance(ledger["candidate_tree"], str)
        or not re.fullmatch(r"[0-9a-f]{40}", ledger["candidate_tree"])
    ):
        raise SemanticV11Error("consumed candidate Git identity drift")
    if require_current_process and (
        ledger["process_identity_sha256"] != current_process_identity_sha256()
    ):
        raise SemanticV11Error("consumed process custody drift")
    if authority is not None:
        authority.require_current()
        if (
            ledger["live_authorized"] is not True
            or authority.live_task_id != binding.live_task_id
            or authority.candidate_commit != ledger["candidate_commit"]
            or authority.candidate_tree != ledger["candidate_tree"]
            or authority.candidate_source_manifest_sha256
            != ledger["candidate_source_manifest_sha256"]
            or authority.contract_sha256 != ledger["contract_sha256"]
            or authority.candidate_review_sha256 != ledger["candidate_review_sha256"]
            or authority.live_gate_sha256 != ledger["live_gate_sha256"]
            or authority.authority_snapshot_sha256
            != ledger["authority_snapshot_sha256"]
        ):
            raise SemanticV11Error("consumed Gate-4 custody drift")
    elif require_current_process and ledger["live_authorized"] is True:
        raise SemanticV11Error("live attempt requires its opaque Gate-4 capability")
    return ConsumedAttempt(
        binding=binding,
        attempt_root=attempt,
        ledger_raw=raw,
        authority=authority,
        token=_ATTEMPT_TOKEN,
    )
