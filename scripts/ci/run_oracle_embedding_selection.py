#!/usr/bin/env python3
# summary: "Runs the one-shot retained-MiniLM versus mDenseOn Oracle selection sequence."
# read_when:
#   - "Executing or reviewing the frozen Oracle dense-model reassessment."

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import pwd
import resource
import secrets
import shutil
import stat
import subprocess
import sys
import sysconfig
import tempfile
import time
from pathlib import Path
from typing import Any, Mapping, cast

from dspx.coordinates.embedding_identity import (
    EmbeddingIdentityError,
    runtime_distribution_hashes,
    runtime_package_versions,
    validate_model_artifact_root,
)
from dspx.coordinates.embeddings import SentenceTransformerEmbedder
from dspx.coordinates.mdenseon import MDenseOnEmbedder, MDenseOnError
from dspx.coordinates.oracle_embedding_evaluation import (
    _identity_spec as baseline_identity_spec,
)
from dspx.coordinates.oracle_embedding_selection import (
    BASELINE_DB_FILE,
    CHALLENGER_DB_FILE,
    EXPECTED_CONTRACT_SHA256,
    SelectionError,
    _array,
    _mapping,
    challenger_identity_spec,
    materialize_record_text,
    score_model,
    select_model,
    validate_contract_payload,
    verify_retained_selection,
)

