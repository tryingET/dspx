# summary: "Adversarial tests for the frozen mDenseOn versus MiniLM Oracle selection."
# read_when:
#   - "Changing the v2 dense-model selection contract, scorer, runner, or claim boundary."

from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

import dspx.coordinates.oracle_embedding_selection as selection_module

from dspx.coordinates.embedding_identity import EmbeddingIdentityError

from dspx.coordinates.mdenseon import (
    MDENSEON_ADAPTER,
    MDENSEON_DIMENSION,
    MDENSEON_DOCUMENT_PROMPT,
    MDENSEON_MAX_TOKENS,
    MDENSEON_QUERY_PROMPT,
    MDENSEON_REPOSITORY_ID,
    MDENSEON_REVISION,
    MDenseOnError,
    modernbert_model_inputs,
    validate_serialized_mdenseon_semantics,
)
from dspx.coordinates.oracle_embedding_selection import (
    BASELINE_DB_FILE,
    CHALLENGER_DB_FILE,
    EXPECTED_CONTRACT_SHA256,
    EXPECTED_QUERY_IDS,
    EXPECTED_RECORD_IDS,
    SelectionError,
    challenger_identity_spec,
    materialize_record_text,
    score_model,
    select_model,
    validate_contract_payload,
    verify_retained_selection,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = REPO_ROOT / "benchmarks/semantic/oracle-embedding-selection-v2.json"
RECOVERY_CONTRACT_PATH = (
    REPO_ROOT / "benchmarks/semantic/oracle-embedding-selection-recovery-v1.json"
)
RUNNER_PATH = REPO_ROOT / "scripts/ci/run_oracle_embedding_selection.py"
V1_CONTRACT_PATH = REPO_ROOT / "benchmarks/semantic/oracle-embedding-evaluation-v1.json"
V1_VERIFIER_PATH = (
    REPO_ROOT
    / "packages/dspx-core/src/dspx/coordinates/oracle_embedding_verification.py"
)


def _contract() -> dict[str, Any]:
    payload = json.loads(CONTRACT_PATH.read_bytes())
    assert isinstance(payload, dict)
    return payload


def _load_runner() -> Any:
    spec = importlib.util.spec_from_file_location(
        "oracle_embedding_selection_runner", RUNNER_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _basis_vectors(
    contract: dict[str, Any], *, dimension: int | None = None
) -> tuple[list[list[float]], list[list[float]]]:
    records = contract["evaluation"]["records"]
    queries = contract["evaluation"]["queries"]
    resolved_dimension = len(records) if dimension is None else dimension
    documents = [
        [1.0 if row == column else 0.0 for column in range(resolved_dimension)]
        for row in range(len(records))
    ]
    record_positions = {row["case_id"]: index for index, row in enumerate(records)}
    query_vectors = [
        documents[record_positions[row["expected_case_id"]]] for row in queries
    ]
    return documents, query_vectors


def _identity(dimension: int, *, challenger: bool) -> dict[str, Any]:
    return {
        "schema_version": (
            "dspx-mdenseon-identity-v1"
            if challenger
            else "dspx-sentence-transformer-identity-v1"
        ),
        "identity_complete": True,
        "encoding": {"dimension": dimension},
    }


def _complete_identity(*, challenger: bool) -> dict[str, Any]:
    dimension = 768 if challenger else 384
    identity: dict[str, Any] = {
        "schema_version": (
            "dspx-mdenseon-identity-v1"
            if challenger
            else "dspx-sentence-transformer-identity-v1"
        ),
        "backend": "transformers-dense" if challenger else "sentence-transformers",
        "repository_id": (
            "lightonai/mDenseOn"
            if challenger
            else "sentence-transformers/all-MiniLM-L6-v2"
        ),
        "revision": MDENSEON_REVISION
        if challenger
        else "c9745ed1d9f207416be6d2e6f8de32d1f16199bf",
        "identity_complete": True,
        "production_semantic_claim_allowed": False,
        "artifacts": [
            {"sha256": f"{index:064x}"} for index in range(1, 9 if challenger else 11)
        ],
        "runtime": {"isolated_frozen": True},
        "encoding": {
            "dimension": dimension,
            "vector_dtype": "float32",
            "normalize_embeddings": True,
        },
    }
    if challenger:
        identity["adapter"] = {
            "name": "dspx-mdenseon-cls-v1",
            "pooling": "last_hidden_state_cls_token",
            "document_prompt": "document: ",
            "query_prompt": "query: ",
            "serialized_semantics_verified": True,
        }
    return identity


def _scored_pair(tmp_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    contract = _contract()
    documents, queries = _basis_vectors(contract)
    baseline = score_model(
        contract=contract,
        model_label="sentence-transformers/all-MiniLM-L6-v2",
        identity=_identity(len(documents), challenger=False),
        document_vectors=documents,
        query_vectors=queries,
        database_path=tmp_path / "baseline.sqlite3",
        embedding_version=1,
    )
    challenger = score_model(
        contract=contract,
        model_label="lightonai/mDenseOn",
        identity=_identity(len(documents), challenger=True),
        document_vectors=documents,
        query_vectors=queries,
        database_path=tmp_path / "challenger.sqlite3",
        embedding_version=2,
    )
    return baseline, challenger


def test_contract_bytes_and_structure_are_frozen() -> None:
    raw = CONTRACT_PATH.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == EXPECTED_CONTRACT_SHA256
    contract = _contract()
    validate_contract_payload(contract)
    assert (
        tuple(row["case_id"] for row in contract["evaluation"]["records"])
        == EXPECTED_RECORD_IDS
    )
    assert (
        tuple(row["id"] for row in contract["evaluation"]["queries"])
        == EXPECTED_QUERY_IDS
    )


def test_selection_does_not_rewrite_v1_evidence_contract_or_verifier() -> None:
    assert hashlib.sha256(V1_CONTRACT_PATH.read_bytes()).hexdigest() == (
        "819204905f94449013fb25a5f6e21157db36210cbaa4b6e6e8811bb67ca3e92e"
    )
    assert "_LEGACY_RESULT_SHA256" in V1_VERIFIER_PATH.read_text()


def test_long_context_label_is_after_minilm_window() -> None:
    record = _contract()["evaluation"]["records"][-1]
    text = materialize_record_text(record)
    assert len(text.split()) > 256
    assert text.endswith("Receipt integrity alone is not runtime reproduction.")


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("status",), "passed"),
        (("candidates", "challenger", "repository_id"), "lightonai/mLateOn"),
        (("candidates", "challenger", "query_prompt"), ""),
        (("candidates", "challenger", "document_prompt"), "query: "),
        (("candidates", "challenger", "trust_remote_code"), True),
        (("candidates", "challenger", "expected_dimension"), 128),
        (("attempt_budget", "selective_query_reruns_allowed"), True),
        (("effects", "semantic_analysis_lm_calls"), 1),
        (("claim_boundary", "statistical_representativeness"), True),
    ],
)
def test_contract_mutations_fail_closed(path: tuple[str, ...], value: object) -> None:
    contract = copy.deepcopy(_contract())
    cursor: dict[str, Any] = contract
    for key in path[:-1]:
        cursor = cursor[key]
    cursor[path[-1]] = value
    with pytest.raises(SelectionError):
        validate_contract_payload(contract)


