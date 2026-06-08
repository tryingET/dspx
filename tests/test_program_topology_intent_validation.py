from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping, cast

import pytest

from dspx.services.program_intent import ProgramIntent
from dspx.services.program_service import materialize_program_from_intent
from program_topology_intent_helpers import (
    PIPELINE_TOPOLOGY,
)


def test_program_intent_rejects_stale_schema_version() -> None:
    with pytest.raises(ValueError, match="program-intent-v2"):
        ProgramIntent.model_validate(
            {"schema_version": "program-intent-v1", "objective": "x"}
        )

    with pytest.raises(ValueError, match="program-intent-v2"):
        ProgramIntent.model_validate(
            {"schema_version": "not-a-schema", "objective": "x"}
        )


def test_program_intent_rejects_unknown_top_level_fields() -> None:
    with pytest.raises(ValueError, match="extra_forbidden"):
        ProgramIntent.model_validate(
            {
                "schema_version": "program-intent-v2",
                "objective": "x",
                "inputs": ["question"],
                "outputs": ["answer"],
                "example_path": "./typoed-examples.jsonl",
            }
        )


def test_explicit_single_module_with_declared_module_requires_edges() -> None:
    with pytest.raises(ValueError, match="topology.edges must connect"):
        ProgramIntent(
            name="DisconnectedSingleModuleProgram",
            objective="Declare one module but omit its graph edges.",
            inputs=["question"],
            outputs=["answer"],
            topology={
                "kind": "single_module",
                "execution_status": "declared_not_materialized",
                "modules": [
                    {
                        "id": "answer_question",
                        "primitive": "Predict",
                        "signature": {
                            "name": "AnswerQuestion",
                            "inputs": ["question"],
                            "outputs": ["answer"],
                        },
                    }
                ],
                "edges": [],
            },
        )


