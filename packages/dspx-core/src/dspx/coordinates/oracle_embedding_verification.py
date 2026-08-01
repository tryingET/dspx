# summary: "Independently verifies retained Oracle embedding evaluation evidence."
# read_when:
#   - "Reviewing retained model artifacts, SQLite vectors, rankings, metrics, or nonclaims."

"""Model-free verification of retained Oracle embedding evidence."""

from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path
from typing import Any, Mapping, cast

from .embedding_identity import validate_unit_vector
from .embeddings import SentenceTransformerEmbedder
from .metrics import cosine_similarity
from .oracle_embedding_evaluation import (
    DB_FILE,
    EXPECTED_CONTRACT_SHA256,
    EXPECTED_QUERY_IDS,
    EXPECTED_RECORD_IDS,
    RESULT_SCHEMA,
    EvaluationError,
    _array,
    _identity_spec,
    _mapping,
    _metric_gate,
    _metrics,
    _sha256_bytes,
    _sha256_file,
    _vector_sha256,
    validate_complete_identity,
)

VERIFICATION_SCHEMA = "dspx-oracle-embedding-evaluation-verification-v1"
RESULT_FILE = "evaluation-result.json"
MODEL_DIR = "model-snapshot"
_LEGACY_RESULT_SHA256 = (
    "92a9d0588c24ea5656b7a82f2c1c920d593d7fe82dcaf3f17359e2000f10466c"
)
_LEGACY_DISTRIBUTION_CONTENT_SHA256 = {
    "huggingface-hub": "8d67b7c6ed638f16f01ffc6604d3af896d31cb7313d06b045bcdc82844113f4b",
    "numpy": "295e43178591134ebca709a8f1dcdd16cdf6184e0050e6397ecaefaa0de147fb",
    "safetensors": "507996dd11e2fab678e3c3e7bf78a413549133b4db385efb46100ca65aa98fde",
    "sentence-transformers": "fe4f47b9e4d6bd5b9ebc162ffdecb8340e345a90e8239d9e18337144bc7e76c4",
    "tokenizers": "73386ca3e794ba43b9fcf27f28f137160d7c36734933536928c07df0e6718a44",
    "torch": "0cebfd9113ed4d60ecdee17f54a178a53d779a0eed44f447c566eb8464f4b4e5",
    "transformers": "ba8120d875b4c97e27b78bd4eb4c66efa85721551d04d7e7df0f4ee7853021bf",
}


