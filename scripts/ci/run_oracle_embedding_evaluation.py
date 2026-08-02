#!/usr/bin/env python3
# summary: "Runs the one-shot local Oracle embedding acquisition and evaluation sequence."
# read_when:
#   - "Executing or reviewing the frozen sentence-transformer held-out routing contract."

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pwd
import secrets
import shutil
import subprocess
import stat
import tempfile
import sys
from pathlib import Path
from typing import Any, Mapping, cast

from dspx.coordinates.embedding_identity import EmbeddingIdentityError
from dspx.coordinates.embeddings import SentenceTransformerEmbedder
from dspx.coordinates.oracle_embedding_evaluation import (
    DB_FILE,
    EXPECTED_CONTRACT_SHA256,
    EXPECTED_RECORD_IDS,
    EvaluationError,
    _array,
    _identity_spec,
    _mapping,
    evaluate_vectors,
    validate_complete_identity,
    validate_contract_payload,
)
from dspx.coordinates.oracle_embedding_verification import (
    MODEL_DIR,
    RESULT_FILE,
    reproduce_model_batch,
    verify_retained_evaluation,
)

__all__ = ["EXPECTED_RECORD_IDS", "validate_complete_identity"]

EXPECTED_SOURCE_HASHES = {
    "benchmarks/semantic/installed-live-oracle-evaluation-v1.json": (
        "9ff735cd4ba29cfe430c9bce12d697877fa18a91cff78bd98defedcdeed5201a"
    ),
    "benchmarks/semantic/program-corpus-v2.json": (
        "4c877c7992d8b70044645c57e2753ea9f170da027179376cafbc4d6000db0ec9"
    ),
    "uv.lock": "d941b76c442e4c89143b1ab0abcc03a57b477943e6cb0e588bc08c3ec5a4ef09",
}
VERIFICATION_FILE = "independent-verification.json"
ATTEMPT_FILE = "attempt-status.json"
_EXPECTED_UV_VERSION = "uv 0.11.14 (3fdfdc7d4 2026-05-12 x86_64-unknown-linux-gnu)"
_HANDOFF_PATH_ENV = "DSPX_ORACLE_EMBEDDING_HANDOFF_PATH"
_HANDOFF_NONCE_ENV = "DSPX_ORACLE_EMBEDDING_HANDOFF_NONCE"
_FROZEN_RUNTIME_VERIFIED = False
FROZEN_LOCK_COMMIT = "7b71dbd92405a3a903e93918c3299090f0347087"


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
            raise EvaluationError("frozen-runtime handoff identity is invalid")
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as stream:
            raw = stream.read(4097)
        if len(raw) > 4096:
            raise EvaluationError("frozen-runtime handoff exceeds size bound")
        payload = json.loads(raw)
        path.unlink()
    except (OSError, json.JSONDecodeError) as exc:
        raise EvaluationError("frozen-runtime handoff is unavailable") from exc
    if payload != {
        "nonce": nonce,
        "lock_sha256": EXPECTED_SOURCE_HASHES["uv.lock"],
        "uv_version": _EXPECTED_UV_VERSION,
    }:
        raise EvaluationError("frozen-runtime handoff receipt drift")
    return True


def _exec_in_frozen_runtime() -> None:
    global _FROZEN_RUNTIME_VERIFIED
    if _consume_runtime_handoff():
        _FROZEN_RUNTIME_VERIFIED = True
        return
    uv = shutil.which("uv")
    if uv is None:
        raise EvaluationError("uv is required for the frozen isolated runtime")
    observed_version = subprocess.run(
        [uv, "--version"], check=True, capture_output=True, text=True
    ).stdout.strip()
    if observed_version != _EXPECTED_UV_VERSION:
        raise EvaluationError(f"uv runtime version drift: {observed_version!r}")
    nonce = secrets.token_hex(32)
    descriptor, handoff_name = tempfile.mkstemp(
        prefix="dspx-oracle-embedding-handoff-", suffix=".json"
    )
    handoff = Path(handoff_name).resolve()
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(
                {
                    "nonce": nonce,
                    "lock_sha256": EXPECTED_SOURCE_HASHES["uv.lock"],
                    "uv_version": _EXPECTED_UV_VERSION,
                },
                stream,
                sort_keys=True,
            )
            stream.flush()
            os.fsync(stream.fileno())
        environment = {
            **os.environ,
            _HANDOFF_PATH_ENV: str(handoff),
            _HANDOFF_NONCE_ENV: nonce,
        }
        os.execve(
            uv,
            [
                uv,
                "run",
                "--isolated",
                "--frozen",
                "--package",
                "dspx-core",
                "--extra",
                "oracle-embeddings",
                "python",
                str(Path(__file__).resolve()),
                *sys.argv[1:],
            ],
            environment,
        )
    finally:
        handoff.unlink(missing_ok=True)