CONTRACT_FILE = "benchmarks/semantic/oracle-embedding-selection-v2.json"
BASELINE_CONTRACT_FILE = "benchmarks/semantic/oracle-embedding-evaluation-v1.json"
RECOVERY_CONTRACT_FILE = (
    "benchmarks/semantic/oracle-embedding-selection-recovery-v1.json"
)
EXPECTED_RECOVERY_CONTRACT_SHA256 = (
    "7ff3259036a2658a633582046150524ce1d2857344ff4862f246a8ee27668713"
)
RESULT_FILE = "selection-result.json"
VERIFICATION_FILE = "independent-verification.json"
ATTEMPT_FILE = "attempt-status.json"
MODEL_DIR = "mdenseon-snapshot"
_EXPECTED_UV_VERSION = "uv 0.11.14 (3fdfdc7d4 2026-05-12 x86_64-unknown-linux-gnu)"
_EXPECTED_LOCK_SHA256 = (
    "d941b76c442e4c89143b1ab0abcc03a57b477943e6cb0e588bc08c3ec5a4ef09"
)
_HANDOFF_PATH_ENV = "DSPX_ORACLE_EMBEDDING_SELECTION_HANDOFF_PATH"
_HANDOFF_NONCE_ENV = "DSPX_ORACLE_EMBEDDING_SELECTION_HANDOFF_NONCE"
_FROZEN_RUNTIME_REEXECUTED = False
_TASK_ID = 4510
_RECOVERY_TASK_ID = 4517
_REQUIRED_TRACKED_SOURCE_FILES = (
    CONTRACT_FILE,
    BASELINE_CONTRACT_FILE,
    RECOVERY_CONTRACT_FILE,
    "uv.lock",
    "packages/dspx-core/src/dspx/coordinates/embedding_identity.py",
    "packages/dspx-core/src/dspx/coordinates/embeddings.py",
    "packages/dspx-core/src/dspx/coordinates/mdenseon.py",
    "packages/dspx-core/src/dspx/coordinates/metrics.py",
    "packages/dspx-core/src/dspx/coordinates/oracle_embedding_evaluation.py",
    "packages/dspx-core/src/dspx/coordinates/oracle_embedding_selection.py",
    "packages/dspx-core/src/dspx/coordinates/storage.py",
    "packages/dspx-core/src/dspx/run_receipts.py",
    "scripts/ci/run_oracle_embedding_selection.py",
    "tests/test_oracle_embedding_selection.py",
)
_SOURCE_STATUS_PATHS = (
    CONTRACT_FILE,
    BASELINE_CONTRACT_FILE,
    RECOVERY_CONTRACT_FILE,
    "uv.lock",
    "packages/dspx-core/src/dspx",
    "scripts/ci/run_oracle_embedding_selection.py",
    "tests/test_oracle_embedding_selection.py",
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    raw = (
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode()
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def _consume_runtime_handoff() -> bool:
    path_value = os.environ.pop(_HANDOFF_PATH_ENV, "")
    nonce = os.environ.pop(_HANDOFF_NONCE_ENV, "")
    if not path_value and not nonce:
        return False
    path = Path(path_value)
    try:
        before = path.lstat()
        if (
            not path.is_absolute()
            or not stat.S_ISREG(before.st_mode)
            or stat.S_IMODE(before.st_mode) != 0o600
            or before.st_uid != os.getuid()
        ):
            raise SelectionError("frozen-runtime handoff identity is invalid")
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as stream:
            raw = stream.read(4097)
        if len(raw) > 4096:
            raise SelectionError("frozen-runtime handoff exceeds size bound")
        payload = json.loads(raw)
        path.unlink()
    except (OSError, json.JSONDecodeError) as exc:
        raise SelectionError("frozen-runtime handoff is unavailable") from exc
    if payload != {
        "nonce": nonce,
        "lock_sha256": _EXPECTED_LOCK_SHA256,
        "uv_version": _EXPECTED_UV_VERSION,
    }:
        raise SelectionError("frozen-runtime handoff receipt drift")
    return True


def _exec_in_frozen_runtime() -> None:
    global _FROZEN_RUNTIME_REEXECUTED
    if _consume_runtime_handoff():
        _FROZEN_RUNTIME_REEXECUTED = True
        return
    uv = shutil.which("uv")
    if uv is None:
        raise SelectionError("uv is required for the frozen isolated runtime")
    observed_version = subprocess.run(
        [uv, "--version"], check=True, capture_output=True, text=True
    ).stdout.strip()
    if observed_version != _EXPECTED_UV_VERSION:
        raise SelectionError(f"uv runtime version drift: {observed_version!r}")
    nonce = secrets.token_hex(32)
    descriptor, handoff_name = tempfile.mkstemp(
        prefix="dspx-oracle-embedding-selection-handoff-", suffix=".json"
    )
    handoff = Path(handoff_name).resolve()
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(
                {
                    "nonce": nonce,
                    "lock_sha256": _EXPECTED_LOCK_SHA256,
                    "uv_version": _EXPECTED_UV_VERSION,
                },
                stream,
                sort_keys=True,
            )
            stream.flush()
            os.fsync(stream.fileno())
        environment = {
            key: value
            for key, value in os.environ.items()
            if key not in {"PYTHONPATH", "PYTHONHOME"}
        }
        environment.update(
            {
                _HANDOFF_PATH_ENV: str(handoff),
                _HANDOFF_NONCE_ENV: nonce,
            }
        )
        recovery_or_verification = any(
            flag in sys.argv
            for flag in ("--recover", "--recovered-adapter", "--verify-only")
        )
        command = [uv, "run"]
        if recovery_or_verification:
            command.append("--offline")
            environment.update(
                {
                    "UV_OFFLINE": "1",
                    "HF_HUB_OFFLINE": "1",
                    "TRANSFORMERS_OFFLINE": "1",
                }
            )
        command.extend(
            [
                "--isolated",
                "--frozen",
                "--package",
                "dspx-core",
                "--extra",
                "oracle-embeddings",
                "python",
                str(Path(__file__).resolve()),
                *sys.argv[1:],
            ]
        )
        os.execve(
            uv,
            command,
            environment,
        )
    finally:
        handoff.unlink(missing_ok=True)


def _verify_frozen_runtime(contract: Mapping[str, Any], repo_root: Path) -> None:
    """Verify runtime effects directly; the handoff is only a recursion receipt."""

    runtime = _mapping(contract["runtime"], "runtime")
    packages = _mapping(runtime["expected_package_versions"], "runtime packages")
    expected_distribution_hashes = _mapping(
        runtime["expected_distribution_content_sha256"],
        "runtime distribution hashes",
    )
    prefix = Path(sys.prefix).resolve()
    virtual_env = os.environ.get("VIRTUAL_ENV")
    if (
        not _FROZEN_RUNTIME_REEXECUTED
        or sys.prefix == sys.base_prefix
        or virtual_env is None
        or Path(virtual_env).resolve() != prefix
        or repo_root.resolve() in prefix.parents
        or os.environ.get("PYTHONPATH") not in (None, "")
        or os.environ.get("PYTHONHOME") not in (None, "")
        or sys.implementation.name != runtime["python_implementation"]
        or f"{sys.version_info.major}.{sys.version_info.minor}"
        != runtime["python_major_minor"]
        or (
            f"{sys.version_info.major}.{sys.version_info.minor}."
            f"{sys.version_info.micro}"
        )
        != runtime["python_version"]
        or sysconfig.get_platform() != runtime["platform"]
        or _sha256_file(repo_root / "uv.lock") != runtime["lock_sha256"]
        or runtime_package_versions(tuple(sorted(packages))) != dict(packages)
        or runtime_distribution_hashes(tuple(sorted(packages)))
        != dict(expected_distribution_hashes)
    ):
        raise SelectionError("isolated frozen runtime verification failed")
    source_root = (repo_root / "packages/dspx-core/src").resolve()
    for module_name in (
        "dspx.coordinates.embedding_identity",
        "dspx.coordinates.embeddings",
        "dspx.coordinates.mdenseon",
        "dspx.coordinates.metrics",
        "dspx.coordinates.oracle_embedding_evaluation",
        "dspx.coordinates.oracle_embedding_selection",
        "dspx.coordinates.storage",
        "dspx.run_receipts",
    ):
        module = __import__(module_name, fromlist=["__name__"])
        module_file = getattr(module, "__file__", None)
        if (
            not isinstance(module_file, str)
            or source_root not in Path(module_file).resolve().parents
        ):
            raise SelectionError(f"import origin drift: {module_name}")
    torch = __import__("torch")
    if (
        bool(torch.cuda.is_available())
        or str(torch.get_default_dtype()) != "torch.float32"
    ):
        raise SelectionError("CPU float32 runtime observation drift")


def _source_commit(repo_root: Path) -> str:
    """Require every attempt-defining source to be tracked and clean."""

    for relative in _REQUIRED_TRACKED_SOURCE_FILES:
        subprocess.run(
            ["git", "ls-files", "--error-unmatch", relative],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    status = subprocess.run(
        [
            "git",
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--",
            *_SOURCE_STATUS_PATHS,
        ],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if status:
        raise SelectionError("attempt-defining sources must be tracked and clean")
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if len(commit) != 40:
        raise SelectionError("source commit identity is unavailable")
    return commit


def _default_attempt_ledger_path() -> Path:
    account_home = Path(pwd.getpwuid(os.getuid()).pw_dir).resolve()
    return (
        account_home
        / ".local/state/dspx/oracle-embedding-selections"
        / f"AK-{_TASK_ID}.json"
    )


def _claim_attempt(root: Path, ledger_path: Path, *, source_commit: str) -> None:
    ledger_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    payload = {
        "schema_version": "dspx-oracle-embedding-selection-ledger-v1",
        "status": "started_effect_indeterminate_if_interrupted",
        "contract_sha256": EXPECTED_CONTRACT_SHA256,
        "ak_task_id": _TASK_ID,
        "source_commit": source_commit,
        "root": str(root),
        "attempt_budget_consumed": 1,
        "another_root_allowed": False,
    }
    raw = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
    try:
        descriptor = os.open(ledger_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise SelectionError(
            "the canonical selection attempt ledger is already consumed"
        ) from exc
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _update_ledger(
    ledger_path: Path,
    *,
    root: Path,
    source_commit: str,
    status: str,
    evidence: Mapping[str, Any],
) -> None:
    _write_json(
        ledger_path,
        {
            "schema_version": "dspx-oracle-embedding-selection-ledger-v1",
            "status": status,
            "contract_sha256": EXPECTED_CONTRACT_SHA256,
            "ak_task_id": _TASK_ID,
            "source_commit": source_commit,
            "root": str(root),
            "attempt_budget_consumed": 1,
            "another_root_allowed": False,
            "evidence": dict(evidence),
        },
    )


def _default_recovery_ledger_path() -> Path:
    account_home = Path(pwd.getpwuid(os.getuid()).pw_dir).resolve()
    return (
        account_home
        / ".local/state/dspx/oracle-embedding-selection-recoveries"
        / f"AK-{_RECOVERY_TASK_ID}.json"
    )


def _claim_recovery(root: Path, ledger_path: Path, *, source_commit: str) -> None:
    ledger_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    payload = {
        "schema_version": "dspx-oracle-embedding-selection-recovery-ledger-v1",
        "status": "started_effect_indeterminate_if_interrupted",
        "recovery_contract_sha256": EXPECTED_RECOVERY_CONTRACT_SHA256,
        "base_contract_sha256": EXPECTED_CONTRACT_SHA256,
        "ak_task_id": _RECOVERY_TASK_ID,
        "source_commit": source_commit,
        "root": str(root),
        "attempt_budget_consumed": 1,
        "another_root_allowed": False,
    }
    raw = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
    try:
        descriptor = os.open(ledger_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise SelectionError(
            "the canonical recovery attempt ledger is already consumed"
        ) from exc
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _update_recovery_ledger(
    ledger_path: Path,
    *,
    root: Path,
    source_commit: str,
    status: str,
    evidence: Mapping[str, Any],
) -> None:
    _write_json(
        ledger_path,
        {
            "schema_version": "dspx-oracle-embedding-selection-recovery-ledger-v1",
            "status": status,
            "recovery_contract_sha256": EXPECTED_RECOVERY_CONTRACT_SHA256,
            "base_contract_sha256": EXPECTED_CONTRACT_SHA256,
            "ak_task_id": _RECOVERY_TASK_ID,
            "source_commit": source_commit,
            "root": str(root),
            "attempt_budget_consumed": 1,
            "another_root_allowed": False,
            "evidence": dict(evidence),
        },
    )


def load_contract(repo_root: Path) -> tuple[dict[str, Any], str]:
    path = repo_root / CONTRACT_FILE
    raw = path.read_bytes()
    observed = hashlib.sha256(raw).hexdigest()
    if observed != EXPECTED_CONTRACT_SHA256:
        raise SelectionError("selection contract byte hash drift")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise SelectionError("selection contract must be an object")
    contract = cast(dict[str, Any], payload)
    validate_contract_payload(contract)
    for relative, expected in {
        BASELINE_CONTRACT_FILE: "819204905f94449013fb25a5f6e21157db36210cbaa4b6e6e8811bb67ca3e92e",
        "uv.lock": _EXPECTED_LOCK_SHA256,
    }.items():
        if _sha256_file(repo_root / relative) != expected:
            raise SelectionError(f"source binding drift: {relative}")
    return contract, observed


def load_recovery_contract(repo_root: Path) -> tuple[dict[str, Any], str]:
    path = repo_root / RECOVERY_CONTRACT_FILE
    raw = path.read_bytes()
    observed = hashlib.sha256(raw).hexdigest()
    if observed != EXPECTED_RECOVERY_CONTRACT_SHA256:
        raise SelectionError("recovery contract byte hash drift")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise SelectionError("recovery contract must be an object")
    contract = cast(dict[str, Any], payload)
    base = _mapping(contract.get("base_selection_contract"), "base contract")
    preserved = _mapping(
        contract.get("preserved_terminal_attempt"), "preserved attempt"
    )
    retained = _mapping(contract.get("retained_challenger"), "retained challenger")
    correction = _mapping(contract.get("correction"), "adapter correction")
    budget = _mapping(contract.get("attempt_budget"), "recovery budget")
    enforcement = _mapping(budget.get("enforcement"), "recovery enforcement")
    effects = _mapping(contract.get("effects"), "recovery effects")
    claims = _mapping(contract.get("claim_boundary"), "recovery claims")
    if (
        contract.get("schema_version")
        != "dspx-oracle-embedding-selection-recovery-contract-v1"
        or contract.get("status") != "precommitted_recovery_not_run"
        or contract.get("ak_task_id") != _RECOVERY_TASK_ID
        or base.get("path") != CONTRACT_FILE
        or base.get("sha256") != EXPECTED_CONTRACT_SHA256
        or _sha256_file(repo_root / CONTRACT_FILE) != EXPECTED_CONTRACT_SHA256
        or preserved.get("ak_task_id") != _TASK_ID
        or preserved.get("status") != "failed_or_indeterminate_terminal"
        or preserved.get("history_mutation_allowed") is not False
        or retained.get("repository_id") != "lightonai/mDenseOn"
        or retained.get("revision") != "a5fdb000f7a21da96c3bddde3a782ef777316df3"
        or retained.get("network_reacquisition_allowed") is not False
        or correction.get("remove_model_input_keys") != ["token_type_ids"]
        or correction.get("other_tokenizer_or_model_input_changes_allowed") is not False
        or correction.get("full_documents_and_queries_required") is not True
        or budget.get("maximum_full_recovery_sequences") != 1
        or budget.get("selective_query_reruns_allowed") is not False
        or budget.get("dspx_managed_retries") != 0
        or enforcement.get("key") != "ak_task_id_and_recovery_contract_sha256"
        or enforcement.get("marker_created_before_model_execution") is not True
        or any(type(value) is not int or value != 0 for value in effects.values())
        or claims.get("same_fifteen_query_oracle_specific_dense_selection_only")
        is not True
        or any(
            value is not False
            for key, value in claims.items()
            if key != "same_fifteen_query_oracle_specific_dense_selection_only"
        )
    ):
        raise SelectionError("recovery contract execution or claim boundary drift")
    for key in ("attempt_status_path", "ledger_path"):
        evidence_path = Path(cast(str, preserved[key]))
        expected_hash = cast(str, preserved[f"{key.removesuffix('_path')}_sha256"])
        if (
            not evidence_path.is_absolute()
            or not evidence_path.is_file()
            or evidence_path.is_symlink()
            or _sha256_file(evidence_path) != expected_hash
        ):
            raise SelectionError(f"preserved recovery lineage drift: {key}")
    return contract, observed


def _load_baseline_contract(repo_root: Path) -> dict[str, Any]:
    payload = json.loads((repo_root / BASELINE_CONTRACT_FILE).read_bytes())
    if not isinstance(payload, dict):
        raise SelectionError("retained baseline contract must be an object")
    return cast(dict[str, Any], payload)


def _record_and_query_texts(contract: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    evaluation = _mapping(contract["evaluation"], "evaluation")
    documents = [
        materialize_record_text(_mapping(row, "record"))
        for row in _array(evaluation["records"], "records")
    ]
    queries = [
        cast(str, _mapping(row, "query")["text"])
        for row in _array(evaluation["queries"], "queries")
    ]
    return documents, queries


def _run_baseline(
    *,
    repo_root: Path,
    contract: Mapping[str, Any],
    model_root: Path,
    root: Path,
) -> dict[str, Any]:
    if (
        not model_root.is_absolute()
        or not model_root.is_dir()
        or model_root.is_symlink()
    ):
        raise SelectionError(
            "baseline model root must be an absolute retained directory"
        )
    spec = baseline_identity_spec(_load_baseline_contract(repo_root))
    embedder = SentenceTransformerEmbedder(
        spec.repository_id,
        model_root=model_root,
        normalize_embeddings=True,
        device="cpu",
    )
    documents, queries = _record_and_query_texts(contract)
    document_vectors = embedder.encode(documents)
    query_vectors = embedder.encode(queries)
    identity = embedder.build_identity(
        spec, frozen_runtime_lock_sha256=spec.runtime_lock_sha256
    )
    result = score_model(
        contract=contract,
        model_label="sentence-transformers/all-MiniLM-L6-v2",
        identity=identity,
        document_vectors=document_vectors,
        query_vectors=query_vectors,
        database_path=root / BASELINE_DB_FILE,
        embedding_version=1,
    )
    del embedder, document_vectors, query_vectors
    gc.collect()
    return result


def _run_challenger(
    *, contract: Mapping[str, Any], model_root: Path, root: Path
) -> tuple[dict[str, Any], dict[str, float | int], dict[str, list[str]]]:
    spec = challenger_identity_spec(contract)
    documents, queries = _record_and_query_texts(contract)
    started = time.perf_counter()
    embedder = MDenseOnEmbedder(
        spec.repository_id, model_root=model_root, device="cpu", max_tokens=8192
    )
    load_seconds = time.perf_counter() - started
    encode_started = time.perf_counter()
    document_vectors = embedder.encode_documents(documents)
    query_vectors = embedder.encode_queries(queries)
    encode_seconds = time.perf_counter() - encode_started
    identity = embedder.build_identity(
        spec, frozen_runtime_lock_sha256=spec.runtime_lock_sha256
    )
    result = score_model(
        contract=contract,
        model_label="lightonai/mDenseOn",
        identity=identity,
        document_vectors=document_vectors,
        query_vectors=query_vectors,
        database_path=root / CHALLENGER_DB_FILE,
        embedding_version=2,
    )
    original_hashes = {
        "documents": [row["vector_sha256"] for row in result["records"]],
        "queries": [row["vector_sha256"] for row in result["queries"]],
    }
    del embedder, document_vectors, query_vectors
    gc.collect()

    reproduction_started = time.perf_counter()
    reproduction = MDenseOnEmbedder(
        spec.repository_id, model_root=model_root, device="cpu", max_tokens=8192
    )
    reproduced_documents = reproduction.encode_documents(documents)
    reproduced_queries = reproduction.encode_queries(queries)
    reproduced_hashes = {
        "documents": [
            hashlib.sha256(
                json.dumps(vector, separators=(",", ":"), allow_nan=False).encode()
            ).hexdigest()
            for vector in reproduced_documents
        ],
        "queries": [
            hashlib.sha256(
                json.dumps(vector, separators=(",", ":"), allow_nan=False).encode()
            ).hexdigest()
            for vector in reproduced_queries
        ],
    }
    reproduction_seconds = time.perf_counter() - reproduction_started
    if reproduced_hashes != original_hashes:
        raise SelectionError("complete mDenseOn batch reproduction drift")
    resources: dict[str, float | int] = {
        "retained_model_bytes": sum(
            path.stat().st_size
            for path in model_root.rglob("*")
            if path.is_file() and ".cache" not in path.parts
        ),
        "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
        "model_load_seconds": load_seconds,
        "total_encode_seconds": encode_seconds,
        "full_batch_reproduction_seconds": reproduction_seconds,
    }
    return result, resources, original_hashes


def _verify_only(
    *,
    repo_root: Path,
    root: Path,
    baseline_model_root: Path,
    challenger_model_root: Path | None = None,
    recovered_adapter: bool = False,
) -> dict[str, Any]:
    contract, _ = load_contract(repo_root)
    _verify_frozen_runtime(contract, repo_root)
    source_commit = _source_commit(repo_root)
    baseline_spec = baseline_identity_spec(_load_baseline_contract(repo_root))
    challenger_root = (
        root / MODEL_DIR if challenger_model_root is None else challenger_model_root
    )
    result = json.loads((root / RESULT_FILE).read_bytes())
    if not isinstance(result, dict) or result.get("source_commit") != source_commit:
        raise SelectionError("retained result source-commit binding drift")
    verification = verify_retained_selection(
        root=root,
        contract=contract,
        baseline_spec=baseline_spec,
        baseline_model_root=baseline_model_root,
        challenger_model_root=challenger_root,
        recovered_adapter=recovered_adapter,
    )
    if recovered_adapter:
        recovery, recovery_hash = load_recovery_contract(repo_root)
        preserved = _mapping(
            recovery["preserved_terminal_attempt"], "preserved attempt"
        )
        retained = _mapping(recovery["retained_challenger"], "retained challenger")
        recovery_result = _mapping(result.get("recovery"), "recovery result")
        resources = _mapping(result.get("resources"), "resources")
        if (
            challenger_root.resolve() != Path(cast(str, retained["root"])).resolve()
            or recovery_result
            != {
                "schema_version": "dspx-oracle-embedding-selection-recovery-result-v1",
                "recovery_contract_sha256": recovery_hash,
                "ak_task_id": _RECOVERY_TASK_ID,
                "model_artifact_acquisitions": 0,
                "network_calls": 0,
                "removed_model_input_keys": ["token_type_ids"],
                "preserved_attempt_status_sha256": preserved["attempt_status_sha256"],
                "preserved_ledger_sha256": preserved["ledger_sha256"],
            }
            or resources.get("artifact_acquisition_seconds") != 0.0
            or resources.get("model_artifact_acquisitions") != 0
            or any(
                os.environ.get(key) != "1"
                for key in (
                    "UV_OFFLINE",
                    "HF_HUB_OFFLINE",
                    "TRANSFORMERS_OFFLINE",
                )
            )
        ):
            raise SelectionError("recovery lineage, offline, or resource drift")
        verification["recovery_contract_sha256"] = recovery_hash
        verification["preserved_failure_lineage_verified"] = True
        verification["zero_acquisition_and_offline_contract_verified"] = True
    return verification


def _run_independent_verifier(
    *,
    repo_root: Path,
    root: Path,
    baseline_model_root: Path,
    challenger_model_root: Path | None = None,
    recovered_adapter: bool = False,
) -> dict[str, Any]:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--root",
        str(root),
        "--baseline-model-root",
        str(baseline_model_root),
        "--verify-only",
    ]
    if challenger_model_root is not None:
        command.extend(["--challenger-model-root", str(challenger_model_root)])
    if recovered_adapter:
        command.append("--recovered-adapter")
    completed = subprocess.run(
        command,
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise SelectionError(
            "independent verification process failed: "
            + completed.stderr.strip()[-500:]
        )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise SelectionError("independent verification output is invalid") from exc
    if not isinstance(payload, dict):
        raise SelectionError("independent verification output must be an object")
    return cast(dict[str, Any], payload)


def _acquire_and_run(*, repo_root: Path, root: Path, baseline_model_root: Path) -> int:
    contract, contract_hash = load_contract(repo_root)
    _verify_frozen_runtime(contract, repo_root)
    source_commit = _source_commit(repo_root)
    baseline_spec = baseline_identity_spec(_load_baseline_contract(repo_root))
    validate_model_artifact_root(baseline_spec, baseline_model_root)
    if not root.is_absolute() or root.exists():
        raise SelectionError("evidence root must be absolute and not already exist")
    if (
        repo_root.resolve() == root.resolve()
        or repo_root.resolve() in root.resolve().parents
        or not root.parent.is_dir()
        or root.parent.is_symlink()
    ):
        raise SelectionError(
            "evidence root parent is unavailable or inside the repository"
        )
    root.mkdir(mode=0o700, parents=False)
    ledger_path = _default_attempt_ledger_path()
    try:
        _claim_attempt(root, ledger_path, source_commit=source_commit)
    except BaseException:
        root.rmdir()
        raise
    _write_json(
        root / ATTEMPT_FILE,
        {
            "schema_version": "dspx-oracle-embedding-selection-attempt-v1",
            "status": "started_terminal_result_pending",
            "contract_sha256": contract_hash,
            "ak_task_id": _TASK_ID,
            "source_commit": source_commit,
            "attempt_budget_consumed": 1,
            "selective_rerun_allowed": False,
        },
    )
    try:
        baseline = _run_baseline(
            repo_root=repo_root,
            contract=contract,
            model_root=baseline_model_root,
            root=root,
        )
        spec = challenger_identity_spec(contract)
        model_root = root / MODEL_DIR
        from huggingface_hub import snapshot_download

        acquisition_started = time.perf_counter()
        downloaded = snapshot_download(
            repo_id=spec.repository_id,
            revision=spec.revision,
            local_dir=model_root,
            allow_patterns=list(spec.artifact_paths),
            token=False,
            max_workers=1,
        )
        acquisition_seconds = time.perf_counter() - acquisition_started
        if Path(downloaded).resolve() != model_root.resolve():
            raise SelectionError("challenger acquisition retained an unexpected root")
        challenger, resources, vector_hashes = _run_challenger(
            contract=contract, model_root=model_root, root=root
        )
        resources["artifact_acquisition_seconds"] = acquisition_seconds
        result = select_model(
            contract=contract,
            baseline=baseline,
            challenger=challenger,
            resources=resources,
        )
        result["full_batch_reproduction"] = {
            "verified": True,
            "vector_hashes": vector_hashes,
        }
        result["source_commit"] = source_commit
        _write_json(root / RESULT_FILE, result)
        verification = _run_independent_verifier(
            repo_root=repo_root,
            root=root,
            baseline_model_root=baseline_model_root,
        )
        _write_json(root / VERIFICATION_FILE, verification)
        terminal = (
            "passed" if result["status"] == "passed" else "challenger_not_selected"
        )
        evidence = {
            "result_sha256": _sha256_file(root / RESULT_FILE),
            "verification_sha256": _sha256_file(root / VERIFICATION_FILE),
            "selected_model": result["selected_model"],
        }
        _write_json(
            root / ATTEMPT_FILE,
            {
                "schema_version": "dspx-oracle-embedding-selection-attempt-v1",
                "status": terminal,
                "contract_sha256": contract_hash,
                "ak_task_id": _TASK_ID,
                "source_commit": source_commit,
                "attempt_budget_consumed": 1,
                "selective_rerun_allowed": False,
                **evidence,
            },
        )
        _update_ledger(
            ledger_path,
            root=root,
            source_commit=source_commit,
            status=terminal,
            evidence=evidence,
        )
        print(json.dumps({"status": terminal, **evidence}, indent=2, sort_keys=True))
        return 0 if terminal == "passed" else 1
    except BaseException as exc:
        sanitized = str(exc).replace(str(root), "<evidence-root>")[:500]
        _write_json(
            root / ATTEMPT_FILE,
            {
                "schema_version": "dspx-oracle-embedding-selection-attempt-v1",
                "status": "failed_or_indeterminate_terminal",
                "contract_sha256": contract_hash,
                "ak_task_id": _TASK_ID,
                "source_commit": source_commit,
                "attempt_budget_consumed": 1,
                "selective_rerun_allowed": False,
                "error_class": type(exc).__name__,
                "error": sanitized,
            },
        )
        _update_ledger(
            ledger_path,
            root=root,
            source_commit=source_commit,
            status="failed_or_indeterminate_terminal",
            evidence={"error_class": type(exc).__name__},
        )
        raise


def _recover_and_run(
    *,
    repo_root: Path,
    root: Path,
    baseline_model_root: Path,
    challenger_model_root: Path,
) -> int:
    recovery, recovery_hash = load_recovery_contract(repo_root)
    contract, contract_hash = load_contract(repo_root)
    _verify_frozen_runtime(contract, repo_root)
    source_commit = _source_commit(repo_root)
    retained = _mapping(recovery["retained_challenger"], "retained challenger")
    preserved = _mapping(recovery["preserved_terminal_attempt"], "preserved attempt")
    expected_challenger_root = Path(cast(str, retained["root"])).resolve()
    preserved_root = Path(cast(str, preserved["root"])).resolve()
    if challenger_model_root.resolve() != expected_challenger_root:
        raise SelectionError("recovery challenger root identity drift")
    baseline_spec = baseline_identity_spec(_load_baseline_contract(repo_root))
    validate_model_artifact_root(baseline_spec, baseline_model_root)
    challenger_spec = challenger_identity_spec(contract)
    validate_model_artifact_root(challenger_spec, challenger_model_root)
    if (
        _sha256_file(challenger_model_root / "model.safetensors")
        != retained["model_safetensors_sha256"]
    ):
        raise SelectionError("recovery challenger model hash drift")
    if not root.is_absolute() or root.exists():
        raise SelectionError("recovery root must be absolute and not already exist")
    if (
        repo_root.resolve() == root.resolve()
        or repo_root.resolve() in root.resolve().parents
        or preserved_root == root.resolve()
        or preserved_root in root.resolve().parents
        or challenger_model_root.resolve() == root.resolve()
        or challenger_model_root.resolve() in root.resolve().parents
        or not root.parent.is_dir()
        or root.parent.is_symlink()
    ):
        raise SelectionError(
            "recovery root parent is unavailable or inside the repository"
        )
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    root.mkdir(mode=0o700, parents=False)
    ledger_path = _default_recovery_ledger_path()
    try:
        _claim_recovery(root, ledger_path, source_commit=source_commit)
    except BaseException:
        root.rmdir()
        raise
    _write_json(
        root / ATTEMPT_FILE,
        {
            "schema_version": "dspx-oracle-embedding-selection-recovery-attempt-v1",
            "status": "started_terminal_result_pending",
            "recovery_contract_sha256": recovery_hash,
            "base_contract_sha256": contract_hash,
            "ak_task_id": _RECOVERY_TASK_ID,
            "source_commit": source_commit,
            "attempt_budget_consumed": 1,
            "selective_rerun_allowed": False,
            "model_artifact_acquisitions": 0,
            "preserved_attempt_status_sha256": preserved["attempt_status_sha256"],
            "preserved_ledger_sha256": preserved["ledger_sha256"],
        },
    )
    try:
        baseline = _run_baseline(
            repo_root=repo_root,
            contract=contract,
            model_root=baseline_model_root,
            root=root,
        )
        challenger, resources, vector_hashes = _run_challenger(
            contract=contract,
            model_root=challenger_model_root,
            root=root,
        )
        resources["artifact_acquisition_seconds"] = 0.0
        resources["model_artifact_acquisitions"] = 0
        result = select_model(
            contract=contract,
            baseline=baseline,
            challenger=challenger,
            resources=resources,
        )
        result["full_batch_reproduction"] = {
            "verified": True,
            "vector_hashes": vector_hashes,
        }
        result["source_commit"] = source_commit
        result["recovery"] = {
            "schema_version": "dspx-oracle-embedding-selection-recovery-result-v1",
            "recovery_contract_sha256": recovery_hash,
            "ak_task_id": _RECOVERY_TASK_ID,
            "model_artifact_acquisitions": 0,
            "network_calls": 0,
            "removed_model_input_keys": ["token_type_ids"],
            "preserved_attempt_status_sha256": preserved["attempt_status_sha256"],
            "preserved_ledger_sha256": preserved["ledger_sha256"],
        }
        _write_json(root / RESULT_FILE, result)
        verification = _run_independent_verifier(
            repo_root=repo_root,
            root=root,
            baseline_model_root=baseline_model_root,
            challenger_model_root=challenger_model_root,
            recovered_adapter=True,
        )
        _write_json(root / VERIFICATION_FILE, verification)
        terminal = (
            "passed" if result["status"] == "passed" else "challenger_not_selected"
        )
        evidence = {
            "result_sha256": _sha256_file(root / RESULT_FILE),
            "verification_sha256": _sha256_file(root / VERIFICATION_FILE),
            "selected_model": result["selected_model"],
            "model_artifact_acquisitions": 0,
        }
        _write_json(
            root / ATTEMPT_FILE,
            {
                "schema_version": "dspx-oracle-embedding-selection-recovery-attempt-v1",
                "status": terminal,
                "recovery_contract_sha256": recovery_hash,
                "base_contract_sha256": contract_hash,
                "ak_task_id": _RECOVERY_TASK_ID,
                "source_commit": source_commit,
                "attempt_budget_consumed": 1,
                "selective_rerun_allowed": False,
                **evidence,
            },
        )
        _update_recovery_ledger(
            ledger_path,
            root=root,
            source_commit=source_commit,
            status=terminal,
            evidence=evidence,
        )
        print(json.dumps({"status": terminal, **evidence}, indent=2, sort_keys=True))
        return 0 if terminal == "passed" else 1
    except BaseException as exc:
        sanitized = str(exc).replace(str(root), "<recovery-root>")[:500]
        _write_json(
            root / ATTEMPT_FILE,
            {
                "schema_version": "dspx-oracle-embedding-selection-recovery-attempt-v1",
                "status": "failed_or_indeterminate_terminal",
                "recovery_contract_sha256": recovery_hash,
                "base_contract_sha256": contract_hash,
                "ak_task_id": _RECOVERY_TASK_ID,
                "source_commit": source_commit,
                "attempt_budget_consumed": 1,
                "selective_rerun_allowed": False,
                "error_class": type(exc).__name__,
                "error": sanitized,
            },
        )
        _update_recovery_ledger(
            ledger_path,
            root=root,
            source_commit=source_commit,
            status="failed_or_indeterminate_terminal",
            evidence={"error_class": type(exc).__name__},
        )
        raise


def main() -> int:
    _exec_in_frozen_runtime()
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--baseline-model-root", type=Path, required=True)
    parser.add_argument("--challenger-model-root", type=Path)
    parser.add_argument("--recover", action="store_true")
    parser.add_argument("--recovered-adapter", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    try:
        if args.verify_only:
            verification = _verify_only(
                repo_root=repo_root,
                root=args.root.resolve(),
                baseline_model_root=args.baseline_model_root.resolve(),
                challenger_model_root=(
                    args.challenger_model_root.resolve()
                    if args.challenger_model_root is not None
                    else None
                ),
                recovered_adapter=args.recovered_adapter,
            )
            print(json.dumps(verification, indent=2, sort_keys=True))
            return 0
        if args.recover:
            if args.challenger_model_root is None:
                raise SelectionError("--recover requires --challenger-model-root")
            return _recover_and_run(
                repo_root=repo_root,
                root=args.root.resolve(),
                baseline_model_root=args.baseline_model_root.resolve(),
                challenger_model_root=args.challenger_model_root.resolve(),
            )
        return _acquire_and_run(
            repo_root=repo_root,
            root=args.root.resolve(),
            baseline_model_root=args.baseline_model_root.resolve(),
        )
    except (
        EmbeddingIdentityError,
        MDenseOnError,
        SelectionError,
        OSError,
        subprocess.SubprocessError,
        ValueError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
