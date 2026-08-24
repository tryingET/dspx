"""Fail-closed loading for the frozen Soomfon DSPy 3.3 evaluation contract."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import platform
import re
import stat
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Mapping, cast

from dspx.services.soomfon_evaluation_candidates import (
    EXPECTED_INPUT_SHA256,
    EXPECTED_RECEIPT_SHA256,
)


PROTECTED_BUILTIN_CALLS = {
    "Exception",
    "RuntimeError",
    "TypeError",
    "ValueError",
    "all",
    "any",
    "bool",
    "dict",
    "enumerate",
    "float",
    "int",
    "isinstance",
    "len",
    "list",
    "max",
    "min",
    "range",
    "set",
    "sorted",
    "str",
    "sum",
    "super",
    "tuple",
    "zip",
}
PROTECTED_MODULE_ATTRIBUTES = {
    "dspy": {
        "ChainOfThought",
        "Example",
        "InputField",
        "Module",
        "OutputField",
        "Predict",
        "Prediction",
        "Signature",
    },
    "dspx.tracing": set(),
    "hashlib": {"sha256"},
    "json": {"dumps", "loads"},
    "os": {"getenv"},
    "pathlib": {"Path"},
    "typing": {
        "Any",
        "Callable",
        "ClassVar",
        "Iterable",
        "Literal",
        "Mapping",
        "Optional",
        "Protocol",
        "Sequence",
        "TypeAlias",
        "TypeVar",
        "cast",
    },
}


def protected_declared_call_names(tree: ast.AST) -> set[str]:
    names = set(PROTECTED_BUILTIN_CALLS)
    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names.update(
                alias.asname or alias.name.split(".", 1)[0] for alias in node.names
            )
    return names


CONTRACT_RELATIVE_PATH = Path(
    "examples/voice_turn_brains/canaries/dspy-3.3.0/soomfon-evaluation-contract.json"
)
CONTRACT_SCHEMA = "soomfon-dspy-3.3-originals-evaluation-contract-v3"
REVIEWED_CONTRACT_SHA256 = (
    "9d9d1b6ea87d3fd16e3db3e1fc97c5bbc68cc241bf67d52cf6c8b2593a1bf24b"
)
EXPECTED_MODES = (
    "simple",
    "elaborate",
    "researched",
    "deep-research",
    "socratic",
    "bloom",
)
REQUIRED_ENVIRONMENT: dict[str, str] = {}
FORBIDDEN_ENVIRONMENT = (
    "DSPX_PROVIDER",
    "DSPX_OPENAI_COMPAT_MODEL",
    "DSPX_OPENAI_COMPAT_API_BASE",
    "DSPX_OPENAI_COMPAT_TIMEOUT",
    "DSPX_OPENAI_COMPAT_API_KEY",
    "OPENAI_API_KEY",
)

_EXPECTED_DISTRIBUTIONS = {
    "dspx-core": "0.2.1",
    "dspy": "3.3.1",
    "dspy-ai": "3.3.1",
    "gepa": "0.1.4",
    "litellm": "1.82.1",
    "httpx": "0.28.1",
    "httpcore": "1.0.9",
}
_TOP_LEVEL_KEYS = {
    "schema_version",
    "task_id",
    "status",
    "purpose",
    "predecessor_contract",
    "source_state",
    "provider_owner_candidate",
    "runtime_target",
    "executor_contract",
    "effect_budget",
    "attempt_ledger",
    "provider_receipt_custody",
    "retention",
    "rubric",
    "cases",
    "deep_research_disposition",
    "nonclaims",
}

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_CONTRACT_BYTES = 256 * 1024


class SoomfonEvaluationContractError(RuntimeError):
    """The frozen evaluation contract or its pre-effect environment is invalid."""


def _read_stable_regular_file(path: Path, *, max_bytes: int) -> bytes:
    resolved_parent = path.expanduser().parent.resolve()
    candidate = resolved_parent / path.name
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(candidate, flags)
    except OSError as exc:
        raise SoomfonEvaluationContractError(
            "contract artifact is unavailable"
        ) from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > max_bytes:
            raise SoomfonEvaluationContractError(
                "contract artifact is not a bounded file"
            )
        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining:
            chunk = os.read(fd, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        after = os.fstat(fd)
    finally:
        os.close(fd)
    identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if identity_before != identity_after or len(raw) != before.st_size:
        raise SoomfonEvaluationContractError("contract artifact changed while read")
    if len(raw) > max_bytes:
        raise SoomfonEvaluationContractError("contract artifact exceeds its byte bound")
    return raw


def _require_exact_keys(
    value: object, expected: set[str], *, label: str
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise SoomfonEvaluationContractError(f"{label} schema is not exact")
    return cast(dict[str, Any], value)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _artifact_path(repo_root: Path, raw: object, *, label: str) -> Path:
    if not isinstance(raw, str) or not raw or Path(raw).is_absolute():
        raise SoomfonEvaluationContractError(f"{label} path is invalid")
    lexical = repo_root / raw
    cursor = repo_root
    for part in Path(raw).parts:
        cursor /= part
        if cursor.is_symlink():
            raise SoomfonEvaluationContractError(f"{label} path uses a symlink")
    path = lexical.resolve()
    if not path.is_relative_to(repo_root) or not path.is_file():
        raise SoomfonEvaluationContractError(f"{label} path escapes or is unavailable")
    return path


def _load_json_bytes(raw: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SoomfonEvaluationContractError(f"{label} JSON is invalid") from exc
    if not isinstance(value, dict):
        raise SoomfonEvaluationContractError(f"{label} JSON is not an object")
    return value


def load_hash_bound_soomfon_contract(
    *, repo_root: Path, expected_sha256: str
) -> tuple[dict[str, Any], str, Path]:
    """Hash raw bytes against an out-of-band digest before JSON parsing."""

    if (
        _SHA256_RE.fullmatch(expected_sha256) is None
        or expected_sha256 != REVIEWED_CONTRACT_SHA256
    ):
        raise SoomfonEvaluationContractError(
            "expected contract SHA-256 is not the reviewed trust anchor"
        )
    root = repo_root.expanduser().resolve()
    contract_path = root / CONTRACT_RELATIVE_PATH
    raw = _read_stable_regular_file(contract_path, max_bytes=_MAX_CONTRACT_BYTES)
    observed = _sha256(raw)
    if observed != expected_sha256:
        raise SoomfonEvaluationContractError("contract SHA-256 does not match")
    contract = _load_json_bytes(raw, label="contract")
    validate_soomfon_contract(contract)
    validate_predecessor_contract_bindings(repo_root=root, contract=contract)
    return contract, observed, contract_path


def validate_soomfon_contract(contract: Mapping[str, Any]) -> None:
    from dspx.services.soomfon_evaluation_schema import (
        validate_soomfon_contract as validate,
    )

    validate(contract)


def validate_predecessor_contract_bindings(
    *, repo_root: Path, contract: Mapping[str, Any]
) -> None:
    predecessor = contract.get("predecessor_contract")
    if not isinstance(predecessor, Mapping):
        raise SoomfonEvaluationContractError("predecessor contract binding is missing")
    archive = _artifact_path(
        repo_root, predecessor.get("archive_path"), label="predecessor contract"
    )
    raw = _read_stable_regular_file(archive, max_bytes=_MAX_CONTRACT_BYTES)
    if _sha256(raw) != predecessor.get("raw_sha256"):
        raise SoomfonEvaluationContractError("predecessor contract SHA-256 drifts")
    earlier = predecessor.get("earlier_predecessor")
    if not isinstance(earlier, Mapping):
        raise SoomfonEvaluationContractError("earlier predecessor binding is missing")
    earlier_path = _artifact_path(
        repo_root, earlier.get("archive_path"), label="earlier predecessor contract"
    )
    earlier_raw = _read_stable_regular_file(earlier_path, max_bytes=_MAX_CONTRACT_BYTES)
    if _sha256(earlier_raw) != earlier.get("raw_sha256"):
        raise SoomfonEvaluationContractError(
            "earlier predecessor contract SHA-256 drifts"
        )


def validate_case_artifact_bindings(
    *, repo_root: Path, contract: Mapping[str, Any]
) -> tuple[dict[str, Any], ...]:
    root = repo_root.expanduser().resolve()
    validated: list[dict[str, Any]] = []
    for raw_case in contract["cases"]:
        case = dict(raw_case)
        manifest_path = _artifact_path(root, case["manifest"], label="manifest")
        index_path = _artifact_path(root, case["canary_index"], label="canary index")
        manifest_raw = _read_stable_regular_file(
            manifest_path, max_bytes=2 * 1024 * 1024
        )
        index_raw = _read_stable_regular_file(index_path, max_bytes=256 * 1024)
        if (
            _sha256(manifest_raw) != case["manifest_sha256"]
            or _sha256(index_raw) != case["canary_index_sha256"]
        ):
            raise SoomfonEvaluationContractError("case artifact SHA-256 does not match")
        manifest = _load_json_bytes(manifest_raw, label="manifest")
        index = _load_json_bytes(index_raw, label="canary index")
        receipt_entry = index.get("fresh_candidate", {}).get("manifest_receipt")
        if not isinstance(receipt_entry, dict):
            raise SoomfonEvaluationContractError("candidate receipt binding is missing")
        receipt_path = _artifact_path(
            root, receipt_entry.get("path"), label="manifest receipt"
        )
        receipt_hash = receipt_entry.get("sha256")
        if (
            not isinstance(receipt_hash, str)
            or _SHA256_RE.fullmatch(receipt_hash) is None
        ):
            raise SoomfonEvaluationContractError("candidate receipt hash is invalid")
        receipt_raw = _read_stable_regular_file(receipt_path, max_bytes=2 * 1024 * 1024)
        if _sha256(receipt_raw) != receipt_hash:
            raise SoomfonEvaluationContractError("candidate receipt SHA-256 drifts")
        try:
            manifest_id = manifest["candidate_assembly"]["candidate_id"]
            index_id = index["fresh_candidate"]["identity"]["candidate_id"]
            index_version = index["fresh_candidate"]["generation_dspy"]["version"]
            index_manifest_hash = index["fresh_candidate"]["manifest"]["sha256"]
        except (KeyError, TypeError) as exc:
            raise SoomfonEvaluationContractError(
                "case artifact identity is invalid"
            ) from exc
        if (
            manifest_id != case["candidate_id"]
            or index_id != case["candidate_id"]
            or index_version != "3.3.1"
            or index_manifest_hash != case["manifest_sha256"]
        ):
            raise SoomfonEvaluationContractError("case artifact identity drifts")
        case["manifest_path"] = manifest_path
        case["canary_index_path"] = index_path
        case["manifest_payload"] = manifest
        case["manifest_receipt_path"] = receipt_path
        case["manifest_receipt_sha256"] = receipt_hash
        validated.append(case)
    return tuple(validated)


def validate_exact_runtime_identity() -> dict[str, str]:
    observed = {"python": platform.python_version()}
    for distribution in _EXPECTED_DISTRIBUTIONS:
        try:
            observed[distribution] = version(distribution)
        except PackageNotFoundError as exc:
            raise SoomfonEvaluationContractError(
                "required distribution is unavailable"
            ) from exc
    expected = {"python": "3.13.12", **_EXPECTED_DISTRIBUTIONS}
    if observed != expected:
        raise SoomfonEvaluationContractError("runtime identity does not match contract")
    return observed


def validate_exact_provider_environment(environment: Mapping[str, str]) -> None:
    if any(key in environment for key in FORBIDDEN_ENVIRONMENT):
        raise SoomfonEvaluationContractError(
            "generic or credential provider environment is forbidden"
        )


def build_sanitized_child_environment(
    environment: Mapping[str, str], *, private_tmp: Path
) -> dict[str, str]:
    validate_exact_provider_environment(environment)
    return {
        "TMPDIR": str(private_tmp),
        "PYTHONUNBUFFERED": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "DSPX_MLFLOW_ENABLE": "0",
    }


def classify_provider_disposition(
    behavior: Mapping[str, Any],
) -> tuple[str, dict[str, object]]:
    provider = behavior.get("provider")
    if not isinstance(provider, Mapping) or provider.get("status") != "configured":
        return "effect_indeterminate", {"reason": "provider_evidence_missing"}
    metadata = provider.get("metadata")
    evidence = provider.get("effect_evidence")
    expected_metadata = {
        "schema_version": "soomfon-dspy-lm-auth-runtime-v1",
        "provider": "soomfon-dspy-lm-auth",
        "model": "codex/gpt-5.6-sol",
        "requested_route": "dspy-lm-auth:codex:gpt-5.6-sol:max",
        "resolved_route": "openai:gpt-5.6-sol:responses",
        "auth_provider": "codex",
        "credential_mode": "no-refresh",
        "reasoning_effort": "max",
        "num_retries": 0,
        "cache": False,
        "timeout_seconds": 60.0,
        "sync_only": True,
        "fallback_allowed": False,
        "health_probe_allowed": False,
        "contract_sha256": REVIEWED_CONTRACT_SHA256,
    }
    if not isinstance(metadata, Mapping) or any(
        metadata.get(key) != expected for key, expected in expected_metadata.items()
    ):
        return "effect_indeterminate", {"reason": "provider_runtime_identity_drift"}
    if set(metadata) != set(expected_metadata) | {
        "mode",
        "source_identity_sha256",
        "dependency_identity_sha256",
    }:
        return "effect_indeterminate", {"reason": "provider_runtime_shape_drift"}
    mode = metadata.get("mode")
    if mode not in EXPECTED_MODES:
        return "effect_indeterminate", {"reason": "provider_mode_identity_drift"}
    try:
        from dspx.services.soomfon_evaluation_provider import (
            validate_soomfon_provider_evidence,
        )

        validated = validate_soomfon_provider_evidence(
            cast(Mapping[str, Any], evidence), mode=cast(str, mode)
        )
    except Exception:
        return "effect_indeterminate", {"reason": "provider_receipt_evidence_invalid"}
    records = validated["call_records"]
    details: dict[str, object] = {
        "mode": mode,
        "artifact_verification": validated["artifact_verification"],
        "logical_call_total": validated["logical_call_total"],
        "maximum_provider_transports": validated["maximum_provider_transports"],
        "call_records": records,
    }
    if (
        validated["artifact_verification"] == "accepted_exact"
        and validated["logical_call_total"] == 2
        and all(
            row.get("provider_outcome_receipt") == "accepted"
            and row.get("producer_terminal") == "provider_response_completed"
            for row in records
        )
    ):
        return "succeeded", details
    return "effect_indeterminate", details


__all__ = [
    "CONTRACT_RELATIVE_PATH",
    "EXPECTED_MODES",
    "EXPECTED_INPUT_SHA256",
    "EXPECTED_RECEIPT_SHA256",
    "REVIEWED_CONTRACT_SHA256",
    "SoomfonEvaluationContractError",
    "classify_provider_disposition",
    "build_sanitized_child_environment",
    "load_hash_bound_soomfon_contract",
    "validate_case_artifact_bindings",
    "validate_predecessor_contract_bindings",
    "validate_exact_provider_environment",
    "validate_exact_runtime_identity",
    "validate_soomfon_contract",
]
