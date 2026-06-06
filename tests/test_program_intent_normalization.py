from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dspx.cache import sha256_text
from dspx.cli.dspx import app
from dspx.services.program_architecture import build_program_architecture_candidates
from dspx.services.program_intent import ProgramIntent, load_program_intent
from dspx.services.program_intent_normalization import (
    build_program_intent_normalization,
    normalize_program_intent_from_prompt,
)

runner = CliRunner()


def _support_by_name(payload: dict, bucket: str) -> dict[str, dict]:
    return {
        item["name"]: item
        for item in payload["support_level_preview"]["classifications"][bucket]
    }


def test_prompt_normalization_emits_valid_intent_hints_and_missing_evidence() -> None:
    payload = normalize_program_intent_from_prompt(
        "Route support tickets by classifying billing versus technical issues, then draft a helpful response with rationale."
    )

    assert payload["schema_version"] == "program-intent-normalization-v1"
    assert payload["status"] == "normalized"
    intent = ProgramIntent.model_validate(payload["normalized_intent"])
    assert intent.inputs == ["ticket_text"]
    assert intent.outputs == ["response"]
    assert intent.examples == []
    assert {item["kind"] for item in payload["missing_evidence"]} >= {
        "examples",
        "dataset",
    }
    assert [hint["hint"] for hint in payload["topology_hints"]] == [
        "route_then_generate",
        "reasoned_single_module",
    ]
    assert [hint["primitive"] for hint in payload["primitive_hints"]] == [
        "Predict",
        "ChainOfThought",
    ]
    preview = payload["generation_assumptions_preview"]
    assert preview["schema_version"] == "program-generation-assumptions-preview-v1"
    assert [candidate["kind"] for candidate in preview["topology_candidates"]] == [
        "router"
    ]
    assert preview["capability_boundaries"]["tools"]["enabled"] is False
    support_preview = payload["support_level_preview"]
    assert support_preview["schema_version"] == "program-support-level-preview-v1"
    assert [item["level"] for item in support_preview["taxonomy"]] == [
        "descriptor_only",
        "local_dry_run_evaluation",
        "executable_local",
        "production_activation",
    ]
    primitive_support = _support_by_name(payload, "primitives")
    assert primitive_support["Predict"]["support_level"] == "executable_local"
    assert primitive_support["ChainOfThought"]["support_level"] == "executable_local"
    topology_support = _support_by_name(payload, "topology_candidates")
    assert topology_support["router"]["support_level"] == "executable_local"
    production = support_preview["classifications"]["production_activation"]
    assert production["in_scope"] is False
    assert production["materialization_effects_allowed"] is False
    assert support_preview["effect"]["authority_mutated"] is False
    assert payload["effect"]["program_materialized"] is False
    assert payload["effect"]["provider_called"] is False
    assert payload["effect"]["oracle_index_mutated"] is False
    assert payload["non_authority"]["normalization_only"] is True
    assert payload["non_authority"]["winner_selection"] is False


def test_prompt_normalization_surfaces_unsupported_primitive_risk() -> None:
    payload = normalize_program_intent_from_prompt(
        "Use retrieval and ReAct tools to answer the question from documents.",
        inputs=["question", "document_text"],
        outputs=["answer"],
    )

    primitive_hints = payload["primitive_hints"]
    assert any(hint["primitive"] == "Retriever" for hint in primitive_hints)
    assert any(hint["primitive"] == "ReAct" for hint in primitive_hints)
    preview = payload["generation_assumptions_preview"]
    assert {candidate["kind"] for candidate in preview["topology_candidates"]} >= {
        "retrieve_then_answer",
        "ReAct",
    }
    assert preview["capability_boundaries"]["tools"] == {
        "need_detected": True,
        "enabled": False,
        "status": "disabled_descriptor_only",
        "boundary": "Tool declarations may be recorded, but dspy.Tool/live tool execution is not bound by program-gen.",
    }
    assert preview["capability_boundaries"]["react"]["requested"] is True
    assert preview["capability_boundaries"]["react_v2"]["requested"] is False
    assert preview["capability_boundaries"]["react_v2"]["tools_enabled"] is False
    assert preview["capability_boundaries"]["retrievers"]["need_detected"] is True
    assert any(
        risk["kind"] == "unsupported_primitive" for risk in payload["generation_risks"]
    )
    primitive_support = _support_by_name(payload, "primitives")
    assert primitive_support["Retriever"]["support_level"] == "descriptor_only"
    assert primitive_support["ReAct"]["support_level"] == "descriptor_only"
    assert primitive_support["ReAct"]["blockers"]
    feature_support = _support_by_name(payload, "features")
    assert feature_support["tools"]["support_level"] == "descriptor_only"
    assert feature_support["retrievers"]["support_level"] == "descriptor_only"
    assert all(
        not item["materialization_effects_allowed"]
        for item in [feature_support["tools"], feature_support["retrievers"]]
    )
    intent = ProgramIntent.model_validate(payload["normalized_intent"])
    assert intent.inputs == ["question", "document_text"]
    assert intent.outputs == ["answer"]


