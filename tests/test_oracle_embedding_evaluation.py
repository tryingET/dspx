# summary: "Tests the frozen one-shot Oracle embedding identity and held-out routing evaluation."

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import math
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, cast

import pytest

import dspx.coordinates.embedding_identity as embedding_identity_module

import dspx.coordinates.embeddings as embeddings_module
import dspx.coordinates.oracle_embedding_verification as verification_module

from dspx.coordinates.embedding_identity import (
    EmbeddingIdentityError,
    SentenceTransformerIdentitySpec,
    build_sentence_transformer_identity,
    validate_unit_vector,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts/ci/run_oracle_embedding_evaluation.py"
CONTRACT_PATH = REPO_ROOT / "benchmarks/semantic/oracle-embedding-evaluation-v1.json"


def _load_runner() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "run_oracle_embedding_evaluation", SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _contract() -> dict[str, Any]:
    payload = json.loads(CONTRACT_PATH.read_text())
    assert isinstance(payload, dict)
    return payload


def _spec(
    module: ModuleType, contract: dict[str, Any] | None = None
) -> SentenceTransformerIdentitySpec:
    return cast(
        SentenceTransformerIdentitySpec, module._identity_spec(contract or _contract())
    )


def _artifact_bytes(index: int, relative_path: str) -> bytes:
    return f"artifact-{index}-{relative_path}".encode()


def _git_blob_oid(raw: bytes) -> str:
    return hashlib.sha1(
        f"blob {len(raw)}\0".encode() + raw, usedforsecurity=False
    ).hexdigest()


def _test_contract() -> dict[str, Any]:
    contract = copy.deepcopy(_contract())
    manifest = []
    for index, row in enumerate(contract["backend"]["artifact_manifest"]):
        raw = _artifact_bytes(index, row["path"])
        manifest.append(
            {
                "path": row["path"],
                "size": len(raw),
                "source_git_oid": _git_blob_oid(raw),
                "lfs_sha256": None,
            }
        )
    contract["backend"]["artifact_manifest"] = manifest
    contract["backend"]["runtime_environment"]["expected_package_versions"] = {
        name: f"test-{index}"
        for index, name in enumerate(contract["backend"]["runtime_identity_packages"])
    }
    return contract


def _create_artifacts(root: Path, spec: SentenceTransformerIdentitySpec) -> None:
    for index, expected in enumerate(spec.artifact_manifest):
        path = root / expected.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_artifact_bytes(index, expected.path))


class _Tokenizer:
    model_max_length = 256
    padding_side = "right"
    truncation_side = "right"

    def __len__(self) -> int:
        return 30_522


def _runtime_observations() -> dict[str, object]:
    return {
        "model_device": "cpu",
        "torch_cuda_available": False,
        "torch_default_dtype": "torch.float32",
        "numpy_output_dtype": "float32",
    }


def _runtime_distribution_hashes(
    spec: SentenceTransformerIdentitySpec,
) -> dict[str, str]:
    return {
        name: hashlib.sha256(f"distribution:{name}".encode()).hexdigest()
        for name in spec.runtime_packages
    }


def _identity(
    module: ModuleType, root: Path, contract: dict[str, Any] | None = None
) -> dict[str, Any]:
    selected_contract = contract or _test_contract()
    spec = _spec(module, selected_contract)
    _create_artifacts(root, spec)
    return build_sentence_transformer_identity(
        spec=spec,
        model_root=root,
        tokenizer=_Tokenizer(),
        dimension=384,
        observed_vector_dtype="float32",
        frozen_runtime_lock_sha256=spec.runtime_lock_sha256,
        runtime_observations=_runtime_observations(),
        runtime_distribution_content_sha256=_runtime_distribution_hashes(spec),
        runtime_versions=dict(spec.runtime_versions),
    )


def _basis(index: int) -> list[float]:
    vector = [0.0] * 384
    vector[index] = 1.0
    return vector


def _reproduction_receipt(
    identity: dict[str, Any], result: dict[str, Any]
) -> dict[str, Any]:
    identity_sha256 = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "schema_version": "dspx-oracle-embedding-model-reproduction-v1",
        "status": "passed",
        "fresh_local_model_instance": True,
        "single_complete_ordered_batch": True,
        "identity_sha256": identity_sha256,
        "batch_order": [
            {
                "kind": "record",
                "id": row["case_id"],
                "vector_sha256": row["vector_sha256"],
            }
            for row in result["records"]
        ]
        + [
            {
                "kind": "query",
                "id": row["id"],
                "vector_sha256": row["vector_sha256"],
            }
            for row in result["queries"]
        ],
    }