def reproduce_model_batch(
    *,
    contract: Mapping[str, Any],
    result: Mapping[str, Any],
    model_root: Path,
    result_sha256: str | None = None,
) -> dict[str, Any]:
    """Reload the retained model and reproduce the complete ordered six-text batch."""

    spec = _identity_spec(contract)
    evaluation = _mapping(contract["evaluation"], "evaluation")
    records = [
        _mapping(value, "contract record")
        for value in _array(evaluation["records"], "contract records")
    ]
    queries = [
        _mapping(value, "contract query")
        for value in _array(evaluation["queries"], "contract queries")
    ]
    texts = [cast(str, row["text"]) for row in [*records, *queries]]
    embedder = SentenceTransformerEmbedder(
        spec.repository_id,
        model_root=model_root,
        normalize_embeddings=spec.normalize_embeddings,
        device=spec.device,
    )
    vectors = embedder.encode(texts)
    reproduced_identity = embedder.build_identity(
        spec, frozen_runtime_lock_sha256=spec.runtime_lock_sha256
    )
    recorded_identity = _mapping(result.get("model_identity"), "model identity")
    identity_reconciliation: dict[str, Any] | None = None
    if reproduced_identity != recorded_identity:
        recorded_comparable = json.loads(json.dumps(recorded_identity))
        reproduced_comparable = json.loads(json.dumps(reproduced_identity))
        recorded_runtime = _mapping(
            recorded_comparable.get("runtime"), "recorded runtime"
        )
        reproduced_runtime = _mapping(
            reproduced_comparable.get("runtime"), "reproduced runtime"
        )
        recorded_hashes = cast(
            dict[str, str],
            cast(dict[str, Any], recorded_runtime).pop(
                "distribution_content_sha256", {}
            ),
        )
        reproduced_hashes = cast(
            dict[str, str],
            cast(dict[str, Any], reproduced_runtime).pop(
                "distribution_content_sha256", {}
            ),
        )
        scope = cast(dict[str, Any], reproduced_runtime).pop(
            "distribution_content_hash_scope", None
        )
        if (
            result_sha256 != _LEGACY_RESULT_SHA256
            or recorded_hashes != _LEGACY_DISTRIBUTION_CONTENT_SHA256
            or "distribution_content_hash_scope" in recorded_runtime
            or recorded_comparable != reproduced_comparable
            or set(recorded_hashes) != set(reproduced_hashes)
            or scope
            != "imported_package_and_library_payload_excluding_dist_info_and_generated_scripts"
        ):
            raise EvaluationError("fresh model reproduction identity drift")
        identity_reconciliation = {
            "resolution": "legacy_install_projection_hashes_excluded",
            "cause": (
                "generated_console_scripts_and_RECORD_include_ephemeral_venv_paths"
            ),
            "recorded_distribution_content_sha256": recorded_hashes,
            "reproduced_stable_distribution_content_sha256": reproduced_hashes,
            "stable_hash_scope": scope,
        }
    recorded_records = [
        _mapping(value, "result record")
        for value in _array(result.get("records"), "result records")
    ]
    recorded_queries = [
        _mapping(value, "result query")
        for value in _array(result.get("queries"), "result queries")
    ]
    expected_hashes = [
        cast(str, row["vector_sha256"])
        for row in [*recorded_records, *recorded_queries]
    ]
    observed_hashes = [_vector_sha256(vector) for vector in vectors]
    if observed_hashes != expected_hashes:
        raise EvaluationError("fresh full-batch model vector reproduction drift")
    batch_order = [
        {"kind": "record", "id": row["case_id"], "vector_sha256": digest}
        for row, digest in zip(records, observed_hashes[: len(records)], strict=True)
    ] + [
        {"kind": "query", "id": row["id"], "vector_sha256": digest}
        for row, digest in zip(queries, observed_hashes[len(records) :], strict=True)
    ]
    identity_sha256 = _sha256_bytes(
        json.dumps(reproduced_identity, sort_keys=True, separators=(",", ":")).encode()
    )
    receipt = {
        "schema_version": "dspx-oracle-embedding-model-reproduction-v1",
        "status": "passed",
        "fresh_local_model_instance": True,
        "single_complete_ordered_batch": True,
        "identity_sha256": identity_sha256,
        "batch_order": batch_order,
    }
    if identity_reconciliation is not None:
        receipt["identity_reconciliation"] = identity_reconciliation
    return receipt


def _verify_artifacts(root: Path, identity: Mapping[str, Any]) -> None:
    model_root = root / MODEL_DIR
    artifacts = _array(identity.get("artifacts"), "identity artifacts")
    for artifact_value in artifacts:
        artifact = _mapping(artifact_value, "identity artifact")
        relative_path = artifact.get("path")
        if (
            not isinstance(relative_path, str)
            or Path(relative_path).is_absolute()
            or ".." in Path(relative_path).parts
        ):
            raise EvaluationError("invalid retained artifact path")
        path = model_root / relative_path
        if path.is_symlink() or not path.is_file():
            raise EvaluationError(f"retained artifact unavailable: {relative_path}")
        if path.stat().st_size != artifact.get("size") or _sha256_file(
            path
        ) != artifact.get("sha256"):
            raise EvaluationError(f"retained artifact identity drift: {relative_path}")


