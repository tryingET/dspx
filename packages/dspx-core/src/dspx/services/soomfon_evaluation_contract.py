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
CONTRACT_SCHEMA = "soomfon-dspy-3.3-originals-evaluation-contract-v1"
REVIEWED_CONTRACT_SHA256 = (
    "b720939ac2b299dab51ededabde9659166647a9e0e2e4d33c37cfd04a17bb625"
)
EXPECTED_MODES = (
    "simple",
    "elaborate",
    "researched",
    "deep-research",
    "socratic",
    "bloom",
)
EXPECTED_INPUT_SHA256 = {
    "simple": "504ff94159b06c326d71068ed325aeefc52459d6c7ae956d75c1b261c86a6900",
    "elaborate": "ed18493c4c17b8a36a30c8d309773845326cb5e4d85edeffad14b052d53e7a16",
    "researched": "99c4c8a9fc5b002e5a1167f97213cfb04c36590d55c95825417a4e19ba943812",
    "deep-research": "f71f02df9921fc502700ec8ab1d102b0092b2870b52ee583a440a95ddc08d01b",
    "socratic": "4693caea691634f9d63cd1e519038baf0a2663b876e110cb06ee0f07af7c6686",
    "bloom": "53e937b087ce752f8ead60dec3151aabda3fee3c76e99cc31a28081c4683c829",
}
EXPECTED_RECEIPT_SHA256 = {
    "simple": "4cb846918dbb5033d1810b77f24fedfcf1e7849ee22a1bff52a7296590ee7eb1",
    "elaborate": "7356d11d793f59a567ebd98fa5940d3e5e333ca1a9a23c9e016142713dda4f9c",
    "researched": "dcc4db729515ab269032bb540ed71fa2e2c4f9c8ed0e8fcac402f4a5d549184e",
    "deep-research": "25be7a94f44341086677fb2ec8f064cd2aafd03a4de64fa2797f4b070711c70d",
    "socratic": "48760064bc40949fd346cc63576826d51d7a7b1a838196baf4dba61095119b6a",
    "bloom": "af56fa8361db5df681175f8e0d1fbc8ee9ebbe07b83d58d92a429786e9eea335",
}
REQUIRED_ENVIRONMENT = {
    "DSPX_PROVIDER": "openai-compatible",
    "DSPX_OPENAI_COMPAT_MODEL": "baseline-text",
    "DSPX_OPENAI_COMPAT_API_BASE": "http://127.0.0.1:1234/v1",
    "DSPX_OPENAI_COMPAT_TIMEOUT": "30",
    "DSPX_POLICY_ALLOW_NETWORK_MUTATE": "1",
}
FORBIDDEN_ENVIRONMENT = ("DSPX_OPENAI_COMPAT_API_KEY",)
_EXPECTED_DISTRIBUTIONS = {
    "dspx-core": "0.2.1",
    "dspy": "3.3.1",
    "dspy-ai": "3.3.1",
    "gepa": "0.1.4",
}
_TOP_LEVEL_KEYS = {
    "schema_version",
    "task_id",
    "status",
    "purpose",
    "source_state",
    "runtime_target",
    "executor_contract",
    "effect_budget",
    "attempt_ledger",
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
    return contract, observed, contract_path


def validate_soomfon_contract(contract: Mapping[str, Any]) -> None:
    from dspx.services.soomfon_evaluation_schema import (
        validate_soomfon_contract as validate,
    )

    validate(contract)


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
            or index_version != "3.3.0"
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
    for key, expected in REQUIRED_ENVIRONMENT.items():
        if environment.get(key) != expected:
            raise SoomfonEvaluationContractError(
                "provider environment does not match contract"
            )
    if any(key in environment for key in FORBIDDEN_ENVIRONMENT):
        raise SoomfonEvaluationContractError("credential environment is forbidden")


def build_sanitized_child_environment(
    environment: Mapping[str, str], *, private_tmp: Path
) -> dict[str, str]:
    validate_exact_provider_environment(environment)
    result = dict(REQUIRED_ENVIRONMENT)
    result.update(
        {
            "TMPDIR": str(private_tmp),
            "NO_PROXY": "127.0.0.1",
            "no_proxy": "127.0.0.1",
            "PYTHONUNBUFFERED": "1",
            "DSPX_MLFLOW_ENABLE": "0",
        }
    )
    return result


def classify_provider_disposition(
    behavior: Mapping[str, Any],
) -> tuple[str, dict[str, object]]:
    provider = behavior.get("provider")
    if not isinstance(provider, dict):
        return "effect_indeterminate", {"reason": "provider_evidence_missing"}
    metadata = provider.get("metadata")
    runtime = metadata.get("runtime") if isinstance(metadata, dict) else None
    if (
        not isinstance(metadata, dict)
        or metadata.get("provider") != "openai-compatible"
        or metadata.get("model") != "baseline-text"
        or not isinstance(runtime, dict)
        or runtime.get("base_endpoint") != "http://127.0.0.1:1234/v1"
        or runtime.get("effective_timeout") != 30.0
    ):
        return "effect_indeterminate", {"reason": "provider_runtime_identity_drift"}
    evidence = provider.get("effect_evidence")
    if (
        not isinstance(evidence, dict)
        or evidence.get("schema_version") != "dspx-provider-effect-evidence-v1"
    ):
        return "effect_indeterminate", {"reason": "provider_effect_evidence_missing"}
    attempts = evidence.get("attempts")
    if evidence.get("attempts_truncated") is not False or not isinstance(
        attempts, list
    ):
        return "effect_indeterminate", {"reason": "provider_effect_evidence_incomplete"}
    dispositions = [
        attempt.get("effect_disposition")
        for attempt in attempts
        if isinstance(attempt, dict)
    ]
    dispatch_counts = [
        attempt.get("dispatch_count")
        for attempt in attempts
        if isinstance(attempt, dict)
    ]
    attempt_total = evidence.get("attempt_total")
    details: dict[str, object] = {
        "attempt_total": attempt_total,
        "terminal_effect": evidence.get("terminal_effect"),
        "dispositions": dispositions,
        "dispatch_counts": dispatch_counts,
    }
    if (
        len(dispositions) != len(attempts)
        or len(dispatch_counts) != len(attempts)
        or type(attempt_total) is not int
        or attempt_total != len(attempts)
        or attempt_total != 1
        or any(type(item) is not int for item in dispatch_counts)
    ):
        return "effect_indeterminate", {"reason": "provider_effect_attempt_invalid"}
    if (
        attempts
        and all(item == "completed_success" for item in dispositions)
        and all(item == 1 for item in dispatch_counts)
        and evidence.get("terminal_effect") == "completed_success"
    ):
        return "succeeded", details
    if (
        attempts
        and all(item == "preflight_rejected" for item in dispositions)
        and all(item == 0 for item in dispatch_counts)
        and evidence.get("terminal_effect") == "preflight_rejected"
    ):
        return "failed_no_effect_proved", details
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
    "validate_exact_provider_environment",
    "validate_exact_runtime_identity",
    "validate_soomfon_contract",
]
