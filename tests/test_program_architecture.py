from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dspx.cache import sha256_text
from dspx.cli.dspx import app
from dspx.services.program_architecture import (
    ProgramArchitectureError,
    build_program_architecture_candidates,
    verify_architecture_contract_intent,
    write_architecture_contract_drafts,
    write_architecture_intent_portfolio,
)
from dspx.services.program_architecture_tournament import (
    run_program_architecture_tournament,
)
from dspx.services.program_intent import ProgramIntent
from dspx.services.program_service import materialize_program_from_intent
from dspx.services.run_replay_service import check_run_receipt

runner = CliRunner()


def _recommendation_tournament_non_authority() -> dict[str, bool]:
    return {
        "winner_selection": False,
        "ranking_authority": False,
        "promotion_authority": False,
        "activation_authority": False,
        "oracle_authority": False,
        "governance_authority": False,
        "external_mutation": False,
        "canonical_mutation": False,
    }


def _write_intent(path: Path, objective: str, *, examples: bool = False) -> None:
    lines = [
        "schema_version: program-intent-v2",
        "name: ArchitectDogfoodProgram",
        f"objective: {objective}",
        "inputs:",
        "  - ticket_text",
        "outputs:",
        "  - response",
        "metric: exact_match",
    ]
    if examples:
        lines.extend(
            [
                "examples:",
                "  - inputs:",
                "      ticket_text: I was charged twice for my subscription.",
                "    outputs:",
                "      response: This is a billing issue.",
            ]
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


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


def test_architecture_contract_verification_accepts_bounded_retrieve_then_answer_draft(
    tmp_path: Path,
) -> None:
    payload = build_program_architecture_candidates(
        ProgramIntent(
            name="RetrieveThenAnswerVerifyProgram",
            objective="Retrieve from documents, then answer the question.",
            inputs=["question"],
            outputs=["answer"],
            capabilities={
                "declarations": [
                    {
                        "id": "policy_docs",
                        "kind": "retriever",
                        "retriever": {
                            "mode": "inline_corpus",
                            "k": 1,
                            "documents": [
                                {"id": "policy", "text": "Policy text for answers."}
                            ],
                        },
                    }
                ]
            },
        )
    )
    index = write_architecture_contract_drafts(payload, tmp_path / "contracts")
    record = next(
        item
        for item in index["contract_drafts"]
        if item["candidate_id"] == "preview_retrieve_then_answer_declared_only"
    )

    verification = verify_architecture_contract_intent(Path(record["intent_path"]))

    assert verification["status"] == "verified_contract_intent"
    assert verification["materialization_allowed_by_contract_verification"] is True
    assert verification["external_retriever_allowed"] is False
    assert verification["materialization_gate"]["allows_external_retrievers"] is False
    assert [module["primitive"] for module in verification["safe_modules"]] == [
        "Retriever",
        "ChainOfThought",
    ]


def test_architecture_contract_drafts_write_materializable_retrieve_then_answer_from_bounded_retriever(
    tmp_path: Path,
) -> None:
    payload = build_program_architecture_candidates(
        ProgramIntent(
            name="RetrieveThenAnswerDraftProgram",
            objective="Retrieve from documents, then answer the question.",
            inputs=["question"],
            outputs=["answer"],
            capabilities={
                "declarations": [
                    {
                        "id": "policy_docs",
                        "kind": "retriever",
                        "retriever": {
                            "mode": "inline_corpus",
                            "k": 1,
                            "documents": [
                                {"id": "policy", "text": "Policy text for answers."}
                            ],
                        },
                    }
                ]
            },
        )
    )

    index = write_architecture_contract_drafts(payload, tmp_path / "contracts")

    record = next(
        item
        for item in index["contract_drafts"]
        if item["candidate_id"] == "preview_retrieve_then_answer_declared_only"
    )
    draft = json.loads(Path(record["intent_path"]).read_text(encoding="utf-8"))
    loaded = ProgramIntent.model_validate(draft)
    assert loaded.topology["kind"] == "retrieve_then_answer"
    modules = loaded.topology["modules"]
    assert [module["primitive"] for module in modules] == [
        "Retriever",
        "ChainOfThought",
    ]
    assert modules[0]["retriever"]["mode"] == "inline_corpus"
    assert modules[0]["retriever"]["documents"] == [
        {"id": "policy", "text": "Policy text for answers."}
    ]
    plan = build_program_architecture_candidates(loaded)
    declared = next(
        item
        for item in plan["candidates"]
        if item["candidate_id"] == "declared_pipeline"
    )
    assert declared["status"] == "materializable"
    assert declared["family"] == "retrieve_then_answer"


def test_architecture_contract_drafts_write_materializable_generate_critique_revise_intent(
    tmp_path: Path,
) -> None:
    payload = build_program_architecture_candidates(
        ProgramIntent(
            name="DraftCritiqueReviseProgram",
            objective="Draft an answer, critique it, review issues, and revise the final response.",
            inputs=["question"],
            outputs=["answer"],
        )
    )

    index = write_architecture_contract_drafts(payload, tmp_path / "contracts")

    record = next(
        item
        for item in index["contract_drafts"]
        if item["candidate_id"] == "preview_generate_critique_revise_declared_only"
    )
    draft = json.loads(Path(record["intent_path"]).read_text(encoding="utf-8"))
    loaded = ProgramIntent.model_validate(draft)
    assert loaded.topology["kind"] == "generate_critique_revise"
    assert [module["role"] for module in loaded.topology["modules"]] == [
        "generate_draft",
        "critique_draft",
        "revise_final",
    ]
    candidate_intent = ProgramIntent.model_validate(draft)
    plan = build_program_architecture_candidates(candidate_intent)
    declared = next(
        item
        for item in plan["candidates"]
        if item["candidate_id"] == "declared_pipeline"
    )
    assert declared["status"] == "materializable"


def test_architecture_contract_drafts_write_reviewable_react_v2_intent(
    tmp_path: Path,
) -> None:
    payload = build_program_architecture_candidates(
        ProgramIntent(
            name="ReactV2DraftProgram",
            objective="Use ReActV2 to answer with tools later.",
            inputs=["question"],
            outputs=["answer"],
        )
    )

    index = write_architecture_contract_drafts(payload, tmp_path / "contracts")

    assert index["schema_version"] == "program-architecture-contract-drafts-v1"
    assert index["status"] == "explicit_contract_drafts_only_not_materialized"
    assert index["effect"]["candidate_program_materialized"] is False
    assert index["effect"]["tool_called"] is False
    record = next(
        item
        for item in index["contract_drafts"]
        if item["candidate_id"] == "preview_reactv2_declared_only"
    )
    assert record["status"] == "explicit_contract_draft_requires_operator_review"
    assert record["materializable_claimed"] is False
    draft = json.loads(Path(record["intent_path"]).read_text(encoding="utf-8"))
    loaded = ProgramIntent.model_validate(draft)
    assert loaded.options["enable_react_v2_materialization"] is True
    assert loaded.options["react_v2_materialization"] is True
    assert loaded.topology["kind"] == "pipeline"
    assert loaded.topology["modules"][0]["primitive"] == "ReActV2"
    assert loaded.topology["modules"][0]["react"]["tools"] == []
    assert loaded.topology["modules"][0]["react"]["declared_tool_refs"] == []
    assert "public dspy.ReActV2" in record["preconditions"][0]
    assert not (tmp_path / "contracts" / "manifest.json").exists()


def test_architecture_intent_portfolio_rejects_path_hostile_candidate_id(
    tmp_path: Path,
) -> None:
    payload = build_program_architecture_candidates(
        ProgramIntent(
            name="PortfolioEscapeProgram",
            objective="Answer a question from context.",
            inputs=["question"],
            outputs=["answer"],
        )
    )
    payload["candidates"][0]["candidate_id"] = "../escaped"

    try:
        write_architecture_intent_portfolio(payload, tmp_path / "portfolio")
    except ProgramArchitectureError as exc:
        assert "path-hostile" in str(exc)
    else:  # pragma: no cover - defensive assertion for clearer failure output
        raise AssertionError("path-hostile candidate id was accepted")
    assert not (tmp_path / "escaped.json").exists()


def test_architecture_planner_cli_writes_plan_and_intent_portfolio(
    tmp_path: Path,
) -> None:
    intent_path = tmp_path / "intent.yaml"
    plan_path = tmp_path / "architecture_plan.json"
    portfolio_dir = tmp_path / "portfolio"
    _write_intent(
        intent_path,
        "Route support tickets by classifying billing versus technical issues, then draft a helpful response with rationale.",
    )

    result = runner.invoke(
        app,
        [
            "program-architect",
            "plan",
            "--intent",
            str(intent_path),
            "--out",
            str(plan_path),
            "--portfolio-outdir",
            str(portfolio_dir),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    stdout_plan = json.loads(result.output)
    assert stdout_plan["schema_version"] == "program-architecture-candidates-v1"
    stdout_without_artifact = dict(stdout_plan)
    stdout_artifact = dict(stdout_without_artifact.pop("artifact"))
    assert stdout_artifact["payload_hash_excluding_artifact"] == sha256_text(
        json.dumps(
            stdout_without_artifact, ensure_ascii=False, indent=2, sort_keys=True
        )
        + "\n"
    )
    assert plan["portfolio"]["schema_version"] == (
        "program-architecture-intent-portfolio-v1"
    )
    assert "content_hash" not in plan["artifact"]
    assert "payload_hash_excluding_artifact" in plan["artifact"]
    assert plan["effect"]["candidate_materialized"] is False
    assert plan["effect"]["portfolio_materialized"] is True
    assert not (portfolio_dir / "manifest.json").exists()
    assert not (portfolio_dir / "program.py").exists()
    index = json.loads((portfolio_dir / "portfolio_index.json").read_text())
    assert index["candidate_intent_count"] == 2
    assert sorted(
        path.name for path in (portfolio_dir / "candidate_intents").glob("*.json")
    ) == [
        "baseline_single_predict.json",
        "prompt_inferred_pipeline.json",
    ]


def test_architecture_contract_draft_links_react_v2_tool_refs_to_pure_tool_contracts(
    tmp_path: Path,
) -> None:
    payload = build_program_architecture_candidates(
        ProgramIntent(
            name="ReactV2ToolRefProgram",
            objective="Use ReActV2 tools later to answer.",
            inputs=["question"],
            outputs=["answer"],
            capabilities={
                "declarations": [
                    {
                        "id": "lookup_policy",
                        "kind": "tool",
                        "effect_class": "pure",
                        "inputs": ["question"],
                        "outputs": ["answer"],
                    },
                    {
                        "id": "mutate_ticket",
                        "kind": "tool",
                        "effect_class": "mutate",
                    },
                ]
            },
        )
    )

    index = write_architecture_contract_drafts(payload, tmp_path / "contracts")

    record = next(
        item
        for item in index["contract_drafts"]
        if item["candidate_id"] == "preview_reactv2_declared_only"
    )
    draft = json.loads(Path(record["intent_path"]).read_text(encoding="utf-8"))
    loaded = ProgramIntent.model_validate(draft)
    react = loaded.topology["modules"][0]["react"]
    assert react["tools"] == []
    assert react["declared_tool_refs"] == ["lookup_policy"]
    assert react["tool_binding_status"] == "declared_refs_only_not_bound"


def test_architecture_contract_verification_rejects_tool_refs_without_pure_contract(
    tmp_path: Path,
) -> None:
    payload = build_program_architecture_candidates(
        ProgramIntent(
            name="ReactV2MissingToolContractProgram",
            objective="Use ReActV2 tools later to answer.",
            inputs=["question"],
            outputs=["answer"],
            capabilities={
                "declarations": [
                    {
                        "id": "mutate_ticket",
                        "kind": "tool",
                        "effect_class": "mutate",
                    }
                ]
            },
        )
    )
    index = write_architecture_contract_drafts(payload, tmp_path / "contracts")
    record = next(
        item
        for item in index["contract_drafts"]
        if item["candidate_id"] == "preview_reactv2_declared_only"
    )
    draft_path = Path(record["intent_path"])
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    draft["topology"]["modules"][0]["tool_refs"] = ["mutate_ticket", "missing"]
    draft_path.write_text(json.dumps(draft, indent=2, sort_keys=True), encoding="utf-8")

    verification = verify_architecture_contract_intent(draft_path)

    assert verification["status"] == "failed"
    assert verification["materialization_allowed_by_contract_verification"] is False
    assert any(
        "matching pure tool declarations" in item for item in verification["violations"]
    )


def test_architecture_contract_verification_accepts_safe_react_v2_tool_ref_preflight(
    tmp_path: Path,
) -> None:
    payload = build_program_architecture_candidates(
        ProgramIntent(
            name="ReactV2ToolPreflightProgram",
            objective="Use ReActV2 tools later to answer.",
            inputs=["question"],
            outputs=["answer"],
            capabilities={
                "declarations": [
                    {
                        "id": "lookup_policy",
                        "kind": "tool",
                        "effect_class": "pure",
                        "inputs": ["question"],
                        "outputs": ["answer"],
                    }
                ]
            },
        )
    )
    index = write_architecture_contract_drafts(payload, tmp_path / "contracts")
    record = next(
        item
        for item in index["contract_drafts"]
        if item["candidate_id"] == "preview_reactv2_declared_only"
    )

    verification = verify_architecture_contract_intent(Path(record["intent_path"]))

    assert verification["status"] == "verified_contract_intent"
    preflight = verification["react_v2_tool_preflight"]
    assert preflight["referenced_tool_ids"] == ["lookup_policy"]
    assert preflight["all_referenced_tools_have_pure_contracts"] is True
    assert preflight["all_referenced_tool_schemas_bounded"] is True
    assert preflight["all_referenced_adapter_blueprints_hash_bound"] is True
    assert preflight["all_referenced_tools_have_replay_policy_preconditions"] is True
    assert preflight["ready_for_tool_adapter_materialization"] is True
    assert preflight["tool_binding_allowed"] is False
    assert preflight["tool_execution_allowed"] is False
    assert verification["materialization_gate"]["allows_live_tools"] is False


def test_architecture_contract_verification_accepts_safe_react_v2_draft(
    tmp_path: Path,
) -> None:
    payload = build_program_architecture_candidates(
        ProgramIntent(
            name="ReactV2VerifyProgram",
            objective="Use ReActV2 to answer with tools later.",
            inputs=["question"],
            outputs=["answer"],
        )
    )
    index = write_architecture_contract_drafts(payload, tmp_path / "contracts")
    record = next(
        item
        for item in index["contract_drafts"]
        if item["candidate_id"] == "preview_reactv2_declared_only"
    )

    verification = verify_architecture_contract_intent(Path(record["intent_path"]))

    assert verification["schema_version"] == (
        "program-architecture-contract-verification-v1"
    )
    assert verification["status"] == "verified_contract_intent"
    assert verification["materialization_allowed_by_contract_verification"] is True
    assert verification["live_tool_binding_allowed"] is False
    assert verification["custom_import_allowed"] is False
    assert verification["external_retriever_allowed"] is False
    assert verification["effect"]["candidate_program_materialized"] is False
    assert verification["violations"] == []


def test_architecture_contract_verification_rejects_react_v2_tools(
    tmp_path: Path,
) -> None:
    intent_path = tmp_path / "unsafe_react_v2.json"
    intent_path.write_text(
        json.dumps(
            {
                "schema_version": "program-intent-v2",
                "name": "UnsafeReActV2Contract",
                "objective": "Use unsafe tools.",
                "inputs": ["question"],
                "outputs": ["answer"],
                "options": {"enable_react_v2_materialization": True},
                "topology": {
                    "kind": "pipeline",
                    "execution_status": "declared_not_materialized",
                    "modules": [
                        {
                            "id": "agent",
                            "primitive": "ReActV2",
                            "signature": {
                                "name": "Agent",
                                "inputs": ["question"],
                                "outputs": ["answer"],
                            },
                            "tools": ["lookup"],
                        }
                    ],
                    "edges": [
                        {"from": "input", "to": "agent"},
                        {"from": "agent", "to": "output"},
                    ],
                },
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    verification = verify_architecture_contract_intent(intent_path)

    assert verification["status"] == "failed"
    assert verification["materialization_allowed_by_contract_verification"] is False
    assert any("empty tools list" in item for item in verification["violations"])


def test_contract_verification_returns_failed_payload_for_missing_modules(
    tmp_path: Path,
) -> None:
    intent_path = tmp_path / "no_modules.json"
    intent_path.write_text(
        json.dumps(
            {
                "schema_version": "program-intent-v2",
                "name": "NoModulesContract",
                "objective": "Verify without modules.",
                "inputs": ["question"],
                "outputs": ["answer"],
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    verification = verify_architecture_contract_intent(intent_path)

    assert verification["status"] == "failed"
    assert verification["violations"] == [
        "contract intent must declare topology modules"
    ]
    assert verification["materialization_allowed_by_contract_verification"] is False
    assert verification["materialization_gate"] == {
        "status": "blocked_by_contract_verification",
        "allows_live_tools": False,
        "allows_custom_imports": False,
        "allows_external_retrievers": False,
        "requires_review": True,
    }
    assert verification["effect"]["candidate_program_materialized"] is False
    assert verification["non_authority"]["planning_only"] is True


def test_architecture_planner_cli_writes_contract_drafts(tmp_path: Path) -> None:
    intent_path = tmp_path / "intent.yaml"
    plan_path = tmp_path / "architecture_plan.json"
    contract_dir = tmp_path / "contracts"
    _write_intent(intent_path, "Use ReActV2 tools later to answer the question.")

    result = runner.invoke(
        app,
        [
            "program-architect",
            "plan",
            "--intent",
            str(intent_path),
            "--out",
            str(plan_path),
            "--contract-outdir",
            str(contract_dir),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    assert plan["contract_drafts"]["schema_version"] == (
        "program-architecture-contract-drafts-v1"
    )
    assert plan["effect"]["contract_drafts_written"] is True
    assert plan["effect"]["candidate_materialized"] is False
    index = json.loads((contract_dir / "contract_drafts_index.json").read_text())
    assert index["contract_draft_count"] >= 1
    assert (
        contract_dir / "contract_intents" / "preview_reactv2_declared_only.json"
    ).exists()
    assert not (contract_dir / "manifest.json").exists()
    assert not (contract_dir / "program.py").exists()


def test_program_gen_records_matching_contract_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    payload = build_program_architecture_candidates(
        ProgramIntent(
            name="ReactContractMaterializeProgram",
            objective="Use ReAct to answer without tools.",
            inputs=["question"],
            outputs=["answer"],
        )
    )
    index = write_architecture_contract_drafts(payload, tmp_path / "contracts")
    record = next(
        item
        for item in index["contract_drafts"]
        if item["candidate_id"] == "preview_react_declared_only"
    )
    verification = verify_architecture_contract_intent(Path(record["intent_path"]))
    verification_path = tmp_path / "contract_verification.json"
    verification_path.write_text(
        json.dumps(verification, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "program-gen",
            "--intent",
            record["intent_path"],
            "--outdir",
            str(tmp_path / "program"),
            "--contract-verification",
            str(verification_path),
        ],
    )

    assert result.exit_code == 0, result.output
    manifest = json.loads((tmp_path / "program" / "manifest.json").read_text())
    recorded = manifest["program_architecture_contract_verification"]
    assert recorded["schema_version"] == (
        "program-architecture-contract-verification-v1"
    )
    assert recorded["status"] == "verified_contract_intent"
    assert recorded["content_hash"] == sha256_text(
        verification_path.read_text(encoding="utf-8")
    )
    assert recorded["materialization_gate"]["allows_live_tools"] is False
    replay = check_run_receipt(tmp_path / "program" / "manifest.json.meta.json")
    assert replay["status"] == "ok"
    assert replay["checks"]["program_contract_verification_exists"] is True
    assert replay["checks"]["program_contract_verification_hash_match"] is True
    assert replay["checks"]["program_contract_verification_semantic_valid"] is True


def test_program_gen_rejects_mismatched_contract_verification(tmp_path: Path) -> None:
    intent_path = tmp_path / "intent.json"
    other_intent_path = tmp_path / "other_intent.json"
    base_intent = {
        "schema_version": "program-intent-v2",
        "name": "MismatchProgram",
        "objective": "Answer safely.",
        "inputs": ["question"],
        "outputs": ["answer"],
    }
    intent_path.write_text(json.dumps(base_intent), encoding="utf-8")
    other_intent_path.write_text(
        json.dumps({**base_intent, "name": "OtherProgram"}), encoding="utf-8"
    )
    verification = {
        "schema_version": "program-architecture-contract-verification-v1",
        "status": "verified_contract_intent",
        "materialization_allowed_by_contract_verification": True,
        "materialization_gate": {
            "status": "verified_for_explicit_program_gen_materialization",
            "program_gen_must_match_intent_hash": sha256_text(
                other_intent_path.read_text(encoding="utf-8")
            ),
            "allows_live_tools": False,
            "allows_custom_imports": False,
            "allows_external_retrievers": False,
        },
    }
    verification_path = tmp_path / "verification.json"
    verification_path.write_text(json.dumps(verification), encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "program-gen",
            "--intent",
            str(intent_path),
            "--outdir",
            str(tmp_path / "program"),
            "--contract-verification",
            str(verification_path),
        ],
    )

    assert result.exit_code == 2
    assert "intent_hash_mismatch" in result.output
    assert not (tmp_path / "program").exists()


def test_architecture_planner_cli_verifies_contract_draft(tmp_path: Path) -> None:
    payload = build_program_architecture_candidates(
        ProgramIntent(
            name="ReactV2CliVerifyProgram",
            objective="Use ReActV2 to answer with tools later.",
            inputs=["question"],
            outputs=["answer"],
        )
    )
    index = write_architecture_contract_drafts(payload, tmp_path / "contracts")
    record = next(
        item
        for item in index["contract_drafts"]
        if item["candidate_id"] == "preview_reactv2_declared_only"
    )
    out = tmp_path / "contract_verification.json"

    result = runner.invoke(
        app,
        [
            "program-architect",
            "verify-contract",
            "--intent",
            record["intent_path"],
            "--out",
            str(out),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    verification = json.loads(out.read_text(encoding="utf-8"))
    assert verification["status"] == "verified_contract_intent"
    assert verification["effect"]["candidate_program_materialized"] is False
    assert not (tmp_path / "manifest.json").exists()


def test_architecture_planner_refuses_candidate_artifact_output(tmp_path: Path) -> None:
    intent_path = tmp_path / "intent.yaml"
    _write_intent(intent_path, "Answer a question from context.")

    result = runner.invoke(
        app,
        [
            "program-architect",
            "plan",
            "--intent",
            str(intent_path),
            "--out",
            str(tmp_path / "manifest.json"),
        ],
    )

    assert result.exit_code == 2
    assert "refusing to write architecture plan" in result.output


def test_program_architect_loop_runs_guided_local_architecture_flow(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    outdir = tmp_path / "architect_loop"

    result = runner.invoke(
        app,
        [
            "program-architect",
            "loop",
            "--prompt",
            "Route support tickets by classifying billing versus technical issues, then draft a helpful response with rationale.",
            "--outdir",
            str(outdir),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema_version"] == "program-architect-loop-v1"
    assert (outdir / "normalization.json").exists()
    assert (outdir / "normalized_intent.json").exists()
    assert (outdir / "architecture_plan.json").exists()
    assert (outdir / "tournament.json").exists()
    assert (outdir / "architecture_recommendation.json").exists()
    assert (outdir / "program_architect_loop.json").exists()
    assert payload == json.loads((outdir / "program_architect_loop.json").read_text())
    assert payload["steps"]["normalization"]["status"] == "normalized"
    assert payload["steps"]["architecture_plan"]["candidate_count"] == 2
    assert payload["steps"]["tournament"]["materialized_candidate_count"] == 2
    assert payload["steps"]["recommendation"]["next_move_count"] >= 1
    assert payload["effect"]["candidate_programs_materialized"] is True
    assert payload["effect"]["receipts_replay_checked"] is True
    assert payload["effect"]["oracle_index_mutated"] is False
    assert payload["effect"]["shared_oracle_mutated"] is False
    assert payload["effect"]["winner_selected"] is False
    assert payload["effect"]["promotion_applied"] is False
    assert payload["effect"]["ak_called"] is False
    assert payload["effect"]["governance_mutated"] is False
    assert payload["non_authority"]["guided_architecture_loop_only"] is True
    assert payload["non_authority"]["winner_selection"] is False
    assert not (outdir / "manifest.json").exists()
    assert not (outdir / "program.py").exists()


def test_program_architect_loop_rejects_unknown_candidate_without_partial_sidecars(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    outdir = tmp_path / "architect_loop"

    result = runner.invoke(
        app,
        [
            "program-architect",
            "loop",
            "--prompt",
            "Route support tickets by classifying billing versus technical issues, then draft a helpful response with rationale.",
            "--outdir",
            str(outdir),
            "--candidate",
            "does_not_exist",
        ],
    )

    assert result.exit_code == 2
    assert "unknown architecture candidate id" in result.output
    assert not (outdir / "normalization.json").exists()
    assert not (outdir / "normalized_intent.json").exists()
    assert not (outdir / "architecture_plan.json").exists()
    assert not (outdir / "tournament.json").exists()
    assert not (outdir / "architecture_recommendation.json").exists()
    assert not (outdir / "program_architect_loop.json").exists()
    assert not (outdir / "tournament" / "candidates").exists()


def test_program_architect_loop_rejects_non_empty_outdir_before_partial_overwrite(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    outdir = tmp_path / "architect_loop"
    first = runner.invoke(
        app,
        [
            "program-architect",
            "loop",
            "--prompt",
            "Route support tickets by classifying billing versus technical issues, then draft a helpful response with rationale.",
            "--outdir",
            str(outdir),
        ],
    )
    assert first.exit_code == 0, first.output
    before = (outdir / "normalized_intent.json").read_text()

    second = runner.invoke(
        app,
        [
            "program-architect",
            "loop",
            "--prompt",
            "Answer a completely different question from context.",
            "--outdir",
            str(outdir),
        ],
    )

    assert second.exit_code == 2
    assert "architecture loop outdir is not empty" in second.output
    assert (outdir / "normalized_intent.json").read_text() == before


def test_program_architect_loop_with_oracle_reports_is_candidate_local(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "mock")
    outdir = tmp_path / "architect_loop"

    result = runner.invoke(
        app,
        [
            "program-architect",
            "loop",
            "--prompt",
            "Route support tickets by classifying billing versus technical issues, then draft a helpful response with rationale.",
            "--outdir",
            str(outdir),
            "--candidate",
            "prompt_inferred_pipeline",
            "--with-oracle-reports",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["effect"]["oracle_index_mutated"] is True
    assert payload["effect"]["oracle_index_scope"] == "candidate_local_explicit_paths"
    assert payload["effect"]["shared_oracle_mutated"] is False
    candidate_root = outdir / "tournament" / "candidates" / "prompt_inferred_pipeline"
    assert (candidate_root / "oracle" / "coordinates.db").exists()
    assert (candidate_root / "program_oracle_report.json").exists()
    recommendation = json.loads(
        (outdir / "architecture_recommendation.json").read_text()
    )
    assert recommendation["effect"]["winner_selected"] is False
    assert recommendation["effect"]["promotion_applied"] is False


def test_program_architect_tournament_materializes_plan_candidates_locally(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    intent_path = tmp_path / "intent.yaml"
    plan_path = tmp_path / "architecture_plan.json"
    tournament_outdir = tmp_path / "tournament"
    tournament_out = tmp_path / "tournament.json"
    _write_intent(
        intent_path,
        "Route support tickets by classifying billing versus technical issues, then draft a helpful response with rationale.",
        examples=True,
    )
    plan_result = runner.invoke(
        app,
        [
            "program-architect",
            "plan",
            "--intent",
            str(intent_path),
            "--out",
            str(plan_path),
        ],
    )
    assert plan_result.exit_code == 0, plan_result.output

    result = runner.invoke(
        app,
        [
            "program-architect",
            "tournament",
            "--architecture-plan",
            str(plan_path),
            "--outdir",
            str(tournament_outdir),
            "--out",
            str(tournament_out),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    stdout_payload = json.loads(result.output)
    sidecar = json.loads(tournament_out.read_text(encoding="utf-8"))
    assert stdout_payload == sidecar
    assert sidecar["schema_version"] == "program-architecture-tournament-v1"
    assert sidecar["status"] == "materialized_and_replay_checked"
    assert sidecar["materialized_candidate_count"] == 2
    assert sidecar["interpretation"]["replay_ok_count"] == 2
    assert sidecar["effect"]["candidate_programs_materialized"] is True
    assert sidecar["effect"]["receipts_replay_checked"] is True
    assert sidecar["effect"]["winner_selected"] is False
    assert sidecar["effect"]["promotion_applied"] is False
    assert sidecar["effect"]["oracle_index_mutated"] is False
    assert sidecar["effect"]["ak_called"] is False
    assert sidecar["non_authority"]["winner_selection"] is False
    matrix = sidecar["evidence_matrix"]
    assert matrix["schema_version"] == (
        "program-architecture-tournament-evidence-matrix-v1"
    )
    assert matrix["source_kind_counts"] == {"inline_examples": 2}
    assert matrix["non_authority"]["raw_examples_included"] is False
    assert matrix["non_authority"]["winner_selection"] is False
    assert [row["candidate_id"] for row in matrix["rows"]] == [
        "baseline_single_predict",
        "prompt_inferred_pipeline",
    ]
    for row in matrix["rows"]:
        assert row["replay_status"] == "ok"
        assert row["behavior_summary"]["total"] == 1
        assert row["behavior_sources"]["source_kinds"] == ["inline_examples"]
        assert row["artifacts"]["behavior_results"]["exists"] is True
        assert row["artifacts"]["behavior_episode"]["exists"] is True
        assert row["artifacts"]["oracle_evidence"]["exists"] is True
        assert row["artifacts"]["module_surfaces"]["exists"] is True
        assert row["artifacts"]["capability_registry"]["exists"] is True
        assert row["artifacts"]["generated_module_policy"]["exists"] is True
        assert row["non_authority"]["winner_selection"] is False
    assert [candidate["candidate_id"] for candidate in sidecar["candidates"]] == [
        "baseline_single_predict",
        "prompt_inferred_pipeline",
    ]
    for candidate in sidecar["candidates"]:
        root = Path(candidate["root_path"])
        assert (root / "manifest.json").exists()
        assert (root / "manifest.json.meta.json").exists()
        assert (root / "program.py").exists()
        assert (root / "module_surfaces.json").exists()
        assert (root / "program_capability_registry.json").exists()
        assert (root / "generated_module_policy.json").exists()
        assert candidate["capability_registry_hash"]
        assert candidate["generated_module_policy_hash"]
        assert not (root / "oracle" / "coordinates.db").exists()
        assert not (root / "program_oracle_report.json").exists()
        assert candidate["replay_check"]["status"] == "ok"
        assert check_run_receipt(root / "manifest.json.meta.json")["status"] == "ok"


def test_program_architect_tournament_with_oracle_reports_writes_candidate_local_reports(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "mock")
    intent_path = tmp_path / "intent.yaml"
    plan_path = tmp_path / "architecture_plan.json"
    tournament_outdir = tmp_path / "tournament"
    tournament_out = tmp_path / "tournament.json"
    _write_intent(
        intent_path,
        "Route support tickets by classifying billing versus technical issues, then draft a helpful response with rationale.",
        examples=True,
    )
    plan_result = runner.invoke(
        app,
        [
            "program-architect",
            "plan",
            "--intent",
            str(intent_path),
            "--out",
            str(plan_path),
        ],
    )
    assert plan_result.exit_code == 0, plan_result.output

    result = runner.invoke(
        app,
        [
            "program-architect",
            "tournament",
            "--architecture-plan",
            str(plan_path),
            "--outdir",
            str(tournament_outdir),
            "--out",
            str(tournament_out),
            "--candidate",
            "prompt_inferred_pipeline",
            "--with-oracle-reports",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(tournament_out.read_text())
    assert payload["effect"]["oracle_index_mutated"] is True
    assert payload["effect"]["oracle_index_scope"] == "candidate_local_explicit_paths"
    assert payload["effect"]["shared_oracle_mutated"] is False
    assert payload["effect"]["winner_selected"] is False
    materialized = next(
        candidate
        for candidate in payload["candidates"]
        if candidate["candidate_id"] == "prompt_inferred_pipeline"
    )
    root = Path(materialized["root_path"])
    assert (root / "oracle" / "coordinates.db").exists()
    report_path = root / "program_oracle_report.json"
    assert report_path.exists()
    report = json.loads(report_path.read_text())
    assert report["schema_version"] == "program-oracle-evidence-report-v1"
    assert report["total_records"] == 1
    assert report["non_authority"]["oracle_promotion"] is False
    assert (
        materialized["candidate_local_oracle"]["report_summary"]["total_records"] == 1
    )
    row = next(
        item
        for item in payload["evidence_matrix"]["rows"]
        if item["candidate_id"] == "prompt_inferred_pipeline"
    )
    assert row["artifacts"]["oracle_report"]["exists"] is True
    assert row["artifacts"]["oracle_index"]["exists"] is True
    assert row["oracle_readability"]["candidate_local_report_status"] == "ok"
    assert row["oracle_readability"]["candidate_local_report_records"] == 1
    skipped = next(
        candidate
        for candidate in payload["candidates"]
        if candidate["candidate_id"] == "baseline_single_predict"
    )
    assert skipped["status"] == "skipped"
    assert not (tournament_outdir / "candidates" / "baseline_single_predict").exists()


def test_program_architect_recommend_emits_next_moves_without_winner_selection(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    intent_path = tmp_path / "intent.yaml"
    plan_path = tmp_path / "architecture_plan.json"
    tournament_out = tmp_path / "tournament.json"
    recommendation_out = tmp_path / "architecture_recommendation.json"
    _write_intent(
        intent_path,
        "Route support tickets by classifying billing versus technical issues, then draft a helpful response with rationale.",
        examples=True,
    )
    assert (
        runner.invoke(
            app,
            [
                "program-architect",
                "plan",
                "--intent",
                str(intent_path),
                "--out",
                str(plan_path),
            ],
        ).exit_code
        == 0
    )
    tournament_result = runner.invoke(
        app,
        [
            "program-architect",
            "tournament",
            "--architecture-plan",
            str(plan_path),
            "--outdir",
            str(tmp_path / "tournament"),
            "--out",
            str(tournament_out),
        ],
    )
    assert tournament_result.exit_code == 0, tournament_result.output
    before_hash = sha256_text(tournament_out.read_text(encoding="utf-8"))

    result = runner.invoke(
        app,
        [
            "program-architect",
            "recommend",
            "--tournament",
            str(tournament_out),
            "--out",
            str(recommendation_out),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(recommendation_out.read_text(encoding="utf-8"))
    assert json.loads(result.output) == payload
    assert sha256_text(tournament_out.read_text(encoding="utf-8")) == before_hash
    assert payload["schema_version"] == "program-architecture-recommendation-v1"
    assert payload["created_from"]["tournament_schema_version"] == (
        "program-architecture-tournament-v1"
    )
    assert payload["status"] in {"advisory_ready", "needs_attention"}
    assert payload["next_moves"]
    assert [item["candidate_id"] for item in payload["candidate_advisories"]] == [
        "baseline_single_predict",
        "prompt_inferred_pipeline",
    ]
    assert all("winner" not in item for item in payload)
    assert "selected_candidate_id" not in payload
    assert "winner_candidate_id" not in payload
    assert payload["effect"]["recommendation_sidecar_written"] is True
    assert payload["effect"]["candidate_programs_materialized"] is False
    assert payload["effect"]["oracle_index_mutated"] is False
    assert payload["effect"]["winner_selected"] is False
    assert payload["effect"]["promotion_applied"] is False
    assert payload["effect"]["ak_called"] is False
    assert payload["effect"]["governance_mutated"] is False
    assert payload["non_authority"]["advisory_only"] is True
    assert payload["non_authority"]["winner_selection"] is False
    assert payload["non_authority"]["promotion_authority"] is False
    for advisory in payload["candidate_advisories"]:
        assert advisory["non_authority"] == {
            "winner_selection": False,
            "ranking_authority": False,
            "promotion_authority": False,
            "activation_authority": False,
            "oracle_authority": False,
            "oracle_ranking": False,
            "oracle_pruning": False,
            "oracle_promotion": False,
            "governance_authority": False,
            "external_mutation": False,
            "canonical_mutation": False,
        }


def test_program_architect_recommend_rejects_authority_widened_tournament(
    tmp_path: Path,
) -> None:
    tournament_path = tmp_path / "tournament.json"
    recommendation_out = tmp_path / "recommendation.json"
    tournament_path.write_text(
        json.dumps(
            {
                "schema_version": "program-architecture-tournament-v1",
                "status": "materialized_and_replay_checked",
                "evidence_matrix": {
                    "schema_version": "program-architecture-tournament-evidence-matrix-v1",
                    "rows": [],
                },
                "effect": {
                    "winner_selected": True,
                    "promotion_applied": False,
                    "ak_called": False,
                    "governance_mutated": False,
                    "external_authority_mutated": False,
                    "shared_oracle_mutated": False,
                },
                "non_authority": {"winner_selection": False},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "program-architect",
            "recommend",
            "--tournament",
            str(tournament_path),
            "--out",
            str(recommendation_out),
        ],
    )

    assert result.exit_code == 2
    assert "widens authority" in result.output
    assert not recommendation_out.exists()


def test_program_architect_recommend_rejects_shared_oracle_mutation(
    tmp_path: Path,
) -> None:
    tournament_path = tmp_path / "tournament.json"
    recommendation_out = tmp_path / "recommendation.json"
    tournament_path.write_text(
        json.dumps(
            {
                "schema_version": "program-architecture-tournament-v1",
                "status": "materialized_and_replay_checked",
                "evidence_matrix": {
                    "schema_version": "program-architecture-tournament-evidence-matrix-v1",
                    "rows": [],
                },
                "effect": {
                    "winner_selected": False,
                    "promotion_applied": False,
                    "ak_called": False,
                    "governance_mutated": False,
                    "external_authority_mutated": False,
                    "shared_oracle_mutated": True,
                },
                "non_authority": _recommendation_tournament_non_authority(),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "program-architect",
            "recommend",
            "--tournament",
            str(tournament_path),
            "--out",
            str(recommendation_out),
        ],
    )

    assert result.exit_code == 2
    assert "shared_oracle_mutated" in result.output
    assert not recommendation_out.exists()


def test_program_architect_recommend_rejects_missing_tournament_non_authority_flags(
    tmp_path: Path,
) -> None:
    tournament_path = tmp_path / "tournament.json"
    recommendation_out = tmp_path / "recommendation.json"
    tournament_path.write_text(
        json.dumps(
            {
                "schema_version": "program-architecture-tournament-v1",
                "status": "materialized_and_replay_checked",
                "evidence_matrix": {
                    "schema_version": "program-architecture-tournament-evidence-matrix-v1",
                    "rows": [],
                    "non_authority": {
                        "evidence_summary_only": True,
                        "winner_selection": False,
                        "promotion_authority": False,
                        "oracle_ranking": False,
                    },
                },
                "effect": {
                    "winner_selected": False,
                    "promotion_applied": False,
                    "ak_called": False,
                    "governance_mutated": False,
                    "external_authority_mutated": False,
                    "shared_oracle_mutated": False,
                },
                "non_authority": {"winner_selection": False},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "program-architect",
            "recommend",
            "--tournament",
            str(tournament_path),
            "--out",
            str(recommendation_out),
        ],
    )

    assert result.exit_code == 2
    assert "tournament non_authority missing authority flags" in result.output
    assert "ranking_authority" in result.output
    assert not recommendation_out.exists()


def test_program_architect_recommend_rejects_missing_evidence_matrix_non_authority_flags(
    tmp_path: Path,
) -> None:
    tournament_path = tmp_path / "tournament.json"
    recommendation_out = tmp_path / "recommendation.json"
    tournament_path.write_text(
        json.dumps(
            {
                "schema_version": "program-architecture-tournament-v1",
                "status": "materialized_and_replay_checked",
                "evidence_matrix": {
                    "schema_version": "program-architecture-tournament-evidence-matrix-v1",
                    "rows": [],
                    "non_authority": {
                        "evidence_summary_only": True,
                        "winner_selection": False,
                        "promotion_authority": False,
                    },
                },
                "effect": {
                    "winner_selected": False,
                    "promotion_applied": False,
                    "ak_called": False,
                    "governance_mutated": False,
                    "external_authority_mutated": False,
                    "shared_oracle_mutated": False,
                },
                "non_authority": _recommendation_tournament_non_authority(),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "program-architect",
            "recommend",
            "--tournament",
            str(tournament_path),
            "--out",
            str(recommendation_out),
        ],
    )

    assert result.exit_code == 2
    assert "evidence_matrix non_authority missing authority flags" in result.output
    assert "oracle_ranking" in result.output
    assert not recommendation_out.exists()


def test_program_architect_recommend_rejects_missing_candidate_row_non_authority_flags(
    tmp_path: Path,
) -> None:
    tournament_path = tmp_path / "tournament.json"
    recommendation_out = tmp_path / "recommendation.json"
    tournament_path.write_text(
        json.dumps(
            {
                "schema_version": "program-architecture-tournament-v1",
                "status": "materialized_and_replay_checked",
                "evidence_matrix": {
                    "schema_version": "program-architecture-tournament-evidence-matrix-v1",
                    "rows": [
                        {
                            "candidate_id": "candidate_a",
                            "status": "skipped",
                            "reason": "test",
                            "non_authority": {
                                "winner_selection": False,
                                "promotion_authority": False,
                            },
                        }
                    ],
                    "non_authority": {
                        "evidence_summary_only": True,
                        "winner_selection": False,
                        "promotion_authority": False,
                        "oracle_ranking": False,
                    },
                },
                "effect": {
                    "winner_selected": False,
                    "promotion_applied": False,
                    "ak_called": False,
                    "governance_mutated": False,
                    "external_authority_mutated": False,
                    "shared_oracle_mutated": False,
                },
                "non_authority": _recommendation_tournament_non_authority(),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "program-architect",
            "recommend",
            "--tournament",
            str(tournament_path),
            "--out",
            str(recommendation_out),
        ],
    )

    assert result.exit_code == 2
    assert "row 0 non_authority missing authority flags" in result.output
    assert "oracle_ranking" in result.output
    assert not recommendation_out.exists()


def test_program_architect_recommend_rejects_widened_evidence_matrix_non_authority(
    tmp_path: Path,
) -> None:
    tournament_path = tmp_path / "tournament.json"
    recommendation_out = tmp_path / "recommendation.json"
    tournament_path.write_text(
        json.dumps(
            {
                "schema_version": "program-architecture-tournament-v1",
                "status": "materialized_and_replay_checked",
                "evidence_matrix": {
                    "schema_version": "program-architecture-tournament-evidence-matrix-v1",
                    "rows": [],
                    "non_authority": {
                        "evidence_summary_only": True,
                        "winner_selection": True,
                        "promotion_authority": False,
                        "oracle_ranking": False,
                    },
                },
                "effect": {
                    "winner_selected": False,
                    "promotion_applied": False,
                    "ak_called": False,
                    "governance_mutated": False,
                    "external_authority_mutated": False,
                    "shared_oracle_mutated": False,
                },
                "non_authority": _recommendation_tournament_non_authority(),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "program-architect",
            "recommend",
            "--tournament",
            str(tournament_path),
            "--out",
            str(recommendation_out),
        ],
    )

    assert result.exit_code == 2
    assert "evidence_matrix non_authority widens authority" in result.output
    assert "winner_selection" in result.output
    assert not recommendation_out.exists()


def test_program_architect_recommend_rejects_widened_candidate_row_non_authority(
    tmp_path: Path,
) -> None:
    tournament_path = tmp_path / "tournament.json"
    recommendation_out = tmp_path / "recommendation.json"
    tournament_path.write_text(
        json.dumps(
            {
                "schema_version": "program-architecture-tournament-v1",
                "status": "materialized_and_replay_checked",
                "evidence_matrix": {
                    "schema_version": "program-architecture-tournament-evidence-matrix-v1",
                    "rows": [
                        {
                            "candidate_id": "candidate_a",
                            "status": "skipped",
                            "reason": "test",
                            "non_authority": {
                                "winner_selection": False,
                                "promotion_authority": False,
                                "oracle_ranking": True,
                            },
                        }
                    ],
                    "non_authority": {
                        "evidence_summary_only": True,
                        "winner_selection": False,
                        "promotion_authority": False,
                        "oracle_ranking": False,
                    },
                },
                "effect": {
                    "winner_selected": False,
                    "promotion_applied": False,
                    "ak_called": False,
                    "governance_mutated": False,
                    "external_authority_mutated": False,
                    "shared_oracle_mutated": False,
                },
                "non_authority": _recommendation_tournament_non_authority(),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "program-architect",
            "recommend",
            "--tournament",
            str(tournament_path),
            "--out",
            str(recommendation_out),
        ],
    )

    assert result.exit_code == 2
    assert "row 0 non_authority widens authority" in result.output
    assert "oracle_ranking" in result.output
    assert not recommendation_out.exists()


def test_program_architect_recommend_rejects_widened_candidate_row_effect(
    tmp_path: Path,
) -> None:
    tournament_path = tmp_path / "tournament.json"
    recommendation_out = tmp_path / "recommendation.json"
    tournament_path.write_text(
        json.dumps(
            {
                "schema_version": "program-architecture-tournament-v1",
                "status": "materialized_and_replay_checked",
                "evidence_matrix": {
                    "schema_version": "program-architecture-tournament-evidence-matrix-v1",
                    "rows": [
                        {
                            "candidate_id": "candidate_a",
                            "status": "skipped",
                            "reason": "test",
                            "effect": {"winner_selected": True},
                            "non_authority": {
                                "winner_selection": False,
                                "promotion_authority": False,
                                "oracle_ranking": False,
                            },
                        }
                    ],
                    "non_authority": {
                        "evidence_summary_only": True,
                        "winner_selection": False,
                        "promotion_authority": False,
                        "oracle_ranking": False,
                    },
                },
                "effect": {
                    "winner_selected": False,
                    "promotion_applied": False,
                    "ak_called": False,
                    "governance_mutated": False,
                    "external_authority_mutated": False,
                    "shared_oracle_mutated": False,
                },
                "non_authority": _recommendation_tournament_non_authority(),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "program-architect",
            "recommend",
            "--tournament",
            str(tournament_path),
            "--out",
            str(recommendation_out),
        ],
    )

    assert result.exit_code == 2
    assert "row 0 effect widens authority" in result.output
    assert "winner_selected" in result.output
    assert not recommendation_out.exists()


def test_program_architect_tournament_materializes_declared_inline_retriever_candidate(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    plan = build_program_architecture_candidates(
        ProgramIntent(
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
    )

    payload = run_program_architecture_tournament(
        architecture_plan=plan,
        outdir=tmp_path / "tournament",
        candidate_ids=["declared_pipeline"],
    )

    assert payload["materialized_candidate_count"] == 1
    assert payload["interpretation"]["replay_ok_count"] == 1
    assert payload["effect"]["candidate_programs_materialized"] is True
    assert payload["effect"]["oracle_index_mutated"] is False
    assert payload["effect"]["winner_selected"] is False
    assert payload["effect"]["promotion_applied"] is False
    materialized = next(
        candidate
        for candidate in payload["candidates"]
        if candidate["candidate_id"] == "declared_pipeline"
    )
    root = Path(materialized["root_path"])
    manifest = json.loads((root / "manifest.json").read_text())
    assert materialized["status"] == "replay_ok"
    assert materialized["replay_check"]["status"] == "ok"
    assert manifest["topology_execution"]["status"] == "pipeline_materialized"
    assert manifest["topology_execution"]["materialized"] is True
    assert (root / "program_capability_registry.json").exists()
    capability_registry = json.loads(
        (root / "program_capability_registry.json").read_text()
    )
    retriever_ref = next(
        ref
        for ref in capability_registry["used_capability_refs"]
        if ref["primitive"] == "Retriever"
    )
    assert retriever_ref["runtime_binding"] == (
        "generated_bounded_inline_retriever_adapter"
    )
    row = next(
        item
        for item in payload["evidence_matrix"]["rows"]
        if item["candidate_id"] == "declared_pipeline"
    )
    assert row["replay_status"] == "ok"
    assert row["topology"]["status"] == "pipeline_materialized"
    assert row["artifacts"]["capability_registry"]["exists"] is True
    skipped = next(
        candidate
        for candidate in payload["candidates"]
        if candidate["candidate_id"] == "baseline_single_predict"
    )
    assert skipped["status"] == "skipped"


def test_program_architect_tournament_skips_declared_only_candidates(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    plan = build_program_architecture_candidates(
        ProgramIntent(
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
    )
    plan_path = tmp_path / "architecture_plan.json"
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")
    tournament_out = tmp_path / "tournament.json"

    result = runner.invoke(
        app,
        [
            "program-architect",
            "tournament",
            "--architecture-plan",
            str(plan_path),
            "--outdir",
            str(tmp_path / "tournament"),
            "--out",
            str(tournament_out),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(tournament_out.read_text())
    assert payload["materialized_candidate_count"] == 1
    skipped = next(
        candidate
        for candidate in payload["candidates"]
        if candidate["candidate_id"] == "declared_only_topology"
    )
    assert skipped["status"] == "skipped"
    assert not (
        tmp_path / "tournament" / "candidates" / "declared_only_topology"
    ).exists()


def test_program_architect_tournament_rejects_wrong_schema_without_partial_dirs(
    tmp_path: Path,
) -> None:
    plan_path = tmp_path / "not_architecture_plan.json"
    outdir = tmp_path / "tournament"
    plan_path.write_text(json.dumps({"schema_version": "wrong", "candidates": []}))

    result = runner.invoke(
        app,
        [
            "program-architect",
            "tournament",
            "--architecture-plan",
            str(plan_path),
            "--outdir",
            str(outdir),
            "--out",
            str(tmp_path / "tournament.json"),
        ],
    )

    assert result.exit_code == 2
    assert "schema_version" in result.output
    assert not outdir.exists()


def test_program_architect_tournament_rejects_invalid_plan_before_out_parent_creation(
    tmp_path: Path,
) -> None:
    plan_path = tmp_path / "not_architecture_plan.json"
    outdir = tmp_path / "tournament"
    plan_path.write_text(json.dumps({"schema_version": "wrong", "candidates": []}))

    result = runner.invoke(
        app,
        [
            "program-architect",
            "tournament",
            "--architecture-plan",
            str(plan_path),
            "--outdir",
            str(outdir),
            "--out",
            str(outdir / "tournament.json"),
        ],
    )

    assert result.exit_code == 2
    assert "schema_version" in result.output
    assert not outdir.exists()


def test_program_architect_tournament_rejects_authority_widened_architecture_plan(
    tmp_path: Path,
) -> None:
    plan_path = tmp_path / "architecture_plan.json"
    outdir = tmp_path / "tournament"
    tournament_out = tmp_path / "tournament.json"
    plan_path.write_text(
        json.dumps(
            {
                "schema_version": "program-architecture-candidates-v1",
                "status": "planned_not_materialized",
                "intent_identity": {
                    "schema_version": "program-intent-v2",
                    "objective": "Answer a question from context.",
                    "inputs": ["question"],
                    "outputs": ["answer"],
                    "intent_hash": "8dac0bb5fea0c081c235e1d0afa69598259199efab3e2a6945eeaadbc12b5cda",
                },
                "source_intent_payload": {
                    "schema_version": "program-intent-v2",
                    "name": "ManualPlanProgram",
                    "objective": "Answer a question from context.",
                    "inputs": ["question"],
                    "outputs": ["answer"],
                },
                "candidates": [
                    {
                        "candidate_id": "baseline_single_predict",
                        "status": "materializable",
                        "effect": {"candidate_materialized": False},
                        "non_authority": {"winner_selection": False},
                    }
                ],
                "effect": {
                    "candidate_materialized": False,
                    "provider_called": False,
                    "oracle_index_mutated": False,
                    "ak_called": False,
                    "governance_mutated": False,
                    "external_authority_mutated": True,
                },
                "non_authority": {"winner_selection": False},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "program-architect",
            "tournament",
            "--architecture-plan",
            str(plan_path),
            "--outdir",
            str(outdir),
            "--out",
            str(tournament_out),
        ],
    )

    assert result.exit_code == 2
    assert "architecture plan effect widens authority" in result.output
    assert "external_authority_mutated" in result.output
    assert not tournament_out.exists()
    assert not outdir.exists()


def test_program_architect_tournament_rejects_missing_plan_authority_flags(
    tmp_path: Path,
) -> None:
    plan_path = tmp_path / "architecture_plan.json"
    outdir = tmp_path / "tournament"
    tournament_out = tmp_path / "tournament.json"
    plan_path.write_text(
        json.dumps(
            {
                "schema_version": "program-architecture-candidates-v1",
                "status": "planned_not_materialized",
                "intent_identity": {
                    "schema_version": "program-intent-v2",
                    "objective": "Answer a question from context.",
                    "inputs": ["question"],
                    "outputs": ["answer"],
                    "intent_hash": "8dac0bb5fea0c081c235e1d0afa69598259199efab3e2a6945eeaadbc12b5cda",
                },
                "source_intent_payload": {
                    "schema_version": "program-intent-v2",
                    "name": "ManualPlanProgram",
                    "objective": "Answer a question from context.",
                    "inputs": ["question"],
                    "outputs": ["answer"],
                },
                "candidates": [],
                "non_authority": {
                    "winner_selection": False,
                    "ranking_authority": False,
                    "promotion_authority": False,
                    "activation_authority": False,
                    "oracle_authority": False,
                    "governance_authority": False,
                    "external_mutation": False,
                    "canonical_mutation": False,
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "program-architect",
            "tournament",
            "--architecture-plan",
            str(plan_path),
            "--outdir",
            str(outdir),
            "--out",
            str(tournament_out),
        ],
    )

    assert result.exit_code == 2
    assert "architecture plan effect missing authority flags" in result.output
    assert "candidate_materialized" in result.output
    assert not tournament_out.exists()
    assert not outdir.exists()


def test_program_architect_tournament_rejects_authority_widened_plan_candidate(
    tmp_path: Path,
) -> None:
    plan_path = tmp_path / "architecture_plan.json"
    outdir = tmp_path / "tournament"
    tournament_out = tmp_path / "tournament.json"
    plan_path.write_text(
        json.dumps(
            {
                "schema_version": "program-architecture-candidates-v1",
                "status": "planned_not_materialized",
                "intent_identity": {
                    "schema_version": "program-intent-v2",
                    "objective": "Answer a question from context.",
                    "inputs": ["question"],
                    "outputs": ["answer"],
                    "intent_hash": "8dac0bb5fea0c081c235e1d0afa69598259199efab3e2a6945eeaadbc12b5cda",
                },
                "source_intent_payload": {
                    "schema_version": "program-intent-v2",
                    "name": "ManualPlanProgram",
                    "objective": "Answer a question from context.",
                    "inputs": ["question"],
                    "outputs": ["answer"],
                },
                "candidates": [
                    {
                        "candidate_id": "baseline_single_predict",
                        "status": "materializable",
                        "effect": {
                            "candidate_materialized": False,
                            "provider_called": False,
                            "oracle_index_mutated": False,
                            "ak_called": False,
                            "governance_mutated": False,
                            "external_authority_mutated": False,
                        },
                        "non_authority": {
                            "winner_selection": False,
                            "ranking_authority": False,
                            "promotion_authority": True,
                            "activation_authority": False,
                            "oracle_authority": False,
                            "governance_authority": False,
                            "external_mutation": False,
                            "canonical_mutation": False,
                        },
                    }
                ],
                "effect": {
                    "candidate_materialized": False,
                    "provider_called": False,
                    "oracle_index_mutated": False,
                    "ak_called": False,
                    "governance_mutated": False,
                    "external_authority_mutated": False,
                },
                "non_authority": {
                    "winner_selection": False,
                    "ranking_authority": False,
                    "promotion_authority": False,
                    "activation_authority": False,
                    "oracle_authority": False,
                    "governance_authority": False,
                    "external_mutation": False,
                    "canonical_mutation": False,
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "program-architect",
            "tournament",
            "--architecture-plan",
            str(plan_path),
            "--outdir",
            str(outdir),
            "--out",
            str(tournament_out),
        ],
    )

    assert result.exit_code == 2
    assert (
        "architecture plan candidate 0 non_authority widens authority" in result.output
    )
    assert "promotion_authority" in result.output
    assert not tournament_out.exists()
    assert not outdir.exists()


def test_program_architect_tournament_rejects_candidate_intent_source_identity_drift_without_partial_dirs(
    tmp_path: Path,
) -> None:
    plan = build_program_architecture_candidates(
        ProgramIntent(
            name="SourceBindingProgram",
            objective="Answer support questions from context.",
            inputs=["question"],
            outputs=["answer"],
        )
    )
    candidate = next(
        item
        for item in plan["candidates"]
        if item["candidate_id"] == "baseline_single_predict"
    )
    candidate["intent_payload"]["objective"] = "Unrelated changed objective."
    candidate["intent_payload"]["inputs"] = ["unrelated_input"]
    candidate["intent_hash"] = sha256_text(
        json.dumps(
            candidate["intent_payload"], ensure_ascii=False, indent=2, sort_keys=True
        )
        + "\n"
    )
    plan_path = tmp_path / "architecture_plan.json"
    outdir = tmp_path / "tournament"
    tournament_out = tmp_path / "tournament.json"
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")

    result = runner.invoke(
        app,
        [
            "program-architect",
            "tournament",
            "--architecture-plan",
            str(plan_path),
            "--outdir",
            str(outdir),
            "--out",
            str(tournament_out),
        ],
    )

    assert result.exit_code == 2
    assert "intent_payload does not match intent_identity.objective" in result.output
    assert not tournament_out.exists()
    assert not outdir.exists()


def test_program_architect_tournament_rejects_source_payload_hash_drift_without_partial_dirs(
    tmp_path: Path,
) -> None:
    plan = build_program_architecture_candidates(
        ProgramIntent(
            name="SourceHashBindingProgram",
            objective="Classify support tickets.",
            inputs=["ticket_text"],
            outputs=["label"],
            metric="exact_match",
        )
    )
    plan["source_intent_payload"]["metric"] = "f1"
    candidate = next(
        item
        for item in plan["candidates"]
        if item["candidate_id"] == "baseline_single_predict"
    )
    candidate["intent_payload"]["metric"] = "f1"
    candidate["intent_hash"] = sha256_text(
        json.dumps(
            candidate["intent_payload"], ensure_ascii=False, indent=2, sort_keys=True
        )
        + "\n"
    )
    plan_path = tmp_path / "architecture_plan.json"
    outdir = tmp_path / "tournament"
    tournament_out = tmp_path / "tournament.json"
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")

    result = runner.invoke(
        app,
        [
            "program-architect",
            "tournament",
            "--architecture-plan",
            str(plan_path),
            "--outdir",
            str(outdir),
            "--out",
            str(tournament_out),
        ],
    )

    assert result.exit_code == 2
    assert "source_intent_payload hash does not match" in result.output
    assert not tournament_out.exists()
    assert not outdir.exists()


def test_program_architect_tournament_rejects_candidate_source_payload_field_drift_without_partial_dirs(
    tmp_path: Path,
) -> None:
    plan = build_program_architecture_candidates(
        ProgramIntent(
            name="SourcePayloadBindingProgram",
            objective="Classify support tickets.",
            inputs=["ticket_text"],
            outputs=["label"],
            metric="exact_match",
            examples=[
                {
                    "inputs": {"ticket_text": "I was charged twice."},
                    "outputs": {"label": "billing"},
                }
            ],
        )
    )
    candidate = next(
        item
        for item in plan["candidates"]
        if item["candidate_id"] == "baseline_single_predict"
    )
    candidate["intent_payload"]["examples"] = [
        {
            "inputs": {"ticket_text": "The app crashes on launch."},
            "outputs": {"label": "technical"},
        }
    ]
    candidate["intent_hash"] = sha256_text(
        json.dumps(
            candidate["intent_payload"], ensure_ascii=False, indent=2, sort_keys=True
        )
        + "\n"
    )
    plan_path = tmp_path / "architecture_plan.json"
    outdir = tmp_path / "tournament"
    tournament_out = tmp_path / "tournament.json"
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")

    result = runner.invoke(
        app,
        [
            "program-architect",
            "tournament",
            "--architecture-plan",
            str(plan_path),
            "--outdir",
            str(outdir),
            "--out",
            str(tournament_out),
        ],
    )

    assert result.exit_code == 2
    assert "source fields drift from source_intent_payload" in result.output
    assert not tournament_out.exists()
    assert not outdir.exists()


def test_program_architect_tournament_rejects_candidate_topology_payload_mismatch_without_partial_dirs(
    tmp_path: Path,
) -> None:
    plan = build_program_architecture_candidates(
        ProgramIntent(
            name="TopologyCongruenceProgram",
            objective=(
                "Route support tickets by classifying billing versus technical issues, "
                "then draft a helpful response with rationale."
            ),
            inputs=["ticket_text"],
            outputs=["response"],
        )
    )
    baseline = next(
        item
        for item in plan["candidates"]
        if item["candidate_id"] == "baseline_single_predict"
    )
    inferred = next(
        item
        for item in plan["candidates"]
        if item["candidate_id"] == "prompt_inferred_pipeline"
    )
    inferred["intent_payload"] = json.loads(json.dumps(baseline["intent_payload"]))
    inferred["intent_hash"] = sha256_text(
        json.dumps(
            inferred["intent_payload"], ensure_ascii=False, indent=2, sort_keys=True
        )
        + "\n"
    )
    plan_path = tmp_path / "architecture_plan.json"
    outdir = tmp_path / "tournament"
    tournament_out = tmp_path / "tournament.json"
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")

    result = runner.invoke(
        app,
        [
            "program-architect",
            "tournament",
            "--architecture-plan",
            str(plan_path),
            "--outdir",
            str(outdir),
            "--out",
            str(tournament_out),
        ],
    )

    assert result.exit_code == 2
    assert "prompt_inferred_pipeline" in result.output
    assert "topology" in result.output
    assert not tournament_out.exists()
    assert not outdir.exists()


def test_program_architect_tournament_rejects_duplicate_candidate_ids_without_partial_dirs(
    tmp_path: Path,
) -> None:
    plan = build_program_architecture_candidates(
        ProgramIntent(
            name="CandidateIdentityProgram",
            objective=(
                "Route support tickets by classifying billing versus technical issues, "
                "then draft a helpful response with rationale."
            ),
            inputs=["ticket_text"],
            outputs=["response"],
        )
    )
    plan["candidates"].append(json.loads(json.dumps(plan["candidates"][0])))
    plan["candidate_count"] = len(plan["candidates"])
    plan_path = tmp_path / "architecture_plan.json"
    outdir = tmp_path / "tournament"
    tournament_out = tmp_path / "tournament.json"
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")

    result = runner.invoke(
        app,
        [
            "program-architect",
            "tournament",
            "--architecture-plan",
            str(plan_path),
            "--outdir",
            str(outdir),
            "--out",
            str(tournament_out),
        ],
    )

    assert result.exit_code == 2
    assert "duplicate architecture candidate_id" in result.output
    assert "baseline_single_predict" in result.output
    assert not tournament_out.exists()
    assert not outdir.exists()


def test_program_architect_tournament_rejects_candidates_file_without_partial_writes(
    tmp_path: Path,
) -> None:
    plan = build_program_architecture_candidates(
        ProgramIntent(
            name="CandidateParentCollisionProgram",
            objective="Answer a question from context.",
            inputs=["question"],
            outputs=["answer"],
        )
    )
    plan_path = tmp_path / "architecture_plan.json"
    outdir = tmp_path / "tournament"
    candidates_path = outdir / "candidates"
    outdir.mkdir()
    candidates_path.write_text("SENTINEL\n")
    tournament_out = tmp_path / "tournament.json"
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")

    result = runner.invoke(
        app,
        [
            "program-architect",
            "tournament",
            "--architecture-plan",
            str(plan_path),
            "--outdir",
            str(outdir),
            "--out",
            str(tournament_out),
        ],
    )

    assert result.exit_code == 2
    assert "candidate outputs path is not a directory" in result.output
    assert candidates_path.read_text() == "SENTINEL\n"
    assert not (outdir / "candidate_intents").exists()
    assert not tournament_out.exists()


def test_program_architect_tournament_rejects_existing_later_candidate_without_partial_writes(
    tmp_path: Path,
) -> None:
    plan = build_program_architecture_candidates(
        ProgramIntent(
            name="CollisionPreflightProgram",
            objective=(
                "Route support tickets by classifying billing versus technical issues, "
                "then draft a helpful response with rationale."
            ),
            inputs=["ticket_text"],
            outputs=["response"],
        )
    )
    plan_path = tmp_path / "architecture_plan.json"
    outdir = tmp_path / "tournament"
    tournament_out = tmp_path / "tournament.json"
    existing_candidate = outdir / "candidates" / "prompt_inferred_pipeline"
    existing_candidate.mkdir(parents=True)
    (existing_candidate / "manifest.json").write_text("{}\n")
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")

    result = runner.invoke(
        app,
        [
            "program-architect",
            "tournament",
            "--architecture-plan",
            str(plan_path),
            "--outdir",
            str(outdir),
            "--out",
            str(tournament_out),
        ],
    )

    assert result.exit_code == 2
    assert "candidate output already exists" in result.output
    assert not tournament_out.exists()
    assert not (outdir / "candidates" / "baseline_single_predict").exists()
    assert not (outdir / "candidate_intents").exists()


def test_program_architect_tournament_rejects_internal_output_path_before_materialization(
    tmp_path: Path,
) -> None:
    plan = build_program_architecture_candidates(
        ProgramIntent(
            name="InternalTournamentOutProgram",
            objective="Answer a question from context.",
            inputs=["question"],
            outputs=["answer"],
        )
    )
    plan_path = tmp_path / "architecture_plan.json"
    outdir = tmp_path / "tournament"
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")

    result = runner.invoke(
        app,
        [
            "program-architect",
            "tournament",
            "--architecture-plan",
            str(plan_path),
            "--outdir",
            str(outdir),
            "--out",
            str(outdir / "candidate_intents" / "baseline_single_predict.json"),
        ],
    )

    assert result.exit_code == 2
    assert "collides with internal tournament artifacts" in result.output
    assert not outdir.exists()


def test_program_architect_tournament_rejects_out_equal_to_outdir_before_materialization(
    tmp_path: Path,
) -> None:
    plan = build_program_architecture_candidates(
        ProgramIntent(
            name="TournamentOutdirCollisionProgram",
            objective="Answer a question from context.",
            inputs=["question"],
            outputs=["answer"],
        )
    )
    plan_path = tmp_path / "architecture_plan.json"
    outdir = tmp_path / "tournament"
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")

    result = runner.invoke(
        app,
        [
            "program-architect",
            "tournament",
            "--architecture-plan",
            str(plan_path),
            "--outdir",
            str(outdir),
            "--out",
            str(outdir),
        ],
    )

    assert result.exit_code == 2
    assert "collides with tournament outdir" in result.output
    assert not outdir.exists()


def test_program_architect_tournament_rejects_forbidden_output_before_materialization(
    tmp_path: Path,
) -> None:
    plan = build_program_architecture_candidates(
        ProgramIntent(
            name="ForbiddenTournamentOutProgram",
            objective="Answer a question from context.",
            inputs=["question"],
            outputs=["answer"],
        )
    )
    plan_path = tmp_path / "architecture_plan.json"
    outdir = tmp_path / "tournament"
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")

    result = runner.invoke(
        app,
        [
            "program-architect",
            "tournament",
            "--architecture-plan",
            str(plan_path),
            "--outdir",
            str(outdir),
            "--out",
            str(tmp_path / "manifest.json"),
        ],
    )

    assert result.exit_code == 2
    assert "refusing to write architecture tournament" in result.output
    assert not outdir.exists()


def test_program_architect_tournament_rejects_candidate_intents_file_without_materialization(
    tmp_path: Path,
) -> None:
    plan = build_program_architecture_candidates(
        ProgramIntent(
            name="CandidateIntentParentCollisionProgram",
            objective="Answer a question from context.",
            inputs=["question"],
            outputs=["answer"],
        )
    )
    plan_path = tmp_path / "architecture_plan.json"
    outdir = tmp_path / "tournament"
    candidate_intents = outdir / "candidate_intents"
    outdir.mkdir()
    candidate_intents.write_text("SENTINEL\n")
    tournament_out = tmp_path / "tournament.json"
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")

    result = runner.invoke(
        app,
        [
            "program-architect",
            "tournament",
            "--architecture-plan",
            str(plan_path),
            "--outdir",
            str(outdir),
            "--out",
            str(tournament_out),
            "--candidate",
            "baseline_single_predict",
        ],
    )

    assert result.exit_code == 2
    assert "candidate intents output path is not a directory" in result.output
    assert candidate_intents.read_text() == "SENTINEL\n"
    assert not (outdir / "candidates" / "baseline_single_predict").exists()
    assert not tournament_out.exists()


def test_program_architect_tournament_rejects_existing_candidate_intent_without_materialization(
    tmp_path: Path,
) -> None:
    plan = build_program_architecture_candidates(
        ProgramIntent(
            name="CandidateIntentCollisionProgram",
            objective="Answer a question from context.",
            inputs=["question"],
            outputs=["answer"],
        )
    )
    plan_path = tmp_path / "architecture_plan.json"
    outdir = tmp_path / "tournament"
    candidate_intent = outdir / "candidate_intents" / "baseline_single_predict.json"
    candidate_intent.parent.mkdir(parents=True)
    candidate_intent.write_text("SENTINEL\n")
    tournament_out = tmp_path / "tournament.json"
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")

    result = runner.invoke(
        app,
        [
            "program-architect",
            "tournament",
            "--architecture-plan",
            str(plan_path),
            "--outdir",
            str(outdir),
            "--out",
            str(tournament_out),
            "--candidate",
            "baseline_single_predict",
        ],
    )

    assert result.exit_code == 2
    assert "candidate intent output already exists" in result.output
    assert candidate_intent.read_text() == "SENTINEL\n"
    assert not (outdir / "candidates" / "baseline_single_predict").exists()
    assert not tournament_out.exists()


def test_program_architect_tournament_rejects_unknown_candidate_filter_without_partial_dirs(
    tmp_path: Path,
) -> None:
    plan = build_program_architecture_candidates(
        ProgramIntent(
            name="CandidateIdentityProgram",
            objective="Answer a question from context.",
            inputs=["question"],
            outputs=["answer"],
        )
    )
    plan_path = tmp_path / "architecture_plan.json"
    outdir = tmp_path / "tournament"
    tournament_out = tmp_path / "tournament.json"
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")

    result = runner.invoke(
        app,
        [
            "program-architect",
            "tournament",
            "--architecture-plan",
            str(plan_path),
            "--outdir",
            str(outdir),
            "--out",
            str(tournament_out),
            "--candidate",
            "typo_candidate",
        ],
    )

    assert result.exit_code == 2
    assert "unknown architecture candidate id" in result.output
    assert "typo_candidate" in result.output
    assert not tournament_out.exists()
    assert not outdir.exists()


def test_program_architect_tournament_rejects_materializable_candidate_missing_intent_payload_without_partial_dirs(
    tmp_path: Path,
) -> None:
    plan = build_program_architecture_candidates(
        ProgramIntent(
            name="IntegrityPreflightProgram",
            objective="Answer a question from context.",
            inputs=["question"],
            outputs=["answer"],
        )
    )
    materializable = next(
        candidate
        for candidate in plan["candidates"]
        if candidate["candidate_id"] == "baseline_single_predict"
    )
    materializable.pop("intent_payload")
    plan_path = tmp_path / "architecture_plan.json"
    outdir = tmp_path / "tournament"
    tournament_out = tmp_path / "tournament.json"
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")

    result = runner.invoke(
        app,
        [
            "program-architect",
            "tournament",
            "--architecture-plan",
            str(plan_path),
            "--outdir",
            str(outdir),
            "--out",
            str(tournament_out),
        ],
    )

    assert result.exit_code == 2
    assert "materializable candidate lacks intent_payload" in result.output
    assert not tournament_out.exists()
    assert not outdir.exists()


def test_program_architect_tournament_rejects_candidate_intent_hash_mismatch_without_partial_dirs(
    tmp_path: Path,
) -> None:
    plan = build_program_architecture_candidates(
        ProgramIntent(
            name="IntegrityPreflightProgram",
            objective="Answer a question from context.",
            inputs=["question"],
            outputs=["answer"],
        )
    )
    materializable = next(
        candidate
        for candidate in plan["candidates"]
        if candidate["candidate_id"] == "baseline_single_predict"
    )
    materializable["intent_hash"] = "not-the-real-hash"
    plan_path = tmp_path / "architecture_plan.json"
    outdir = tmp_path / "tournament"
    tournament_out = tmp_path / "tournament.json"
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")

    result = runner.invoke(
        app,
        [
            "program-architect",
            "tournament",
            "--architecture-plan",
            str(plan_path),
            "--outdir",
            str(outdir),
            "--out",
            str(tournament_out),
        ],
    )

    assert result.exit_code == 2
    assert "intent_hash mismatch" in result.output
    assert not tournament_out.exists()
    assert not outdir.exists()


def test_architecture_plan_portfolio_dogfoods_program_gen_and_replay(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    intent_path = tmp_path / "intent.yaml"
    plan_path = tmp_path / "architecture_plan.json"
    portfolio_dir = tmp_path / "portfolio"
    _write_intent(
        intent_path,
        "Route support tickets by classifying billing versus technical issues, then draft a helpful response with rationale.",
    )
    result = runner.invoke(
        app,
        [
            "program-architect",
            "plan",
            "--intent",
            str(intent_path),
            "--out",
            str(plan_path),
            "--portfolio-outdir",
            str(portfolio_dir),
        ],
    )
    assert result.exit_code == 0, result.output

    candidate_intent = (
        portfolio_dir / "candidate_intents" / "prompt_inferred_pipeline.json"
    )
    artifact = materialize_program_from_intent(
        ProgramIntent.model_validate(json.loads(candidate_intent.read_text())),
        outdir=tmp_path / "generated" / "prompt_inferred_pipeline",
    )
    root = Path(artifact.root_path)
    generated_surfaces = json.loads((root / "module_surfaces.json").read_text())
    planned = json.loads(plan_path.read_text())
    planned_inferred = next(
        candidate
        for candidate in planned["candidates"]
        if candidate["candidate_id"] == "prompt_inferred_pipeline"
    )

    assert generated_surfaces == planned_inferred["module_surface_preview"]
    assert check_run_receipt(root / "manifest.json.meta.json")["status"] == "ok"