def test_boolean_effect_does_not_pass_as_zero() -> None:
    contract = copy.deepcopy(_contract())
    contract["effects"]["shared_store_connections"] = False
    with pytest.raises(SelectionError, match="effect"):
        validate_contract_payload(contract)


def test_materialization_rejects_weak_or_ambiguous_recipe() -> None:
    with pytest.raises(SelectionError):
        materialize_record_text({"text": "literal", "text_recipe": {}})
    with pytest.raises(SelectionError):
        materialize_record_text(
            {"text_recipe": {"prefix": "x ", "repeat": 89, "tail": "tail"}}
        )


def test_challenger_spec_binds_exact_artifacts_runtime_and_prompts() -> None:
    contract = _contract()
    spec = challenger_identity_spec(contract)
    assert spec.repository_id == MDENSEON_REPOSITORY_ID
    assert spec.revision == MDENSEON_REVISION
    assert spec.expected_dimension == MDENSEON_DIMENSION
    assert spec.artifact_paths == tuple(sorted(spec.artifact_paths))
    assert len(spec.artifact_paths) == 8
    assert dict(spec.runtime_versions)["transformers"] == "4.57.6"
    assert contract["candidates"]["challenger"]["adapter"] == MDENSEON_ADAPTER
    assert (
        contract["candidates"]["challenger"]["document_prompt"]
        == MDENSEON_DOCUMENT_PROMPT
    )
    assert contract["candidates"]["challenger"]["query_prompt"] == MDENSEON_QUERY_PROMPT
    assert contract["candidates"]["challenger"]["maximum_tokens"] == MDENSEON_MAX_TOKENS


