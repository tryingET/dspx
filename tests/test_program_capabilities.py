from __future__ import annotations

import json

import pytest

from dspx.services.program_capabilities import (
    build_program_capability_registry,
    capability_contract_for_primitive,
)
from dspx.services.program_intent import ProgramIntent


def test_builtin_capability_registry_is_descriptor_only_and_fail_closed() -> None:
    intent = ProgramIntent(
        name="CapabilityProgram",
        objective="Answer from context.",
        inputs=["context"],
        outputs=["answer"],
    )

    registry = build_program_capability_registry(intent)

    assert registry["schema_version"] == "program-capability-registry-v1"
    assert registry["status"] == "descriptor_only_no_runtime_binding"
    assert registry["materialization_policy"] == {
        "default": "fail_closed",
        "materializable_primitives": ["ChainOfThought", "Predict"],
        "conditional_materializable_primitives": {
            "ProgramOfThought": "explicit bounded materializable topology module with empty PythonInterpreter sandbox only",
            "ReAct": "explicit bounded materializable topology module with tools=[] and bounded max_iters only",
            "Retriever": "explicit bounded materializable topology module with retriever.mode=inline_corpus or local_corpus_snapshot only; local snapshots are normalized into generated inline adapters during materialization",
        },
        "experimental_primitives": {
            "ReActV2": "descriptor-only until DSPy 3.3 beta support is explicitly enabled behind generated policy and tool contracts"
        },
        "unsupported_primitives_are_declared_only": True,
        "custom_imports_are_declarations_only": True,
        "external_tools_retrievers_are_not_bound_or_executed": True,
        "react_materialization_requires_empty_tools": True,
        "program_of_thought_uses_empty_sandbox": True,
    }
    by_id = {item["capability_id"]: item for item in registry["builtin_capabilities"]}
    assert by_id["dspy.primitive.Predict"]["materializable"] is True
    assert by_id["dspy.primitive.ChainOfThought"]["materializable"] is True
    assert by_id["dspy.primitive.Retriever"]["materializable"] is False
    assert by_id["dspy.primitive.Retriever"]["conditional_materializable"] is True
    assert by_id["dspy.primitive.ReAct"]["materializable"] is False
    assert by_id["dspy.primitive.ReAct"]["conditional_materializable"] is True
    assert by_id["dspy.primitive.ReActV2"]["materializable"] is False
    assert by_id["dspy.primitive.ReActV2"]["experimental"] is True
    assert by_id["dspy.primitive.ReActV2"]["status"] == (
        "experimental_declared_only_not_materializable"
    )
    assert by_id["dspy.primitive.ProgramOfThought"]["materializable"] is False
    assert (
        by_id["dspy.primitive.ProgramOfThought"]["conditional_materializable"] is True
    )
    assert by_id["dspy.primitive.Custom"]["materializable"] is False
    assert registry["effects"] == {
        "provider_called": False,
        "tool_called": False,
        "custom_import_loaded": False,
        "network": False,
        "filesystem_read": False,
        "filesystem_write": False,
        "subprocess": False,
        "external_authority": False,
    }
    assert registry["non_authority"]["promotion_authority"] is False
    assert registry["non_authority"]["external_mutation"] is False
    assert json.dumps(registry, sort_keys=True)


def test_react_v2_topology_declaration_is_preserved_but_not_bound() -> None:
    intent = ProgramIntent(
        name="DeclaredReActV2Program",
        objective="Declare experimental ReActV2 without materializing it.",
        inputs=["question"],
        outputs=["answer"],
        topology={
            "kind": "custom",
            "execution_status": "declared_not_materialized",
            "modules": [
                {
                    "id": "agent",
                    "primitive": "react_v2",
                    "signature": {
                        "name": "DeclaredAgent",
                        "inputs": ["question"],
                        "outputs": ["answer"],
                    },
                    "tools": [],
                    "max_iters": 2,
                }
            ],
            "edges": [
                {"from": "input", "to": "agent"},
                {"from": "agent", "to": "output"},
            ],
        },
    )

    assert intent.topology["modules"][0]["primitive"] == "ReActV2"
    assert intent.topology["modules"][0]["react"] == {
        "tools": [],
        "max_iters": 2,
        "version": "v2",
        "status": "experimental_declared_only_not_materializable",
    }
    registry = build_program_capability_registry(intent)
    ref = registry["used_capability_refs"][0]
    assert ref["primitive"] == "ReActV2"
    assert ref["status"] == "experimental_declared_only_not_materializable"
    assert ref["materializable"] is False
    assert ref["runtime_binding"] == "none"


