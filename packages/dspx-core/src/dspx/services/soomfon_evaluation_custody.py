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
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from dspx.services.soomfon_evaluation_contract import (
    EXPECTED_INPUT_SHA256,
    EXPECTED_RECEIPT_SHA256,
    REVIEWED_CONTRACT_SHA256,
)

from dspx.services.soomfon_evaluation_filesystem import (
    SoomfonCustodyError,
    ensure_private_tree as ensure_private_tree,
    fsync_private_tree as fsync_private_tree,
    open_private_directory as open_private_directory,
    stable_source_bytes,
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


PROTECTED_MANIFESTS = {
    "aa0b473e7f0cd056246149eacfcb25c5ed023ab61a1b9410103443e68c30fac1": "simple",
    "1304cc07864c241ab9b66e19589394e729640204996b317c0286c628d8e727cd": "elaborate",
    "bc3fbd7dc5d4993d93ee1af9737be7d12720d67a4df7793509e171e094cfe051": "researched",
    "03e4d23e6d0eede3cd474d5d84d8fc1091e3c52c3b5c318f4b9be686e71c09fa": "deep-research",
    "01b28caa003943e616ad07815870f1abb0f200d0990e52f487271c79ed855fac": "socratic",
    "087994808d60ee46b7283c4d8f0b7c269323c016c392d1e9bdee075abe8a53ba": "bloom",
    "ed0fd9db0268aef35fa5cd7314800b26a66864afd384271785fb0a09b5b24cd4": "simple",
    "7025d592f61b3afe70440ca3f3420736998cd286ed47761596f3e9458538f699": "elaborate",
    "69696b0d12cb0694b0a63ea3270bb7503df2a70f9112e51a5a152307f104aa5c": "researched",
    "8aebeda59ab883211c5318208f53086febc802e195170442cf6c0bc4c62fab5c": "deep-research",
    "ce43ee0674fd1adc1141f929d12cc897f8537bbd8be15475110e62d5d2810f95": "socratic",
    "77dc9cf7bf265f719160e4eea6547801255ad745b92b886a46b8cc0c672f39a0": "bloom",
}
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
    *, ledger_fd: int, contract_sha256: str, mode: str
) -> tuple[int, str]:
    name = _marker_name(contract_sha256, mode)
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
    record = {
        "schema_version": _LEDGER_SCHEMA,
        "contract_sha256": contract_sha256,
        "mode": mode,
        "state": state,
        "sequence": 1,
        "details": dict(details),
    }
    current = _read_marker_records(marker_fd)
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


def _claim_child_dispatch(*, ledger_fd: int, contract_sha256: str, mode: str) -> None:
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
                    "state": "child_dispatch_claimed",
                }
            ),
        )
        os.fsync(fd)
        os.fsync(ledger_fd)
    finally:
        os.close(fd)


def _json_object(raw: bytes, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SoomfonCustodyError(f"protected {label} JSON is invalid") from exc
    if not isinstance(payload, dict):
        raise SoomfonCustodyError(f"protected {label} is not an object")
    return payload


def _capture_runtime_snapshot(
    *, manifest_path: Path, inputs_path: Path, custody: SoomfonRuntimeCustody
) -> object:
    from dspx.services.soomfon_evaluation_runtime import (
        SoomfonRuntimeSnapshot,
        verified_surface_declarations,
    )

    manifest_raw = stable_source_bytes(
        manifest_path, expected_sha256=custody.expected_manifest_sha256
    )
    manifest = _json_object(manifest_raw, label="manifest")
    inputs_raw = stable_source_bytes(
        inputs_path, expected_sha256=custody.expected_inputs_sha256
    )
    inputs_payload = _json_object(inputs_raw, label="inputs")
    nested_inputs = inputs_payload.get("inputs")
    if not isinstance(nested_inputs, dict) or not nested_inputs:
        raise SoomfonCustodyError("protected candidate inputs are invalid")
    receipt_raw = stable_source_bytes(
        manifest_path.with_name("manifest.json.meta.json"),
        expected_sha256=custody.expected_receipt_sha256,
    )
    receipt_sha256 = hashlib.sha256(receipt_raw).hexdigest()
    sources: dict[str, str] = {}
    module_surfaces: dict[str, Any] = {"module_surfaces": []}
    seen: set[PurePosixPath] = set()
    for declaration in verified_surface_declarations(manifest):
        relative = PurePosixPath(declaration["path"])
        if (
            relative.is_absolute()
            or not relative.parts
            or any(part in {"", ".", ".."} for part in relative.parts)
            or relative in seen
        ):
            raise SoomfonCustodyError("protected candidate surface path is invalid")
        seen.add(relative)
        if relative.name == manifest_path.name:
            continue
        raw = stable_source_bytes(
            manifest_path.parent.joinpath(*relative.parts),
            expected_sha256=declaration["content_hash"],
        )
        if relative.as_posix() in {"program.py", "module.py", "signature.py"}:
            try:
                sources[relative.stem] = raw.decode("utf-8")
            except UnicodeError as exc:
                raise SoomfonCustodyError(
                    "protected candidate source is not UTF-8"
                ) from exc
        elif relative.as_posix() == "module_surfaces.json":
            module_surfaces = _json_object(raw, label="module surfaces")
    if "program" not in sources:
        raise SoomfonCustodyError("protected candidate program source is missing")
    return SoomfonRuntimeSnapshot(
        manifest_path=manifest_path,
        manifest_sha256=custody.expected_manifest_sha256,
        manifest_payload=manifest,
        receipt_sha256=receipt_sha256,
        runtime_inputs={str(key): value for key, value in nested_inputs.items()},
        surface_sources=sources,
        module_surfaces=module_surfaces,
    )


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
    ):
        raise SoomfonCustodyError("protected candidate custody identity drifts")
    suite_root = default_state_root().absolute() / custody.contract_sha256
    expected_ledger = suite_root / "ledger"
    expected_marker = expected_ledger / _marker_name(custody.contract_sha256, mode)
    expected_lock = suite_root / "suite.lock"
    expected_raw = suite_root / "raw" / mode
    expected_stage = suite_root / "stage" / mode / "manifest.json"
    expected_inputs = expected_raw / "inputs.json"
    expected_outdir = expected_raw / "runtime"
    try:
        observed = {
            "marker": Path(f"/proc/self/fd/{custody.marker_fd}").resolve(strict=True),
            "ledger": Path(f"/proc/self/fd/{custody.ledger_fd}").resolve(strict=True),
            "lock": Path(f"/proc/self/fd/{custody.lock_fd}").resolve(strict=True),
            "raw": Path(f"/proc/self/fd/{custody.raw_root_fd}").resolve(strict=True),
            "runtime": Path(f"/proc/self/fd/{custody.runtime_fd}").resolve(strict=True),
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
        or record.get("state") != "attempted_outcome_unknown"
        or record.get("sequence") != 0
    ):
        raise SoomfonCustodyError("protected candidate marker identity drifts")
    from dspx.services.soomfon_evaluation_contract import (
        validate_exact_provider_environment,
        validate_exact_runtime_identity,
    )

    validate_exact_runtime_identity()
    validate_exact_provider_environment(os.environ)
    if not _prior_modes_succeeded(custody.ledger_fd, mode):
        raise SoomfonCustodyError("protected candidate mode order is invalid")
    snapshot = _capture_runtime_snapshot(
        manifest_path=manifest_path, inputs_path=inputs_path, custody=custody
    )
    _claim_child_dispatch(
        ledger_fd=custody.ledger_fd,
        contract_sha256=custody.contract_sha256,
        mode=mode,
    )
    return snapshot
