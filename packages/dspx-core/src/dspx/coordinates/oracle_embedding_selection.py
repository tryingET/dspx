# summary: "Validates and scores the frozen MiniLM-versus-mDenseOn Oracle selection contract."
# read_when:
#   - "Changing dense-model selection labels, comparative gates, resources, or evidence claims."

"""Deterministic Oracle-specific dense embedding selection logic."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import stat
from pathlib import Path
from typing import Any, Mapping, Sequence, cast

from .embedding_identity import (
    ModelArtifactExpectation,
    SentenceTransformerIdentitySpec,
    validate_model_artifact_root,
    validate_unit_vector,
)
from .embeddings import ExecutionEmbedding
from .mdenseon import validate_serialized_mdenseon_semantics
from .storage import CoordinateIndex

CONTRACT_SCHEMA = "dspx-oracle-embedding-selection-contract-v2"
RESULT_SCHEMA = "dspx-oracle-embedding-selection-result-v2"
EXPECTED_CONTRACT_SHA256 = (
    "e4ff030f2133f19a65b7586606874f1c8fa3895f6bf114580fc2e8d8ab43d9a3"
)
BASELINE_DB_FILE = "minilm-comparison.sqlite3"
CHALLENGER_DB_FILE = "mdenseon-comparison.sqlite3"
EXPECTED_RECORD_IDS = (
    "authority-boundary",
    "uncertainty-calibration",
    "review-only-transition",
    "replay-identity",
    "effect-indeterminate-stop",
    "release-evidence-not-authority",
    "model-identity-layers",
    "store-semantics-separation",
    "embedding-role-prompts",
    "runtime-reproduction-boundary",
)
EXPECTED_QUERY_IDS = (
    "authority-en",
    "authority-fr",
    "calibration-de",
    "review-es",
    "replay-en",
    "terminal-en",
    "release-ar",
    "release-en",
    "identity-en",
    "store-fr",
    "store-en",
    "prompts-en",
    "runtime-tail-en",
    "authority-pt",
    "terminal-code",
)


class SelectionError(ValueError):
    """Raised when the selection contract or evidence drifts."""


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise SelectionError(f"{label} must be an object")
    return cast(Mapping[str, Any], value)


def _array(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise SelectionError(f"{label} must be an array")
    return value


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _vector_sha256(vector: Sequence[float]) -> str:
    return _sha256_bytes(
        json.dumps(list(vector), separators=(",", ":"), allow_nan=False).encode()
    )


def materialize_record_text(record: Mapping[str, Any]) -> str:
    """Materialize either literal text or the frozen long-context recipe."""

    literal = record.get("text")
    recipe = record.get("text_recipe")
    if isinstance(literal, str) and literal and recipe is None:
        return literal
    if literal is not None or not isinstance(recipe, dict):
        raise SelectionError("record must contain exactly one text representation")
    prefix = recipe.get("prefix")
    repeat = recipe.get("repeat")
    tail = recipe.get("tail")
    if (
        not isinstance(prefix, str)
        or not prefix
        or type(repeat) is not int
        or repeat != 90
        or not isinstance(tail, str)
        or not tail
    ):
        raise SelectionError("long-context text recipe drift")
    materialized = prefix * repeat + tail
    if len(materialized.split()) <= 256:
        raise SelectionError("long-context case must place its label after 256 words")
    return materialized


def validate_contract_payload(contract: Mapping[str, Any]) -> None:
    if contract.get("schema_version") != CONTRACT_SCHEMA:
        raise SelectionError("selection contract schema drift")
    if contract.get("status") != "precommitted_evaluation_not_run":
        raise SelectionError("selection contract status drift")
    candidates = _mapping(contract.get("candidates"), "candidates")
    baseline = _mapping(candidates.get("baseline"), "baseline")
    challenger = _mapping(candidates.get("challenger"), "challenger")
    if baseline != {
        "repository_id": "sentence-transformers/all-MiniLM-L6-v2",
        "revision": "c9745ed1d9f207416be6d2e6f8de32d1f16199bf",
        "adapter": "sentence-transformers-v1",
        "document_prompt": "",
        "query_prompt": "",
        "expected_dimension": 384,
        "maximum_tokens": 256,
        "tokenizer_identity": {
            "implementation": "transformers.models.bert.tokenization_bert_fast.BertTokenizerFast",
            "model_max_length": 256,
            "padding_side": "right",
            "truncation_side": "right",
            "vocabulary_size": 30522,
        },
        "retained_snapshot_must_match_v1_identity": True,
    }:
        raise SelectionError("retained MiniLM baseline identity drift")
    required_challenger = {
        "repository_id": "lightonai/mDenseOn",
        "revision": "a5fdb000f7a21da96c3bddde3a782ef777316df3",
        "license": "apache-2.0",
        "architecture": "modernbert_cls_dense_single_vector",
        "adapter": "dspx-mdenseon-cls-v1",
        "trust_remote_code": False,
        "document_prompt": "document: ",
        "query_prompt": "query: ",
        "expected_dimension": 768,
        "maximum_tokens": 8192,
        "vector_dtype": "float32",
        "normalize_embeddings": True,
        "ranking_metric": "cosine_similarity_descending",
        "reported_distance": "one_minus_cosine_similarity",
    }
    if any(
        challenger.get(key) != value for key, value in required_challenger.items()
    ) or challenger.get("tokenizer_identity") != {
        "implementation": "transformers.tokenization_utils_fast.PreTrainedTokenizerFast",
        "model_max_length": 8192,
        "padding_side": "right",
        "truncation_side": "right",
        "vocabulary_size": 256000,
    }:
        raise SelectionError("mDenseOn execution identity drift")
    manifest = _array(challenger.get("artifact_manifest"), "artifact manifest")
    if len(manifest) != 8:
        raise SelectionError("mDenseOn loader artifact manifest drift")
    paths: tuple[str, ...] = tuple(
        cast(str, _mapping(row, "artifact")["path"]) for row in manifest
    )
    if (
        any(not isinstance(path, str) or not path for path in paths)
        or paths != tuple(sorted(paths))
        or len(set(paths)) != len(paths)
    ):
        raise SelectionError("mDenseOn artifact paths must be sorted and unique")

    runtime = _mapping(contract.get("runtime"), "runtime")
    versions = _mapping(runtime.get("expected_package_versions"), "runtime versions")
    wheels = _mapping(runtime.get("selected_wheel_sha256"), "runtime wheel hashes")
    distributions = _mapping(
        runtime.get("expected_distribution_content_sha256"),
        "runtime distribution hashes",
    )
    if (
        runtime.get("lock_sha256")
        != "d941b76c442e4c89143b1ab0abcc03a57b477943e6cb0e588bc08c3ec5a4ef09"
        or runtime.get("installer") != "uv_run_isolated_frozen"
        or runtime.get("python_implementation") != "cpython"
        or runtime.get("python_major_minor") != "3.13"
        or runtime.get("python_version") != "3.13.12"
        or runtime.get("distribution_content_hash_scope")
        != "imported_package_and_library_payload_excluding_dist_info_and_generated_scripts"
        or runtime.get("platform") != "linux-x86_64"
        or runtime.get("device") != "cpu"
        or set(versions) != set(wheels)
        or set(versions) != set(distributions)
        or any(
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            for digest in distributions.values()
        )
    ):
        raise SelectionError("frozen CPU runtime identity drift")

    evaluation = _mapping(contract.get("evaluation"), "evaluation")
    records = [
        _mapping(row, "record") for row in _array(evaluation.get("records"), "records")
    ]
    queries = [
        _mapping(row, "query") for row in _array(evaluation.get("queries"), "queries")
    ]
    if evaluation.get("coverage_claim") != (
        "fifteen_model_blind_queries_over_ten_declared_oracle_concepts_"
        "including_six_cross_lingual_and_one_post_256_token_tail_case"
    ):
        raise SelectionError("selection coverage claim drift")
    if tuple(row.get("case_id") for row in records) != EXPECTED_RECORD_IDS:
        raise SelectionError("record order or identity drift")
    if tuple(row.get("id") for row in queries) != EXPECTED_QUERY_IDS:
        raise SelectionError("query order or identity drift")
    record_ids = set(EXPECTED_RECORD_IDS)
    for record in records:
        materialize_record_text(record)
    for query in queries:
        if (
            query.get("expected_case_id") not in record_ids
            or not isinstance(query.get("text"), str)
            or not query["text"]
            or query.get("subset")
            not in {
                "general",
                "critical",
                "cross_lingual",
                "cross_lingual_critical",
                "long_context_critical",
            }
        ):
            raise SelectionError("query label, text, or subset drift")
    if (
        sum(cast(str, query["subset"]).startswith("cross_lingual") for query in queries)
        != 6
    ):
        raise SelectionError("cross-lingual query count drift")
    if _mapping(evaluation.get("absolute_thresholds"), "absolute thresholds") != {
        "recall_at_1": 0.9,
        "mean_reciprocal_rank": 0.95,
        "normalized_discounted_cumulative_gain_at_5": 0.95,
        "minimum_labeled_query_count": 15,
        "critical_queries_must_rank_first": True,
        "cross_lingual_recall_at_1": 0.8,
        "long_context_recall_at_1": 1.0,
    }:
        raise SelectionError("absolute selection thresholds drift")
    budget = _mapping(contract.get("attempt_budget"), "attempt budget")
    enforcement = _mapping(budget.get("enforcement"), "attempt enforcement")
    if (
        budget.get(
            "maximum_challenger_acquisition_and_comparative_evaluation_sequences"
        )
        != 1
        or budget.get("selective_query_reruns_allowed") is not False
        or budget.get("dspx_managed_retries") != 0
        or enforcement.get("kind") != "canonical_local_atomic_consumed_marker"
        or enforcement.get("namespace") != "dspx/oracle-embedding-selections"
        or enforcement.get("key") != "ak_task_id_and_contract_sha256"
        or enforcement.get("marker_created_before_challenger_acquisition") is not True
        or enforcement.get("started_or_terminal_marker_forbids_another_root")
        is not True
    ):
        raise SelectionError("challenger attempt budget drift")
    effects = _mapping(contract.get("effects"), "effects")
    if any(type(value) is not int or value != 0 for value in effects.values()):
        raise SelectionError("forbidden effect declaration drift")
    claims = _mapping(contract.get("claim_boundary"), "claim boundary")
    if claims.get("oracle_specific_comparative_selection_only") is not True or any(
        value is not False
        for key, value in claims.items()
        if key != "oracle_specific_comparative_selection_only"
    ):
        raise SelectionError("selection claim boundary widened")


def challenger_identity_spec(
    contract: Mapping[str, Any],
) -> SentenceTransformerIdentitySpec:
    validate_contract_payload(contract)
    challenger = _mapping(
        _mapping(contract["candidates"], "candidates")["challenger"], "challenger"
    )
    runtime = _mapping(contract["runtime"], "runtime")
    artifacts = tuple(
        ModelArtifactExpectation(
            path=cast(str, row["path"]),
            size=cast(int, row["size"]),
            source_git_oid=cast(str, row["source_git_oid"]),
            lfs_sha256=cast(str | None, row["lfs_sha256"]),
        )
        for row in (
            _mapping(value, "artifact")
            for value in _array(challenger["artifact_manifest"], "artifact manifest")
        )
    )
    versions = _mapping(runtime["expected_package_versions"], "runtime versions")
    wheels = _mapping(runtime["selected_wheel_sha256"], "runtime wheel hashes")
    return SentenceTransformerIdentitySpec(
        repository_id=cast(str, challenger["repository_id"]),
        revision=cast(str, challenger["revision"]),
        artifact_manifest=artifacts,
        expected_dimension=cast(int, challenger["expected_dimension"]),
        normalize_embeddings=True,
        vector_dtype="float32",
        ranking_metric="cosine_similarity_descending",
        reported_distance="one_minus_cosine_similarity",
        runtime_versions=tuple(
            sorted((name, cast(str, value)) for name, value in versions.items())
        ),
        runtime_lock_sha256=cast(str, runtime["lock_sha256"]),
        runtime_wheel_sha256=tuple(
            sorted((name, cast(str, value)) for name, value in wheels.items())
        ),
        runtime_installer=cast(str, runtime["installer"]),
        uv_version=cast(str, runtime["uv_version"]),
        platform=cast(str, runtime["platform"]),
        python_implementation=cast(str, runtime["python_implementation"]),
        python_major_minor=cast(str, runtime["python_major_minor"]),
        device=cast(str, runtime["device"]),
    )


def _metrics(ranks: Sequence[int], *, cutoff: int = 5) -> dict[str, float | int]:
    if not ranks:
        raise SelectionError("at least one rank is required")
    count = len(ranks)
    return {
        "labeled_query_count": count,
        "recall_at_1": sum(rank == 1 for rank in ranks) / count,
        "mean_reciprocal_rank": sum(1.0 / rank for rank in ranks) / count,
        "normalized_discounted_cumulative_gain_at_5": sum(
            1.0 / math.log2(rank + 1) if rank <= cutoff else 0.0 for rank in ranks
        )
        / count,
    }


def score_model(
    *,
    contract: Mapping[str, Any],
    model_label: str,
    identity: Mapping[str, Any],
    document_vectors: Sequence[list[float]],
    query_vectors: Sequence[list[float]],
    database_path: Path,
    embedding_version: int,
) -> dict[str, Any]:
    validate_contract_payload(contract)
    evaluation = _mapping(contract["evaluation"], "evaluation")
    records = [
        _mapping(row, "record") for row in _array(evaluation["records"], "records")
    ]
    queries = [
        _mapping(row, "query") for row in _array(evaluation["queries"], "queries")
    ]
    if len(document_vectors) != len(records) or len(query_vectors) != len(queries):
        raise SelectionError("vector count does not match frozen labels")
    dimension = (
        identity.get("encoding", {}).get("dimension")
        if isinstance(identity.get("encoding"), dict)
        else None
    )
    if type(dimension) is not int or any(
        len(vector) != dimension for vector in [*document_vectors, *query_vectors]
    ):
        raise SelectionError("vector dimension drift")

    index = CoordinateIndex(db_path=database_path)
    inserted = index.upsert_batch(
        [
            ExecutionEmbedding(
                run_id=cast(str, record["case_id"]),
                vector=vector,
                input_text=materialize_record_text(record),
                output_text="",
                config_text="frozen-oracle-embedding-selection-v2",
                run_kind="semantic-routing-record",
                provider=model_label,
                template_version="oracle-embedding-selection-v2",
                created_at="2026-08-02T00:00:00+00:00",
                dimension=dimension,
                metadata={"embedding_backend": dict(identity)},
                embedding_version=embedding_version,
            )
            for record, vector in zip(records, document_vectors, strict=True)
        ]
    )
    if inserted != len(records):
        raise SelectionError("candidate-local SQLite indexing was incomplete")

    rows: list[dict[str, Any]] = []
    ranks: list[int] = []
    by_subset: dict[str, list[int]] = {
        "cross_lingual": [],
        "critical": [],
        "long_context": [],
    }
    falsifiers: list[str] = []
    for query, vector in zip(queries, query_vectors, strict=True):
        ranking_results = index.search(
            vector,
            top_k=len(records),
            min_similarity=-1.0,
            embedding_version=embedding_version,
        )
        if len(ranking_results) != len(records):
            raise SelectionError("SQLite search returned an incomplete ranking")
        ranking = [
            {
                "case_id": row.run_id,
                "similarity": row.similarity,
                "distance": row.distance,
            }
            for row in ranking_results
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
            raise SelectionError("expected label absent from ranking")
        tied = len(ranking) > 1 and math.isclose(
            cast(float, ranking[0]["similarity"]),
            cast(float, ranking[1]["similarity"]),
            rel_tol=0.0,
            abs_tol=1e-12,
        )
        if tied:
            falsifiers.append(f"top_rank_tied:{query['id']}")
        subset = cast(str, query["subset"])
        if subset.startswith("cross_lingual"):
            by_subset["cross_lingual"].append(rank)
        if "critical" in subset:
            by_subset["critical"].append(rank)
        if subset.startswith("long_context"):
            by_subset["long_context"].append(rank)
        ranks.append(rank)
        rows.append(
            {
                "id": query["id"],
                "expected_case_id": expected,
                "subset": subset,
                "expected_rank": rank,
                "top_rank_tied": tied,
                "vector": vector,
                "vector_sha256": _vector_sha256(vector),
                "ranking": ranking,
            }
        )

    metrics = _metrics(ranks)
    subset_metrics = {name: _metrics(values) for name, values in by_subset.items()}
    return {
        "model": model_label,
        "identity": dict(identity),
        "records": [
            {"case_id": record["case_id"], "vector_sha256": _vector_sha256(vector)}
            for record, vector in zip(records, document_vectors, strict=True)
        ],
        "queries": rows,
        "metrics": metrics,
        "subset_metrics": subset_metrics,
        "falsifiers_observed": falsifiers,
        "store": {
            "backend": "sqlite",
            "path": database_path.name,
            "row_count": len(records),
        },
    }


def select_model(
    *,
    contract: Mapping[str, Any],
    baseline: Mapping[str, Any],
    challenger: Mapping[str, Any],
    resources: Mapping[str, float | int],
) -> dict[str, Any]:
    validate_contract_payload(contract)
    evaluation = _mapping(contract["evaluation"], "evaluation")
    absolute = _mapping(evaluation["absolute_thresholds"], "absolute thresholds")
    comparative = _mapping(
        evaluation["comparative_thresholds"], "comparative thresholds"
    )
    limits = _mapping(evaluation["resource_thresholds"], "resource thresholds")
    base_metrics = _mapping(baseline["metrics"], "baseline metrics")
    challenger_metrics = _mapping(challenger["metrics"], "challenger metrics")
    base_subsets = _mapping(baseline["subset_metrics"], "baseline subsets")
    challenger_subsets = _mapping(challenger["subset_metrics"], "challenger subsets")

    critical_pass = all(
        row.get("expected_rank") == 1 and row.get("top_rank_tied") is False
        for row in _array(challenger["queries"], "challenger queries")
        if "critical" in cast(str, _mapping(row, "query row")["subset"])
    )
    absolute_pass = (
        challenger_metrics["labeled_query_count"]
        >= absolute["minimum_labeled_query_count"]
        and challenger_metrics["recall_at_1"] >= absolute["recall_at_1"]
        and challenger_metrics["mean_reciprocal_rank"]
        >= absolute["mean_reciprocal_rank"]
        and challenger_metrics["normalized_discounted_cumulative_gain_at_5"]
        >= absolute["normalized_discounted_cumulative_gain_at_5"]
        and challenger_subsets["cross_lingual"]["recall_at_1"]
        >= absolute["cross_lingual_recall_at_1"]
        and challenger_subsets["long_context"]["recall_at_1"]
        >= absolute["long_context_recall_at_1"]
        and critical_pass
        and not challenger["falsifiers_observed"]
    )
    capability_improvements = {
        "cross_lingual_recall_at_1": challenger_subsets["cross_lingual"]["recall_at_1"]
        - base_subsets["cross_lingual"]["recall_at_1"],
        "long_context_recall_at_1": challenger_subsets["long_context"]["recall_at_1"]
        - base_subsets["long_context"]["recall_at_1"],
    }
    comparative_pass = (
        (
            not comparative["challenger_overall_recall_must_not_regress"]
            or challenger_metrics["recall_at_1"] >= base_metrics["recall_at_1"]
        )
        and (
            not comparative["challenger_mrr_must_not_regress"]
            or challenger_metrics["mean_reciprocal_rank"]
            >= base_metrics["mean_reciprocal_rank"]
        )
        and max(capability_improvements.values())
        >= comparative["minimum_improvement_on_cross_lingual_or_long_context_recall"]
    )
    resource_pass = (
        resources.get("retained_model_bytes", math.inf)
        <= limits["maximum_retained_model_bytes"]
        and resources.get("peak_rss_bytes", math.inf)
        <= limits["maximum_peak_rss_bytes"]
        and resources.get("model_load_seconds", math.inf)
        <= limits["maximum_model_load_seconds"]
        and resources.get("total_encode_seconds", math.inf)
        <= limits["maximum_total_encode_seconds"]
    )
    identity_pass = (
        challenger.get("identity", {}).get("identity_complete") is True
        and challenger.get("identity", {}).get("schema_version")
        == "dspx-mdenseon-identity-v1"
    )
    selected = (
        "lightonai/mDenseOn"
        if all((absolute_pass, comparative_pass, resource_pass, identity_pass))
        else "sentence-transformers/all-MiniLM-L6-v2"
    )
    return {
        "schema_version": RESULT_SCHEMA,
        "status": "passed"
        if selected == "lightonai/mDenseOn"
        else "challenger_not_selected",
        "contract_sha256": EXPECTED_CONTRACT_SHA256,
        "selected_model": selected,
        "embedding_version": 2 if selected == "lightonai/mDenseOn" else 1,
        "gates": {
            "absolute_oracle_specific_quality": absolute_pass,
            "comparative_capability": comparative_pass,
            "bounded_cpu_resources": resource_pass,
            "complete_identity": identity_pass,
        },
        "capability_improvements": capability_improvements,
        "resources": dict(resources),
        "baseline": dict(baseline),
        "challenger": dict(challenger),
        "effects": dict(_mapping(contract["effects"], "effects")),
        "claims": {
            "oracle_specific_dense_model_selection_passed": selected
            == "lightonai/mDenseOn",
            "statistical_representativeness": False,
            "broad_production_semantic_quality": False,
            "semantic_analysis_lm_quality": False,
            "shared_coordinate_store_readiness": False,
            "oracle_governance_authority": False,
            "release_authority": False,
            "package_publication": False,
            "production_activation": False,
        },
    }


def _load_retained_json(path: Path, label: str) -> dict[str, Any]:
    try:
        before = path.lstat()
        if (
            path.is_symlink()
            or not stat.S_ISREG(before.st_mode)
            or before.st_size <= 0
            or before.st_size > 10_000_000
        ):
            raise SelectionError(f"retained {label} is not a bounded regular file")
        payload = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise SelectionError(f"retained {label} is invalid") from exc
    if not isinstance(payload, dict):
        raise SelectionError(f"retained {label} must be an object")
    return cast(dict[str, Any], payload)


def _verify_identity(
    result: Mapping[str, Any],
    *,
    challenger: bool,
    expected_artifacts: Sequence[Mapping[str, Any]],
    expected_runtime: Mapping[str, Any],
    expected_tokenizer: Mapping[str, Any],
    recovered_adapter: bool = False,
) -> int:
    identity = _mapping(result.get("identity"), "model identity")
    encoding = _mapping(identity.get("encoding"), "encoding identity")
    distance = _mapping(identity.get("distance"), "distance identity")
    tokenizer = _mapping(identity.get("tokenizer"), "tokenizer identity")
    runtime = _mapping(identity.get("runtime"), "runtime identity")
    expected_dimension = 768 if challenger else 384
    expected_schema = (
        "dspx-mdenseon-identity-v1"
        if challenger
        else "dspx-sentence-transformer-identity-v1"
    )
    expected_repository = (
        "lightonai/mDenseOn" if challenger else "sentence-transformers/all-MiniLM-L6-v2"
    )
    expected_revision = (
        "a5fdb000f7a21da96c3bddde3a782ef777316df3"
        if challenger
        else "c9745ed1d9f207416be6d2e6f8de32d1f16199bf"
    )
    artifacts = [
        _mapping(row, "identity artifact")
        for row in _array(identity.get("artifacts"), "identity artifacts")
    ]
    if (
        identity.get("schema_version") != expected_schema
        or identity.get("repository_id") != expected_repository
        or identity.get("revision") != expected_revision
        or identity.get("identity_complete") is not True
        or identity.get("production_semantic_claim_allowed") is not False
        or artifacts != list(expected_artifacts)
        or encoding
        != {
            "dimension": expected_dimension,
            "vector_dtype": "float32",
            "normalize_embeddings": True,
            "normalization_postcondition": "finite_l2_unit_vector",
        }
        or distance
        != {
            "ranking_metric": "cosine_similarity_descending",
            "reported_distance": "one_minus_cosine_similarity",
        }
        or tokenizer != dict(expected_tokenizer)
        or runtime.get("python") != expected_runtime["python_version"]
        or runtime.get("python_implementation")
        != expected_runtime["python_implementation"]
        or runtime.get("lock_sha256") != expected_runtime["lock_sha256"]
        or runtime.get("wheel_sha256")
        != dict(_mapping(expected_runtime["selected_wheel_sha256"], "wheel hashes"))
        or runtime.get("installer") != expected_runtime["installer"]
        or runtime.get("uv_version") != expected_runtime["uv_version"]
        or runtime.get("isolated_frozen") is not True
        or runtime.get("packages")
        != dict(_mapping(expected_runtime["expected_package_versions"], "versions"))
        or runtime.get("distribution_content_sha256")
        != dict(
            _mapping(
                expected_runtime["expected_distribution_content_sha256"],
                "distribution hashes",
            )
        )
        or runtime.get("distribution_content_hash_scope")
        != expected_runtime["distribution_content_hash_scope"]
        or runtime.get("platform") != expected_runtime["platform"]
        or runtime.get("device") != "cpu"
        or runtime.get("observations")
        != {
            "model_device": "cpu",
            "torch_cuda_available": False,
            "torch_default_dtype": "torch.float32",
            "numpy_output_dtype": "float32",
        }
    ):
        raise SelectionError("retained model identity is not bound to root and runtime")
    if challenger:
        adapter = _mapping(identity.get("adapter"), "mDenseOn adapter identity")
        expected_adapter: dict[str, Any] = {
            "name": "dspx-mdenseon-cls-v1",
            "trust_remote_code": False,
            "pooling": "last_hidden_state_cls_token",
            "document_prompt": "document: ",
            "query_prompt": "query: ",
            "maximum_tokens": 8192,
            "serialized_semantics_verified": True,
        }
        if recovered_adapter:
            expected_adapter["removed_model_input_keys"] = ["token_type_ids"]
        architecture = _mapping(
            identity.get("architecture"), "mDenseOn architecture identity"
        )
        if (
            identity.get("backend") != "transformers-dense"
            or adapter != expected_adapter
            or architecture
            != {
                "model_type": "modernbert",
                "hidden_size": 768,
                "parameter_dtype": "torch.float32",
                "maximum_position_embeddings": 8192,
            }
        ):
            raise SelectionError("retained mDenseOn adapter identity drift")
    elif identity.get("backend") != "sentence-transformers":
        raise SelectionError("retained MiniLM backend identity drift")
    return expected_dimension


def _verify_database(
    path: Path,
    *,
    embedding_version: int,
    dimension: int,
    result_records: Sequence[Any],
) -> tuple[str, dict[str, list[float]]]:
    try:
        before = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(before.st_mode) or before.st_size <= 0:
            raise SelectionError("retained database is not a regular SQLite file")
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()
            rows = connection.execute(
                "SELECT run_id, vector_json, embedding_version, dimension "
                "FROM coordinates"
            ).fetchall()
        finally:
            connection.close()
    except (OSError, sqlite3.DatabaseError, TypeError) as exc:
        raise SelectionError("retained database verification failed") from exc
    vectors: dict[str, list[float]] = {}
    try:
        for run_id, vector_json, version, observed_dimension in rows:
            vector = json.loads(vector_json)
            if (
                not isinstance(run_id, str)
                or not isinstance(vector, list)
                or len(vector) != dimension
                or any(
                    not isinstance(value, float) or not math.isfinite(value)
                    for value in vector
                )
                or version != embedding_version
                or observed_dimension != dimension
            ):
                raise SelectionError("retained database vector identity drift")
            resolved_vector = cast(list[float], vector)
            validate_unit_vector(resolved_vector)
            vectors[run_id] = resolved_vector
    except (json.JSONDecodeError, TypeError) as exc:
        raise SelectionError("retained database vector is invalid") from exc
    expected_records = [_mapping(row, "result record") for row in result_records]
    if (
        integrity != ("ok",)
        or set(vectors) != set(EXPECTED_RECORD_IDS)
        or tuple(row.get("case_id") for row in expected_records) != EXPECTED_RECORD_IDS
        or any(
            _vector_sha256(vectors[cast(str, row["case_id"])])
            != row.get("vector_sha256")
            for row in expected_records
        )
    ):
        raise SelectionError("retained database row or vector binding drift")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest(), vectors


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        raise SelectionError("retained vector has zero norm")
    return dot / (left_norm * right_norm)


def _verify_scored_result(
    result: Mapping[str, Any],
    *,
    contract: Mapping[str, Any],
    document_vectors: Mapping[str, list[float]],
) -> None:
    contract_queries = [
        _mapping(row, "contract query")
        for row in _array(
            _mapping(contract["evaluation"], "evaluation")["queries"], "queries"
        )
    ]
    query_rows = [
        _mapping(row, "query result")
        for row in _array(result.get("queries"), "query results")
    ]
    if tuple(row.get("id") for row in query_rows) != EXPECTED_QUERY_IDS:
        raise SelectionError("retained query result order drift")
    ranks: list[int] = []
    subsets: dict[str, list[int]] = {
        "cross_lingual": [],
        "critical": [],
        "long_context": [],
    }
    falsifiers: list[str] = []
    for contract_query, row in zip(contract_queries, query_rows, strict=True):
        vector = row.get("vector")
        digest = row.get("vector_sha256")
        if (
            not isinstance(vector, list)
            or any(
                not isinstance(value, float) or not math.isfinite(value)
                for value in vector
            )
            or _vector_sha256(cast(list[float], vector)) != digest
            or row.get("id") != contract_query.get("id")
            or row.get("expected_case_id") != contract_query.get("expected_case_id")
            or row.get("subset") != contract_query.get("subset")
        ):
            raise SelectionError("retained query vector or label drift")
        resolved_query_vector = cast(list[float], vector)
        validate_unit_vector(resolved_query_vector)
        derived = sorted(
            (
                {
                    "case_id": case_id,
                    "similarity": _cosine(resolved_query_vector, document),
                }
                for case_id, document in document_vectors.items()
            ),
            key=lambda value: cast(float, value["similarity"]),
            reverse=True,
        )
        ranking = [
            _mapping(value, "ranking row")
            for value in _array(row.get("ranking"), "ranking")
        ]
        if len(ranking) != len(derived) or any(
            observed.get("case_id") != expected["case_id"]
            or not math.isclose(
                cast(float, observed.get("similarity")),
                cast(float, expected["similarity"]),
                rel_tol=0.0,
                abs_tol=1e-12,
            )
            or not math.isclose(
                cast(float, observed.get("distance")),
                1.0 - cast(float, expected["similarity"]),
                rel_tol=0.0,
                abs_tol=1e-12,
            )
            for observed, expected in zip(ranking, derived, strict=True)
        ):
            raise SelectionError("retained ranking does not derive from SQLite vectors")
        expected_case_id = cast(str, contract_query["expected_case_id"])
        rank = next(
            index
            for index, value in enumerate(derived, 1)
            if value["case_id"] == expected_case_id
        )
        tied = len(derived) > 1 and math.isclose(
            cast(float, derived[0]["similarity"]),
            cast(float, derived[1]["similarity"]),
            rel_tol=0.0,
            abs_tol=1e-12,
        )
        if tied:
            falsifiers.append(f"top_rank_tied:{row['id']}")
        if rank != row.get("expected_rank") or tied is not row.get("top_rank_tied"):
            raise SelectionError("retained rank or tie drift")
        subset = cast(str, row["subset"])
        if subset.startswith("cross_lingual"):
            subsets["cross_lingual"].append(rank)
        if "critical" in subset:
            subsets["critical"].append(rank)
        if subset.startswith("long_context"):
            subsets["long_context"].append(rank)
        ranks.append(rank)
    if (
        _mapping(result.get("metrics"), "metrics") != _metrics(ranks)
        or _mapping(result.get("subset_metrics"), "subset metrics")
        != {name: _metrics(values) for name, values in subsets.items()}
        or result.get("falsifiers_observed") != falsifiers
    ):
        raise SelectionError("retained metric or falsifier drift")


def verify_retained_selection(
    *,
    root: Path,
    contract: Mapping[str, Any],
    baseline_spec: SentenceTransformerIdentitySpec,
    baseline_model_root: Path,
    challenger_model_root: Path,
    recovered_adapter: bool = False,
) -> dict[str, Any]:
    """Independently reload, re-rank, and verify the retained selection package."""

    validate_contract_payload(contract)
    result_path = root / "selection-result.json"
    result = _load_retained_json(result_path, "selection result")
    if (
        result.get("schema_version") != RESULT_SCHEMA
        or result.get("contract_sha256") != EXPECTED_CONTRACT_SHA256
    ):
        raise SelectionError("retained result contract identity drift")
    baseline = _mapping(result.get("baseline"), "baseline result")
    challenger = _mapping(result.get("challenger"), "challenger result")
    expected_runtime = _mapping(contract["runtime"], "runtime")
    expected_candidates = _mapping(contract["candidates"], "candidates")
    expected_baseline = _mapping(expected_candidates["baseline"], "baseline")
    expected_challenger = _mapping(expected_candidates["challenger"], "challenger")
    baseline_artifacts = validate_model_artifact_root(
        baseline_spec, baseline_model_root
    )
    challenger_spec = challenger_identity_spec(contract)
    challenger_artifacts = validate_model_artifact_root(
        challenger_spec, challenger_model_root
    )
    validate_serialized_mdenseon_semantics(challenger_model_root)
    baseline_dimension = _verify_identity(
        baseline,
        challenger=False,
        expected_artifacts=baseline_artifacts,
        expected_runtime=expected_runtime,
        expected_tokenizer=_mapping(
            expected_baseline["tokenizer_identity"], "baseline tokenizer"
        ),
    )
    challenger_dimension = _verify_identity(
        challenger,
        challenger=True,
        expected_artifacts=challenger_artifacts,
        expected_runtime=expected_runtime,
        expected_tokenizer=_mapping(
            expected_challenger["tokenizer_identity"], "challenger tokenizer"
        ),
        recovered_adapter=recovered_adapter,
    )
    baseline_db_sha256, baseline_vectors = _verify_database(
        root / BASELINE_DB_FILE,
        embedding_version=1,
        dimension=baseline_dimension,
        result_records=_array(baseline.get("records"), "baseline records"),
    )
    challenger_db_sha256, challenger_vectors = _verify_database(
        root / CHALLENGER_DB_FILE,
        embedding_version=2,
        dimension=challenger_dimension,
        result_records=_array(challenger.get("records"), "challenger records"),
    )
    _verify_scored_result(
        baseline, contract=contract, document_vectors=baseline_vectors
    )
    _verify_scored_result(
        challenger, contract=contract, document_vectors=challenger_vectors
    )
    resources = _mapping(result.get("resources"), "resources")
    retained_model_bytes = sum(
        path.stat().st_size
        for path in challenger_model_root.rglob("*")
        if path.is_file() and ".cache" not in path.parts
    )
    if (
        resources.get("retained_model_bytes") != retained_model_bytes
        or type(resources.get("peak_rss_bytes")) is not int
        or cast(int, resources["peak_rss_bytes"]) <= 0
        or any(
            not isinstance(resources.get(key), (int, float))
            or isinstance(resources.get(key), bool)
            or not math.isfinite(cast(float, resources[key]))
            or cast(float, resources[key]) < 0.0
            for key in (
                "model_load_seconds",
                "total_encode_seconds",
                "full_batch_reproduction_seconds",
            )
        )
    ):
        raise SelectionError("retained resource observation drift")
    expected = select_model(
        contract=contract,
        baseline=baseline,
        challenger=challenger,
        resources=resources,
    )
    for key in (
        "status",
        "selected_model",
        "embedding_version",
        "gates",
        "capability_improvements",
        "effects",
        "claims",
    ):
        if result.get(key) != expected.get(key):
            raise SelectionError(f"retained selection derivation drift: {key}")
    reproduction = _mapping(
        result.get("full_batch_reproduction"), "full-batch reproduction"
    )
    hashes = _mapping(reproduction.get("vector_hashes"), "reproduction hashes")
    if (
        reproduction.get("verified") is not True
        or hashes.get("documents")
        != [row["vector_sha256"] for row in _array(challenger["records"], "records")]
        or hashes.get("queries")
        != [row["vector_sha256"] for row in _array(challenger["queries"], "queries")]
    ):
        raise SelectionError("retained full-batch reproduction binding drift")
    result_sha256 = hashlib.sha256(result_path.read_bytes()).hexdigest()
    return {
        "schema_version": "dspx-oracle-embedding-selection-verification-v1",
        "status": (
            "accepted"
            if expected["status"] == "passed"
            else "accepted_challenger_not_selected"
        ),
        "contract_sha256": EXPECTED_CONTRACT_SHA256,
        "result_sha256": result_sha256,
        "baseline_database_sha256": baseline_db_sha256,
        "challenger_database_sha256": challenger_db_sha256,
        "full_batch_reproduction_verified": True,
        "database_vectors_independently_ranked": True,
        "metrics_independently_rederived": True,
        "selection_independently_rederived": True,
        "resource_contract_independently_checked": True,
        "claim_boundary_verified": True,
    }