def test_capability_declarations_are_validated_but_not_bound() -> None:
    intent = ProgramIntent(
        name="RetrieverDeclaredProgram",
        objective="Answer with declared future retrieval.",
        inputs=["question"],
        outputs=["answer"],
        capabilities={
            "declarations": [
                {
                    "id": "local_docs",
                    "kind": "retriever",
                    "module": "dspx.local.docs",
                    "inputs": ["question"],
                    "outputs": ["passages"],
                },
                {
                    "id": "safe_helper",
                    "kind": "custom_import",
                    "import": "company.package.helper",
                },
            ]
        },
    )

    registry = build_program_capability_registry(intent)

    assert registry["declared_capabilities"][0]["id"] == "local_docs"
    assert registry["declared_capabilities"][0]["status"] == "declared_only_not_bound"
    assert registry["declared_capabilities"][0]["runtime_binding"] == "none"
    assert registry["declared_capabilities"][0]["effects"]["tool_called"] is False
    assert (
        registry["declared_capabilities"][1]["effects"]["custom_import_loaded"] is False
    )


@pytest.mark.parametrize(
    "capabilities",
    [
        {"declarations": [{"id": "bad-name", "kind": "tool"}]},
        {"declarations": [{"id": "tool_a", "kind": "network_tool"}]},
        {
            "declarations": [
                {"id": "tool_a", "kind": "custom_import", "import": "os.system;rm"}
            ]
        },
        {
            "declarations": [
                {"id": "dup", "kind": "tool"},
                {"id": "dup", "kind": "tool"},
            ]
        },
    ],
)
def test_capability_declarations_fail_closed(capabilities: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        ProgramIntent(
            name="InvalidCapabilityProgram",
            objective="Invalid capability declaration.",
            inputs=["question"],
            outputs=["answer"],
            capabilities=capabilities,
        )


@pytest.mark.parametrize(
    ("primitive", "policy_key"),
    [
        ("ReAct", "react_loop_allowed"),
        ("ProgramOfThought", "program_of_thought_allowed"),
    ],
)
def test_bounded_reasoning_primitive_contracts_are_conditionally_materializable(
    primitive: str, policy_key: str
) -> None:
    contract = capability_contract_for_primitive(primitive)

    assert contract["capability_id"] == f"dspy.primitive.{primitive}"
    assert contract["status"] == "conditionally_materializable_with_adapter"
    assert contract["materializable"] is False
    assert contract["conditional_materializable"] is True
    assert contract["materialization_policy"][policy_key] is True
    assert contract["allowed_topology_kinds"] == [
        "pipeline",
        "router",
        "retrieve_then_answer",
        "extract_transform_validate",
        "generate_critique_revise",
    ]
    assert contract["effects"]["provider_called"] is False


def test_react_v2_primitive_contract_is_experimental_declared_only() -> None:
    contract = capability_contract_for_primitive("react_v2")

    assert contract["capability_id"] == "dspy.primitive.ReActV2"
    assert contract["status"] == "experimental_declared_only_not_materializable"
    assert contract["materializable"] is False
    assert contract["conditional_materializable"] is False
    assert contract["experimental"] is True
    assert contract["allowed_topology_kinds"] == ["custom"]
    assert contract["materialization_policy"]["react_v2_declared_only"] is True
    assert contract["materialization_policy"]["react_v2_tool_binding_allowed"] is False
    assert contract["effects"]["tool_called"] is False


def test_retriever_primitive_contract_requires_bounded_inline_adapter() -> None:
    contract = capability_contract_for_primitive("Retriever")

    assert contract["capability_id"] == "dspy.primitive.Retriever"
    assert contract["status"] == "conditionally_materializable_with_adapter"
    assert contract["materializable"] is False
    assert contract["conditional_materializable"] is True
    assert contract["allowed_topology_kinds"] == [
        "pipeline",
        "router",
        "retrieve_then_answer",
        "extract_transform_validate",
        "generate_critique_revise",
    ]
    assert (
        contract["materialization_policy"]["bounded_inline_retriever_adapter_allowed"]
        is True
    )
    assert (
        contract["materialization_policy"]["local_corpus_snapshot_adapter_allowed"]
        is True
    )
    assert (
        contract["materialization_policy"]["live_external_retriever_binding_allowed"]
        is False
    )
    assert contract["materialization_policy"]["retriever_binding_allowed"] is False
    assert contract["effects"]["provider_called"] is False