def test_perfect_vectors_score_all_declared_subsets(tmp_path: Path) -> None:
    baseline, challenger = _scored_pair(tmp_path)
    for result in (baseline, challenger):
        assert result["metrics"] == {
            "labeled_query_count": 15,
            "recall_at_1": 1.0,
            "mean_reciprocal_rank": 1.0,
            "normalized_discounted_cumulative_gain_at_5": 1.0,
        }
        assert result["subset_metrics"]["cross_lingual"]["recall_at_1"] == 1.0
        assert result["subset_metrics"]["critical"]["recall_at_1"] == 1.0
        assert result["subset_metrics"]["long_context"]["recall_at_1"] == 1.0
        assert result["falsifiers_observed"] == []


def test_tied_top_rank_is_a_falsifier(tmp_path: Path) -> None:
    contract = _contract()
    documents, queries = _basis_vectors(contract)
    documents[1] = documents[0]
    result = score_model(
        contract=contract,
        model_label="challenger",
        identity=_identity(len(documents), challenger=True),
        document_vectors=documents,
        query_vectors=queries,
        database_path=tmp_path / "ties.sqlite3",
        embedding_version=2,
    )
    assert any(
        item.startswith("top_rank_tied:") for item in result["falsifiers_observed"]
    )


def test_selection_requires_material_capability_improvement(tmp_path: Path) -> None:
    baseline, challenger = _scored_pair(tmp_path)
    result = select_model(
        contract=_contract(),
        baseline=baseline,
        challenger=challenger,
        resources={
            "retained_model_bytes": 1_227_771_776,
            "peak_rss_bytes": 4_000_000_000,
            "model_load_seconds": 30.0,
            "total_encode_seconds": 40.0,
        },
    )
    assert result["selected_model"] == "sentence-transformers/all-MiniLM-L6-v2"
    assert result["gates"]["comparative_capability"] is False


def test_selection_accepts_nonregressing_challenger_with_crosslingual_gain(
    tmp_path: Path,
) -> None:
    baseline, challenger = _scored_pair(tmp_path)
    baseline = copy.deepcopy(baseline)
    baseline["metrics"]["recall_at_1"] = 0.8
    baseline["metrics"]["mean_reciprocal_rank"] = 0.85
    baseline["subset_metrics"]["cross_lingual"]["recall_at_1"] = 0.4
    baseline["subset_metrics"]["long_context"]["recall_at_1"] = 0.0
    result = select_model(
        contract=_contract(),
        baseline=baseline,
        challenger=challenger,
        resources={
            "retained_model_bytes": 1_227_771_776,
            "peak_rss_bytes": 4_000_000_000,
            "model_load_seconds": 30.0,
            "total_encode_seconds": 40.0,
        },
    )
    assert result["status"] == "passed"
    assert result["selected_model"] == "lightonai/mDenseOn"
    assert all(result["gates"].values())
    assert result["embedding_version"] == 2
    assert result["claims"]["broad_production_semantic_quality"] is False


@pytest.mark.parametrize(
    ("resource", "value"),
    [
        ("retained_model_bytes", 1_300_000_001),
        ("peak_rss_bytes", 8_589_934_593),
        ("model_load_seconds", 300.1),
        ("total_encode_seconds", 600.1),
    ],
)
def test_each_resource_limit_fails_closed(
    tmp_path: Path, resource: str, value: float | int
) -> None:
    baseline, challenger = _scored_pair(tmp_path)
    baseline = copy.deepcopy(baseline)
    baseline["metrics"]["recall_at_1"] = 0.7
    baseline["metrics"]["mean_reciprocal_rank"] = 0.8
    baseline["subset_metrics"]["cross_lingual"]["recall_at_1"] = 0.2
    baseline["subset_metrics"]["long_context"]["recall_at_1"] = 0.0
    resources: dict[str, float | int] = {
        "retained_model_bytes": 1_227_771_776,
        "peak_rss_bytes": 4_000_000_000,
        "model_load_seconds": 30.0,
        "total_encode_seconds": 40.0,
    }
    resources[resource] = value
    result = select_model(
        contract=_contract(),
        baseline=baseline,
        challenger=challenger,
        resources=resources,
    )
    assert result["selected_model"] == "sentence-transformers/all-MiniLM-L6-v2"
    assert result["gates"]["bounded_cpu_resources"] is False


