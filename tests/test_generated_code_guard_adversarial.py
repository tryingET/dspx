from __future__ import annotations

from pathlib import Path

from dspx.generated_code_guard import _validate_module_source, smoke_module_code


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