def _verify_retained_consistency(
    root: Path, contract: Mapping[str, Any]
) -> dict[str, Any]:
    """Check retained consistency without emitting a production gate claim."""

    result_path = root / RESULT_FILE
    result = json.loads(result_path.read_text())
    if not isinstance(result, dict) or result.get("schema_version") != RESULT_SCHEMA:
        raise EvaluationError("retained evaluation result schema drift")
    if result.get("contract_sha256") != EXPECTED_CONTRACT_SHA256:
        raise EvaluationError("retained result contract binding drift")
    identity = _mapping(result.get("model_identity"), "model identity")
    validate_complete_identity(contract, identity)
    _verify_artifacts(root, identity)

    db_path = root / DB_FILE
    if not db_path.is_file() or db_path.is_symlink():
        raise EvaluationError("candidate-local SQLite evidence is unavailable")
    with sqlite3.connect(db_path) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if integrity != ("ok",):
            raise EvaluationError("candidate-local SQLite integrity check failed")
        rows = connection.execute(
            "SELECT run_id, vector_json, input_text, metadata_json "
            "FROM coordinates ORDER BY run_id"
        ).fetchall()
    if len(rows) != len(EXPECTED_RECORD_IDS) or {row[0] for row in rows} != set(
        EXPECTED_RECORD_IDS
    ):
        raise EvaluationError("candidate-local SQLite record identity drift")
    evaluation = _mapping(contract["evaluation"], "evaluation")
    contract_records = {
        cast(str, row["case_id"]): cast(str, row["text"])
        for row in (
            _mapping(value, "contract record")
            for value in _array(evaluation["records"], "contract records")
        )
    }
    vectors: dict[str, list[float]] = {}
    for run_id, vector_json, input_text, metadata_json in rows:
        if input_text != contract_records[run_id]:
            raise EvaluationError("candidate-local SQLite record text drift")
        metadata = _mapping(json.loads(metadata_json), "SQLite record metadata")
        if metadata.get("embedding_backend") != identity:
            raise EvaluationError("candidate-local SQLite backend identity drift")
        vector = cast(list[float], json.loads(vector_json))
        validate_unit_vector(vector)
        vectors[run_id] = vector
    result_records = [
        _mapping(row, "result record")
        for row in _array(result.get("records"), "result records")
    ]
    if tuple(row.get("case_id") for row in result_records) != EXPECTED_RECORD_IDS:
        raise EvaluationError("retained result record order drift")
    for record in result_records:
        case_id = cast(str, record["case_id"])
        if record.get("text_sha256") != _sha256_bytes(
            contract_records[case_id].encode()
        ) or record.get("vector_sha256") != _vector_sha256(vectors[case_id]):
            raise EvaluationError("retained result record hash drift")

    contract_queries = [
        _mapping(value, "contract query")
        for value in _array(evaluation["queries"], "contract queries")
    ]
    result_queries = [
        _mapping(value, "result query")
        for value in _array(result.get("queries"), "result queries")
    ]
    if tuple(row.get("id") for row in result_queries) != EXPECTED_QUERY_IDS:
        raise EvaluationError("retained query order or identity drift")
    expected_ranks: list[int] = []
    derived_falsifiers: list[str] = []
    for contract_query, query in zip(contract_queries, result_queries, strict=True):
        if query.get("expected_case_id") != contract_query.get("expected_case_id"):
            raise EvaluationError("retained held-out label drift")
        vector = cast(list[float], query.get("vector"))
        validate_unit_vector(vector)
        if _vector_sha256(vector) != query.get("vector_sha256"):
            raise EvaluationError("retained query vector hash drift")
        reranked = sorted(
            (
                (case_id, cosine_similarity(vector, candidate))
                for case_id, candidate in vectors.items()
            ),
            key=lambda row: (-row[1], EXPECTED_RECORD_IDS.index(row[0])),
        )
        expected = query.get("expected_case_id")
        rank = next(
            position for position, row in enumerate(reranked, 1) if row[0] == expected
        )
        if rank != query.get("expected_rank"):
            raise EvaluationError("independently derived expected rank drift")
        top_rank_tied = len(reranked) > 1 and math.isclose(
            reranked[0][1], reranked[1][1], rel_tol=0.0, abs_tol=1e-12
        )
        if query.get("top_rank_tied") is not top_rank_tied:
            raise EvaluationError("independently derived top-rank tie drift")
        if rank != 1 or top_rank_tied:
            derived_falsifiers.append(
                f"expected_case_not_uniquely_ranked_first:{query['id']}"
            )
        recorded_ranking = [
            _mapping(row, "ranking row")
            for row in _array(query.get("ranking"), "recorded ranking")
        ]
        if [row[0] for row in reranked] != [
            row.get("case_id") for row in recorded_ranking
        ]:
            raise EvaluationError("independently derived ranking identity drift")
        for derived, recorded in zip(reranked, recorded_ranking, strict=True):
            similarity = derived[1]
            if not math.isclose(
                similarity,
                cast(float, recorded.get("similarity")),
                rel_tol=0.0,
                abs_tol=1e-12,
            ) or not math.isclose(
                1.0 - similarity,
                cast(float, recorded.get("distance")),
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                raise EvaluationError(
                    "independently derived similarity or distance drift"
                )
        expected_ranks.append(rank)

    derived_metrics = _metrics(expected_ranks)
    if derived_metrics != result.get("metrics"):
        raise EvaluationError("independently derived metric drift")
    thresholds = _mapping(evaluation["thresholds"], "thresholds")
    if not _metric_gate(derived_metrics, thresholds):
        derived_falsifiers.append("metric_below_threshold")
    if result.get("falsifiers_observed") != derived_falsifiers:
        raise EvaluationError("independently derived falsifier set drift")
    passed = not derived_falsifiers
    expected_reproduction = {
        "schema_version": "dspx-oracle-embedding-model-reproduction-v1",
        "status": "passed",
        "fresh_local_model_instance": True,
        "single_complete_ordered_batch": True,
        "identity_sha256": _sha256_bytes(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
        ),
        "batch_order": [
            {
                "kind": "record",
                "id": row["case_id"],
                "vector_sha256": row["vector_sha256"],
            }
            for row in result_records
        ]
        + [
            {
                "kind": "query",
                "id": row["id"],
                "vector_sha256": row["vector_sha256"],
            }
            for row in result_queries
        ],
    }
    if result.get("model_reproduction") != expected_reproduction:
        raise EvaluationError("full-batch model reproduction evidence is incomplete")
    expected_claims = {
        "held_out_routing_metric_gate_passed": passed,
        "full_batch_model_reproduction_verified": True,
        "production_semantic_embedding_gate_passed": (
            passed and _sha256_file(result_path) == _LEGACY_RESULT_SHA256
        ),
        "broad_or_statistically_representative_semantic_quality": False,
        "semantic_analysis_lm_quality": False,
        "shared_coordinate_store_readiness": False,
        "oracle_governance_authority": False,
        "release_authority": False,
        "package_publication": False,
        "production_activation": False,
    }
    if (
        (result.get("status") == "passed") is not passed
        or result.get("claims") != expected_claims
        or result.get("effects") != contract.get("effects")
    ):
        raise EvaluationError("retained status, claim, or effect boundary drift")
    return {
        "schema_version": VERIFICATION_SCHEMA,
        "status": "passed",
        "evaluation_status": result["status"],
        "result_sha256": _sha256_file(result_path),
        "database_sha256": _sha256_file(db_path),
        "model_artifact_count": len(
            _array(identity["artifacts"], "identity artifacts")
        ),
        "derived_metrics": derived_metrics,
        "internally_consistent_embedding_gate_passed": passed,
        "nonclaims_preserved": True,
    }


def verify_retained_evaluation(
    root: Path, contract: Mapping[str, Any]
) -> dict[str, Any]:
    """Reproduce the model batch, then verify evidence and emit the gate."""

    result = _mapping(json.loads((root / RESULT_FILE).read_text()), "evaluation result")
    result_sha256 = _sha256_file(root / RESULT_FILE)
    reproduction = reproduce_model_batch(
        contract=contract,
        result=result,
        model_root=root / MODEL_DIR,
        result_sha256=result_sha256,
    )
    recorded_reproduction = _mapping(
        result.get("model_reproduction"), "recorded model reproduction"
    )
    exact_receipt_match = reproduction == recorded_reproduction
    reconciliation = reproduction.get("identity_reconciliation")
    if not exact_receipt_match:
        stable_fields = (
            "schema_version",
            "status",
            "fresh_local_model_instance",
            "single_complete_ordered_batch",
            "batch_order",
        )
        if not isinstance(reconciliation, dict) or any(
            reproduction.get(field) != recorded_reproduction.get(field)
            for field in stable_fields
        ):
            raise EvaluationError("independent full-batch reproduction receipt drift")
    consistency = _verify_retained_consistency(root, contract)
    passed = consistency.pop("internally_consistent_embedding_gate_passed")
    return {
        **consistency,
        "production_semantic_embedding_gate_passed": passed,
        "full_batch_model_reproduction_verified": True,
        "original_reproduction_receipt_match": exact_receipt_match,
        "identity_reconciliation": reconciliation,
    }
