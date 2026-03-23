from __future__ import annotations

from pathlib import Path
import json

from dspx.dtos import ModuleSpec
from dspx.synthesis import (
    build_module_synthesis_bundle,
    build_module_synthesis_request,
    execute_module_synthesis_bundle,
    materialize_module_synthesis_bundle,
    module_spec_to_ir,
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
    assert bundle.strategy is not None
    assert bundle.strategy.strategy_id == bundle.request.strategy_id
    assert len(bundle.candidates) == 1
    assert bundle.candidates[0].candidate_id.startswith("cand-")
    assert bundle.candidates[0].request_id == bundle.request.request_id
    assert bundle.evaluations[0].candidate_id == bundle.candidates[0].candidate_id
    assert bundle.evaluations[0].status == "pending"
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
    workspace = bundle.candidate_workspaces[0]
    assert Path(workspace.artifact_path).exists()
    assert Path(workspace.manifest_path).exists()
    manifest = json.loads(Path(workspace.manifest_path).read_text(encoding="utf-8"))
    assert manifest["strategy"]["strategy_id"] == bundle.request.strategy_id
    assert manifest["candidate"]["candidate_id"] == bundle.candidates[0].candidate_id
    assert bundle.candidates[0].metadata["workspace_id"] == workspace.workspace_id
    assert bundle.promotion_shell is not None
    assert bundle.promotion_shell.target_path.endswith("Planner.py")
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
        code=(
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
        workspace_root=tmp_path / "scratch",
        promotion_target=tmp_path / "final" / "Judge.py",
    )

    out = tmp_path / "final" / "Judge.py"
    assert out.exists()
    assert bundle.evaluations[0].status == "passed"
    assert bundle.evaluations[0].evidence["static"]["python-parse"] is True
    assert bundle.evaluations[0].evidence["smoke"]["module-smoke"] is True
    assert bundle.candidates[0].status == "promoted"
    assert bundle.candidate_workspaces[0].status == "promoted"
    assert bundle.promotion_shell is not None
    assert bundle.promotion_shell.status == "promoted"
    assert bundle.promotion_decision.outcome == "promoted"
    assert bundle.promotion_decision.metadata["promoted_path"] == str(out.resolve())


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

    promoted = promote_selected_module_candidate(
        bundle,
        target_path=tmp_path / "final" / "Judge.py",
    )

    out = tmp_path / "final" / "Judge.py"
    assert out.exists()
    assert out.read_text(encoding="utf-8") == "class Judge: ...\n"
    assert promoted.candidates[0].status == "promoted"
    assert promoted.candidate_workspaces[0].status == "promoted"
    assert promoted.promotion_shell is not None
    assert promoted.promotion_shell.status == "promoted"
    assert promoted.promotion_decision.outcome == "promoted"
    assert promoted.promotion_decision.metadata["promoted_path"] == str(out.resolve())