def test_runner_loads_only_exact_contract_and_source_bindings() -> None:
    runner = _load_runner()
    contract, observed = runner.load_contract(REPO_ROOT)
    assert observed == EXPECTED_CONTRACT_SHA256
    validate_contract_payload(contract)


def test_source_preflight_covers_every_imported_coordinate_module() -> None:
    runner = _load_runner()
    assert "packages/dspx-core/src/dspx" in runner._SOURCE_STATUS_PATHS
    assert {
        "packages/dspx-core/src/dspx/coordinates/embeddings.py",
        "packages/dspx-core/src/dspx/coordinates/metrics.py",
        "packages/dspx-core/src/dspx/coordinates/oracle_embedding_evaluation.py",
        "packages/dspx-core/src/dspx/coordinates/storage.py",
        "packages/dspx-core/src/dspx/run_receipts.py",
    }.issubset(set(runner._REQUIRED_TRACKED_SOURCE_FILES))


def test_runner_attempt_ledger_is_atomic_and_single_use(tmp_path: Path) -> None:
    runner = _load_runner()
    ledger = tmp_path / "ledger.json"
    root = tmp_path / "evidence"
    source_commit = "a" * 40
    runner._claim_attempt(root, ledger, source_commit=source_commit)
    with pytest.raises(SelectionError, match="already consumed"):
        runner._claim_attempt(root, ledger, source_commit=source_commit)
    payload = json.loads(ledger.read_bytes())
    assert payload["attempt_budget_consumed"] == 1
    assert payload["another_root_allowed"] is False

    assert payload["ak_task_id"] == 4510
    assert payload["source_commit"] == source_commit


def test_forged_handoff_cannot_replace_runtime_verification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _load_runner()
    monkeypatch.setattr(runner, "_FROZEN_RUNTIME_REEXECUTED", True)
    with pytest.raises(SelectionError, match="runtime verification"):
        runner._verify_frozen_runtime(_contract(), REPO_ROOT)


def test_select_model_rejects_mutated_unvalidated_contract(tmp_path: Path) -> None:
    baseline, challenger = _scored_pair(tmp_path)
    mutated = copy.deepcopy(_contract())
    mutated["evaluation"]["queries"] = []
    with pytest.raises(SelectionError, match="query order"):
        select_model(
            contract=mutated,
            baseline=baseline,
            challenger=challenger,
            resources={},
        )


def test_serialized_adapter_semantics_are_parsed_not_only_hashed(
    tmp_path: Path,
) -> None:
    root = tmp_path / "model"
    (root / "1_Pooling").mkdir(parents=True)
    payloads = {
        "modules.json": [
            {
                "idx": 0,
                "name": "0",
                "path": "",
                "type": "sentence_transformers.base.modules.transformer.Transformer",
            },
            {
                "idx": 1,
                "name": "1",
                "path": "1_Pooling",
                "type": "sentence_transformers.sentence_transformer.modules.pooling.Pooling",
            },
        ],
        "1_Pooling/config.json": {
            "embedding_dimension": 768,
            "pooling_mode": "cls",
            "include_prompt": True,
        },
        "config_sentence_transformers.json": {
            "__version__": {},
            "default_prompt_name": None,
            "model_type": "SentenceTransformer",
            "prompts": {"document": "document: ", "query": "query: "},
            "similarity_fn_name": "cosine",
        },
        "sentence_bert_config.json": {
            "transformer_task": "feature-extraction",
            "modality_config": {
                "text": {
                    "method": "forward",
                    "method_output_name": "last_hidden_state",
                }
            },
            "module_output_name": "token_embeddings",
        },
    }
    for relative, payload in payloads.items():
        path = root / relative
        path.write_text(json.dumps(payload))
    validate_serialized_mdenseon_semantics(root)
    payloads["1_Pooling/config.json"]["pooling_mode"] = "mean"
    (root / "1_Pooling/config.json").write_text(
        json.dumps(payloads["1_Pooling/config.json"])
    )
    with pytest.raises(MDenseOnError, match="pooling"):
        validate_serialized_mdenseon_semantics(root)


