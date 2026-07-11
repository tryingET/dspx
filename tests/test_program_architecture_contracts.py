# summary: "Tests architecture contract drafts and verification for bounded retrievers, ReActV2, and tool references."
# read_when:
#   - "Changing architecture contract drafting, verification gates, or bounded capability policies."

from __future__ import annotations

import json
from pathlib import Path


from dspx.services.program_architecture import (
    ProgramArchitectureError,
    build_program_architecture_candidates,
    verify_architecture_contract_intent,
    write_architecture_contract_drafts,
    write_architecture_intent_portfolio,
)
from dspx.services.program_intent import ProgramIntent


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
