# summary: "Tests module synthesis IR, request and bundle contracts, workspace evidence, ranking, and selected-candidate promotion."
# read_when:
#   - "You are changing module synthesis contracts, candidate materialization, evaluation lineage, selection, or promotion mechanics."

from __future__ import annotations

from pathlib import Path
import json

import pytest

from dspx.dtos import ModuleSpec
from dspx.synthesis import (
    build_module_synthesis_bundle,
    build_module_synthesis_request,
    execute_module_synthesis_bundle,
    materialize_module_synthesis_bundle,
    module_spec_to_ir,
    module_synthesis_run_summary,
    promote_selected_module_candidate,
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
    ranked_request = build_module_synthesis_request(
        spec,
        use_signature=False,
        candidate_budget=3,
    )

    assert request.request_id.startswith("sreq-")
    assert request.artifact_kind == "module"
    assert request.source_command == "module-gen"
    assert request.strategy_id == "module.single_candidate.template"
    assert request.constraints["preserve_cli_surface"] is True
    assert request.options["template_version"] == "simple-v1"
    assert request.spec.inputs[0].name == "text"

    assert ranked_request.strategy_id == "module.multi_candidate.template"
    assert ranked_request.constraints["candidate_budget"] == 3


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
    assert bundle.strategy is not None
    assert bundle.strategy.strategy_id == bundle.request.strategy_id
    assert len(bundle.candidates) == 1
    assert bundle.candidates[0].candidate_id.startswith("cand-")
    assert bundle.candidates[0].request_id == bundle.request.request_id
    assert bundle.evaluations[0].candidate_id == bundle.candidates[0].candidate_id
    assert bundle.evaluations[0].status == "pending"
    assert bundle.candidate_assemblies == []
    assert bundle.execution_episodes == []
    assert bundle.receipt_bundles == []
    assert bundle.selection_policy.mode == "single_best"
    assert bundle.promotion_decision.outcome == "withheld"
    assert bundle.promotion_decision.candidate_id == bundle.candidates[0].candidate_id
    assert bundle.promotion_shell is None

    dumped = bundle.model_dump(mode="json")
    assert dumped["request"]["spec"]["name"] == "Classifier"
    assert (
        dumped["selection_policy"]["metadata"]["promote_without_evaluations"] is False
    )


def test_materialize_module_synthesis_bundle_persists_strategy_and_workspace(
    tmp_path: Path,
) -> None:
    spec = ModuleSpec(
        name="Planner",
        description="Plan the next action",
        inputs=["goal"],
        outputs=["plan"],
        options={"template_version": "simple-v1"},
    )

    bundle = materialize_module_synthesis_bundle(
        spec,
        code="class Planner: ...\n",
        use_signature=True,
        workspace_root=tmp_path / "synthesis-root",
    )

    assert bundle.strategy is not None
    assert bundle.strategy.metadata["workspace_mode"] == "scratch"
    assert len(bundle.candidate_workspaces) == 1
    assert len(bundle.candidate_assemblies) == 1
    assert len(bundle.execution_episodes) == 1
    assert len(bundle.receipt_bundles) == 1
    workspace = bundle.candidate_workspaces[0]
    assembly = bundle.candidate_assemblies[0]
    execution_episode = bundle.execution_episodes[0]
    receipt_bundle = bundle.receipt_bundles[0]
    assert Path(workspace.artifact_path).exists()
    assert Path(workspace.manifest_path).exists()
    manifest = json.loads(Path(workspace.manifest_path).read_text(encoding="utf-8"))
    assert manifest["strategy"]["strategy_id"] == bundle.request.strategy_id
    assert manifest["candidate"]["candidate_id"] == bundle.candidates[0].candidate_id
    assert manifest["candidate_assembly"]["assembly_id"] == assembly.assembly_id
    assert manifest["execution_episode"]["episode_id"] == execution_episode.episode_id
    assert (
        manifest["receipt_bundle"]["receipt_bundle_id"]
        == receipt_bundle.receipt_bundle_id
    )
    assert bundle.candidates[0].metadata["workspace_id"] == workspace.workspace_id
    assert bundle.candidates[0].metadata["assembly_id"] == assembly.assembly_id
    assert (
        bundle.candidates[0].metadata["execution_episode_id"]
        == execution_episode.episode_id
    )
    assert (
        bundle.candidates[0].metadata["receipt_bundle_id"]
        == receipt_bundle.receipt_bundle_id
    )
    assert bundle.promotion_shell is not None
    assert bundle.promotion_shell.target_path is not None
    assert bundle.promotion_shell.target_path.endswith("Planner.py")
    assert bundle.promotion_shell.selected_candidate_id is None
    assert (
        bundle.promotion_decision.metadata["promotion_shell_id"]
        == bundle.promotion_shell.shell_id
    )


def test_execute_module_synthesis_bundle_validates_and_promotes_runtime_path(
    tmp_path: Path,
) -> None:
    spec = ModuleSpec(
        name="Judge",
        description="Judge candidate quality",
        inputs=["text"],
        outputs=["verdict"],
        options={"template_version": "simple-v1"},
    )

    bundle = execute_module_synthesis_bundle(
        spec,
        candidate_sources=[
            {
                "code": (
                    "import dspy\n\n"
                    "class Judge(dspy.Module):\n"
                    "    def __init__(self, use_cot: bool = False) -> None:\n"
                    "        super().__init__()\n"
                    "        self.predict = dspy.Predict('text -> verdict')\n\n"
                    "    def forward(self, text: str) -> dspy.Prediction:\n"
                    "        pred = self.predict(text=text)\n"
                    "        return pred\n\n"
                    "def build_student(*, use_cot: bool = False) -> dspy.Module:\n"
                    "    return Judge(use_cot=use_cot)\n\n"
                    "def io_spec() -> dict[str, list[str]]:\n"
                    "    return {'inputs': ['text'], 'outputs': ['verdict']}\n\n"
                    "def output_weights() -> dict[str, float]:\n"
                    "    return {'verdict': 1.0}\n\n"
                    "def normalize_output(key: str, gold: str, pred: str, pred_name: str | None = None, pred_trace: object | None = None) -> tuple[str, str]:\n"
                    "    return gold, pred\n"
                ),
                "candidate_metadata": {
                    "variant_id": "baseline",
                    "variant_label": "Baseline",
                    "selection_bonus": 1.0,
                    "selection_basis": "Control candidate",
                },
            },
            {
                "code": (
                    "import dspy\n\n"
                    "# Ranked synthesis candidate\n"
                    "class Judge(dspy.Module):\n"
                    "    def __init__(self, use_cot: bool = False) -> None:\n"
                    "        super().__init__()\n"
                    "        self.predict = dspy.Predict('text -> verdict')\n\n"
                    "    def forward(self, text: str) -> dspy.Prediction:\n"
                    "        pred = self.predict(text=text)\n"
                    "        return pred\n\n"
                    "def build_student(*, use_cot: bool = False) -> dspy.Module:\n"
                    '    """Construct the generated module for runtime selection."""\n'
                    "    return Judge(use_cot=use_cot)\n\n"
                    "def io_spec() -> dict[str, list[str]]:\n"
                    '    """Return the declared module IO contract."""\n'
                    "    return {'inputs': ['text'], 'outputs': ['verdict']}\n\n"
                    "def output_weights() -> dict[str, float]:\n"
                    '    """Provide deterministic output weighting for evaluation."""\n'
                    "    return {'verdict': 1.0}\n\n"
                    "def normalize_output(key: str, gold: str, pred: str, pred_name: str | None = None, pred_trace: object | None = None) -> tuple[str, str]:\n"
                    "    return gold, pred\n"
                ),
                "candidate_metadata": {
                    "variant_id": "explainable",
                    "variant_label": "Explainable",
                    "selection_bonus": 3.0,
                    "selection_basis": "Prefer explainable helper scaffolds.",
                },
            },
        ],
        workspace_root=tmp_path / "scratch",
        promotion_target=tmp_path / "final" / "Judge.py",
    )

    out = tmp_path / "final" / "Judge.py"
    assert out.exists()
    assert len(bundle.candidates) == 2
    assert all(item.status in {"rendered", "promoted"} for item in bundle.candidates)
    assert bundle.evaluations[0].evidence["phase"] == "AK-256"
    assert sum(1 for item in bundle.evaluations if item.status == "passed") == 2
    assert bundle.promotion_shell is not None
    assert bundle.promotion_shell.status == "promoted"
    assert bundle.promotion_decision.outcome == "promoted"
    ranked = bundle.promotion_decision.metadata["ranked_candidates"]
    assert len(ranked) == 2
    assert ranked[0]["rank"] == 1
    assert ranked[0]["candidate_id"] == bundle.promotion_decision.candidate_id
    assert ranked[0]["assembly_id"] is not None
    assert ranked[0]["execution_episode_id"] is not None
    assert ranked[0]["receipt_bundle_id"] is not None
    assert bundle.promotion_decision.metadata["promoted_path"] == str(out.resolve())

    summary = module_synthesis_run_summary(bundle)
    assert summary["runtime_spine_version"] == "v1"
    assert summary["assembly_count"] == 2
    assert summary["execution_episode_count"] == 2
    assert summary["receipt_bundle_count"] == 2
    assert summary["selected_assembly_id"] is not None
    assert summary["selected_execution_episode_id"] is not None
    assert summary["selected_receipt_bundle_id"] is not None

    promoted_workspace = next(
        workspace
        for workspace in bundle.candidate_workspaces
        if workspace.candidate_id == bundle.promotion_decision.candidate_id
    )
    manifest = json.loads(
        Path(promoted_workspace.manifest_path).read_text(encoding="utf-8")
    )
    assert manifest["candidate"]["status"] == "promoted"
    assert manifest["candidate_assembly"]["status"] == "promoted"
    assert manifest["execution_episode"]["status"] == "promoted"
    assert manifest["receipt_bundle"]["status"] == "promoted"


def test_promote_selected_module_candidate_copies_only_selected_output(
    tmp_path: Path,
) -> None:
    spec = ModuleSpec(
        name="Judge",
        description="Judge candidate quality",
        inputs=["text"],
        outputs=["verdict"],
        options={"template_version": "simple-v1"},
    )
    bundle = materialize_module_synthesis_bundle(
        spec,
        code="class Judge: ...\n",
        workspace_root=tmp_path / "scratch",
    )
    evaluated = bundle.model_copy(
        update={
            "candidates": [
                bundle.candidates[0].model_copy(update={"status": "selected"})
            ],
            "evaluations": [
                bundle.evaluations[0].model_copy(update={"status": "passed"})
            ],
            "promotion_shell": bundle.promotion_shell.model_copy(
                update={"selected_candidate_id": bundle.candidates[0].candidate_id}
            )
            if bundle.promotion_shell is not None
            else None,
            "promotion_decision": bundle.promotion_decision.model_copy(
                update={"candidate_id": bundle.candidates[0].candidate_id}
            ),
        }
    )

    promoted = promote_selected_module_candidate(
        evaluated,
        target_path=tmp_path / "final" / "Judge.py",
    )

    out = tmp_path / "final" / "Judge.py"
    assert out.exists()
    assert out.read_text(encoding="utf-8") == "class Judge: ...\n"
    assert promoted.candidates[0].status == "promoted"
    assert promoted.candidate_workspaces[0].status == "promoted"
    assert promoted.candidate_assemblies[0].status == "promoted"
    assert promoted.execution_episodes[0].status == "promoted"
    assert promoted.receipt_bundles[0].status == "promoted"
    assert promoted.promotion_shell is not None
    assert promoted.promotion_shell.status == "promoted"
    assert promoted.promotion_decision.outcome == "promoted"
    assert promoted.promotion_decision.metadata["promoted_path"] == str(out.resolve())


def test_promote_selected_module_candidate_rejects_non_selected_candidate(
    tmp_path: Path,
) -> None:
    spec = ModuleSpec(
        name="Judge",
        description="Judge candidate quality",
        inputs=["text"],
        outputs=["verdict"],
        options={"template_version": "simple-v1"},
    )
    code_good = (
        "import dspy\n\n"
        "class Judge(dspy.Module):\n"
        "    def __init__(self, use_cot: bool = False) -> None:\n"
        "        super().__init__()\n"
        "        self.predict = dspy.Predict('text -> verdict')\n\n"
        "    def forward(self, text: str) -> dspy.Prediction:\n"
        "        pred = self.predict(text=text)\n"
        "        return pred\n\n"
        "def build_student(*, use_cot: bool = False) -> dspy.Module:\n"
        "    return Judge(use_cot=use_cot)\n\n"
        "def io_spec() -> dict[str, list[str]]:\n"
        "    return {'inputs': ['text'], 'outputs': ['verdict']}\n\n"
        "def output_weights() -> dict[str, float]:\n"
        "    return {'verdict': 1.0}\n\n"
        "def normalize_output(key: str, gold: str, pred: str, pred_name: str | None = None, pred_trace: object | None = None) -> tuple[str, str]:\n"
        "    return gold, pred\n"
    )
    evaluated = execute_module_synthesis_bundle(
        spec,
        candidate_sources=[
            {"code": "class Judge: ...\n", "candidate_metadata": {"variant_id": "bad"}},
            {"code": code_good, "candidate_metadata": {"variant_id": "good"}},
        ],
        workspace_root=tmp_path / "scratch",
    )

    rejected_candidate_id = next(
        candidate.candidate_id
        for candidate in evaluated.candidates
        if candidate.status == "rejected"
    )

    with pytest.raises(ValueError, match="selected candidate"):
        promote_selected_module_candidate(
            evaluated,
            candidate_id=rejected_candidate_id,
            target_path=tmp_path / "final" / "Judge.py",
        )
