# summary: "Validates and scores the frozen candidate-local Oracle embedding evaluation."
# read_when:
#   - "Changing held-out embedding contracts, metric gates, or candidate-local scoring."

"""Deterministic contract and scoring logic for Oracle embedding evaluation."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence, cast

from .embedding_identity import (
    ModelArtifactExpectation,
    SentenceTransformerIdentitySpec,
    validate_unit_vector,
)
from .embeddings import ExecutionEmbedding
from .storage import CoordinateIndex

CONTRACT_SCHEMA = "dspx-oracle-embedding-evaluation-contract-v1"
RESULT_SCHEMA = "dspx-oracle-embedding-evaluation-result-v1"
EXPECTED_CONTRACT_SHA256 = (
    "819204905f94449013fb25a5f6e21157db36210cbaa4b6e6e8811bb67ca3e92e"
)
EXPECTED_RECORD_IDS = (
    "single-module-authority-boundary",
    "pipeline-evidence-calibration",
    "pdf-transition-review-runtime-replay",
)
EXPECTED_QUERY_IDS = (
    "authority-boundary-paraphrase",
    "calibration-paraphrase",
    "review-only-paraphrase",
)
DB_FILE = "oracle-evaluation.sqlite3"


class EvaluationError(ValueError):
    """Raised when the frozen evaluation contract or evidence fails closed."""


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _vector_sha256(vector: Sequence[float]) -> str:
    raw = json.dumps(list(vector), separators=(",", ":"), allow_nan=False).encode()
    return _sha256_bytes(raw)


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise EvaluationError(f"{label} must be an object")
    return cast(Mapping[str, Any], value)


def _array(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise EvaluationError(f"{label} must be an array")
    return value


def validate_contract_payload(contract: Mapping[str, Any]) -> None:
    """Validate execution-critical structure after the fixed byte hash passes."""

    if contract.get("schema_version") != CONTRACT_SCHEMA:
        raise EvaluationError("embedding evaluation contract schema drift")
    if contract.get("status") != "precommitted_evaluation_not_run":
        raise EvaluationError("embedding evaluation contract status drift")
    backend = _mapping(contract.get("backend"), "backend")
    if backend.get("name") != "sentence-transformers":
        raise EvaluationError(
            "only the frozen sentence-transformers backend is allowed"
        )
    if backend.get("repository_id") != "sentence-transformers/all-MiniLM-L6-v2":
        raise EvaluationError("model repository drift")
    revision = backend.get("revision")
    if not isinstance(revision, str) or len(revision) != 40:
        raise EvaluationError("model revision must be an exact commit")
    if backend.get("dependency") != "sentence-transformers==5.1.2":
        raise EvaluationError("sentence-transformers runtime dependency drift")
    if backend.get("torch_dependency") != "torch==2.13.0+cpu":
        raise EvaluationError("CPU-only torch runtime dependency drift")
    manifest = _array(backend.get("artifact_manifest"), "artifact manifest")
    if len(manifest) != 10:
        raise EvaluationError("loader-relevant artifact manifest drift")
    runtime_environment = _mapping(
        backend.get("runtime_environment"), "runtime environment"
    )
    if (
        runtime_environment.get("lock_path") != "uv.lock"
        or runtime_environment.get("device") != "cpu"
        or runtime_environment.get("python_implementation") != "cpython"
        or runtime_environment.get("python_major_minor") != "3.13"
        or runtime_environment.get("platform") != "linux-x86_64"
        or runtime_environment.get("lock_sha256")
        != _mapping(
            _mapping(contract.get("source_bindings"), "source bindings").get("uv_lock"),
            "uv lock binding",
        ).get("sha256")
        or runtime_environment.get("installer") != "uv_run_isolated_frozen"
        or runtime_environment.get("uv_version")
        != "uv 0.11.14 (3fdfdc7d4 2026-05-12 x86_64-unknown-linux-gnu)"
        or set(
            _mapping(
                runtime_environment.get("selected_wheel_sha256"),
                "selected wheel hashes",
            )
        )
        != set(
            _mapping(
                runtime_environment.get("expected_package_versions"),
                "expected package versions",
            )
        )
    ):
        raise EvaluationError("runtime lock, Python, or device identity drift")
    if backend.get("expected_dimension") != 384 or isinstance(
        backend.get("expected_dimension"), bool
    ):
        raise EvaluationError("embedding dimension drift")
    normalization = _mapping(backend.get("normalization"), "normalization")
    distance = _mapping(backend.get("distance"), "distance")
    if normalization != {
        "encode_normalize_embeddings": True,
        "postcondition": "finite_l2_unit_vector",
    }:
        raise EvaluationError("normalization contract drift")
    if distance != {
        "ranking_metric": "cosine_similarity_descending",
        "reported_distance": "one_minus_cosine_similarity",
    }:
        raise EvaluationError("distance contract drift")

    evaluation = _mapping(contract.get("evaluation"), "evaluation")
    records = _array(evaluation.get("records"), "evaluation records")
    queries = _array(evaluation.get("queries"), "evaluation queries")
    if (
        tuple(_mapping(row, "record").get("case_id") for row in records)
        != EXPECTED_RECORD_IDS
    ):
        raise EvaluationError("record order or identity drift")
    if tuple(_mapping(row, "query").get("id") for row in queries) != EXPECTED_QUERY_IDS:
        raise EvaluationError("query order or identity drift")
    if (
        tuple(_mapping(row, "query").get("expected_case_id") for row in queries)
        != EXPECTED_RECORD_IDS
    ):
        raise EvaluationError("held-out label order drift")
    for label, rows, text_key in (
        ("record", records, "text"),
        ("query", queries, "text"),
    ):
        if any(
            not isinstance(_mapping(row, label).get(text_key), str)
            or not _mapping(row, label)[text_key]
            for row in rows
        ):
            raise EvaluationError(f"{label} text must be non-empty")
    thresholds = _mapping(evaluation.get("thresholds"), "thresholds")
    if thresholds != {
        "recall_at_1": 1.0,
        "mean_reciprocal_rank": 1.0,
        "normalized_discounted_cumulative_gain_at_3": 1.0,
        "minimum_labeled_query_count": 3,
    }:
        raise EvaluationError("metric thresholds drift")
    budget = _mapping(contract.get("attempt_budget"), "attempt_budget")
    if budget.get("maximum_model_acquisition_and_evaluation_sequences") != 1:
        raise EvaluationError("model acquisition attempt budget drift")
    if budget.get("selective_query_reruns_allowed") is not False:
        raise EvaluationError("selective query reruns must remain forbidden")
    enforcement = _mapping(budget.get("enforcement"), "attempt enforcement")
    if (
        enforcement.get("kind") != "canonical_local_atomic_consumed_marker"
        or enforcement.get("marker_created_before_model_acquisition") is not True
        or enforcement.get("started_or_terminal_marker_forbids_another_root")
        is not True
    ):
        raise EvaluationError("one-shot attempt ledger enforcement drift")
    effects = _mapping(contract.get("effects"), "effects")
    if any(type(value) is not int or value != 0 for value in effects.values()):
        raise EvaluationError("forbidden evaluation effect declared")


def _identity_spec(contract: Mapping[str, Any]) -> SentenceTransformerIdentitySpec:
    backend = _mapping(contract["backend"], "backend")
    normalization = _mapping(backend["normalization"], "normalization")
    distance = _mapping(backend["distance"], "distance")
    runtime = _mapping(backend["runtime_environment"], "runtime environment")
    manifest = tuple(
        ModelArtifactExpectation(
            path=cast(str, row["path"]),
            size=cast(int, row["size"]),
            source_git_oid=cast(str, row["source_git_oid"]),
            lfs_sha256=cast(str | None, row["lfs_sha256"]),
        )
        for row in (
            _mapping(value, "artifact expectation")
            for value in _array(backend["artifact_manifest"], "artifact manifest")
        )
    )
    versions = _mapping(
        runtime["expected_package_versions"], "expected package versions"
    )
    wheel_hashes = _mapping(runtime["selected_wheel_sha256"], "selected wheel hashes")
    return SentenceTransformerIdentitySpec(
        repository_id=cast(str, backend["repository_id"]),
        revision=cast(str, backend["revision"]),
        artifact_manifest=manifest,
        expected_dimension=cast(int, backend["expected_dimension"]),
        normalize_embeddings=cast(bool, normalization["encode_normalize_embeddings"]),
        vector_dtype=cast(str, backend["vector_dtype"]),
        ranking_metric=cast(str, distance["ranking_metric"]),
        reported_distance=cast(str, distance["reported_distance"]),
        runtime_versions=tuple(
            sorted((name, cast(str, value)) for name, value in versions.items())
        ),
        runtime_lock_sha256=cast(str, runtime["lock_sha256"]),
        runtime_wheel_sha256=tuple(
            sorted((name, cast(str, value)) for name, value in wheel_hashes.items())
        ),
        runtime_installer=cast(str, runtime["installer"]),
        uv_version=cast(str, runtime["uv_version"]),
        platform=cast(str, runtime["platform"]),
        python_implementation=cast(str, runtime["python_implementation"]),
        python_major_minor=cast(str, runtime["python_major_minor"]),
        device=cast(str, runtime["device"]),
    )


def validate_complete_identity(
    contract: Mapping[str, Any], identity: Mapping[str, Any]
) -> None:
    """Require every precommitted identity field before evaluating a claim."""

    spec = _identity_spec(contract)
    if (
        identity.get("schema_version") != "dspx-sentence-transformer-identity-v1"
        or identity.get("backend") != "sentence-transformers"
        or identity.get("repository_id") != spec.repository_id
        or identity.get("revision") != spec.revision
        or identity.get("identity_complete") is not True
        or identity.get("production_semantic_claim_allowed") is not False
    ):
        raise EvaluationError("model backend or revision identity drift")
    artifacts = [
        _mapping(row, "identity artifact")
        for row in _array(identity.get("artifacts"), "identity artifacts")
    ]
    if tuple(row.get("path") for row in artifacts) != spec.artifact_paths:
        raise EvaluationError("model artifact identity path drift")
    for artifact, expected in zip(artifacts, spec.artifact_manifest, strict=True):
        digest = artifact.get("sha256")
        if (
            artifact.get("size") != expected.size
            or artifact.get("source_git_oid") != expected.source_git_oid
            or artifact.get("lfs_sha256") != expected.lfs_sha256
            or not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            or (expected.lfs_sha256 is not None and digest != expected.lfs_sha256)
        ):
            raise EvaluationError("model artifact provenance identity drift")
    tokenizer = _mapping(identity.get("tokenizer"), "tokenizer identity")
    expected_tokenizer_fields = set(
        cast(
            list[str],
            _mapping(contract["backend"], "backend")["tokenizer_runtime_fields"],
        )
    )
    if set(tokenizer) != expected_tokenizer_fields or any(
        value in (None, "") or isinstance(value, bool) for value in tokenizer.values()
    ):
        raise EvaluationError("tokenizer runtime identity is incomplete")
    runtime = _mapping(identity.get("runtime"), "runtime identity")
    if (
        not isinstance(runtime.get("python"), str)
        or not cast(str, runtime["python"]).startswith("3.13.")
        or runtime.get("python_implementation") != spec.python_implementation
        or runtime.get("lock_sha256") != spec.runtime_lock_sha256
        or runtime.get("wheel_sha256") != dict(spec.runtime_wheel_sha256)
        or runtime.get("installer") != spec.runtime_installer
        or runtime.get("uv_version") != spec.uv_version
        or runtime.get("isolated_frozen") is not True
        or runtime.get("platform") != spec.platform
        or set(
            _mapping(
                runtime.get("distribution_content_sha256"),
                "runtime distribution hashes",
            )
        )
        != set(spec.runtime_packages)
        or runtime.get("device") != spec.device
        or runtime.get("observations")
        != {
            "model_device": "cpu",
            "torch_cuda_available": False,
            "torch_default_dtype": "torch.float32",
            "numpy_output_dtype": "float32",
        }
        or any(
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            for digest in _mapping(
                runtime.get("distribution_content_sha256"),
                "runtime distribution hashes",
            ).values()
        )
        or _mapping(runtime.get("packages"), "runtime packages")
        != dict(spec.runtime_versions)
    ):
        raise EvaluationError("runtime package or lock identity drift")
    encoding = _mapping(identity.get("encoding"), "identity encoding")
    if encoding != {
        "dimension": spec.expected_dimension,
        "vector_dtype": spec.vector_dtype,
        "normalize_embeddings": True,
        "normalization_postcondition": "finite_l2_unit_vector",
    }:
        raise EvaluationError("encoding identity drift")
    if _mapping(identity.get("distance"), "distance identity") != {
        "ranking_metric": spec.ranking_metric,
        "reported_distance": spec.reported_distance,
    }:
        raise EvaluationError("distance identity drift")


def _metrics(expected_ranks: Sequence[int]) -> dict[str, float | int]:
    count = len(expected_ranks)
    if count == 0:
        raise EvaluationError("at least one labeled query is required")
    return {
        "labeled_query_count": count,
        "recall_at_1": sum(rank == 1 for rank in expected_ranks) / count,
        "mean_reciprocal_rank": sum(1.0 / rank for rank in expected_ranks) / count,
        "normalized_discounted_cumulative_gain_at_3": sum(
            1.0 / math.log2(rank + 1) if rank <= 3 else 0.0 for rank in expected_ranks
        )
        / count,
    }


def _metric_gate(
    metrics: Mapping[str, float | int], thresholds: Mapping[str, Any]
) -> bool:
    return (
        metrics["labeled_query_count"] >= thresholds["minimum_labeled_query_count"]
        and metrics["recall_at_1"] >= thresholds["recall_at_1"]
        and metrics["mean_reciprocal_rank"] >= thresholds["mean_reciprocal_rank"]
        and metrics["normalized_discounted_cumulative_gain_at_3"]
        >= thresholds["normalized_discounted_cumulative_gain_at_3"]
    )


def evaluate_vectors(
    *,
    contract: Mapping[str, Any],
    identity: Mapping[str, Any],
    document_vectors: Sequence[list[float]],
    query_vectors: Sequence[list[float]],
    database_path: Path,
) -> dict[str, Any]:
    """Index exact records, rank all queries once, and calculate frozen metrics."""

    validate_complete_identity(contract, identity)
    evaluation = _mapping(contract["evaluation"], "evaluation")
    records = [
        _mapping(row, "record") for row in _array(evaluation["records"], "records")
    ]
    queries = [
        _mapping(row, "query") for row in _array(evaluation["queries"], "queries")
    ]
    dimension = _mapping(identity["encoding"], "identity encoding")["dimension"]
    if len(document_vectors) != len(records) or len(query_vectors) != len(queries):
        raise EvaluationError("vector count does not match the frozen evaluation")
    for vector in [*document_vectors, *query_vectors]:
        if len(vector) != dimension:
            raise EvaluationError("mixed embedding dimension")
        validate_unit_vector(vector)

    index = CoordinateIndex(db_path=database_path)
    embeddings = [
        ExecutionEmbedding(
            run_id=cast(str, record["case_id"]),
            vector=vector,
            input_text=cast(str, record["text"]),
            output_text="",
            config_text="frozen-oracle-embedding-evaluation-v1",
            run_kind="semantic-routing-record",
            provider="sentence-transformers",
            template_version="oracle-embedding-evaluation-v1",
            created_at="2026-08-01T00:00:00+00:00",
            dimension=cast(int, dimension),
            metadata={"embedding_backend": dict(identity)},
        )
        for record, vector in zip(records, document_vectors, strict=True)
    ]
    if index.upsert_batch(embeddings) != len(embeddings):
        raise EvaluationError("candidate-local SQLite indexing was incomplete")

    query_rows: list[dict[str, Any]] = []
    ranks: list[int] = []
    falsifiers: list[str] = []
    for query, vector in zip(queries, query_vectors, strict=True):
        results = index.search(vector, top_k=len(records), min_similarity=-1.0)
        if len(results) != len(records):
            raise EvaluationError(
                "candidate-local SQLite search returned incomplete rankings"
            )
        ranking = [
            {
                "case_id": result.run_id,
                "similarity": result.similarity,
                "distance": result.distance,
            }
            for result in results
        ]
        expected = cast(str, query["expected_case_id"])
        rank = next(
            (
                position
                for position, row in enumerate(ranking, 1)
                if row["case_id"] == expected
            ),
            0,
        )
        if rank == 0:
            raise EvaluationError("expected label is absent from ranking")
        top_is_tied = len(ranking) > 1 and math.isclose(
            cast(float, ranking[0]["similarity"]),
            cast(float, ranking[1]["similarity"]),
            rel_tol=0.0,
            abs_tol=1e-12,
        )
        if rank != 1 or top_is_tied:
            falsifiers.append(f"expected_case_not_uniquely_ranked_first:{query['id']}")
        ranks.append(rank)
        query_rows.append(
            {
                "id": query["id"],
                "expected_case_id": expected,
                "expected_rank": rank,
                "top_rank_tied": top_is_tied,
                "vector": vector,
                "vector_sha256": _vector_sha256(vector),
                "ranking": ranking,
            }
        )

    metrics = _metrics(ranks)
    thresholds = _mapping(evaluation["thresholds"], "thresholds")
    if not _metric_gate(metrics, thresholds):
        falsifiers.append("metric_below_threshold")
    passed = not falsifiers and identity.get("identity_complete") is True
    return {
        "schema_version": RESULT_SCHEMA,
        "status": "passed" if passed else "failed",
        "coverage_claim": evaluation["coverage_claim"],
        "contract_sha256": EXPECTED_CONTRACT_SHA256,
        "model_identity": dict(identity),
        "records": [
            {
                "case_id": record["case_id"],
                "text_sha256": _sha256_bytes(cast(str, record["text"]).encode()),
                "vector_sha256": _vector_sha256(vector),
            }
            for record, vector in zip(records, document_vectors, strict=True)
        ],
        "queries": query_rows,
        "metrics": metrics,
        "thresholds": dict(thresholds),
        "falsifiers_observed": falsifiers,
        "store": {"backend": "sqlite", "path": DB_FILE, "row_count": len(records)},
        "effects": dict(_mapping(contract["effects"], "effects")),
        "claims": {
            "held_out_routing_metric_gate_passed": passed,
            "full_batch_model_reproduction_verified": False,
            "production_semantic_embedding_gate_passed": False,
            "broad_or_statistically_representative_semantic_quality": False,
            "semantic_analysis_lm_quality": False,
            "shared_coordinate_store_readiness": False,
            "oracle_governance_authority": False,
            "release_authority": False,
            "package_publication": False,
            "production_activation": False,
        },
    }
