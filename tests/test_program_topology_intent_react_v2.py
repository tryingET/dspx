# summary: "Tests that ReActV2 remains descriptor-only during the typed Core cutover."
# read_when:
#   - "Changing ReActV2 availability, topology materialization, or generated capabilities."

from __future__ import annotations

from pathlib import Path

import pytest

from dspx.services.program_intent import ProgramIntent
from dspx.services.program_service import materialize_program_from_intent
from dspx.services.program_topology import render_pipeline_module_surface
from program_topology_intent_helpers import _react_v2_intent


@pytest.mark.parametrize("opt_in", [False, True])
def test_react_v2_pipeline_is_unavailable_even_with_legacy_opt_in(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    opt_in: bool,
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")

    with pytest.raises(
        ValueError,
        match="unsupported primitives: \\['ReActV2'\\]",
    ):
        materialize_program_from_intent(
            _react_v2_intent(opt_in=opt_in), outdir=tmp_path / "program"
        )


def test_react_v2_environment_switch_cannot_enable_materialization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("DSPX_PROGRAM_GEN_ENABLE_REACT_V2", "1")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")

    with pytest.raises(ValueError, match="unsupported primitives"):
        materialize_program_from_intent(
            _react_v2_intent(opt_in=True), outdir=tmp_path / "program"
        )


def test_react_v2_tool_refs_remain_declared_and_unbound() -> None:
    intent = ProgramIntent(
        name="ReActV2ToolRefProgram",
        objective="Declare experimental ReActV2 reasoning with a future tool ref.",
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

    with pytest.raises(ValueError, match="unsupported primitives"):
        render_pipeline_module_surface(intent)

    module = intent.topology["modules"][0]
    assert module["primitive"] == "ReActV2"
    assert module["react"]["declared_tool_refs"] == ["lookup_policy"]
    assert module["react"]["tool_binding_status"] == "declared_refs_only_not_bound"
