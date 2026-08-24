"""No-follow filesystem and runtime custody for protected Soomfon candidates."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import pwd
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from dspx.services.soomfon_evaluation_contract import (
    CONTRACT_PREPARATION_TASK_ID,
    EXPECTED_INPUT_SHA256,
    EXPECTED_RECEIPT_SHA256,
    REVIEWED_CONTRACT_SHA256,
)

from dspx.services.soomfon_evaluation_filesystem import (
    SoomfonCustodyError,
    ensure_private_tree as ensure_private_tree,
    fsync_private_tree as fsync_private_tree,
    open_private_directory as open_private_directory,
    stage_candidate as stage_candidate,
)
from dspx.services.soomfon_evaluation_ledger import (
    LEDGER_SCHEMA as _LEDGER_SCHEMA,
    MAX_LEDGER_RECORD as _MAX_LEDGER_RECORD,
    is_complete_terminal_marker as _is_complete_terminal_marker,
    prior_modes_succeeded as _prior_modes_succeeded,
    read_marker_records as _read_marker_records,
    reconciliation_sidecar_present as _reconciliation_sidecar_present,
    runtime_evidence_hashes as _runtime_evidence_hashes,
    valid_reconciliation_sidecar as _valid_reconciliation_sidecar,
)


from dspx.services.soomfon_evaluation_candidates import PROTECTED_MANIFESTS

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class SoomfonRuntimeCustody:
    contract_sha256: str
    mode: str
    expected_manifest_sha256: str
    expected_receipt_sha256: str
    staged_manifest_path: Path
    inputs_path: Path
    expected_inputs_sha256: str
    outdir: Path
    raw_root_fd: int
    runtime_fd: int
    marker_fd: int
    ledger_fd: int
    lock_fd: int
    provider_journal_fd: int
    execution_task_id: int
    authorization_sha256: str
    ak_reconciliation_sha256: str
    authorization_path: Path
    repo_root: Path
    owner_source_root: Path


def default_state_root() -> Path:
    home = Path(pwd.getpwuid(os.geteuid()).pw_dir)
    return home / ".local/state/dspx/soomfon-evaluation"


def acquire_suite_lock(root_fd: int) -> int:
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    lock_fd = -1
    try:
        lock_fd = os.open("suite.lock", flags, 0o600, dir_fd=root_fd)
        info = os.fstat(lock_fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o600
        ):
            raise SoomfonCustodyError("suite lock identity is invalid")
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        os.fsync(lock_fd)
        os.fsync(root_fd)
        return lock_fd
    except BlockingIOError as exc:
        if lock_fd >= 0:
            os.close(lock_fd)
        raise SoomfonCustodyError("evaluation suite is already running") from exc
    except Exception:
        if lock_fd >= 0:
            os.close(lock_fd)
        raise


def _record_bytes(payload: object) -> bytes:
    raw = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode()
    if len(raw) > _MAX_LEDGER_RECORD:
        raise SoomfonCustodyError("ledger record exceeds its bound")
    return raw


def _write_once(fd: int, raw: bytes) -> None:
    if os.write(fd, raw) != len(raw):
        raise SoomfonCustodyError("ledger write was incomplete")


def marker_sha256(marker_fd: int) -> str:
    """Hash one stable current marker before its terminal append."""

    try:
        before = os.fstat(marker_fd)
        raw = os.pread(marker_fd, before.st_size, 0)
        after = os.fstat(marker_fd)
    except OSError as exc:
        raise SoomfonCustodyError("ledger marker is unavailable") from exc
    if (
        before.st_size <= 0
        or len(raw) != before.st_size
        or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    ):
        raise SoomfonCustodyError("ledger marker identity drifts")
    return hashlib.sha256(raw).hexdigest()


def _marker_name(contract_sha256: str, mode: str) -> str:
    if (
        _SHA256_RE.fullmatch(contract_sha256) is None
        or contract_sha256 != REVIEWED_CONTRACT_SHA256
        or mode not in set(PROTECTED_MANIFESTS.values())
    ):
        raise SoomfonCustodyError("ledger key is invalid")
    return f"{contract_sha256}.{mode}.jsonl"


def reconcile_marker_indeterminate(
    *, ledger_fd: int, marker_name: str, reason: str
) -> None:
    marker_fd = os.open(
        marker_name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=ledger_fd
    )
    try:
        info = os.fstat(marker_fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o600
        ):
            raise SoomfonCustodyError("existing marker identity is invalid")
        if (
            reason != "terminal_persistence_failed"
            and not _reconciliation_sidecar_present(ledger_fd, marker_name)
            and _is_complete_terminal_marker(
                _read_marker_records(marker_fd),
                marker_name,
                evidence_hashes=_runtime_evidence_hashes(ledger_fd, marker_name),
            )
        ):
            return
    finally:
        os.close(marker_fd)
    payload = {
        "schema_version": _LEDGER_SCHEMA,
        "state": "effect_indeterminate",
        "reason": reason,
        "marker_name": marker_name,
        "latency_ms": None,
        "latency_disposition": "unknown_during_reconciliation",
    }
    canonical = f"{marker_name}.reconciled-indeterminate.json"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    for sidecar in (canonical, f"{canonical}.repair.json"):
        try:
            fd = os.open(sidecar, flags, 0o600, dir_fd=ledger_fd)
        except FileExistsError:
            try:
                fd = os.open(
                    sidecar,
                    os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=ledger_fd,
                )
            except OSError:
                continue
            try:
                info = os.fstat(fd)
                if (
                    stat.S_ISREG(info.st_mode)
                    and info.st_uid == os.geteuid()
                    and stat.S_IMODE(info.st_mode) == 0o600
                    and _valid_reconciliation_sidecar(fd, marker_name)
                ):
                    os.fsync(fd)
                    os.fsync(ledger_fd)
                    return
            finally:
                os.close(fd)
            continue
        try:
            _write_once(fd, _record_bytes(payload))
            os.fsync(fd)
            os.fsync(ledger_fd)
            return
        finally:
            os.close(fd)
    raise SoomfonCustodyError("indeterminate reconciliation sidecars are invalid")


def create_attempt_marker(
    *,
    ledger_fd: int,
    contract_sha256: str,
    mode: str,
    execution_task_id: int,
    authorization_sha256: str,
    ak_reconciliation_sha256: str,
) -> tuple[int, str]:
    name = _marker_name(contract_sha256, mode)
    if (
        isinstance(execution_task_id, bool)
        or not isinstance(execution_task_id, int)
        or execution_task_id <= CONTRACT_PREPARATION_TASK_ID
        or _SHA256_RE.fullmatch(authorization_sha256) is None
        or _SHA256_RE.fullmatch(ak_reconciliation_sha256) is None
    ):
        raise SoomfonCustodyError("execution authorization identity is invalid")
    flags = (
        os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        marker_fd = os.open(name, flags, 0o600, dir_fd=ledger_fd)
    except FileExistsError as exc:
        reconcile_marker_indeterminate(
            ledger_fd=ledger_fd,
            marker_name=name,
            reason="reconciled_existing_consumed_marker",
        )
        raise SoomfonCustodyError(
            f"evaluation attempt already consumed for {mode}"
        ) from exc
    record = {
        "schema_version": _LEDGER_SCHEMA,
        "contract_sha256": contract_sha256,
        "mode": mode,
        "execution_task_id": execution_task_id,
        "authorization_sha256": authorization_sha256,
        "ak_reconciliation_sha256": ak_reconciliation_sha256,
        "state": "attempted_outcome_unknown",
        "sequence": 0,
    }
    try:
        _write_once(marker_fd, _record_bytes(record))
        os.fsync(marker_fd)
        os.fsync(ledger_fd)
        return marker_fd, name
    except Exception:
        os.close(marker_fd)
        raise


def append_terminal(
    *,
    marker_fd: int,
    ledger_fd: int,
    contract_sha256: str,
    mode: str,
    state: str,
    details: Mapping[str, object],
) -> None:
    marker_name = _marker_name(contract_sha256, mode)
    if state not in {"succeeded", "failed_no_effect_proved", "effect_indeterminate"}:
        raise SoomfonCustodyError("terminal state is invalid")
    latency = details.get("latency_ms")
    if not isinstance(latency, int) or isinstance(latency, bool) or latency < 0:
        raise SoomfonCustodyError("terminal latency evidence is invalid")
    current = _read_marker_records(marker_fd)
    initial = current[0] if current is not None and len(current) == 1 else {}
    record = {
        "schema_version": _LEDGER_SCHEMA,
        "contract_sha256": contract_sha256,
        "mode": mode,
        "execution_task_id": initial.get("execution_task_id"),
        "authorization_sha256": initial.get("authorization_sha256"),
        "ak_reconciliation_sha256": initial.get("ak_reconciliation_sha256"),
        "state": state,
        "sequence": 1,
        "details": dict(details),
    }
    candidate = [*current, record] if current is not None else None
    evidence_hashes = _runtime_evidence_hashes(ledger_fd, marker_name)
    if not _is_complete_terminal_marker(
        candidate,
        marker_name,
        evidence_hashes=evidence_hashes,
    ):
        raise SoomfonCustodyError("terminal evidence is invalid")
    _write_once(marker_fd, _record_bytes(record))
    os.fsync(marker_fd)
    if not _is_complete_terminal_marker(
        _read_marker_records(marker_fd),
        marker_name,
        evidence_hashes=_runtime_evidence_hashes(ledger_fd, marker_name),
    ):
        raise SoomfonCustodyError("persisted terminal evidence is invalid")
    os.fsync(ledger_fd)


def _claim_child_dispatch(
    *,
    ledger_fd: int,
    contract_sha256: str,
    mode: str,
    execution_task_id: int,
    authorization_sha256: str,
    ak_reconciliation_sha256: str,
) -> None:
    name = f"{_marker_name(contract_sha256, mode)}.child-claim.json"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(name, flags, 0o600, dir_fd=ledger_fd)
    except FileExistsError as exc:
        raise SoomfonCustodyError(
            "protected candidate child claim is consumed"
        ) from exc
    try:
        _write_once(
            fd,
            _record_bytes(
                {
                    "schema_version": _LEDGER_SCHEMA,
                    "contract_sha256": contract_sha256,
                    "mode": mode,
                    "execution_task_id": execution_task_id,
                    "authorization_sha256": authorization_sha256,
                    "ak_reconciliation_sha256": ak_reconciliation_sha256,
                    "state": "child_dispatch_claimed",
                }
            ),
        )
        os.fsync(fd)
        os.fsync(ledger_fd)
    finally:
        os.close(fd)


def validate_runtime_custody(
    *,
    manifest_path: Path,
    manifest_sha256: str,
    inputs_path: Path,
    outdir: Path,
    custody: SoomfonRuntimeCustody | None,
) -> object | None:
    mode = PROTECTED_MANIFESTS.get(manifest_sha256)
    if mode is None:
        if custody is not None:
            raise SoomfonCustodyError(
                "custody cannot authorize an unprotected manifest"
            )
        return None
    if custody is None:
        raise SoomfonCustodyError(
            "protected Soomfon candidate requires executor custody"
        )
    if (
        custody.contract_sha256 != REVIEWED_CONTRACT_SHA256
        or custody.mode != mode
        or custody.expected_manifest_sha256 != manifest_sha256
        or custody.expected_inputs_sha256 != EXPECTED_INPUT_SHA256[mode]
        or custody.expected_receipt_sha256 != EXPECTED_RECEIPT_SHA256[mode]
        or custody.staged_manifest_path != manifest_path.resolve()
        or custody.inputs_path != inputs_path.resolve()
        or custody.outdir != outdir.resolve()
        or custody.execution_task_id <= CONTRACT_PREPARATION_TASK_ID
        or _SHA256_RE.fullmatch(custody.authorization_sha256) is None
        or _SHA256_RE.fullmatch(custody.ak_reconciliation_sha256) is None
    ):
        raise SoomfonCustodyError("protected candidate custody identity drifts")
    suite_root = default_state_root().absolute() / custody.contract_sha256
    expected_ledger = suite_root / "ledger"
    expected_marker = expected_ledger / _marker_name(custody.contract_sha256, mode)
    expected_lock = suite_root / "suite.lock"
    expected_raw = suite_root / "raw" / mode
    expected_stage = suite_root / "stage" / mode / "manifest.json"
    expected_journal = suite_root / "provider-outcomes" / mode
    expected_inputs = expected_raw / "inputs.json"
    expected_outdir = expected_raw / "runtime"
    try:
        observed = {
            "marker": Path(f"/proc/self/fd/{custody.marker_fd}").resolve(strict=True),
            "ledger": Path(f"/proc/self/fd/{custody.ledger_fd}").resolve(strict=True),
            "lock": Path(f"/proc/self/fd/{custody.lock_fd}").resolve(strict=True),
            "raw": Path(f"/proc/self/fd/{custody.raw_root_fd}").resolve(strict=True),
            "runtime": Path(f"/proc/self/fd/{custody.runtime_fd}").resolve(strict=True),
            "provider_journal": Path(
                f"/proc/self/fd/{custody.provider_journal_fd}"
            ).resolve(strict=True),
        }
    except OSError as exc:
        raise SoomfonCustodyError(
            "protected candidate custody FD path is unavailable"
        ) from exc
    if (
        observed
        != {
            "marker": expected_marker,
            "ledger": expected_ledger,
            "lock": expected_lock,
            "raw": expected_raw,
            "runtime": expected_outdir,
            "provider_journal": expected_journal,
        }
        or manifest_path.resolve() != expected_stage
        or inputs_path.resolve() != expected_inputs
        or outdir.resolve() != expected_outdir
    ):
        raise SoomfonCustodyError("protected candidate custody path drifts")
    for fd, expected_type, expected_mode in (
        (custody.marker_fd, stat.S_ISREG, 0o600),
        (custody.ledger_fd, stat.S_ISDIR, 0o700),
        (custody.lock_fd, stat.S_ISREG, 0o600),
        (custody.raw_root_fd, stat.S_ISDIR, 0o700),
        (custody.runtime_fd, stat.S_ISDIR, 0o700),
        (custody.provider_journal_fd, stat.S_ISDIR, 0o700),
    ):
        info = os.fstat(fd)
        if (
            not expected_type(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != expected_mode
        ):
            raise SoomfonCustodyError("protected candidate custody FD is invalid")
    fcntl.flock(custody.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    records = _read_marker_records(custody.marker_fd)
    if records is None or len(records) != 1:
        raise SoomfonCustodyError("protected candidate marker is already consumed")
    record = records[0]
    if (
        record.get("schema_version") != _LEDGER_SCHEMA
        or record.get("contract_sha256") != custody.contract_sha256
        or record.get("mode") != mode
        or record.get("execution_task_id") != custody.execution_task_id
        or record.get("authorization_sha256") != custody.authorization_sha256
        or record.get("ak_reconciliation_sha256") != custody.ak_reconciliation_sha256
        or record.get("state") != "attempted_outcome_unknown"
        or record.get("sequence") != 0
    ):
        raise SoomfonCustodyError("protected candidate marker identity drifts")
    from dspx.services.soomfon_evaluation_contract import (
        validate_exact_provider_environment,
        validate_exact_runtime_identity,
    )
    from dspx.services.soomfon_evaluation_provider import (
        verify_soomfon_owner_source,
    )

    verify_soomfon_owner_source(custody.owner_source_root)
    validate_exact_runtime_identity()
    validate_exact_provider_environment(os.environ)
    if not _prior_modes_succeeded(custody.ledger_fd, mode):
        raise SoomfonCustodyError("protected candidate mode order is invalid")
    from dspx.services.soomfon_evaluation_snapshot import _capture_runtime_snapshot

    snapshot = _capture_runtime_snapshot(
        manifest_path=manifest_path, inputs_path=inputs_path, custody=custody
    )
    _claim_child_dispatch(
        ledger_fd=custody.ledger_fd,
        contract_sha256=custody.contract_sha256,
        mode=mode,
        execution_task_id=custody.execution_task_id,
        authorization_sha256=custody.authorization_sha256,
        ak_reconciliation_sha256=custody.ak_reconciliation_sha256,
    )
    return snapshot
