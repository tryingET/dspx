# summary: "Defines receipt-bound local replay helpers and evidence for deterministic generated-program runtime episodes."
# read_when:
#   - "Changing runtime replay identity checks, output publication, or replay evidence."

"""Receipt-bound local replay for deterministic generated-program runtime episodes."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from pathlib import Path
from typing import Any, Mapping, cast

from dspx.provider_runtime import sanitize_text

PROGRAM_RUNTIME_REPLAY_STRATEGY = "program-runtime-local-reexecution"
PROGRAM_RUNTIME_REPLAY_EVIDENCE_SCHEMA = "program-execution-replay-evidence-v2"
_MAX_JSON_BYTES = 5_000_000
_MAX_DIAGNOSTIC_CHARS = 20_000
_ALLOWED_ENVIRONMENT_KEYS = {
    "LANG",
    "LC_ALL",
    "PATH",
    "SYSTEMROOT",
    "TMPDIR",
    "VIRTUAL_ENV",
    "WINDIR",
}
_EFFECTS: dict[str, bool] = {
    "network_access_requested": False,
    "network_isolation_enforced": False,
    "provider_call": False,
    "mlflow": False,
    "subprocess": True,
    "temporary_filesystem": True,
    "external_filesystem_access_requested": False,
    "external_filesystem_isolation_enforced": False,
    "source_artifact_write": False,
    "shared_oracle": False,
    "external_authority_mutation_requested": False,
    "explicit_replay_output_write": True,
}


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _canonical_hash(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as stream:
        while chunk := stream.read(64 * 1024):
            total += len(chunk)
            if total > _MAX_JSON_BYTES:
                raise ValueError(
                    f"replay artifact exceeds {_MAX_JSON_BYTES}-byte limit: {path}"
                )
            digest.update(chunk)
    return digest.hexdigest()


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be a regular non-symlink file: {path}")
    if path.stat().st_size > _MAX_JSON_BYTES:
        raise ValueError(f"{label} exceeds {_MAX_JSON_BYTES}-byte limit: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return cast(dict[str, Any], payload)


def _safe_mapping(value: object) -> dict[str, Any]:
    return (
        {str(key): item for key, item in value.items()}
        if isinstance(value, Mapping)
        else {}
    )


def _add_error(
    report: dict[str, Any], *, code: str, message: str, status: str = "failed"
) -> dict[str, Any]:
    report["status"] = status
    sanitized = sanitize_text(message, limit=500)
    report.setdefault("errors", []).append(sanitized)
    report.setdefault("error_codes", []).append(code)
    report.setdefault("error_details", []).append({"code": code, "message": sanitized})
    return report


def _hash_tree(root: Path) -> dict[str, str]:
    if root.is_symlink() or not root.is_dir():
        raise ValueError(f"replay source root must be a directory: {root}")
    result: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"replay source tree contains symlink: {path}")
        if path.is_file():
            result[path.relative_to(root).as_posix()] = _sha256_file(path)
    return result


def _resolved_bound_path(value: object, *, expected_hash: object, label: str) -> Path:
    text = str(value or "").strip()
    expected = str(expected_hash or "").strip()
    if not text or len(expected) != 64:
        raise ValueError(f"{label} path/hash binding is incomplete")
    path = Path(text).expanduser()
    if path.is_symlink():
        raise ValueError(f"{label} must not be a symlink")
    resolved = path.resolve()
    if not resolved.is_file() or _sha256_file(resolved) != expected:
        raise ValueError(f"{label} current hash does not match receipt")
    return resolved


def _prepare_replay_target(meta_path: Path, replay_output: Path) -> Path:
    receipt_root = meta_path.expanduser().resolve().parent
    raw = replay_output.expanduser()
    target = raw if raw.is_absolute() else receipt_root / raw
    if target.is_symlink():
        raise FileExistsError(f"replay output already exists: {target}")
    target = Path(os.path.abspath(target))
    try:
        relative = target.relative_to(receipt_root)
    except ValueError as exc:
        raise ValueError(
            "replay output must stay inside the receipt directory"
        ) from exc
    if not relative.parts or target.name.endswith(".meta.json"):
        raise ValueError("replay output must be a new non-receipt JSON file")
    current = receipt_root
    for component in relative.parts[:-1]:
        current /= component
        if current.is_symlink() or not current.is_dir():
            raise ValueError(
                "replay output parent must be an existing non-symlink directory"
            )
    if target.exists():
        raise FileExistsError(f"replay output already exists: {target}")
    return target


def _open_directory_no_symlinks(path: Path) -> int:
    absolute = Path(os.path.abspath(path))
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(absolute.anchor, flags)
    try:
        for component in absolute.parts[1:]:
            next_descriptor = os.open(component, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _exclusive_publish(
    *, receipt_root: Path, target: Path, payload: Mapping[str, Any]
) -> int:
    relative = target.relative_to(receipt_root)
    parent_fd = _open_directory_no_symlinks(receipt_root)
    directory_flags = (
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        for component in relative.parts[:-1]:
            next_descriptor = os.open(component, directory_flags, dir_fd=parent_fd)
            os.close(parent_fd)
            parent_fd = next_descriptor
    except Exception:
        os.close(parent_fd)
        raise
    target_name = relative.parts[-1]
    temporary_name = f".{target_name}.{secrets.token_hex(12)}.tmp"
    descriptor = -1
    published = False
    try:
        descriptor = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=parent_fd,
        )
        content = (
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode(
                "utf-8"
            )
            + b"\n"
        )
        written = 0
        while written < len(content):
            count = os.write(descriptor, content[written:])
            if count <= 0:
                raise OSError("replay evidence write made no progress")
            written += count
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.link(
            temporary_name,
            target_name,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
            follow_symlinks=False,
        )
        published = True
        os.unlink(temporary_name, dir_fd=parent_fd)
        os.fsync(parent_fd)
        return len(content)
    except Exception:
        if published:
            try:
                os.unlink(target_name, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
        raise
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            os.unlink(temporary_name, dir_fd=parent_fd)
        except FileNotFoundError:
            pass
        os.close(parent_fd)


def _observed_outputs(bundle_behavior: Mapping[str, Any]) -> dict[str, Any]:
    examples = bundle_behavior.get("examples")
    if (
        not isinstance(examples, list)
        or len(examples) != 1
        or not isinstance(examples[0], Mapping)
    ):
        raise ValueError("runtime behavior evidence must contain exactly one record")
    outputs = examples[0].get("observed_outputs")
    if not isinstance(outputs, Mapping):
        raise ValueError("runtime behavior evidence has no observed outputs")
    return {str(key): value for key, value in outputs.items()}


def _build_replay_evidence(
    *,
    stdout: str,
    stderr: str,
    source_receipt_hash: str,
    manifest_hash: str,
    candidate_receipt_hash: str,
    expected: Mapping[str, Any],
    reproduction_checks: Mapping[str, bool],
    behavior_results_hash: str,
    runtime_traces_hash: object,
    oracle_evidence_hash: object,
    observed_outputs_hash: str,
) -> dict[str, Any]:
    return {
        "schema_version": PROGRAM_RUNTIME_REPLAY_EVIDENCE_SCHEMA,
        "status": "execution_reproduced",
        "strategy": PROGRAM_RUNTIME_REPLAY_STRATEGY,
        "source_receipt_sha256": source_receipt_hash,
        "candidate_manifest_sha256": manifest_hash,
        "candidate_receipt_sha256": candidate_receipt_hash,
        "runtime_episode_id": expected.get("runtime_episode_id"),
        "contract_mode": expected.get("contract_mode"),
        "execution_status": expected.get("execution_status"),
        "behavior_status": expected.get("status"),
        "quality_status": expected.get("quality_status"),
        "quality_evaluation_sha256": expected.get("quality_evaluation_sha256"),
        "behavior_quality_approved": False,
        "checks": dict(reproduction_checks),
        "fresh": {
            "behavior_results_sha256": behavior_results_hash,
            "program_runtime_traces_sha256": runtime_traces_hash,
            "oracle_evidence_sha256": oracle_evidence_hash,
            "observed_outputs_sha256": observed_outputs_hash,
        },
        "subprocess": {
            "returncode": 0,
            "stdout_sha256": hashlib.sha256(stdout.encode()).hexdigest(),
            "stderr_sha256": hashlib.sha256(stderr.encode()).hexdigest(),
            "stdout_preview": sanitize_text(stdout[-_MAX_DIAGNOSTIC_CHARS:], limit=500),
            "stderr_preview": sanitize_text(stderr[-_MAX_DIAGNOSTIC_CHARS:], limit=500),
        },
        "effects": dict(_EFFECTS),
        "non_authority": {
            "promotion_authority": False,
            "activation_authority": False,
            "governance_mutated": False,
            "ak_called": False,
            "shared_oracle_mutated": False,
            "external_authority_mutated": False,
        },
    }


def _replay_failure_code(exc: Exception) -> str:
    message = str(exc)
    if isinstance(exc, FileExistsError):
        return "execution_replay_output_exists"
    if isinstance(exc, OSError):
        return "execution_replay_write_failed"
    if any(
        marker in message
        for marker in (
            "undeclared files",
            "produced a symlink",
            "changed during replay",
        )
    ):
        return "execution_replay_unexpected_effect"
    return "execution_replay_output_hash_mismatch"


def execute_program_runtime_receipt(
    meta_path: Path, replay_output: Path, report: dict[str, Any]
) -> dict[str, Any]:
    """Reproduce one supported stub-backed runtime episode and publish evidence."""
    from dspx.services.program_execution_replay_executor import (
        execute_program_runtime_receipt_impl,
    )

    return execute_program_runtime_receipt_impl(meta_path, replay_output, report)