def _passed_evidence(
    module: ModuleType, root: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    model_root = root / module.MODEL_DIR
    contract = _test_contract()
    identity = _identity(module, model_root, contract)
    vectors = [_basis(0), _basis(1), _basis(2)]
    result = module.evaluate_vectors(
        contract=contract,
        identity=identity,
        document_vectors=vectors,
        query_vectors=vectors,
        database_path=root / module.DB_FILE,
    )
    result["model_reproduction"] = _reproduction_receipt(identity, result)
    result["claims"]["full_batch_model_reproduction_verified"] = True
    result["claims"]["production_semantic_embedding_gate_passed"] = False
    module._write_json(root / module.RESULT_FILE, result)
    return identity, result


def test_checked_in_contract_is_exact_and_source_bound() -> None:
    module = _load_runner()

    contract, observed_hash = module.load_contract(REPO_ROOT)

    assert observed_hash == module.EXPECTED_CONTRACT_SHA256
    assert (
        contract["attempt_budget"]["maximum_model_acquisition_and_evaluation_sequences"]
        == 1
    )
    assert contract["attempt_budget"]["selective_query_reruns_allowed"] is False
    assert contract["effects"] == {
        "semantic_analysis_lm_calls": 0,
        "shared_store_connections": 0,
        "shared_oracle_publications": 0,
        "release_or_activation_mutations": 0,
        "ak_mutations_from_evaluated_code": 0,
    }


@pytest.mark.parametrize(
    "mutate,match",
    [
        (lambda value: value["backend"].update({"revision": "main"}), "revision"),
        (
            lambda value: value["backend"].update({"expected_dimension": True}),
            "dimension",
        ),
        (
            lambda value: value["backend"]["normalization"].update(
                {"encode_normalize_embeddings": False}
            ),
            "normalization",
        ),
        (
            lambda value: value["backend"]["artifact_manifest"].pop(),
            "artifact manifest",
        ),
        (
            lambda value: value["backend"]["runtime_environment"].update(
                {"lock_sha256": "0" * 64}
            ),
            "runtime lock",
        ),
        (
            lambda value: value["evaluation"]["queries"].reverse(),
            "query order",
        ),
        (
            lambda value: value["evaluation"]["thresholds"].update(
                {"recall_at_1": 0.0}
            ),
            "thresholds",
        ),
        (
            lambda value: value["attempt_budget"].update(
                {"selective_query_reruns_allowed": True}
            ),
            "selective",
        ),
        (
            lambda value: value["attempt_budget"]["enforcement"].update(
                {"marker_created_before_model_acquisition": False}
            ),
            "ledger",
        ),
        (
            lambda value: value["effects"].update(
                {"semantic_analysis_lm_calls": False}
            ),
            "effect",
        ),
    ],
)
def test_contract_claim_or_execution_drift_fails_closed(
    mutate: Any, match: str
) -> None:
    module = _load_runner()
    payload = copy.deepcopy(_contract())
    mutate(payload)

    with pytest.raises(module.EvaluationError, match=match):
        module.validate_contract_payload(payload)


def test_identity_hash_binds_artifacts_tokenizer_runtime_and_vector_semantics(
    tmp_path: Path,
) -> None:
    module = _load_runner()
    contract = _test_contract()
    identity = _identity(module, tmp_path, contract)

    module.validate_complete_identity(contract, identity)

    assert [row["path"] for row in identity["artifacts"]] == list(
        _spec(module, contract).artifact_paths
    )
    assert all(
        len(row["sha256"]) == 64 and row["size"] > 0 for row in identity["artifacts"]
    )
    assert identity["tokenizer"] == {
        "implementation": f"{__name__}._Tokenizer",
        "model_max_length": 256,
        "padding_side": "right",
        "truncation_side": "right",
        "vocabulary_size": 30_522,
    }
    assert identity["encoding"] == {
        "dimension": 384,
        "vector_dtype": "float32",
        "normalize_embeddings": True,
        "normalization_postcondition": "finite_l2_unit_vector",
    }
    assert identity["distance"] == {
        "ranking_metric": "cosine_similarity_descending",
        "reported_distance": "one_minus_cosine_similarity",
    }
    assert identity["production_semantic_claim_allowed"] is False


def test_identity_rejects_symlinked_artifact_and_incomplete_runtime(
    tmp_path: Path,
) -> None:
    module = _load_runner()
    contract = _test_contract()
    spec = _spec(module, contract)
    _create_artifacts(tmp_path, spec)
    target = tmp_path / spec.artifact_paths[0]
    replacement = tmp_path / "replacement"
    replacement.write_bytes(target.read_bytes())
    target.unlink()
    target.symlink_to(replacement)

    with pytest.raises(EmbeddingIdentityError, match="loader-relevant artifacts"):
        build_sentence_transformer_identity(
            spec=spec,
            model_root=tmp_path,
            tokenizer=_Tokenizer(),
            dimension=384,
            observed_vector_dtype="float32",
            frozen_runtime_lock_sha256=spec.runtime_lock_sha256,
            runtime_observations=_runtime_observations(),
            runtime_distribution_content_sha256=_runtime_distribution_hashes(spec),
            runtime_versions=dict(spec.runtime_versions),
        )

    target.unlink()
    target.write_bytes(_artifact_bytes(0, spec.artifact_paths[0]))
    replacement.unlink()
    with pytest.raises(EmbeddingIdentityError, match="runtime package identity"):
        build_sentence_transformer_identity(
            spec=spec,
            model_root=tmp_path,
            tokenizer=_Tokenizer(),
            dimension=384,
            observed_vector_dtype="float32",
            frozen_runtime_lock_sha256=spec.runtime_lock_sha256,
            runtime_observations=_runtime_observations(),
            runtime_distribution_content_sha256=_runtime_distribution_hashes(spec),
            runtime_versions={spec.runtime_packages[0]: "1"},
        )


def test_stable_distribution_path_excludes_install_projections(
    tmp_path: Path,
) -> None:
    del tmp_path
    assert embedding_identity_module._is_stable_distribution_path(
        Path("transformers/modeling_utils.py")
    )
    assert embedding_identity_module._is_stable_distribution_path(
        Path("numpy.libs/libscipy_openblas.so")
    )
    for projected in (
        Path("../../../bin/transformers"),
        Path("transformers-4.57.6.dist-info/RECORD"),
        Path("transformers-4.57.6.dist-info/INSTALLER"),
        Path("transformers-4.57.6.dist-info/direct_url.json"),
    ):
        assert not embedding_identity_module._is_stable_distribution_path(projected)


def test_identity_rejects_same_size_artifact_substitution(tmp_path: Path) -> None:
    module = _load_runner()
    contract = _test_contract()
    spec = _spec(module, contract)
    _create_artifacts(tmp_path, spec)
    first = tmp_path / spec.artifact_paths[0]
    first.write_bytes(b"x" * first.stat().st_size)

    with pytest.raises(EmbeddingIdentityError, match="Git artifact identity drift"):
        build_sentence_transformer_identity(
            spec=spec,
            model_root=tmp_path,
            tokenizer=_Tokenizer(),
            dimension=384,
            observed_vector_dtype="float32",
            frozen_runtime_lock_sha256=spec.runtime_lock_sha256,
            runtime_observations=_runtime_observations(),
            runtime_distribution_content_sha256=_runtime_distribution_hashes(spec),
            runtime_versions=dict(spec.runtime_versions),
        )


def test_sentence_transformer_embedder_rejects_non_float32_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeMatrix:
        dtype = "float64"
        shape = (1, 384)

    class FakeModel:
        tokenizer = _Tokenizer()

        def __init__(self, *_args: Any, **_kwargs: Any):
            pass

        def get_sentence_embedding_dimension(self) -> int:
            return 384

        def encode(self, *_args: Any, **_kwargs: Any) -> FakeMatrix:
            return FakeMatrix()

    monkeypatch.setattr(
        embeddings_module,
        "import_module",
        lambda _name: SimpleNamespace(SentenceTransformer=FakeModel),
    )
    embedder = embeddings_module.SentenceTransformerEmbedder(
        "test/model",
        model_root=tmp_path,
        normalize_embeddings=True,
        device="cpu",
    )

    with pytest.raises(
        embeddings_module.EmbeddingValidationError, match="float32 matrix"
    ):
        embedder.encode(["one"])


@pytest.mark.parametrize("vector", [[], [1.0, math.nan], [1.0, 1.0], [1, 0]])
def test_unit_vector_validation_fails_closed(vector: list[float]) -> None:
    with pytest.raises(EmbeddingIdentityError):
        validate_unit_vector(vector)


def test_three_query_local_sqlite_evaluation_passes_only_complete_top1_gate(
    tmp_path: Path,
) -> None:
    module = _load_runner()
    contract = _test_contract()
    identity = _identity(module, tmp_path / module.MODEL_DIR, contract)
    vectors = [_basis(0), _basis(1), _basis(2)]

    result = module.evaluate_vectors(
        contract=contract,
        identity=identity,
        document_vectors=vectors,
        query_vectors=vectors,
        database_path=tmp_path / module.DB_FILE,
    )

    assert result["status"] == "passed"
    assert result["metrics"] == {
        "labeled_query_count": 3,
        "recall_at_1": 1.0,
        "mean_reciprocal_rank": 1.0,
        "normalized_discounted_cumulative_gain_at_3": 1.0,
    }
    assert [row["expected_rank"] for row in result["queries"]] == [1, 1, 1]
    assert result["claims"]["held_out_routing_metric_gate_passed"] is True
    assert result["claims"]["full_batch_model_reproduction_verified"] is False
    assert result["claims"]["production_semantic_embedding_gate_passed"] is False
    assert (
        result["claims"]["broad_or_statistically_representative_semantic_quality"]
        is False
    )
    with sqlite3.connect(tmp_path / module.DB_FILE) as connection:
        assert connection.execute("SELECT COUNT(*) FROM coordinates").fetchone() == (3,)


def test_semantic_miss_and_top_tie_are_terminal_failed_evidence(tmp_path: Path) -> None:
    module = _load_runner()
    contract = _test_contract()
    identity = _identity(module, tmp_path / module.MODEL_DIR, contract)
    documents = [_basis(0), _basis(1), _basis(2)]
    query_vectors = [_basis(1), _basis(1), _basis(2)]

    miss = module.evaluate_vectors(
        contract=contract,
        identity=identity,
        document_vectors=documents,
        query_vectors=query_vectors,
        database_path=tmp_path / "miss.sqlite3",
    )

    assert miss["status"] == "failed"
    assert miss["metrics"]["recall_at_1"] == pytest.approx(2 / 3)
    assert "metric_below_threshold" in miss["falsifiers_observed"]

    tied = [0.0] * 384
    tied[0] = tied[1] = 1 / math.sqrt(2)
    tie = module.evaluate_vectors(
        contract=contract,
        identity=identity,
        document_vectors=documents,
        query_vectors=[tied, _basis(1), _basis(2)],
        database_path=tmp_path / "tie.sqlite3",
    )
    assert tie["status"] == "failed"
    assert tie["queries"][0]["top_rank_tied"] is True
    assert tie["falsifiers_observed"][0].startswith(
        "expected_case_not_uniquely_ranked_first:"
    )


def test_independent_verifier_rederives_sqlite_rankings_metrics_and_nonclaims(
    tmp_path: Path,
) -> None:
    module = _load_runner()
    _passed_evidence(module, tmp_path)

    verification = verification_module._verify_retained_consistency(
        tmp_path, _test_contract()
    )

    assert verification["status"] == "passed"
    assert verification["internally_consistent_embedding_gate_passed"] is True
    assert "production_semantic_embedding_gate_passed" not in verification
    assert verification["model_artifact_count"] == 10
    assert verification["nonclaims_preserved"] is True


def test_fresh_model_reproduction_encodes_one_complete_ordered_batch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_runner()
    identity, result = _passed_evidence(module, tmp_path)
    calls: list[list[str]] = []

    class FakeReproductionEmbedder:
        def __init__(self, *_args: Any, **_kwargs: Any):
            pass

        def encode(self, texts: list[str]) -> list[list[float]]:
            calls.append(texts)
            return [_basis(0), _basis(1), _basis(2), _basis(0), _basis(1), _basis(2)]

        def build_identity(
            self, _spec: SentenceTransformerIdentitySpec, **_kwargs: Any
        ) -> dict[str, Any]:
            return identity

    monkeypatch.setattr(
        verification_module, "SentenceTransformerEmbedder", FakeReproductionEmbedder
    )

    reproduced = verification_module.reproduce_model_batch(
        contract=_test_contract(),
        result=result,
        model_root=tmp_path / module.MODEL_DIR,
    )

    assert reproduced == result["model_reproduction"]
    assert len(calls) == 1
    assert len(calls[0]) == 6
    verification = verification_module.verify_retained_evaluation(
        tmp_path, _test_contract()
    )
    assert verification["production_semantic_embedding_gate_passed"] is True
    assert verification["full_batch_model_reproduction_verified"] is True
    assert len(calls) == 2


def test_legacy_distribution_reconciliation_is_bound_to_exact_known_packet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_runner()
    identity, result = _passed_evidence(module, tmp_path)

    class FakeReproductionEmbedder:
        def __init__(self, *_args: Any, **_kwargs: Any):
            pass

        def encode(self, _texts: list[str]) -> list[list[float]]:
            return [_basis(0), _basis(1), _basis(2), _basis(0), _basis(1), _basis(2)]

        def build_identity(
            self, _spec: SentenceTransformerIdentitySpec, **_kwargs: Any
        ) -> dict[str, Any]:
            return identity

    monkeypatch.setattr(
        verification_module, "SentenceTransformerEmbedder", FakeReproductionEmbedder
    )
    legacy = copy.deepcopy(result)
    legacy_runtime = legacy["model_identity"]["runtime"]
    legacy_runtime.pop("distribution_content_hash_scope")
    legacy_runtime["distribution_content_sha256"] = dict(
        verification_module._LEGACY_DISTRIBUTION_CONTENT_SHA256
    )

    receipt = verification_module.reproduce_model_batch(
        contract=_test_contract(),
        result=legacy,
        model_root=tmp_path / module.MODEL_DIR,
        result_sha256=verification_module._LEGACY_RESULT_SHA256,
    )
    assert receipt["identity_reconciliation"]["resolution"] == (
        "legacy_install_projection_hashes_excluded"
    )

    legacy_runtime["distribution_content_sha256"]["torch"] = "0" * 64
    with pytest.raises(module.EvaluationError, match="identity drift"):
        verification_module.reproduce_model_batch(
            contract=_test_contract(),
            result=legacy,
            model_root=tmp_path / module.MODEL_DIR,
            result_sha256=verification_module._LEGACY_RESULT_SHA256,
        )


@pytest.mark.parametrize("target", ["artifact", "database", "claim", "query-label"])
def test_independent_verifier_rejects_evidence_drift(
    tmp_path: Path, target: str
) -> None:
    module = _load_runner()
    identity, result = _passed_evidence(module, tmp_path)
    if target == "artifact":
        artifact = identity["artifacts"][0]
        (tmp_path / module.MODEL_DIR / artifact["path"]).write_bytes(b"drift")
    elif target == "database":
        with sqlite3.connect(tmp_path / module.DB_FILE) as connection:
            connection.execute(
                "UPDATE coordinates SET input_text = 'drift' WHERE run_id = ?",
                (module.EXPECTED_RECORD_IDS[0],),
            )
    elif target == "claim":
        result["claims"]["release_authority"] = True
        module._write_json(tmp_path / module.RESULT_FILE, result)
    else:
        result["queries"][0]["expected_case_id"] = module.EXPECTED_RECORD_IDS[1]
        module._write_json(tmp_path / module.RESULT_FILE, result)

    with pytest.raises(module.EvaluationError):
        verification_module._verify_retained_consistency(tmp_path, _test_contract())


def test_independent_verifier_rejects_forged_unique_top_tie(
    tmp_path: Path,
) -> None:
    module = _load_runner()
    identity, result = _passed_evidence(module, tmp_path)
    tied = [0.0] * 384
    tied[0] = tied[1] = 1 / math.sqrt(2)
    ranking = [
        {
            "case_id": module.EXPECTED_RECORD_IDS[0],
            "similarity": 1 / math.sqrt(2),
            "distance": 1 - 1 / math.sqrt(2),
        },
        {
            "case_id": module.EXPECTED_RECORD_IDS[1],
            "similarity": 1 / math.sqrt(2),
            "distance": 1 - 1 / math.sqrt(2),
        },
        {
            "case_id": module.EXPECTED_RECORD_IDS[2],
            "similarity": 0.0,
            "distance": 1.0,
        },
    ]
    result["queries"][0].update(
        {
            "vector": tied,
            "vector_sha256": hashlib.sha256(
                json.dumps(tied, separators=(",", ":")).encode()
            ).hexdigest(),
            "ranking": ranking,
            "expected_rank": 1,
            "top_rank_tied": False,
        }
    )
    result["falsifiers_observed"] = []
    result["model_reproduction"] = _reproduction_receipt(identity, result)
    module._write_json(tmp_path / module.RESULT_FILE, result)

    with pytest.raises(module.EvaluationError, match="top-rank tie"):
        verification_module._verify_retained_consistency(tmp_path, _test_contract())


def test_evaluation_refuses_nonisolated_unfrozen_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_runner()
    monkeypatch.setattr(module, "_FROZEN_RUNTIME_VERIFIED", False)
    monkeypatch.setenv(
        "DSPX_ORACLE_EMBEDDING_FROZEN_RUNTIME",
        module.EXPECTED_SOURCE_HASHES["uv.lock"],
    )

    with pytest.raises(
        module.EvaluationError, match="authenticated isolated frozen uv runtime"
    ):
        module._acquire_and_run(repo_root=REPO_ROOT, root=tmp_path / "evaluation")


def test_one_shot_runner_uses_atomic_ledger_across_distinct_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_runner()
    calls = {"snapshot": 0, "encode": 0}

    def snapshot_download(**kwargs: Any) -> str:
        calls["snapshot"] += 1
        root = Path(kwargs["local_dir"])
        root.mkdir()
        return str(root)

    class FakeEmbedder:
        def __init__(self, *_args: Any, **_kwargs: Any):
            pass

        def encode(self, texts: list[str]) -> list[list[float]]:
            calls["encode"] += 1
            assert len(texts) == 6
            return [_basis(0), _basis(1), _basis(2), _basis(0), _basis(1), _basis(2)]

        def build_identity(
            self, _spec: SentenceTransformerIdentitySpec, **_kwargs: Any
        ) -> dict[str, Any]:
            return {"test_identity": True}

    monkeypatch.setitem(
        sys.modules,
        "huggingface_hub",
        SimpleNamespace(snapshot_download=snapshot_download),
    )
    monkeypatch.setattr(module, "SentenceTransformerEmbedder", FakeEmbedder)
    monkeypatch.setattr(
        module,
        "evaluate_vectors",
        lambda **_kwargs: {
            "status": "passed",
            "claims": {
                "full_batch_model_reproduction_verified": False,
                "production_semantic_embedding_gate_passed": False,
            },
        },
    )
    monkeypatch.setattr(
        module,
        "reproduce_model_batch",
        lambda **_kwargs: {"status": "passed", "batch_order": [1, 2, 3, 4, 5, 6]},
    )
    monkeypatch.setattr(
        module,
        "verify_retained_evaluation",
        lambda *_args: {"status": "passed"},
    )
    ledger = tmp_path / "state" / "ledger.json"
    root = tmp_path / "evaluation-a"
    monkeypatch.setattr(module, "_default_attempt_ledger_path", lambda: ledger)
    monkeypatch.setattr(module, "_FROZEN_RUNTIME_VERIFIED", True)

    assert module._acquire_and_run(repo_root=REPO_ROOT, root=root) == 0
    assert calls == {"snapshot": 1, "encode": 1}
    assert json.loads((root / module.ATTEMPT_FILE).read_text())["status"] == "passed"
    root.rename(tmp_path / "moved-evidence")
    with pytest.raises(module.EvaluationError, match="ledger is already consumed"):
        module._acquire_and_run(repo_root=REPO_ROOT, root=tmp_path / "evaluation-b")
    assert calls == {"snapshot": 1, "encode": 1}


def test_verifier_failure_retains_only_false_production_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_runner()

    def snapshot_download(**kwargs: Any) -> str:
        root = Path(kwargs["local_dir"])
        root.mkdir()
        return str(root)

    class FakeEmbedder:
        def __init__(self, *_args: Any, **_kwargs: Any):
            pass

        def encode(self, _texts: list[str]) -> list[list[float]]:
            return [_basis(0), _basis(1), _basis(2), _basis(0), _basis(1), _basis(2)]

        def build_identity(
            self, _spec: SentenceTransformerIdentitySpec, **_kwargs: Any
        ) -> dict[str, Any]:
            return {"test_identity": True}

    monkeypatch.setitem(
        sys.modules,
        "huggingface_hub",
        SimpleNamespace(snapshot_download=snapshot_download),
    )
    monkeypatch.setattr(module, "SentenceTransformerEmbedder", FakeEmbedder)
    monkeypatch.setattr(
        module,
        "evaluate_vectors",
        lambda **_kwargs: {
            "status": "passed",
            "claims": {
                "full_batch_model_reproduction_verified": False,
                "production_semantic_embedding_gate_passed": False,
            },
        },
    )
    monkeypatch.setattr(
        module,
        "reproduce_model_batch",
        lambda **_kwargs: {"status": "passed", "batch_order": [1, 2, 3, 4, 5, 6]},
    )

    def reject_verification(*_args: Any) -> dict[str, Any]:
        raise module.EvaluationError("forced verification failure")

    monkeypatch.setattr(module, "verify_retained_evaluation", reject_verification)
    ledger = tmp_path / "state" / "ledger.json"
    root = tmp_path / "failed-verifier"
    monkeypatch.setattr(module, "_default_attempt_ledger_path", lambda: ledger)
    monkeypatch.setattr(module, "_FROZEN_RUNTIME_VERIFIED", True)

    with pytest.raises(module.EvaluationError, match="forced verification failure"):
        module._acquire_and_run(repo_root=REPO_ROOT, root=root)

    retained = json.loads((root / module.RESULT_FILE).read_text())
    assert retained["claims"]["full_batch_model_reproduction_verified"] is True
    assert retained["claims"]["production_semantic_embedding_gate_passed"] is False
    assert json.loads((root / module.ATTEMPT_FILE).read_text())["status"] == (
        "failed_or_indeterminate_terminal"
    )


def test_attempt_ledger_claim_is_atomic_under_concurrency(tmp_path: Path) -> None:
    module = _load_runner()
    ledger = tmp_path / "state" / "ledger.json"

    def claim(index: int) -> str:
        try:
            module._claim_attempt(tmp_path / f"root-{index}", ledger)
        except module.EvaluationError:
            return "rejected"
        return "claimed"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(claim, range(2)))

    assert sorted(outcomes) == ["claimed", "rejected"]
    assert json.loads(ledger.read_text())["attempt_budget_consumed"] == 1


