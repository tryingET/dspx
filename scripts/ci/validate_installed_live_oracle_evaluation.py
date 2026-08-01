#!/usr/bin/env python3
# summary: "Validates the no-live installed corpus and Oracle evaluation contract."
# read_when:
#   - "Changing declared live corpus strata, attempt budgets, or Oracle semantic evaluation gates."

from __future__ import annotations

import ast
import hashlib
import json
import os
import stat
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

CONTRACT_SCHEMA = "dspx-installed-live-oracle-evaluation-contract-v1"
CORPUS_SCHEMA = "dspx-program-semantic-benchmark-corpus-v2"
EXPECTED_CONTRACT_FILE_SHA256 = (
    "9ff735cd4ba29cfe430c9bce12d697877fa18a91cff78bd98defedcdeed5201a"
)
EXPECTED_CORPUS_FILE_SHA256 = (
    "4c877c7992d8b70044645c57e2753ea9f170da027179376cafbc4d6000db0ec9"
)
EXPECTED_MODEL_ROLES_FILE_SHA256 = (
    "8d4a8b6c8de2de11482475bf8ae5d245dd8b82592e6957854f2d1f173be174d2"
)
EXPECTED_EMBEDDINGS_FILE_SHA256 = (
    "ae3be19a7935b15f15fcae49bd527122625a0485254690e92abbd5f2e5b0bc87"
)
EXPECTED_CASES = (
    (
        "single-module-authority-boundary",
        "64105f9a7743f0c145af1d6b3d14057177c42fd71349af693f32d20fad715aeb",
    ),
    (
        "pipeline-evidence-calibration",
        "56d8a9dc8b41f6e357f41a6f1357ab58ca00c342f54335e88f6f1eb86d1b1493",
    ),
    (
        "pdf-transition-review-runtime-replay",
        "c189e6a0d4a98e781418cf1e05aadafc1c0e90177f62063fcacc12b97c3ad2e7",
    ),
)
EXPECTED_EFFECTS = {
    "provider_calls": 0,
    "embedding_models_loaded": 0,
    "model_artifacts_downloaded": 0,
    "shared_store_connections": 0,
    "oracle_records_written": 0,
    "ak_mutated": False,
    "governance_mutated": False,
    "publication_performed": False,
}
EXPECTED_NONCLAIMS = {
    "representative_live_quality": False,
    "statistical_representativeness": False,
    "production_semantic_oracle_quality": False,
    "resolved_live_model_identity": False,
    "provider_transport_call_cardinality": False,
    "provider_internal_retry_absence": False,
    "shared_backend_readiness": False,
    "release_readiness": False,
    "release_authority": False,
    "package_publication": False,
    "production_activation": False,
}
_MAX_BYTES = 1_000_000


class ContractValidationError(ValueError):
    """Raised when the pre-live contract widens or drifts."""