def test_generation_assumptions_preview_uses_capability_declarations() -> None:
    intent = ProgramIntent(
        name="CapabilityDeclaredProgram",
        objective="Answer the question.",
        inputs=["question"],
        outputs=["answer"],
        capabilities={
            "declarations": [
                {
                    "id": "docs",
                    "kind": "retriever",
                    "module": "company.safe.docs",
                },
                {
                    "id": "agent",
                    "kind": "dspy_primitive",
                    "primitive": "ReActV2",
                },
            ]
        },
    )

    payload = build_program_intent_normalization(
        intent, source={"kind": "test", "content_hash": "sha256:test"}
    )

    preview = payload["generation_assumptions_preview"]
    by_kind = {
        candidate["kind"]: candidate for candidate in preview["topology_candidates"]
    }
    assert {"retrieve_then_answer", "ReActV2"}.issubset(by_kind)
    assert "single_module" not in by_kind
    assert by_kind["retrieve_then_answer"]["materializable_now"] is False
    assert by_kind["ReActV2"]["materializable_now"] is False
    assert preview["capability_boundaries"]["retrievers"]["need_detected"] is True
    assert preview["capability_boundaries"]["react_v2"]["requested"] is True


def test_generation_assumptions_preview_recognizes_spaced_react_v2() -> None:
    payload = normalize_program_intent_from_prompt(
        "Use ReAct V2 tools to answer the question.",
        inputs=["question"],
        outputs=["answer"],
    )

    assert any(hint["primitive"] == "ReActV2" for hint in payload["primitive_hints"])
    assert not any(hint["primitive"] == "ReAct" for hint in payload["primitive_hints"])
    preview = payload["generation_assumptions_preview"]
    by_kind = {
        candidate["kind"]: candidate for candidate in preview["topology_candidates"]
    }
    assert "ReActV2" in by_kind
    assert "ReAct" not in by_kind
    assert by_kind["ReActV2"]["materializable_now"] is False
    assert preview["capability_boundaries"]["react"]["requested"] is False
    assert preview["capability_boundaries"]["react_v2"]["requested"] is True
    assert preview["capability_boundaries"]["react_v2"]["tool_need_detected"] is True


def test_generation_assumptions_preview_keeps_react_v2_declared_only() -> None:
    intent = ProgramIntent(
        name="DeclaredReactV2Program",
        objective="Declare a ReActV2 agent.",
        inputs=["question"],
        outputs=["answer"],
        topology={
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
                    "tools": [],
                    "max_iters": 1,
                }
            ],
            "edges": [
                {"from": "input", "to": "agent"},
                {"from": "agent", "to": "output"},
            ],
        },
    )

    payload = build_program_intent_normalization(
        intent, source={"kind": "test", "content_hash": "sha256:test"}
    )

    by_kind = {
        candidate["kind"]: candidate
        for candidate in payload["generation_assumptions_preview"][
            "topology_candidates"
        ]
    }
    assert by_kind["pipeline"]["materializable_now"] is False
    assert by_kind["ReActV2"]["materializable_now"] is False


