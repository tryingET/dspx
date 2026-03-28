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


def test_module_smoke_checks_fail_closed_on_default_arg_side_effects(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "marker.txt"
    code = f"""
import dspy

class Sneaky(dspy.Module):
    def __init__(self, use_cot: bool = False) -> None:
        super().__init__()
        self.predict = dspy.Predict("text -> summary")

    def forward(self, text: str) -> dspy.Prediction:
        return self.predict(text=text)


def build_student(*, use_cot: bool = False, _x=open({str(marker)!r}, "w")) -> dspy.Module:
    return Sneaky(use_cot=use_cot)


def io_spec() -> dict[str, list[str]]:
    return {{"inputs": ["text"], "outputs": ["summary"]}}


def output_weights() -> dict[str, float]:
    return {{"summary": 1.0}}


def normalize_output(key: str, gold: str, pred: str, pred_name: str | None = None, pred_trace: object | None = None) -> tuple[str, str]:
    return gold, pred
"""
    request = build_module_synthesis_request(
        ModuleSpec(
            name="Sneaky",
            description="executes default-arg code",
            inputs=["text"],
            outputs=["summary"],
            options={},
        ),
        use_signature=False,
    )

    ok, checks, errors = _module_smoke_checks(request, code)

    assert ok is False
    assert checks["module-smoke"] is False
    assert "top_level_function_defaults_not_literal:build_student" in errors
    assert not marker.exists()


def test_module_smoke_checks_fail_closed_on_signature_forward_input_drift() -> None:
    code = '''
import dspy

class Sig_QA(dspy.Signature):
    """QA contract"""

    question: str = dspy.InputField(desc="question")
    context: str = dspy.InputField(desc="context")
    answer: str = dspy.OutputField(desc="answer")


class QA(dspy.Module):
    def __init__(self, use_cot: bool = False) -> None:
        super().__init__()
        self.predict = dspy.Predict(Sig_QA)

    def forward(self, question: str, context: str) -> dspy.Prediction:
        return self.predict(context=context)


def build_student(*, use_cot: bool = False) -> dspy.Module:
    return QA(use_cot=use_cot)


def io_spec() -> dict[str, list[str]]:
    return {"inputs": ["question", "context"], "outputs": ["answer"]}


def output_weights() -> dict[str, float]:
    return {"answer": 1.0}


def normalize_output(key: str, gold: str, pred: str, pred_name: str | None = None, pred_trace: object | None = None) -> tuple[str, str]:
    return gold, pred
'''
    request = build_module_synthesis_request(
        ModuleSpec(
            name="QA",
            description="drifted signature forward mapping",
            inputs=["question", "context"],
            outputs=["answer"],
            options={},
        ),
        use_signature=True,
    )

    ok, checks, errors = _module_smoke_checks(request, code)

    assert ok is False
    assert checks["module-smoke"] is False
    assert "forward_input_mapping_mismatch" in errors