def _read_bytes(path: Path, *, label: str) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ContractValidationError(
            f"{label} must be an existing regular non-symlink file: {path}"
        ) from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ContractValidationError(f"{label} must be a regular file: {path}")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            raw = stream.read(_MAX_BYTES + 1)
            after = os.fstat(stream.fileno())
        if len(raw) > _MAX_BYTES:
            raise ContractValidationError(
                f"{label} exceeds the {_MAX_BYTES}-byte bound: {path}"
            )
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
            raise ContractValidationError(f"{label} changed while being read: {path}")
        return raw
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _read_json(path: Path, *, label: str) -> tuple[dict[str, Any], bytes]:
    raw = _read_bytes(path, label=label)
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractValidationError(f"{label} must be valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ContractValidationError(f"{label} must contain one JSON object")
    return cast(dict[str, Any], payload), raw


def _read_contract(path: Path) -> tuple[dict[str, Any], bytes]:
    contract, raw = _read_json(path, label="evaluation contract")
    _expect(
        hashlib.sha256(raw).hexdigest(),
        EXPECTED_CONTRACT_FILE_SHA256,
        "contract file hash",
    )
    return contract, raw


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractValidationError(f"{label} must be an object")
    return cast(Mapping[str, Any], value)


def _sequence(value: object, label: str) -> Sequence[Any]:
    if not isinstance(value, list):
        raise ContractValidationError(f"{label} must be an array")
    return value


def _strict_equal(value: object, expected: object) -> bool:
    if type(value) is not type(expected):
        return False
    if isinstance(expected, dict):
        if not isinstance(value, dict) or set(value) != set(expected):
            return False
        actual = cast(dict[object, object], value)
        expected_mapping = cast(dict[object, object], expected)
        return all(
            _strict_equal(actual[key], item) for key, item in expected_mapping.items()
        )
    if isinstance(expected, list):
        return (
            isinstance(value, list)
            and len(value) == len(expected)
            and all(
                _strict_equal(left, right)
                for left, right in zip(value, expected, strict=True)
            )
        )
    return value == expected


def _expect(value: object, expected: object, label: str) -> None:
    if not _strict_equal(value, expected):
        raise ContractValidationError(
            f"{label} drift: expected {expected!r}, observed {value!r}"
        )


def _canonical_sha256(value: object) -> str:
    raw = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _constant_keyword(call: ast.Call, name: str, label: str) -> str:
    for keyword in call.keywords:
        if keyword.arg == name and isinstance(keyword.value, ast.Constant):
            value = keyword.value.value
            if isinstance(value, str):
                return value
    raise ContractValidationError(f"{label} source constant {name!r} is unavailable")


def _model_role_source_identity(path: Path) -> tuple[str, str]:
    raw = _read_bytes(path, label="model roles source")
    _expect(
        hashlib.sha256(raw).hexdigest(),
        EXPECTED_MODEL_ROLES_FILE_SHA256,
        "model roles source hash",
    )
    tree = ast.parse(raw, filename=str(path))
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        if any(
            isinstance(target, ast.Name) and target.id == "ORACLE_SEMANTIC_ROLE"
            for target in node.targets
        ):
            return (
                _constant_keyword(node.value, "model", "Oracle semantic role"),
                _constant_keyword(
                    node.value, "reasoning_effort", "Oracle semantic role"
                ),
            )
    raise ContractValidationError(
        "ORACLE_SEMANTIC_ROLE source declaration is unavailable"
    )


def _embedding_source_identity(path: Path) -> tuple[set[str], str]:
    raw = _read_bytes(path, label="embedding source")
    _expect(
        hashlib.sha256(raw).hexdigest(),
        EXPECTED_EMBEDDINGS_FILE_SHA256,
        "embedding source hash",
    )
    tree = ast.parse(raw, filename=str(path))
    backends: set[str] | None = None
    model: str | None = None
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name)
                and target.id == "_VALID_EMBEDDING_BACKENDS"
                for target in node.targets
            )
            and isinstance(node.value, ast.Set)
        ):
            values = [
                item.value
                for item in node.value.elts
                if isinstance(item, ast.Constant) and isinstance(item.value, str)
            ]
            backends = set(values)
        if (
            isinstance(node, ast.ClassDef)
            and node.name == "SentenceTransformerEmbedder"
        ):
            for method in node.body:
                if (
                    isinstance(method, ast.FunctionDef)
                    and method.name == "__init__"
                    and method.args.defaults
                    and isinstance(method.args.defaults[-1], ast.Constant)
                    and isinstance(method.args.defaults[-1].value, str)
                ):
                    model = method.args.defaults[-1].value
    if backends is None or model is None:
        raise ContractValidationError(
            "embedding backend source identity is unavailable"
        )
    return backends, model


def _require_canonical_path(supplied: Path, canonical: Path, label: str) -> None:
    if (
        supplied.absolute() != canonical.absolute()
        or supplied.resolve() != canonical.resolve()
    ):
        raise ContractValidationError(f"{label} must be canonical path {canonical}")


def _validate_corpus(
    contract: Mapping[str, Any], corpus: Mapping[str, Any], raw: bytes
) -> None:
    _expect(
        hashlib.sha256(raw).hexdigest(), EXPECTED_CORPUS_FILE_SHA256, "corpus file hash"
    )
    _expect(
        set(corpus),
        {"schema_version", "name", "version", "thresholds", "cases"},
        "corpus fields",
    )
    _expect(corpus.get("schema_version"), CORPUS_SCHEMA, "corpus schema")
    _expect(corpus.get("name"), "dspx-generated-program-semantic-corpus", "corpus name")
    _expect(corpus.get("version"), 2, "corpus version")
    _expect(
        corpus.get("thresholds"),
        {"min_overall_score": 1.0, "min_case_score": 1.0, "max_failed_cases": 0},
        "corpus thresholds",
    )
    cases = _sequence(corpus.get("cases"), "corpus cases")
    _expect(len(cases), len(EXPECTED_CASES), "corpus case count")
    for index, (case_id, case_hash) in enumerate(EXPECTED_CASES):
        case = _mapping(cases[index], f"corpus case {index}")
        _expect(case.get("id"), case_id, f"corpus case {index} id")
        _expect(_canonical_sha256(case), case_hash, f"corpus case {index} hash")

    source = _mapping(contract.get("source_corpus"), "source_corpus")
    _expect(
        source.get("file_sha256"), EXPECTED_CORPUS_FILE_SHA256, "declared corpus hash"
    )
    _expect(
        source.get("coverage_claim"),
        "declared_strata_only_not_statistically_representative",
        "coverage claim",
    )


