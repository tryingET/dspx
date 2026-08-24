"""Strict parsing for the no-replace Soomfon attempt ledger."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from pathlib import Path
from typing import Any, Mapping

from dspx.services.run_replay_service import check_run_receipt
from dspx.services.soomfon_evaluation_filesystem import open_private_directory

from dspx.services.soomfon_evaluation_contract import (
    CONTRACT_PREPARATION_TASK_ID,
    classify_provider_disposition,
    EXPECTED_MODES,
    REVIEWED_CONTRACT_SHA256,
)

LEDGER_SCHEMA = "soomfon-dspy33-attempt-ledger-v1"
MAX_LEDGER_RECORD = 4096
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_EVIDENCE_FILE_BYTES = 32 * 1024 * 1024


def _marker_mode(marker_name: str) -> str | None:
    prefix, suffix = f"{REVIEWED_CONTRACT_SHA256}.", ".jsonl"
    if not marker_name.startswith(prefix) or not marker_name.endswith(suffix):
        return None
    mode = marker_name[len(prefix) : -len(suffix)]
    return mode if mode in EXPECTED_MODES else None


def _open_private_directory_at(parent_fd: int, name: str) -> int:
    fd = os.open(
        name,
        os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
        dir_fd=parent_fd,
    )
    info = os.fstat(fd)
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        os.close(fd)
        raise OSError("runtime evidence directory identity is invalid")
    return fd


def _read_private_file_at(parent_fd: int, name: str) -> tuple[bytes, str]:
    fd = os.open(
        name,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
        dir_fd=parent_fd,
    )
    try:
        before = os.fstat(fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.geteuid()
            or stat.S_IMODE(before.st_mode) != 0o600
            or before.st_nlink != 1
            or before.st_size > _MAX_EVIDENCE_FILE_BYTES
        ):
            raise OSError("runtime evidence file identity is invalid")
        raw = bytearray()
        offset = 0
        while offset < before.st_size:
            chunk = os.pread(fd, min(65536, before.st_size - offset), offset)
            if not chunk:
                raise OSError("runtime evidence file read was incomplete")
            raw.extend(chunk)
            offset += len(chunk)
        after = os.fstat(fd)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise OSError("runtime evidence file changed while hashing")
        content = bytes(raw)
        return content, hashlib.sha256(content).hexdigest()
    finally:
        os.close(fd)


def private_runtime_tree_sha256(root_fd: int) -> str:
    digest = hashlib.sha256()
    seen = 0

    def visit(directory_fd: int, prefix: str) -> None:
        nonlocal seen
        for name in sorted(os.listdir(directory_fd)):
            seen += 1
            if seen > 512:
                raise OSError("runtime evidence tree is too large")
            relative = f"{prefix}{name}"
            info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if info.st_uid != os.geteuid() or stat.S_ISLNK(info.st_mode):
                raise OSError("runtime evidence tree identity is invalid")
            if stat.S_ISDIR(info.st_mode):
                if stat.S_IMODE(info.st_mode) != 0o700:
                    raise OSError("runtime evidence directory mode is invalid")
                child_fd = _open_private_directory_at(directory_fd, name)
                try:
                    digest.update(b"D\0" + relative.encode() + b"\0")
                    visit(child_fd, f"{relative}/")
                finally:
                    os.close(child_fd)
            elif stat.S_ISREG(info.st_mode):
                _, file_sha256 = _read_private_file_at(directory_fd, name)
                digest.update(
                    b"F\0" + relative.encode() + b"\0" + file_sha256.encode() + b"\0"
                )
            else:
                raise OSError("runtime evidence tree type is invalid")

    visit(root_fd, "")
    return digest.hexdigest()


def private_runtime_tree_sha256_path(path: Path) -> str:
    fd = open_private_directory(path)
    try:
        return private_runtime_tree_sha256(fd)
    finally:
        os.close(fd)


def runtime_evidence_hashes(
    ledger_fd: int, marker_name: str
) -> dict[str, object] | None:
    """Bind terminal claims to private runtime evidence via directory descriptors."""

    mode = _marker_mode(marker_name)
    if mode is None:
        return None
    opened: list[int] = []
    try:
        suite_fd = _open_private_directory_at(ledger_fd, "..")
        opened.append(suite_fd)
        raw_fd = _open_private_directory_at(suite_fd, "raw")
        opened.append(raw_fd)
        mode_fd = _open_private_directory_at(raw_fd, mode)
        opened.append(mode_fd)
        runtime_fd = _open_private_directory_at(mode_fd, "runtime")
        opened.append(runtime_fd)
        runtime_tree_sha256 = private_runtime_tree_sha256(runtime_fd)
        runtime_raw, runtime_sha256 = _read_private_file_at(
            runtime_fd, "runtime_episode.json"
        )
        behavior_raw, behavior_sha256 = _read_private_file_at(
            runtime_fd, "behavior_results.json"
        )
        receipt_name = "runtime_episode.json.meta.json"
        receipt_raw, receipt_sha256 = _read_private_file_at(runtime_fd, receipt_name)
        receipt_path = Path(f"/proc/self/fd/{runtime_fd}") / receipt_name
        if check_run_receipt(receipt_path).get("status") != "ok":
            return None
        runtime_payload = json.loads(runtime_raw)
        behavior_payload = json.loads(behavior_raw)
        if not isinstance(runtime_payload, dict) or not isinstance(
            behavior_payload, dict
        ):
            return None
        artifact_hashes = runtime_payload.get("artifact_hashes")
        output_files = runtime_payload.get("output_files")
        required_artifacts = {
            "runtime_inputs.json": "runtime_inputs_sha256",
            "behavior_results.json": "behavior_results_sha256",
            "program_runtime_traces.json": "program_runtime_traces_sha256",
            "oracle_evidence.json": "oracle_evidence_sha256",
        }
        required_names = {
            "manifest.json",
            "runtime_episode.json",
            receipt_name,
            *required_artifacts,
        }
        entries = set(os.listdir(runtime_fd))
        if (
            not isinstance(artifact_hashes, dict)
            or not isinstance(output_files, list)
            or not required_names <= entries
            or any(
                not isinstance(name, str)
                or name in {"", ".", ".."}
                or "/" in name
                or name not in entries
                for name in output_files
            )
        ):
            return None
        for filename, hash_key in required_artifacts.items():
            _, observed_sha256 = _read_private_file_at(runtime_fd, filename)
            if artifact_hashes.get(hash_key) != observed_sha256:
                return None
        for output_name in output_files:
            _read_private_file_at(runtime_fd, output_name)
        provider_state, provider = classify_provider_disposition(behavior_payload)
        examples = behavior_payload.get("examples")
        response: object = None
        if (
            isinstance(examples, list)
            and len(examples) == 1
            and isinstance(examples[0], dict)
        ):
            outputs = examples[0].get("observed_outputs")
            if isinstance(outputs, dict):
                response = outputs.get("response")
        evidence: dict[str, object] = {
            "runtime_episode_sha256": runtime_sha256,
            "runtime_tree_sha256": runtime_tree_sha256,
            "runtime_receipt_sha256": receipt_sha256,
            "behavior_results_sha256": behavior_sha256,
            "runtime_execution_status": runtime_payload.get("execution_status"),
            "provider_state": provider_state,
            "provider": provider,
        }
        if isinstance(response, str) and response.strip():
            evidence["response_sha256"] = hashlib.sha256(response.encode()).hexdigest()
            evidence["response_length"] = len(response)
        return evidence
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    finally:
        for fd in reversed(opened):
            os.close(fd)


def read_marker_records(marker_fd: int) -> list[dict[str, Any]] | None:
    raw = os.pread(marker_fd, MAX_LEDGER_RECORD * 2 + 1, 0)
    if not raw.endswith(b"\n") or len(raw) > MAX_LEDGER_RECORD * 2:
        return None
    try:
        records = [json.loads(line) for line in raw.splitlines()]
    except (UnicodeError, json.JSONDecodeError):
        return None
    if not records or not all(isinstance(record, dict) for record in records):
        return None
    return records


def is_complete_terminal_marker(
    records: list[dict[str, Any]] | None,
    marker_name: str,
    *,
    evidence_hashes: Mapping[str, object] | None = None,
) -> bool:
    mode = _marker_mode(marker_name)
    if records is None or len(records) != 2 or mode is None:
        return False
    first, terminal = records
    details = terminal.get("details")
    latency = details.get("latency_ms") if isinstance(details, dict) else None
    identity = (
        first.get("schema_version") == LEDGER_SCHEMA
        and first.get("contract_sha256") == REVIEWED_CONTRACT_SHA256
        and first.get("mode") == mode
        and type(first.get("execution_task_id")) is int
        and first["execution_task_id"] > CONTRACT_PREPARATION_TASK_ID
        and isinstance(first.get("authorization_sha256"), str)
        and _SHA256_RE.fullmatch(first["authorization_sha256"]) is not None
        and isinstance(first.get("ak_reconciliation_sha256"), str)
        and _SHA256_RE.fullmatch(first["ak_reconciliation_sha256"]) is not None
        and first.get("state") == "attempted_outcome_unknown"
        and first.get("sequence") == 0
        and terminal.get("schema_version") == LEDGER_SCHEMA
        and terminal.get("contract_sha256") == REVIEWED_CONTRACT_SHA256
        and terminal.get("mode") == mode
        and terminal.get("execution_task_id") == first.get("execution_task_id")
        and terminal.get("authorization_sha256") == first.get("authorization_sha256")
        and terminal.get("sequence") == 1
        and isinstance(latency, int)
        and not isinstance(latency, bool)
        and latency >= 0
    )
    if not identity or not isinstance(details, dict):
        return False
    state = terminal.get("state")
    provider = details.get("provider")
    call_records = provider.get("call_records") if isinstance(provider, dict) else None
    logical_call_total = (
        provider.get("logical_call_total") if isinstance(provider, dict) else None
    )
    runtime_hashes_valid = evidence_hashes is not None and all(
        isinstance(details.get(key), str)
        and _SHA256_RE.fullmatch(details[key]) is not None
        and details[key] == evidence_hashes.get(key)
        for key in (
            "runtime_episode_sha256",
            "runtime_tree_sha256",
            "runtime_receipt_sha256",
            "behavior_results_sha256",
        )
    )
    response_hash = details.get("response_sha256")
    response_hash_valid = (
        isinstance(response_hash, str)
        and _SHA256_RE.fullmatch(response_hash) is not None
    )
    provider_shape = (
        isinstance(provider, dict)
        and provider.get("mode") == mode
        and provider.get("artifact_verification") == "accepted_exact"
        and type(logical_call_total) is int
        and logical_call_total == 2
        and provider.get("maximum_provider_transports") == 2
        and isinstance(call_records, list)
        and len(call_records) == logical_call_total
        and all(
            isinstance(item, dict)
            and item.get("call_ordinal") == index
            and item.get("provider_outcome_receipt") == "accepted"
            and item.get("request_acknowledged") is True
            and item.get("external_effect_possible") is True
            and item.get("producer_terminal") == "provider_response_completed"
            and item.get("empirical_disposition") == "not_evaluated"
            for index, item in enumerate(call_records, start=1)
        )
    )
    provider_evidence_valid = (
        evidence_hashes is not None and evidence_hashes.get("provider") == provider
    )
    if state == "succeeded":
        return (
            set(details)
            == {
                "latency_ms",
                "runtime_episode_sha256",
                "runtime_tree_sha256",
                "runtime_receipt_sha256",
                "behavior_results_sha256",
                "provider",
                "response_sha256",
                "response_length",
            }
            and runtime_hashes_valid
            and response_hash_valid
            and evidence_hashes is not None
            and evidence_hashes.get("runtime_execution_status") == "executed"
            and evidence_hashes.get("provider_state") == "succeeded"
            and provider_evidence_valid
            and evidence_hashes.get("response_sha256") == response_hash
            and evidence_hashes.get("response_length") == details.get("response_length")
            and type(details.get("response_length")) is int
            and details["response_length"] > 0
            and provider_shape
        )
    if state == "failed_no_effect_proved":
        return False
    return state == "effect_indeterminate" and (
        isinstance(details.get("reason"), str) or isinstance(provider, dict)
    )


def reconciliation_sidecar_present(ledger_fd: int, marker_name: str) -> bool:
    canonical = f"{marker_name}.reconciled-indeterminate.json"
    for sidecar in (canonical, f"{canonical}.repair.json"):
        try:
            fd = os.open(
                sidecar,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=ledger_fd,
            )
        except FileNotFoundError:
            continue
        except OSError:
            return True
        else:
            os.close(fd)
            return True
    return False


def prior_modes_succeeded(ledger_fd: int, mode: str) -> bool:
    if mode not in EXPECTED_MODES:
        return False
    for predecessor in EXPECTED_MODES[: EXPECTED_MODES.index(mode)]:
        marker_name = f"{REVIEWED_CONTRACT_SHA256}.{predecessor}.jsonl"
        if reconciliation_sidecar_present(ledger_fd, marker_name):
            return False
        try:
            marker_fd = os.open(
                marker_name,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=ledger_fd,
            )
        except OSError:
            return False
        try:
            info = os.fstat(marker_fd)
            records = read_marker_records(marker_fd)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o600
                or not is_complete_terminal_marker(
                    records,
                    marker_name,
                    evidence_hashes=runtime_evidence_hashes(ledger_fd, marker_name),
                )
                or records is None
                or records[1].get("state") != "succeeded"
            ):
                return False
        finally:
            os.close(marker_fd)
    return True


def valid_reconciliation_sidecar(sidecar_fd: int, marker_name: str) -> bool:
    raw = os.pread(sidecar_fd, MAX_LEDGER_RECORD + 1, 0)
    if not raw.endswith(b"\n") or len(raw) > MAX_LEDGER_RECORD:
        return False
    try:
        payload = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError):
        return False
    return (
        isinstance(payload, dict)
        and payload
        == {
            "schema_version": LEDGER_SCHEMA,
            "state": "effect_indeterminate",
            "reason": payload.get("reason"),
            "marker_name": marker_name,
            "latency_ms": None,
            "latency_disposition": "unknown_during_reconciliation",
        }
        and isinstance(payload.get("reason"), str)
        and bool(payload["reason"])
    )


__all__ = [
    "LEDGER_SCHEMA",
    "MAX_LEDGER_RECORD",
    "is_complete_terminal_marker",
    "prior_modes_succeeded",
    "reconciliation_sidecar_present",
    "read_marker_records",
    "runtime_evidence_hashes",
    "valid_reconciliation_sidecar",
]
