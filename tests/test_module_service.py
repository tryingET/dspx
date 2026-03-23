from __future__ import annotations

from pathlib import Path

from dspx.dtos import ModuleSpec
from dspx.services.module_service import run_generate


def test_module_service_simple_no_signature(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DSPX_SYNTHESIS_DIR", str(tmp_path / "synthesis"))
    spec = ModuleSpec(
        name="Summarizer",
        description="Summarizes text",
        inputs=["text"],
        outputs=["summary"],
        options={"template_version": "simple-v1"},
    )
    art = run_generate(spec, use_signature=False)
    assert "class Summarizer(dspy.Module):" in art.code
    assert "self.predict = dspy.Predict('text -> summary')" in art.code
    assert "def forward(self, text: str)" in art.code

    synthesis = art.metadata["synthesis"]
    assert synthesis["request"]["artifact_kind"] == "module"
    assert synthesis["request"]["spec"]["name"] == "Summarizer"
    assert synthesis["strategy"]["strategy_id"] == "module.single_candidate.template"
    assert synthesis["candidates"][0]["artifact"]["content_hash"]
    assert synthesis["promotion_decision"]["outcome"] == "withheld"
    workspace = synthesis["candidate_workspaces"][0]
    assert Path(workspace["artifact_path"]).exists()
    assert Path(workspace["manifest_path"]).exists()
    assert synthesis["promotion_shell"]["target_path"].endswith("Summarizer.py")


def test_module_service_simple_with_signature(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DSPX_SYNTHESIS_DIR", str(tmp_path / "synthesis"))
    spec = ModuleSpec(
        name="Intent",
        description="Extracts intent from context",
        inputs=["context"],
        outputs=["output"],
        options={"template_version": "simple-v1"},
    )
    art = run_generate(spec, use_signature=True)
    assert "class Sig_Intent(dspy.Signature):" in art.code
    assert "self.predict = dspy.Predict(Sig_Intent)" in art.code
    assert "def forward(self, context: str)" in art.code

    synthesis = art.metadata["synthesis"]
    assert synthesis["request"]["spec"]["use_signature"] is True
    assert synthesis["request"]["spec"]["template_version"] == "simple-v1"
    assert synthesis["evaluations"][0]["status"] == "pending"
    assert (
        synthesis["selection_policy"]["policy_id"]
        == "module.v7.single-candidate-pass-through"
    )
    assert synthesis["strategy"]["metadata"]["use_signature"] is True
    assert synthesis["candidate_workspaces"][0]["metadata"]["strategy_version"] == "v0"