def test_generation_assumptions_preview_surfaces_pot_custom_boundaries() -> None:
    intent = ProgramIntent(
        name="CustomProgramOfThoughtProgram",
        objective="Use ProgramOfThought with a custom imported calculator module to compute an answer.",
        inputs=["question"],
        outputs=["answer"],
        capabilities={
            "declarations": [
                {
                    "id": "calculator",
                    "kind": "custom_import",
                    "import": "company.safe.calculator",
                }
            ]
        },
    )

    payload = build_program_intent_normalization(
        intent, source={"kind": "test", "content_hash": "sha256:test"}
    )

    preview = payload["generation_assumptions_preview"]
    assert {candidate["kind"] for candidate in preview["topology_candidates"]} >= {
        "ProgramOfThought",
        "custom",
    }
    assert preview["capability_boundaries"]["program_of_thought"] == {
        "requested": True,
        "sandbox": "empty",
        "status": "empty_sandbox_boundary",
        "boundary": "No filesystem, network, env vars, tools, or sync files are exposed.",
    }
    assert (
        preview["capability_boundaries"]["custom_modules"]["imports_enabled"] is False
    )
    assert any(
        item["feature"] == "custom_modules" and item["status"] == "blocked_policy_only"
        for item in preview["unsupported_or_preserved_declared_only_features"]
    )