def test_interrupted_attempt_consumes_ledger_without_query_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_runner()

    def snapshot_download(**kwargs: Any) -> str:
        root = Path(kwargs["local_dir"])
        root.mkdir()
        return str(root)

    class InterruptedEmbedder:
        def __init__(self, *_args: Any, **_kwargs: Any):
            pass

        def encode(self, _texts: list[str]) -> list[list[float]]:
            raise KeyboardInterrupt()

    monkeypatch.setitem(
        sys.modules,
        "huggingface_hub",
        SimpleNamespace(snapshot_download=snapshot_download),
    )
    monkeypatch.setattr(module, "SentenceTransformerEmbedder", InterruptedEmbedder)
    root = tmp_path / "failed-evaluation"
    ledger = tmp_path / "state" / "ledger.json"
    monkeypatch.setattr(module, "_default_attempt_ledger_path", lambda: ledger)
    monkeypatch.setattr(module, "_FROZEN_RUNTIME_VERIFIED", True)

    with pytest.raises(KeyboardInterrupt):
        module._acquire_and_run(repo_root=REPO_ROOT, root=root)

    attempt = json.loads((root / module.ATTEMPT_FILE).read_text())
    assert attempt["status"] == "failed_or_indeterminate_terminal"
    assert (
        json.loads(ledger.read_text())["status"] == "failed_or_indeterminate_terminal"
    )
    with pytest.raises(module.EvaluationError, match="ledger is already consumed"):
        module._acquire_and_run(
            repo_root=REPO_ROOT, root=tmp_path / "alternate-evaluation"
        )