def test_independent_verifier_rederives_metrics_and_rejects_non_sqlite(
    tmp_path: Path,
) -> None:
    contract = _contract()
    baseline_documents, baseline_perfect_queries = _basis_vectors(
        contract, dimension=384
    )
    challenger_documents, challenger_queries = _basis_vectors(contract, dimension=768)
    record_positions = {
        row["case_id"]: index
        for index, row in enumerate(contract["evaluation"]["records"])
    }
    baseline_queries: list[list[float]] = []
    for query, perfect in zip(
        contract["evaluation"]["queries"], baseline_perfect_queries, strict=True
    ):
        if query["subset"].startswith(("cross_lingual", "long_context")):
            wrong = (record_positions[query["expected_case_id"]] + 1) % len(
                baseline_documents
            )
            baseline_queries.append(baseline_documents[wrong])
        else:
            baseline_queries.append(perfect)
    baseline = score_model(
        contract=contract,
        model_label="sentence-transformers/all-MiniLM-L6-v2",
        identity=_complete_identity(challenger=False),
        document_vectors=baseline_documents,
        query_vectors=baseline_queries,
        database_path=tmp_path / BASELINE_DB_FILE,
        embedding_version=1,
    )
    challenger = score_model(
        contract=contract,
        model_label="lightonai/mDenseOn",
        identity=_complete_identity(challenger=True),
        document_vectors=challenger_documents,
        query_vectors=challenger_queries,
        database_path=tmp_path / CHALLENGER_DB_FILE,
        embedding_version=2,
    )
    result = select_model(
        contract=contract,
        baseline=baseline,
        challenger=challenger,
        resources={
            "retained_model_bytes": 1_227_771_776,
            "peak_rss_bytes": 4_000_000_000,
            "model_load_seconds": 30.0,
            "total_encode_seconds": 40.0,
        },
    )
    assert result["status"] == "passed"
    result["full_batch_reproduction"] = {
        "verified": True,
        "vector_hashes": {
            "documents": [row["vector_sha256"] for row in challenger["records"]],
            "queries": [row["vector_sha256"] for row in challenger["queries"]],
        },
    }
    (tmp_path / "selection-result.json").write_text(json.dumps(result, sort_keys=True))
    _, baseline_vectors = selection_module._verify_database(
        tmp_path / BASELINE_DB_FILE,
        embedding_version=1,
        dimension=384,
        result_records=baseline["records"],
    )
    _, challenger_vectors = selection_module._verify_database(
        tmp_path / CHALLENGER_DB_FILE,
        embedding_version=2,
        dimension=768,
        result_records=challenger["records"],
    )
    selection_module._verify_scored_result(
        baseline, contract=contract, document_vectors=baseline_vectors
    )
    selection_module._verify_scored_result(
        challenger, contract=contract, document_vectors=challenger_vectors
    )
    result_path = tmp_path / "selection-result.json"
    tampered = json.loads(result_path.read_bytes())
    ranking = tampered["challenger"]["queries"][0]["ranking"]
    ranking[0], ranking[1] = ranking[1], ranking[0]
    result_path.write_text(json.dumps(tampered, sort_keys=True))
    with pytest.raises(SelectionError, match="derive from SQLite"):
        selection_module._verify_scored_result(
            tampered["challenger"],
            contract=contract,
            document_vectors=challenger_vectors,
        )
    result_path.write_text(json.dumps(result, sort_keys=True))
    with pytest.raises(EmbeddingIdentityError):
        verify_retained_selection(
            root=tmp_path,
            contract=contract,
            baseline_spec=challenger_identity_spec(contract),
            baseline_model_root=tmp_path / "missing-baseline-model",
            challenger_model_root=tmp_path / "missing-challenger-model",
        )
    (tmp_path / BASELINE_DB_FILE).write_text("not sqlite")
    with pytest.raises(SelectionError, match="database"):
        selection_module._verify_database(
            tmp_path / BASELINE_DB_FILE,
            embedding_version=1,
            dimension=384,
            result_records=baseline["records"],
        )