@pytest.mark.parametrize(
    ("topology", "message"),
    [
        (
            {
                **PIPELINE_TOPOLOGY,
                "modules": [
                    PIPELINE_TOPOLOGY["modules"][0],
                    {**PIPELINE_TOPOLOGY["modules"][1], "id": "classify_ticket"},
                ],
            },
            "module ids must be unique",
        ),
        (
            {
                **PIPELINE_TOPOLOGY,
                "edges": [{"from": "classify_ticket", "to": "missing_module"}],
            },
            "edges must reference input, output, or declared module ids",
        ),
        (
            {
                **PIPELINE_TOPOLOGY,
                "modules": [
                    {
                        **PIPELINE_TOPOLOGY["modules"][0],
                        "signature": {
                            "name": "ClassifyTicket",
                            "inputs": ["ticket_text"],
                        },
                    }
                ],
                "edges": [{"from": "input", "to": "classify_ticket"}],
            },
            "signature.outputs must be a list",
        ),
        (
            {
                **PIPELINE_TOPOLOGY,
                "modules": [
                    {
                        **PIPELINE_TOPOLOGY["modules"][0],
                        "signature": {
                            "name": "ClassifyTicket",
                            "inputs": ["bad-field"],
                            "outputs": ["route"],
                        },
                    }
                ],
                "edges": [{"from": "input", "to": "classify_ticket"}],
            },
            "must be a valid Python identifier",
        ),
        (
            {
                **PIPELINE_TOPOLOGY,
                "edges": [
                    {"from": "input", "to": "classify_ticket"},
                    {
                        "from": "classify_ticket",
                        "to": "draft_response",
                        "when": "route == billing",
                    },
                ],
            },
            "when clauses must be objects",
        ),
    ],
)
def test_invalid_explicit_topology_fails_validation(
    topology: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        ProgramIntent(
            name="BrokenTopologyProgram",
            objective="Reject invalid topology.",
            inputs=["ticket_text"],
            outputs=["response"],
            topology=topology,
        )


def test_pipeline_topology_rejects_cyclic_module_graph(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    topology = {
        "kind": "pipeline",
        "execution_status": "declared_not_materialized",
        "modules": [
            {
                "id": "module_a",
                "primitive": "Predict",
                "signature": {"name": "ModuleA", "inputs": ["b"], "outputs": ["a"]},
            },
            {
                "id": "module_b",
                "primitive": "Predict",
                "signature": {"name": "ModuleB", "inputs": ["a"], "outputs": ["b"]},
            },
        ],
        "edges": [
            {"from": "input", "to": "module_a"},
            {"from": "module_a", "to": "module_b"},
            {"from": "module_b", "to": "module_a"},
            {"from": "module_a", "to": "output"},
        ],
    }

    with pytest.raises(ValueError, match="must be acyclic"):
        ProgramIntent(
            name="CyclicPipelineProgram",
            objective="Reject cyclic topology.",
            inputs=["question"],
            outputs=["a"],
            topology=topology,
        )
    assert not (tmp_path / "program" / "manifest.json").exists()


def test_pipeline_topology_rejects_missing_direct_data_dependency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    topology = {
        "kind": "pipeline",
        "execution_status": "declared_not_materialized",
        "modules": [
            {
                "id": "extract_facts",
                "primitive": "Predict",
                "signature": {
                    "name": "ExtractFacts",
                    "inputs": ["ticket_text"],
                    "outputs": ["facts"],
                },
            },
            {
                "id": "compose_answer",
                "primitive": "ChainOfThought",
                "signature": {
                    "name": "ComposeAnswer",
                    "inputs": ["facts"],
                    "outputs": ["answer"],
                },
            },
        ],
        "edges": [
            {"from": "input", "to": "extract_facts"},
            {"from": "input", "to": "compose_answer"},
            {"from": "compose_answer", "to": "output"},
        ],
    }
    with pytest.raises(ValueError, match="disconnected"):
        ProgramIntent(
            name="MissingDependencyPipelineProgram",
            objective="Reject missing direct dependency edge.",
            inputs=["ticket_text"],
            outputs=["answer"],
            topology=topology,
        )
    assert not (tmp_path / "program" / "manifest.json").exists()


def test_local_corpus_snapshot_retriever_requires_intent_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    intent = ProgramIntent(
        name="SnapshotRetrieverRequiresSourceProgram",
        objective="Reject source-less local corpus snapshots.",
        inputs=["question"],
        outputs=["passages"],
        topology={
            "kind": "pipeline",
            "execution_status": "declared_not_materialized",
            "modules": [
                {
                    "id": "retrieve_context",
                    "primitive": "Retriever",
                    "signature": {
                        "name": "RetrieveRequiresSource",
                        "inputs": ["question"],
                        "outputs": ["passages"],
                    },
                    "retriever": {
                        "mode": "local_corpus_snapshot",
                        "path": "corpus.jsonl",
                        "k": 1,
                    },
                }
            ],
            "edges": [
                {"from": "input", "to": "retrieve_context"},
                {"from": "retrieve_context", "to": "output"},
            ],
        },
    )

    with pytest.raises(ValueError, match="requires intent_source"):
        materialize_program_from_intent(intent, outdir=tmp_path / "program")
    assert not (tmp_path / "program" / "manifest.json").exists()


def test_local_corpus_snapshot_retriever_rejects_parent_traversal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    intent_dir = tmp_path / "intents"
    intent_dir.mkdir()
    intent_source = intent_dir / "intent.json"
    intent_source.write_text("{}\n", encoding="utf-8")
    (tmp_path / "corpus.jsonl").write_text(
        json.dumps({"id": "doc", "text": "text"}) + "\n",
        encoding="utf-8",
    )
    intent = ProgramIntent(
        name="SnapshotRetrieverTraversalProgram",
        objective="Reject path traversal for local corpus snapshots.",
        inputs=["question"],
        outputs=["passages"],
        topology={
            "kind": "pipeline",
            "execution_status": "declared_not_materialized",
            "modules": [
                {
                    "id": "retrieve_context",
                    "primitive": "Retriever",
                    "signature": {
                        "name": "RetrieveTraversal",
                        "inputs": ["question"],
                        "outputs": ["passages"],
                    },
                    "retriever": {
                        "mode": "local_corpus_snapshot",
                        "path": "../corpus.jsonl",
                        "k": 1,
                    },
                }
            ],
            "edges": [
                {"from": "input", "to": "retrieve_context"},
                {"from": "retrieve_context", "to": "output"},
            ],
        },
    )

    with pytest.raises(ValueError, match="must stay under the intent file directory"):
        materialize_program_from_intent(
            intent, outdir=tmp_path / "program", intent_source=intent_source
        )
    assert not (tmp_path / "program" / "manifest.json").exists()


def test_local_corpus_snapshot_retriever_rejects_oversized_source_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    corpus_path = tmp_path / "corpus.jsonl"
    corpus_path.write_text("x" * 1_000_001, encoding="utf-8")
    intent_source = tmp_path / "intent.json"
    intent_source.write_text("{}\n", encoding="utf-8")
    intent = ProgramIntent(
        name="SnapshotRetrieverOversizedProgram",
        objective="Reject oversized local corpus snapshots.",
        inputs=["question"],
        outputs=["passages"],
        topology={
            "kind": "pipeline",
            "execution_status": "declared_not_materialized",
            "modules": [
                {
                    "id": "retrieve_context",
                    "primitive": "Retriever",
                    "signature": {
                        "name": "RetrieveOversized",
                        "inputs": ["question"],
                        "outputs": ["passages"],
                    },
                    "retriever": {
                        "mode": "local_corpus_snapshot",
                        "path": "corpus.jsonl",
                        "k": 1,
                    },
                }
            ],
            "edges": [
                {"from": "input", "to": "retrieve_context"},
                {"from": "retrieve_context", "to": "output"},
            ],
        },
    )

    with pytest.raises(ValueError, match="source file exceeds byte limit"):
        materialize_program_from_intent(
            intent, outdir=tmp_path / "program", intent_source=intent_source
        )
    assert not (tmp_path / "program" / "manifest.json").exists()


def test_generate_critique_revise_named_topology_requires_semantic_stage_edges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    intent = ProgramIntent(
        name="BrokenGenerateCritiqueReviseProgram",
        objective="Draft, critique, and revise an answer.",
        inputs=["question"],
        outputs=["answer"],
        topology={
            "kind": "generate_critique_revise",
            "execution_status": "declared_not_materialized",
            "modules": [
                {
                    "id": "generate_draft",
                    "primitive": "ChainOfThought",
                    "role": "generate_draft",
                    "signature": {
                        "name": "GenerateDraftBroken",
                        "inputs": ["question"],
                        "outputs": ["draft"],
                    },
                },
                {
                    "id": "critique_draft",
                    "primitive": "ChainOfThought",
                    "role": "critique_draft",
                    "signature": {
                        "name": "CritiqueDraftBroken",
                        "inputs": ["question", "draft"],
                        "outputs": ["critique"],
                    },
                },
                {
                    "id": "revise_final",
                    "primitive": "ChainOfThought",
                    "role": "revise_final",
                    "signature": {
                        "name": "ReviseFinalBroken",
                        "inputs": ["question", "critique"],
                        "outputs": ["answer"],
                    },
                },
            ],
            "edges": [
                {"from": "input", "to": "generate_draft"},
                {"from": "generate_draft", "to": "critique_draft"},
                {"from": "critique_draft", "to": "revise_final"},
                {"from": "revise_final", "to": "output"},
            ],
        },
    )

    with pytest.raises(ValueError, match="generate_draft outputs to feed revise_final"):
        materialize_program_from_intent(intent, outdir=tmp_path / "program")


def test_extract_transform_validate_named_topology_requires_semantic_stage_roles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    intent = ProgramIntent(
        name="BrokenExtractTransformValidateProgram",
        objective="Extract, transform, and validate an answer.",
        inputs=["text"],
        outputs=["answer"],
        topology={
            "kind": "extract_transform_validate",
            "execution_status": "declared_not_materialized",
            "modules": [
                {
                    "id": "extract_evidence",
                    "primitive": "Predict",
                    "role": "extract",
                    "signature": {
                        "name": "ExtractEvidenceBroken",
                        "inputs": ["text"],
                        "outputs": ["evidence"],
                    },
                },
                {
                    "id": "validate_final",
                    "primitive": "ChainOfThought",
                    "role": "validate",
                    "signature": {
                        "name": "ValidateFinalBroken",
                        "inputs": ["text", "evidence"],
                        "outputs": ["answer"],
                    },
                },
            ],
            "edges": [
                {"from": "input", "to": "extract_evidence"},
                {"from": "extract_evidence", "to": "validate_final"},
                {"from": "validate_final", "to": "output"},
            ],
        },
    )

    with pytest.raises(ValueError, match=r"missing roles: \['transform'\]"):
        materialize_program_from_intent(intent, outdir=tmp_path / "program")


def test_retrieve_then_answer_fails_closed_when_retriever_does_not_feed_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    with pytest.raises(ValueError, match="disconnected"):
        ProgramIntent(
            name="DisconnectedRetrieveThenAnswerProgram",
            objective="Retrieve local inline passages, then answer.",
            inputs=["question"],
            outputs=["answer"],
            topology={
                "kind": "retrieve_then_answer",
                "execution_status": "declared_not_materialized",
                "modules": [
                    {
                        "id": "retrieve_context",
                        "primitive": "Retriever",
                        "signature": {
                            "name": "RetrieveContext",
                            "inputs": ["question"],
                            "outputs": ["passages"],
                        },
                        "retriever": {
                            "mode": "inline_corpus",
                            "k": 1,
                            "documents": [
                                {"id": "billing_doc", "text": "Billing invoices."}
                            ],
                        },
                    },
                    {
                        "id": "answer_question",
                        "primitive": "ChainOfThought",
                        "signature": {
                            "name": "AnswerQuestion",
                            "inputs": ["question"],
                            "outputs": ["answer"],
                        },
                    },
                ],
                "edges": [
                    {"from": "input", "to": "retrieve_context"},
                    {"from": "input", "to": "answer_question"},
                    {"from": "answer_question", "to": "output"},
                ],
            },
        )

    assert not (tmp_path / "program" / "intent_normalization.json").exists()


def test_pipeline_retriever_fails_closed_without_bounded_inline_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    with pytest.raises(ValueError, match="final-output producer"):
        ProgramIntent(
            name="InvalidRetrieverProgram",
            objective="Reject unbounded retriever modules.",
            inputs=["question"],
            outputs=["answer"],
            topology={
                "kind": "pipeline",
                "execution_status": "declared_not_materialized",
                "modules": [
                    {
                        "id": "retrieve_context",
                        "primitive": "Retriever",
                        "signature": {
                            "name": "RetrieveContext",
                            "inputs": ["question"],
                            "outputs": ["passages"],
                        },
                    }
                ],
                "edges": [{"from": "input", "to": "retrieve_context"}],
            },
        )
    assert not (tmp_path / "program" / "manifest.json").exists()


@pytest.mark.parametrize(
    "retriever",
    [
        {"mode": "remote", "k": 1, "documents": [{"id": "doc", "text": "text"}]},
        {
            "mode": "inline_corpus",
            "k": 99,
            "documents": [{"id": "doc", "text": "text"}],
        },
        {"mode": "inline_corpus", "k": 1, "documents": []},
        {
            "mode": "local_corpus_snapshot",
            "k": 99,
            "path": "corpus.jsonl",
        },
        {
            "mode": "local_corpus_snapshot",
            "k": 1,
        },
        {
            "mode": "inline_corpus",
            "k": 1,
            "documents": [{"id": "doc", "text": "text", "path": "secret.md"}],
        },
    ],
)
def test_pipeline_retriever_contract_validation_rejects_unsafe_shapes(
    retriever: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        ProgramIntent(
            name="InvalidRetrieverContractProgram",
            objective="Reject unsafe retriever contracts.",
            inputs=["question"],
            outputs=["answer"],
            topology={
                "kind": "pipeline",
                "execution_status": "declared_not_materialized",
                "modules": [
                    {
                        "id": "retrieve_context",
                        "primitive": "Retriever",
                        "signature": {
                            "name": "RetrieveContext",
                            "inputs": ["question"],
                            "outputs": ["passages"],
                        },
                        "retriever": retriever,
                    }
                ],
                "edges": [{"from": "input", "to": "retrieve_context"}],
            },
        )


@pytest.mark.parametrize(
    "extra_key",
    ["provider", "endpoint", "tool", "import"],
)
def test_pipeline_retriever_rejects_external_module_level_keys(extra_key: str) -> None:
    with pytest.raises(ValueError, match="unsupported keys"):
        ProgramIntent(
            name="ExternalRetrieverRejectedProgram",
            objective="Reject external retriever hints on materialized retriever module.",
            inputs=["question"],
            outputs=["answer"],
            topology={
                "kind": "pipeline",
                "execution_status": "declared_not_materialized",
                "modules": [
                    {
                        "id": "retrieve_context",
                        "primitive": "Retriever",
                        "signature": {
                            "name": "RetrieveContext",
                            "inputs": ["question"],
                            "outputs": ["passages"],
                        },
                        "retriever": {
                            "mode": "inline_corpus",
                            "k": 1,
                            "documents": [{"id": "doc", "text": "text"}],
                        },
                        extra_key: "external",
                    }
                ],
                "edges": [{"from": "input", "to": "retrieve_context"}],
            },
        )


@pytest.mark.parametrize(
    ("module_patch", "match"),
    [
        ({"primitive": "ReAct", "tools": ["external_search"]}, "empty tools list"),
        ({"primitive": "ReAct", "max_iters": 99}, "max_iters"),
        ({"primitive": "ProgramOfThought", "max_iters": 99}, "max_iters"),
        ({"primitive": "ProgramOfThought", "tools": []}, "unsupported keys"),
    ],
)
def test_bounded_reasoning_primitives_reject_unsafe_shapes(
    module_patch: dict[str, object], match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        ProgramIntent(
            name="UnsafeReasoningPrimitiveProgram",
            objective="Reject unsafe reasoning primitive config.",
            inputs=["question"],
            outputs=["answer"],
            topology={
                "kind": "pipeline",
                "execution_status": "declared_not_materialized",
                "modules": [
                    {
                        "id": "reason_answer",
                        "signature": {
                            "name": "ReasonAnswer",
                            "inputs": ["question"],
                            "outputs": ["answer"],
                        },
                        **module_patch,
                    }
                ],
                "edges": [
                    {"from": "input", "to": "reason_answer"},
                    {"from": "reason_answer", "to": "output"},
                ],
            },
        )


def test_unsupported_pipeline_primitive_fails_when_materializing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    intent = ProgramIntent(
        name="UnsupportedPipelineProgram",
        objective="Reject unsupported executable topology primitives.",
        inputs=["ticket_text"],
        outputs=["answer"],
        topology={
            **PIPELINE_TOPOLOGY,
            "modules": [
                PIPELINE_TOPOLOGY["modules"][0],
                {
                    **cast(Mapping[str, object], PIPELINE_TOPOLOGY["modules"][1]),
                    "primitive": "Custom",
                },
            ],
        },
    )

    with pytest.raises(ValueError, match="supports only module primitives"):
        materialize_program_from_intent(intent, outdir=tmp_path / "program")
    assert not (tmp_path / "program" / "manifest.json").exists()