def test_explicit_bounded_retriever_normalization_is_not_reported_unsupported() -> None:
    intent = ProgramIntent(
        name="RetrieveThenAnswerProgram",
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
                        "documents": [{"id": "doc", "text": "Billing invoices."}],
                    },
                },
                {
                    "id": "answer_question",
                    "primitive": "ChainOfThought",
                    "signature": {
                        "name": "AnswerQuestion",
                        "inputs": ["question", "passages"],
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

    payload = build_program_intent_normalization(
        intent, source={"kind": "test", "content_hash": "sha256:test"}
    )

    retriever_hints = [
        hint for hint in payload["primitive_hints"] if hint["primitive"] == "Retriever"
    ]
    assert retriever_hints
    assert all(
        hint["status"] == "conditionally_materializable_with_bounded_inline_adapter"
        for hint in retriever_hints
    )
    assert not any(
        risk["kind"] == "unsupported_primitive" for risk in payload["generation_risks"]
    )
    primitive_support = _support_by_name(payload, "primitives")
    assert primitive_support["Retriever"]["support_level"] == "executable_local"
    assert primitive_support["Retriever"]["materialization_effects_allowed"] is True
    assert primitive_support["Retriever"]["safe_next_actions"]


def test_normalize_intent_cli_writes_sidecar_and_loadable_intent(
    tmp_path: Path,
) -> None:
    sidecar_path = tmp_path / "normalization.json"
    intent_path = tmp_path / "normalized_intent.json"

    result = runner.invoke(
        app,
        [
            "program-gen",
            "normalize-intent",
            "--prompt",
            "Review evidence and explain the strongest recommendation.",
            "--input",
            "evidence",
            "--output",
            "recommendation",
            "--out",
            str(sidecar_path),
            "--normalized-intent-out",
            str(intent_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
    stdout_payload = json.loads(result.output)
    assert stdout_payload == payload
    without_artifact = dict(payload)
    artifact = dict(without_artifact.pop("artifact"))
    assert artifact["payload_hash_excluding_artifact"] == sha256_text(
        json.dumps(without_artifact, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    )
    loaded = load_program_intent(intent_path)
    assert loaded.inputs == ["evidence"]
    assert loaded.outputs == ["recommendation"]
    assert payload["normalized_intent_artifact"]["path"] == str(intent_path.resolve())
    assert payload["effect"]["normalized_intent_written"] is True
    assert not (tmp_path / "manifest.json").exists()
    assert not (tmp_path / "program.py").exists()
    assert not (tmp_path / "oracle" / "coordinates.db").exists()


def test_normalized_intent_feeds_architecture_plan_without_materialization(
    tmp_path: Path,
) -> None:
    sidecar_path = tmp_path / "normalization.json"
    intent_path = tmp_path / "normalized_intent.json"
    plan_path = tmp_path / "architecture_plan.json"

    normalize_result = runner.invoke(
        app,
        [
            "program-gen",
            "normalize-intent",
            "--prompt",
            "Route support tickets by classifying billing versus technical issues, then draft a helpful response with rationale.",
            "--out",
            str(sidecar_path),
            "--normalized-intent-out",
            str(intent_path),
        ],
    )
    assert normalize_result.exit_code == 0, normalize_result.output

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
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    assert plan["schema_version"] == "program-architecture-candidates-v1"
    assert plan["recommended_candidate_id"] == "prompt_inferred_pipeline"
    assert plan["effect"]["candidate_materialized"] is False
    assert not (tmp_path / "manifest.json").exists()
    assert not (tmp_path / "program.py").exists()
    assert (
        build_program_architecture_candidates(load_program_intent(intent_path))[
            "recommended_candidate_id"
        ]
        == "prompt_inferred_pipeline"
    )


def test_normalize_intent_cli_requires_exactly_one_source(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "program-gen",
            "normalize-intent",
            "--out",
            str(tmp_path / "normalization.json"),
        ],
    )

    assert result.exit_code == 2
    assert "exactly one" in result.output


def _topology_intent(topology: dict) -> dict:
    return {
        "name": "TopologyContractProgram",
        "objective": "Validate a declared topology contract.",
        "inputs": ["question"],
        "outputs": ["answer"],
        "topology": topology,
    }


def test_program_intent_topology_contract_rejects_missing_final_output_producer() -> (
    None
):
    with pytest.raises(ValueError, match="final-output producer"):
        ProgramIntent.model_validate(
            _topology_intent(
                {
                    "kind": "pipeline",
                    "execution_status": "declared_not_materialized",
                    "modules": [
                        {
                            "id": "answer_question",
                            "primitive": "ChainOfThought",
                            "signature": {
                                "name": "AnswerQuestion",
                                "inputs": ["question"],
                                "outputs": ["answer"],
                            },
                        }
                    ],
                    "edges": [{"from": "input", "to": "answer_question"}],
                }
            )
        )


def test_program_intent_topology_contract_rejects_disconnected_modules() -> None:
    with pytest.raises(ValueError, match="disconnected"):
        ProgramIntent.model_validate(
            _topology_intent(
                {
                    "kind": "pipeline",
                    "execution_status": "declared_not_materialized",
                    "modules": [
                        {
                            "id": "extract_question",
                            "primitive": "Predict",
                            "signature": {
                                "name": "ExtractQuestion",
                                "inputs": ["question"],
                                "outputs": ["extracted_question"],
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
                        {"from": "input", "to": "answer_question"},
                        {"from": "answer_question", "to": "output"},
                    ],
                }
            )
        )


def test_program_intent_topology_contract_rejects_cycles() -> None:
    with pytest.raises(ValueError, match="acyclic"):
        ProgramIntent.model_validate(
            _topology_intent(
                {
                    "kind": "pipeline",
                    "execution_status": "declared_not_materialized",
                    "modules": [
                        {
                            "id": "draft_answer",
                            "primitive": "ChainOfThought",
                            "signature": {
                                "name": "DraftAnswer",
                                "inputs": ["question"],
                                "outputs": ["draft"],
                            },
                        },
                        {
                            "id": "revise_answer",
                            "primitive": "ChainOfThought",
                            "signature": {
                                "name": "ReviseAnswer",
                                "inputs": ["question", "draft"],
                                "outputs": ["answer"],
                            },
                        },
                    ],
                    "edges": [
                        {"from": "input", "to": "draft_answer"},
                        {"from": "draft_answer", "to": "revise_answer"},
                        {"from": "revise_answer", "to": "draft_answer"},
                        {"from": "revise_answer", "to": "output"},
                    ],
                }
            )
        )


def test_program_intent_topology_contract_accepts_fan_in_dag() -> None:
    intent = ProgramIntent.model_validate(
        _topology_intent(
            {
                "kind": "generate_critique_revise",
                "execution_status": "declared_not_materialized",
                "modules": [
                    {
                        "id": "generate_draft",
                        "primitive": "ChainOfThought",
                        "signature": {
                            "name": "GenerateDraft",
                            "inputs": ["question"],
                            "outputs": ["draft"],
                        },
                    },
                    {
                        "id": "critique_draft",
                        "primitive": "ChainOfThought",
                        "signature": {
                            "name": "CritiqueDraft",
                            "inputs": ["question", "draft"],
                            "outputs": ["critique"],
                        },
                    },
                    {
                        "id": "revise_final",
                        "primitive": "ChainOfThought",
                        "signature": {
                            "name": "ReviseFinal",
                            "inputs": ["question", "draft", "critique"],
                            "outputs": ["answer"],
                        },
                    },
                ],
                "edges": [
                    {"from": "input", "to": "generate_draft"},
                    {"from": "generate_draft", "to": "critique_draft"},
                    {"from": "generate_draft", "to": "revise_final"},
                    {"from": "critique_draft", "to": "revise_final"},
                    {"from": "revise_final", "to": "output"},
                ],
            }
        )
    )

    assert intent.topology["kind"] == "generate_critique_revise"
    assert intent.topology["edges"][-1] == {"from": "revise_final", "to": "output"}
