# summary: "Tests non-authoritative architecture planning and materializability classification for program candidates."
# read_when:
#   - "Changing architecture candidate inference, capability previews, or declared-topology classification."

from __future__ import annotations


import pytest

from dspx.services.program_architecture import (
    build_program_architecture_candidates,
)
from dspx.services.program_intent import ProgramIntent


def test_architecture_planner_emits_non_authoritative_prompt_inferred_candidates() -> (
    None
):
    intent = ProgramIntent(
        name="ArchitectDogfoodProgram",
        objective=(
            "Route support tickets by classifying billing versus technical issues, "
            "then draft a helpful response with rationale."
        ),
        inputs=["ticket_text"],
        outputs=["response"],
    )

    plan = build_program_architecture_candidates(intent)

    assert plan["schema_version"] == "program-architecture-candidates-v1"
    assert plan["status"] == "planned_not_materialized"
    assert plan["recommended_candidate_id"] == "prompt_inferred_pipeline"
    assert plan["effect"] == {
        "candidate_materialized": False,
        "portfolio_materialized": False,
        "provider_called": False,
        "oracle_index_mutated": False,
        "ak_called": False,
        "governance_mutated": False,
        "external_authority_mutated": False,
    }
    assert plan["non_authority"]["planning_only"] is True
    assert plan["non_authority"]["winner_selection"] is False
    assert [candidate["candidate_id"] for candidate in plan["candidates"]] == [
        "baseline_single_predict",
        "prompt_inferred_pipeline",
    ]
    baseline, inferred = plan["candidates"]
    assert baseline["module_surface_preview"]["module_surface_count"] == 1
    assert baseline["module_surface_preview"]["module_surfaces"][0]["primitive"] == (
        "Predict"
    )
    assert inferred["module_surface_preview"]["module_surface_count"] == 2
    assert [
        surface["primitive"]
        for surface in inferred["module_surface_preview"]["module_surfaces"]
    ] == ["Predict", "ChainOfThought"]
    assert [
        surface["source_kind"]
        for surface in inferred["module_surface_preview"]["module_surfaces"]
    ] == ["generated_topology_module", "generated_topology_module"]
    assert plan["generation_assumptions_preview"]["schema_version"] == (
        "program-generation-assumptions-preview-v1"
    )


def test_architecture_planner_adds_preview_only_capability_advisories() -> None:
    intent = ProgramIntent(
        name="AgenticRetrievalProgram",
        objective=(
            "Use ReActV2 tools and retrieval over documents, with ProgramOfThought "
            "python computation and a custom imported helper, to answer the question."
        ),
        inputs=["question"],
        outputs=["answer"],
    )

    plan = build_program_architecture_candidates(intent)

    assert plan["recommended_candidate_id"] == "baseline_single_predict"
    by_id = {candidate["candidate_id"]: candidate for candidate in plan["candidates"]}
    assert {
        "preview_retrieve_then_answer_declared_only",
        "preview_reactv2_declared_only",
        "preview_programofthought_declared_only",
        "preview_custom_declared_only",
    }.issubset(by_id)
    for candidate_id in [
        "preview_retrieve_then_answer_declared_only",
        "preview_reactv2_declared_only",
        "preview_programofthought_declared_only",
        "preview_custom_declared_only",
    ]:
        candidate = by_id[candidate_id]
        assert candidate["status"] == "declared_only_not_materializable"
        assert candidate["topology_source"] == "generation_assumptions_preview"
        assert candidate["module_surface_preview"] is None
        assert candidate["effect"]["candidate_materialized"] is False
    assert (
        plan["generation_assumptions_preview"]["capability_boundaries"]["tools"][
            "enabled"
        ]
        is False
    )
    react_v2_boundary = plan["generation_assumptions_preview"]["capability_boundaries"][
        "react_v2"
    ]
    assert react_v2_boundary["status"] == (
        "experimental_no_tool_explicit_opt_in_boundary"
    )
    assert react_v2_boundary["tool_need_detected"] is True
    assert react_v2_boundary["tools_enabled"] is False
    assert react_v2_boundary["tool_binding_status"] == (
        "blocked_until_safe_tool_adapter_contract"
    )
    react_v2_contract = by_id["preview_reactv2_declared_only"]["topology_preview"][
        "required_explicit_contract"
    ]
    assert react_v2_contract["intent_patch"]["options"] == {
        "enable_react_v2_materialization": True,
        "react_v2_materialization": True,
    }
    module = react_v2_contract["intent_patch"]["topology"]["modules"][0]
    assert module["primitive"] == "ReActV2"
    assert module["tools"] == []
    assert module["tool_refs"] == []
    assert "public dspy.ReActV2" in react_v2_contract["production_readiness_missing"][0]
    assert plan["effect"]["candidate_materialized"] is False


