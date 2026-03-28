from __future__ import annotations

from pathlib import Path

from dspx.dtos import ModuleSpec
from dspx.synthesis.contracts import build_module_synthesis_request
from dspx.synthesis.runtime import _module_smoke_checks


def test_module_smoke_checks_fail_closed_on_top_level_side_effects(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    marker = "relative-marker.txt"
    code = f"""
from pathlib import Path
Path({marker!r}).write_text("executed", encoding="utf-8")
import dspy

class Sneaky(dspy.Module):
    def __init__(self):
        super().__init__()
        self.predict = dspy.Predict("text -> summary")

    def forward(self, text: str):
        return self.predict(text=text)


def build_student(use_cot: bool = False):
    return Sneaky()


def io_spec():
    return {{"inputs": ["text"], "outputs": ["summary"]}}


def output_weights():
    return {{"summary": 1.0}}


def normalize_output(key, gold, pred, pred_name=None, pred_trace=None):
    return gold, pred
"""
    request = build_module_synthesis_request(
        ModuleSpec(
            name="Sneaky",
            description="executes top-level code",
            inputs=["text"],
            outputs=["summary"],
            options={},
        ),
        use_signature=False,
    )

    ok, checks, errors = _module_smoke_checks(request, code)

    assert ok is False
    assert checks["module-smoke"] is False
    assert errors
    assert not (tmp_path / marker).exists()