def test_runner_ast_enforces_one_exact_snapshot_download() -> None:
    tree = ast.parse(RUNNER_PATH.read_text())
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "snapshot_download"
    ]
    assert len(calls) == 1
    keywords = {keyword.arg: keyword.value for keyword in calls[0].keywords}
    assert ast.literal_eval(keywords["token"]) is False
    assert ast.literal_eval(keywords["max_workers"]) == 1
    assert "allow_patterns" in keywords
    assert "revision" in keywords


def test_runner_has_no_semantic_lm_or_shared_store_imports() -> None:
    source = RUNNER_PATH.read_text()
    assert "program_oracle_semantic_backend" not in source
    assert "PostgresPgvectorCoordinateStore" not in source
    assert "psycopg" not in source


def test_modernbert_input_filter_removes_only_token_type_ids() -> None:
    input_ids = object()
    attention_mask = object()
    token_type_ids = object()
    original = {
        "input_ids": input_ids,
        "attention_mask": attention_mask,
        "token_type_ids": token_type_ids,
    }
    resolved = modernbert_model_inputs(original)
    assert resolved == {
        "input_ids": input_ids,
        "attention_mask": attention_mask,
    }
    assert original["token_type_ids"] is token_type_ids


def test_recovery_contract_binds_failed_history_and_retained_model() -> None:
    runner = _load_runner()
    recovery, observed = runner.load_recovery_contract(REPO_ROOT)
    assert observed == runner.EXPECTED_RECOVERY_CONTRACT_SHA256
    assert runner._sha256_file(RECOVERY_CONTRACT_PATH) == observed
    preserved = recovery["preserved_terminal_attempt"]
    retained = recovery["retained_challenger"]
    assert (
        runner._sha256_file(Path(preserved["attempt_status_path"]))
        == preserved["attempt_status_sha256"]
    )
    assert (
        runner._sha256_file(Path(preserved["ledger_path"]))
        == preserved["ledger_sha256"]
    )
    assert (
        runner._sha256_file(Path(retained["root"]) / "model.safetensors")
        == retained["model_safetensors_sha256"]
    )
    assert retained["network_reacquisition_allowed"] is False


def test_recovery_attempt_ledger_is_task_fixed_and_single_use(tmp_path: Path) -> None:
    runner = _load_runner()
    ledger = tmp_path / "recovery-ledger.json"
    root = tmp_path / "recovery"
    source_commit = "b" * 40
    runner._claim_recovery(root, ledger, source_commit=source_commit)
    with pytest.raises(SelectionError, match="already consumed"):
        runner._claim_recovery(root, ledger, source_commit=source_commit)
    payload = json.loads(ledger.read_bytes())
    assert payload["ak_task_id"] == 4517
    assert (
        payload["recovery_contract_sha256"] == runner.EXPECTED_RECOVERY_CONTRACT_SHA256
    )
    assert payload["another_root_allowed"] is False


def test_recovery_path_has_no_acquisition_call_and_forces_offline_mode() -> None:
    tree = ast.parse(RUNNER_PATH.read_text())
    recovery = next(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "_recover_and_run"
    )
    assert not any(
        isinstance(node, ast.Name) and node.id == "snapshot_download"
        for node in ast.walk(recovery)
    )
    source = ast.get_source_segment(RUNNER_PATH.read_text(), recovery)
    assert source is not None
    assert 'os.environ["HF_HUB_OFFLINE"] = "1"' in source
    assert 'os.environ["TRANSFORMERS_OFFLINE"] = "1"' in source
    runner_source = RUNNER_PATH.read_text()
    assert 'command.append("--offline")' in runner_source
    assert '"UV_OFFLINE": "1"' in runner_source
    assert "preserved_root in root.resolve().parents" in source
    assert "challenger_model_root.resolve() in root.resolve().parents" in source
    assert "recovered_adapter=True" in source
