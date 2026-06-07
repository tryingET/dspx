from __future__ import annotations

from pathlib import Path

from dspx.generated_code_guard import (
    _validate_module_source,
    _validate_signature_source,
    smoke_module_code,
    smoke_signature_code,
)


def test_generated_signature_guard_allows_passive_type_annotations() -> None:
    code = """
from __future__ import annotations
from typing import Literal
import dspy

class SafeSig(dspy.Signature):
    text: str = dspy.InputField()
    maybe_summary: str | None = dspy.OutputField()
    tags: list[str] = dspy.OutputField()
    label: Literal['positive', 'negative'] = dspy.OutputField()
"""

    errors = _validate_signature_source(code)

    assert errors == []


def test_generated_signature_guard_rejects_executable_annotations() -> None:
    code = """
import dspy

class UnsafeSig(dspy.Signature):
    text: eval("str") = dspy.InputField()
    summary: str = dspy.OutputField()
"""

    errors = _validate_signature_source(code)

    assert "signature_annotation_not_allowed:text" in errors


def test_generated_signature_guard_rejects_string_forwardref_annotations() -> None:
    code = """
import dspy

class UnsafeSig(dspy.Signature):
    text: "__import__('os').system('touch /tmp/dspx-forwardref')" = dspy.InputField()
    summary: str = dspy.OutputField()
"""

    errors = _validate_signature_source(code)

    assert "signature_annotation_not_allowed:text" in errors


def test_generated_signature_smoke_does_not_allow_annotation_file_read() -> None:
    code = """
import dspy

class UnsafeSig(dspy.Signature):
    text: eval("open('/etc/hosts').read().__class__") = dspy.InputField()
    summary: str = dspy.OutputField()
"""

    ok, errors = smoke_signature_code(code, expected_class_name="UnsafeSig")

    assert ok is False
    assert "signature_annotation_not_allowed:text" in errors


def test_generated_module_guard_rejects_executable_method_annotations() -> None:
    code = """
import dspy

class MyModule(dspy.Module):
    def __init__(self):
        self.predict = dspy.Predict("x -> y")

    def forward(self, x: eval("str")):
        return self.predict(x=x)

def build_student(use_cot=False):
    return MyModule()

def io_spec():
    return {"inputs": ["x"], "outputs": ["y"]}

def output_weights():
    return {"y": 1.0}

def normalize_output(key, gold, pred, pred_name=None, pred_trace=None):
    return (gold, pred)
"""

    errors = _validate_module_source(code)

    assert "method_annotation_not_allowed:forward.x" in errors


def test_generated_module_guard_rejects_dunder_reflection_escape() -> None:
    code = """
import dspy

class MyModule(dspy.Module):
    def __init__(self):
        self.predict = dspy.Predict("x -> y")

    def forward(self, x):
        for candidate in object.__subclasses__():
            if candidate.__name__ == "FileIO":
                return self.predict(x=x)
        return self.predict(x=x)

def build_student(use_cot=False):
    return MyModule()

def io_spec():
    return {"inputs": ["x"], "outputs": ["y"]}

def output_weights():
    return {"y": 1.0}

def normalize_output(key, gold, pred, pred_name=None, pred_trace=None):
    return (gold, pred)
"""

    errors = _validate_module_source(code)

    assert any("dunder_attribute_not_allowed" in error for error in errors)
    assert any("__subclasses__" in error for error in errors)


def test_generated_module_smoke_does_not_allow_reflective_fileio_write() -> None:
    probe = Path("/tmp/dspx_guard_escape_probe")
    probe.unlink(missing_ok=True)
    code = """
import dspy

class MyModule(dspy.Module):
    def __init__(self):
        self.predict = dspy.Predict("x -> y")

    def forward(self, x):
        for a in object.__subclasses__():
            if a.__name__ != "type":
                for b in a.__subclasses__():
                    if b.__name__ != "type":
                        for c in b.__subclasses__():
                            if c.__name__ == "FileIO":
                                f = c("/tmp/dspx_guard_escape_probe", "w")
                                f.write(b"owned")
                                f.close()
                                return self.predict(x=x)
        return self.predict(x=x)

def build_student(use_cot=False):
    return MyModule()

def io_spec():
    return {"inputs": ["x"], "outputs": ["y"]}

def output_weights():
    return {"y": 1.0}

def normalize_output(key, gold, pred, pred_name=None, pred_trace=None):
    return (gold, pred)
"""

    ok, checks, errors = smoke_module_code(
        code,
        payload={"expected_module": "MyModule", "inputs": ["x"], "outputs": ["y"]},
    )

    assert ok is False
    assert checks["module-smoke"] is False
    assert any("dunder_attribute_not_allowed" in error for error in errors)
    assert not probe.exists()
