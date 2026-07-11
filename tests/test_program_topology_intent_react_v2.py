# summary: "Tests experimental ReActV2 topology opt-in, DSPy capability checks, and fail-closed no-tool materialization."
# read_when:
#   - "Changing ReActV2 availability detection, explicit opt-in, tool-reference handling, or generated capability metadata."

from __future__ import annotations

from pathlib import Path

import pytest

from dspx.services import program_topology
from dspx.services.program_capabilities import build_program_capability_registry
from dspx.services.program_intent import ProgramIntent
from dspx.services.program_module_surface import build_program_module_surfaces
from dspx.services.program_service import materialize_program_from_intent
from program_topology_intent_helpers import (
    _react_v2_intent,
)


def test_react_v2_pipeline_requires_explicit_opt_in_for_materialization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setattr(program_topology, "_dspy_react_v2_available", lambda: True)

    with pytest.raises(
        ValueError,
        match="unsupported primitives: \\['ReActV2'\\]",
    ):
        materialize_program_from_intent(
            _react_v2_intent(opt_in=False), outdir=tmp_path / "program"
        )


def test_react_v2_pipeline_fails_closed_when_dspy_lacks_react_v2(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setattr(program_topology, "_dspy_react_v2_available", lambda: False)

    with pytest.raises(
        ValueError, match="requires installed DSPy with public dspy.ReActV2"
    ):
        materialize_program_from_intent(
            _react_v2_intent(opt_in=True), outdir=tmp_path / "program"
        )


def test_react_v2_explicit_opt_in_renders_declared_tool_refs_not_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(program_topology, "_dspy_react_v2_available", lambda: True)
    intent = ProgramIntent(
        name="ReActV2ToolRefProgram",
        objective="Use explicitly enabled experimental ReActV2 reasoning with a future tool ref.",
        inputs=["question"],
        outputs=["answer"],
        options={"enable_react_v2_materialization": True},
        topology={
            "kind": "pipeline",
            "execution_status": "declared_not_materialized",
            "modules": [
                {
                    "id": "reason_answer",
                    "primitive": "react_v2",
                    "signature": {
                        "name": "ReasonAnswer",
                        "inputs": ["question"],
                        "outputs": ["answer"],
                    },
                    "tools": [],
                    "tool_refs": ["lookup_policy"],
                    "max_iters": 2,
                }
            ],
            "edges": [
                {"from": "input", "to": "reason_answer"},
                {"from": "reason_answer", "to": "output"},
            ],
        },
        capabilities={
            "declarations": [
                {"id": "lookup_policy", "kind": "tool", "effect_class": "pure"}
            ]
        },
    )

    module_text, _metadata = program_topology.render_pipeline_module_surface(intent)
    module_surfaces = build_program_module_surfaces(intent)

    assert "_DECLARED_TOOL_REFS = ['lookup_policy']" in module_text
    assert "_TOOL_BINDING_STATUS = 'declared_refs_only_not_bound'" in module_text
    assert "dspy.ReActV2(ReasonAnswer, tools=[], max_iters=2)" in module_text
    assert "dspy.Tool" not in module_text
    surface = module_surfaces["module_surfaces"][0]
    assert surface["react"]["declared_tool_refs"] == ["lookup_policy"]
    assert surface["react"]["tool_binding_allowed"] is False


def test_react_v2_explicit_opt_in_renders_no_tool_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(program_topology, "_dspy_react_v2_available", lambda: True)
    intent = _react_v2_intent(opt_in=True)

    module_text, metadata = program_topology.render_pipeline_module_surface(intent)
    module_surfaces = build_program_module_surfaces(intent)
    registry = build_program_capability_registry(intent)

    assert metadata["module_classes"] == ["ReasonAnswerModule"]
    assert "dspy.ReActV2(ReasonAnswer, tools=[], max_iters=2)" in module_text
    assert "dspy.Tool" not in module_text
    assert "_TOOL_BINDING_ALLOWED = False" in module_text
    surface = module_surfaces["module_surfaces"][0]
    assert surface["primitive"] == "ReActV2"
    assert surface["capability_ref"] == {
        "schema_version": "program-capability-contract-v1",
        "capability_id": "dspy.primitive.ReActV2",
        "primitive": "ReActV2",
        "status": "experimental_materializable_with_empty_tools_explicit_opt_in",
        "materializable": True,
        "runtime_binding": "generated_experimental_react_v2_no_tools",
    }
    used = registry["used_capability_refs"][0]
    assert used["primitive"] == "ReActV2"
    assert used["materializable"] is True
    assert used["runtime_binding"] == "generated_experimental_react_v2_no_tools"
