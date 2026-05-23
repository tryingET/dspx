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
            "Retriever": "explicit pipeline module with retriever.mode=inline_corpus only"
        },
        "unsupported_primitives_are_declared_only": True,
        "custom_imports_are_declarations_only": True,
        "external_tools_retrievers_and_react_are_not_bound_or_executed": True,
    }
    by_id = {item["capability_id"]: item for item in registry["builtin_capabilities"]}
    assert by_id["dspy.primitive.Predict"]["materializable"] is True
    assert by_id["dspy.primitive.ChainOfThought"]["materializable"] is True
    assert by_id["dspy.primitive.Retriever"]["materializable"] is False
    assert by_id["dspy.primitive.Retriever"]["conditional_materializable"] is True
    assert by_id["dspy.primitive.ReAct"]["materializable"] is False
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


def test_unsupported_primitive_contract_is_declared_only() -> None:
    contract = capability_contract_for_primitive("ReAct")

    assert contract["capability_id"] == "dspy.primitive.ReAct"
    assert contract["status"] == "declared_only_not_materializable"
    assert contract["materializable"] is False
    assert contract["materialization_policy"]["react_loop_allowed"] is False
    assert contract["effects"]["provider_called"] is False


def test_retriever_primitive_contract_requires_bounded_inline_adapter() -> None:
    contract = capability_contract_for_primitive("Retriever")

    assert contract["capability_id"] == "dspy.primitive.Retriever"
    assert contract["status"] == "conditionally_materializable_with_adapter"
    assert contract["materializable"] is False
    assert contract["conditional_materializable"] is True
    assert (
        contract["materialization_policy"]["bounded_inline_retriever_adapter_allowed"]
        is True
    )
    assert contract["materialization_policy"]["retriever_binding_allowed"] is False
    assert contract["effects"]["provider_called"] is False