def test_architecture_planner_preserves_bounded_inline_retriever_as_materializable_candidate() -> (
    None
):
    intent = ProgramIntent(
        name="InlineRetrieverDeclaredProgram",
        objective="Retrieve local context for a question from an inline corpus.",
        inputs=["question"],
        outputs=["context"],
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
                        "outputs": ["context"],
                    },
                    "retriever": {
                        "mode": "inline_corpus",
                        "k": 1,
                        "documents": [
                            {
                                "id": "refund_policy",
                                "text": "Refunds are available for duplicate billing within 30 days.",
                            }
                        ],
                    },
                }
            ],
            "edges": [
                {"from": "input", "to": "retrieve_context"},
                {"from": "retrieve_context", "to": "output"},
            ],
        },
    )

    plan = build_program_architecture_candidates(intent)

    assert plan["recommended_candidate_id"] == "declared_pipeline"
    declared = next(
        candidate
        for candidate in plan["candidates"]
        if candidate["candidate_id"] == "declared_pipeline"
    )
    assert declared["status"] == "materializable"
    module = declared["intent_payload"]["topology"]["modules"][0]
    assert module["primitive"] == "Retriever"
    assert module["retriever"] == {
        "mode": "inline_corpus",
        "k": 1,
        "documents": [
            {
                "id": "refund_policy",
                "text": "Refunds are available for duplicate billing within 30 days.",
            }
        ],
    }
    surface = declared["module_surface_preview"]["module_surfaces"][0]
    assert surface["primitive"] == "Retriever"
    assert surface["capability_ref"]["runtime_binding"] == (
        "generated_bounded_inline_retriever_adapter"
    )
    assert surface["capability_ref"]["materializable"] is True
    assert declared["effect"]["candidate_materialized"] is False
    assert declared["non_authority"]["winner_selection"] is False


def test_architecture_planner_preserves_retrieve_then_answer_as_materializable_candidate() -> (
    None
):
    intent = ProgramIntent(
        name="RetrieveThenAnswerDeclaredProgram",
        objective="Retrieve local context and answer a question.",
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
                        "outputs": ["context"],
                    },
                    "retriever": {
                        "mode": "inline_corpus",
                        "k": 1,
                        "documents": [{"id": "doc", "text": "Refund policy context."}],
                    },
                },
                {
                    "id": "answer_question",
                    "primitive": "ChainOfThought",
                    "signature": {
                        "name": "AnswerQuestion",
                        "inputs": ["question", "context"],
                        "outputs": ["answer"],
                    },
                },
            ],
            "edges": [
                {"from": "input", "to": "retrieve_context"},
                {"from": "retrieve_context", "to": "answer_question"},
                {"from": "answer_question", "to": "output"},
            ],
        },
    )

    plan = build_program_architecture_candidates(intent)

    assert plan["recommended_candidate_id"] == "declared_pipeline"
    declared = next(
        candidate
        for candidate in plan["candidates"]
        if candidate["candidate_id"] == "declared_pipeline"
    )
    assert declared["status"] == "materializable"
    assert declared["family"] == "retrieve_then_answer"
    assert declared["intent_payload"]["topology"]["kind"] == "retrieve_then_answer"
    assert [
        surface["primitive"]
        for surface in declared["module_surface_preview"]["module_surfaces"]
    ] == ["Retriever", "ChainOfThought"]


@pytest.mark.parametrize("kind", ["router"])
def test_architecture_planner_preserves_named_bounded_topologies_as_materializable(
    kind: str,
) -> None:
    intent = ProgramIntent(
        name="NamedTopologyDeclaredProgram",
        objective=f"Run the declared {kind} topology.",
        inputs=["text"],
        outputs=["answer"],
        topology={
            "kind": kind,
            "execution_status": "declared_not_materialized",
            "modules": [
                {
                    "id": "prepare",
                    "primitive": "Predict",
                    "signature": {
                        "name": "Prepare",
                        "inputs": ["text"],
                        "outputs": ["draft"],
                    },
                },
                {
                    "id": "answer",
                    "primitive": "ChainOfThought",
                    "signature": {
                        "name": "Answer",
                        "inputs": ["text", "draft"],
                        "outputs": ["answer"],
                    },
                },
            ],
            "edges": [
                {"from": "input", "to": "prepare"},
                {"from": "prepare", "to": "answer"},
                {"from": "answer", "to": "output"},
            ],
        },
    )

    plan = build_program_architecture_candidates(intent)

    declared = next(
        candidate
        for candidate in plan["candidates"]
        if candidate["candidate_id"] == "declared_pipeline"
    )
    assert declared["status"] == "materializable"
    assert declared["family"] == kind
    assert declared["intent_payload"]["topology"]["kind"] == kind
    assert declared["module_surface_preview"]["module_surface_count"] == 2


def test_architecture_planner_preserves_unsupported_declared_pipeline_as_declared_only() -> (
    None
):
    intent = ProgramIntent(
        name="UnsupportedDeclaredProgram",
        objective="Use an unsupported custom reasoning architecture.",
        inputs=["question"],
        outputs=["answer"],
        topology={
            "kind": "pipeline",
            "execution_status": "declared_not_materialized",
            "modules": [
                {
                    "id": "custom_answer",
                    "primitive": "Custom",
                    "signature": {
                        "name": "CustomAnswer",
                        "inputs": ["question"],
                        "outputs": ["answer"],
                    },
                }
            ],
            "edges": [
                {"from": "input", "to": "custom_answer"},
                {"from": "custom_answer", "to": "output"},
            ],
        },
    )

    plan = build_program_architecture_candidates(intent)

    assert plan["recommended_candidate_id"] == "baseline_single_predict"
    declared = next(
        candidate
        for candidate in plan["candidates"]
        if candidate["candidate_id"] == "declared_only_topology"
    )
    assert declared["status"] == "declared_only_not_materializable"
    assert declared["module_surface_preview"] is None
    assert any("unsupported primitives" in item for item in declared["limitations"])
    assert declared["effect"]["candidate_materialized"] is False