def _default_attempt_ledger_path() -> Path:
    account_home = Path(pwd.getpwuid(os.getuid()).pw_dir).resolve()
    return (
        account_home
        / ".local/state/dspx/oracle-embedding-evaluations"
        / f"{EXPECTED_CONTRACT_SHA256}.json"
    )


def _claim_attempt(root: Path, ledger_path: Path) -> None:
    ledger_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    payload = {
        "schema_version": "dspx-oracle-embedding-attempt-ledger-v1",
        "status": "started_effect_indeterminate_if_interrupted",
        "contract_sha256": EXPECTED_CONTRACT_SHA256,
        "root": str(root),
        "attempt_budget_consumed": 1,
        "another_root_allowed": False,
    }
    raw = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
    try:
        descriptor = os.open(ledger_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise EvaluationError(
            "the canonical local attempt ledger is already consumed"
        ) from exc
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _update_attempt_ledger(
    ledger_path: Path, *, root: Path, status: str, evidence: Mapping[str, Any]
) -> None:
    _write_json(
        ledger_path,
        {
            "schema_version": "dspx-oracle-embedding-attempt-ledger-v1",
            "status": status,
            "contract_sha256": EXPECTED_CONTRACT_SHA256,
            "root": str(root),
            "attempt_budget_consumed": 1,
            "another_root_allowed": False,
            "evidence": dict(evidence),
        },
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_git_blob(repo_root: Path, commit: str, path: str) -> str:
    try:
        raw = subprocess.check_output(
            ["git", "-C", str(repo_root), "show", f"{commit}:{path}"],
            stderr=subprocess.STDOUT,
        )
    except subprocess.CalledProcessError as exc:
        raise EvaluationError(
            f"frozen source binding is unavailable: {commit}:{path}"
        ) from exc
    return hashlib.sha256(raw).hexdigest()


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


def load_contract(repo_root: Path) -> tuple[dict[str, Any], str]:
    contract_path = (
        repo_root / "benchmarks/semantic/oracle-embedding-evaluation-v1.json"
    )
    raw = contract_path.read_bytes()
    observed_hash = hashlib.sha256(raw).hexdigest()
    if observed_hash != EXPECTED_CONTRACT_SHA256:
        raise EvaluationError("embedding evaluation contract byte hash drift")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise EvaluationError("embedding evaluation contract must be an object")
    contract = cast(dict[str, Any], payload)
    validate_contract_payload(contract)
    for relative_path, expected_hash in EXPECTED_SOURCE_HASHES.items():
        observed_source_hash = (
            _sha256_git_blob(repo_root, FROZEN_LOCK_COMMIT, relative_path)
            if relative_path == "uv.lock"
            else _sha256_file(repo_root / relative_path)
        )
        if observed_source_hash != expected_hash:
            raise EvaluationError(f"source binding drift: {relative_path}")
    return contract, observed_hash


def _acquire_and_run(*, repo_root: Path, root: Path) -> int:
    if not _FROZEN_RUNTIME_VERIFIED:
        raise EvaluationError(
            "evaluation requires the authenticated isolated frozen uv runtime"
        )
    if not root.is_absolute() or root.exists():
        raise EvaluationError(
            "evaluation root must be absolute and must not already exist"
        )
    if (
        repo_root.resolve() in root.resolve().parents
        or root.resolve() == repo_root.resolve()
    ):
        raise EvaluationError("evaluation root must remain outside the repository")
    contract, contract_hash = load_contract(repo_root)
    ledger_path = _default_attempt_ledger_path()
    _claim_attempt(root, ledger_path)
    try:
        root.mkdir(mode=0o700, parents=False)
    except BaseException as exc:
        _update_attempt_ledger(
            ledger_path,
            root=root,
            status="failed_or_indeterminate_terminal",
            evidence={"error_class": type(exc).__name__},
        )
        raise
    _write_json(
        root / ATTEMPT_FILE,
        {
            "schema_version": "dspx-oracle-embedding-evaluation-attempt-v1",
            "status": "started_terminal_result_pending",
            "contract_sha256": contract_hash,
            "attempt_budget_consumed": 1,
            "selective_rerun_allowed": False,
        },
    )
    model_root = root / MODEL_DIR
    try:
        from huggingface_hub import snapshot_download

        spec = _identity_spec(contract)
        downloaded = snapshot_download(
            repo_id=spec.repository_id,
            revision=spec.revision,
            local_dir=model_root,
            allow_patterns=list(spec.artifact_paths),
            token=False,
            max_workers=1,
        )
        if Path(downloaded).resolve() != model_root.resolve():
            raise EvaluationError(
                "model acquisition did not retain the requested local root"
            )
        embedder = SentenceTransformerEmbedder(
            spec.repository_id,
            model_root=model_root,
            normalize_embeddings=spec.normalize_embeddings,
            device=spec.device,
        )
        evaluation = _mapping(contract["evaluation"], "evaluation")
        record_texts = [
            cast(str, _mapping(row, "record")["text"])
            for row in _array(evaluation["records"], "records")
        ]
        query_texts = [
            cast(str, _mapping(row, "query")["text"])
            for row in _array(evaluation["queries"], "queries")
        ]
        vectors = embedder.encode([*record_texts, *query_texts])
        identity = embedder.build_identity(
            spec, frozen_runtime_lock_sha256=spec.runtime_lock_sha256
        )
        result = evaluate_vectors(
            contract=contract,
            identity=identity,
            document_vectors=vectors[: len(record_texts)],
            query_vectors=vectors[len(record_texts) :],
            database_path=root / DB_FILE,
        )
        result["model_reproduction"] = reproduce_model_batch(
            contract=contract,
            result=result,
            model_root=model_root,
        )
        claims = _mapping(result["claims"], "evaluation claims")
        cast(dict[str, Any], claims)["full_batch_model_reproduction_verified"] = True
        _write_json(root / RESULT_FILE, result)
        verification = verify_retained_evaluation(root, contract)
        _write_json(root / VERIFICATION_FILE, verification)
        _write_json(
            root / ATTEMPT_FILE,
            {
                "schema_version": "dspx-oracle-embedding-evaluation-attempt-v1",
                "status": "passed" if result["status"] == "passed" else "semantic_miss",
                "contract_sha256": contract_hash,
                "attempt_budget_consumed": 1,
                "selective_rerun_allowed": False,
                "result_sha256": _sha256_file(root / RESULT_FILE),
                "verification_sha256": _sha256_file(root / VERIFICATION_FILE),
            },
        )
        _update_attempt_ledger(
            ledger_path,
            root=root,
            status="passed" if result["status"] == "passed" else "semantic_miss",
            evidence={
                "result_sha256": _sha256_file(root / RESULT_FILE),
                "verification_sha256": _sha256_file(root / VERIFICATION_FILE),
            },
        )
        return 0 if result["status"] == "passed" else 1
    except BaseException as exc:
        _write_json(
            root / ATTEMPT_FILE,
            {
                "schema_version": "dspx-oracle-embedding-evaluation-attempt-v1",
                "status": "failed_or_indeterminate_terminal",
                "contract_sha256": contract_hash,
                "attempt_budget_consumed": 1,
                "selective_rerun_allowed": False,
                "error_class": type(exc).__name__,
                "error": str(exc).replace(str(root), "<evaluation-root>")[:500],
            },
        )
        _update_attempt_ledger(
            ledger_path,
            root=root,
            status="failed_or_indeterminate_terminal",
            evidence={"error_class": type(exc).__name__},
        )
        raise


def main() -> int:
    _exec_in_frozen_runtime()
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    try:
        contract, _ = load_contract(repo_root)
        if args.verify_only:
            verification = verify_retained_evaluation(args.root.resolve(), contract)
            print(json.dumps(verification, indent=2, sort_keys=True))
            return 0
        return _acquire_and_run(repo_root=repo_root, root=args.root)
    except (EvaluationError, EmbeddingIdentityError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