def _validate_source_bindings(
    contract: Mapping[str, Any], *, model_roles_path: Path, embeddings_path: Path
) -> None:
    role_model, role_effort = _model_role_source_identity(model_roles_path)
    backend_names, embedding_model = _embedding_source_identity(embeddings_path)
    _expect(
        backend_names,
        {"none", "mock", "sentence-transformers"},
        "embedding backend set",
    )
    oracle = _mapping(contract.get("oracle_evaluation"), "oracle_evaluation")
    semantic = _mapping(oracle.get("semantic_analysis_lm"), "semantic_analysis_lm")
    _expect(semantic.get("preferred_model"), role_model, "semantic preferred model")
    _expect(semantic.get("reasoning_effort"), role_effort, "semantic reasoning effort")
    embedding = _mapping(oracle.get("embedding_model"), "embedding_model")
    _expect(embedding.get("backend"), "sentence-transformers", "embedding backend")
    _expect(embedding.get("model"), embedding_model, "embedding model")
    _expect(
        embedding.get("production_semantic_claim_allowed"),
        False,
        "embedding production claim",
    )
    _expect(
        _mapping(oracle.get("coordinate_store"), "coordinate_store").get(
            "production_semantic_claim_allowed"
        ),
        False,
        "store production-semantic claim",
    )


def validate_contract(
    *, contract_path: Path, corpus_path: Path, repo_root: Path
) -> dict[str, Any]:
    root = repo_root.resolve()
    canonical_contract = (
        root / "benchmarks/semantic/installed-live-oracle-evaluation-v1.json"
    )
    canonical_corpus = root / "benchmarks/semantic/program-corpus-v2.json"
    model_roles_path = root / "packages/dspx-core/src/dspx/model_roles.py"
    embeddings_path = root / "packages/dspx-core/src/dspx/coordinates/embeddings.py"
    _require_canonical_path(contract_path, canonical_contract, "evaluation contract")
    _require_canonical_path(corpus_path, canonical_corpus, "source corpus")
    contract, contract_raw = _read_contract(contract_path)
    corpus, corpus_raw = _read_json(corpus_path, label="source corpus")
    _expect(contract.get("schema_version"), CONTRACT_SCHEMA, "contract schema")
    _expect(
        contract.get("status"), "offline_contract_ready_live_not_run", "contract status"
    )
    _validate_corpus(contract, corpus, corpus_raw)
    _validate_source_bindings(
        contract,
        model_roles_path=model_roles_path,
        embeddings_path=embeddings_path,
    )
    _expect(
        contract.get("contract_check_effects"), EXPECTED_EFFECTS, "declared operations"
    )
    _expect(contract.get("nonclaims"), EXPECTED_NONCLAIMS, "nonclaims")
    return {
        "schema_version": "dspx-installed-live-oracle-evaluation-contract-check-v1",
        "status": "passed",
        "contract_sha256": hashlib.sha256(contract_raw).hexdigest(),
        "corpus_file_sha256": hashlib.sha256(corpus_raw).hexdigest(),
        "case_ids": [row[0] for row in EXPECTED_CASES],
        "coverage_claim": "declared_strata_only_not_statistically_representative",
        "live_execution_status": "not_run",
        "embedding_evaluation_status": "not_run",
        "semantic_analysis_evaluation_status": "not_run",
        "declared_operation_contract": EXPECTED_EFFECTS,
        "production_semantic_claim_allowed": False,
    }


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    try:
        result = validate_contract(
            contract_path=repo_root
            / "benchmarks/semantic/installed-live-oracle-evaluation-v1.json",
            corpus_path=repo_root / "benchmarks/semantic/program-corpus-v2.json",
            repo_root=repo_root,
        )
    except ContractValidationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
