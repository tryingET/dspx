from __future__ import annotations

from dspx.dtos import ModuleSpec
from dspx.synthesis import (
    build_module_synthesis_bundle,
    build_module_synthesis_request,
    module_spec_to_ir,
)


def test_module_spec_to_ir_preserves_structure() -> None:
    spec = ModuleSpec(
        name="Retriever",
        description="Retrieve the best answer",
        inputs=["question", "context"],
        outputs=["answer"],
        options={"template_version": "simple-v1", "temperature": 0},
    )

    ir = module_spec_to_ir(spec, use_signature=True)

    assert ir.kind == "module"
    assert [field.name for field in ir.inputs] == ["question", "context"]
    assert [field.role for field in ir.inputs] == ["input", "input"]
    assert [field.ordinal for field in ir.inputs] == [0, 1]
    assert [field.name for field in ir.outputs] == ["answer"]
    assert ir.use_signature is True
    assert ir.template_version == "simple-v1"
    assert ir.options["temperature"] == 0


def test_build_module_synthesis_request_is_stable_contract_shell() -> None:
    spec = ModuleSpec(
        name="Summarizer",
        description="Summarizes text",
        inputs=["text"],
        outputs=["summary"],
        options={"template_version": "simple-v1"},
    )

    request = build_module_synthesis_request(spec, use_signature=False)

    assert request.request_id.startswith("sreq-")
    assert request.artifact_kind == "module"
    assert request.source_command == "module-gen"
    assert request.strategy_id == "module.single_candidate.template"
    assert request.constraints["preserve_cli_surface"] is True
    assert request.options["template_version"] == "simple-v1"
    assert request.spec.inputs[0].name == "text"


def test_build_module_synthesis_bundle_exposes_candidate_evaluation_policy_and_promotion() -> (
    None
):
    spec = ModuleSpec(
        name="Classifier",
        description="Classify incoming text",
        inputs=["text"],
        outputs=["label"],
        options={"template_version": "simple-v1"},
    )

    bundle = build_module_synthesis_bundle(
        spec,
        code="class Classifier: ...\n",
        use_signature=False,
    )

    assert bundle.request.request_id.startswith("sreq-")
    assert len(bundle.candidates) == 1
    assert bundle.candidates[0].candidate_id.startswith("cand-")
    assert bundle.candidates[0].request_id == bundle.request.request_id
    assert bundle.evaluations[0].candidate_id == bundle.candidates[0].candidate_id
    assert bundle.evaluations[0].status == "pending"
    assert bundle.selection_policy.mode == "single_best"
    assert bundle.promotion_decision.outcome == "withheld"
    assert bundle.promotion_decision.candidate_id == bundle.candidates[0].candidate_id

    dumped = bundle.model_dump(mode="json")
    assert dumped["request"]["spec"]["name"] == "Classifier"
    assert (
        dumped["selection_policy"]["metadata"]["promote_without_evaluations"] is False
    )
