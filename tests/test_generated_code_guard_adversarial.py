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


def test_generated_signature_guard_rejects_effect_root_annotations_with_future_annotations() -> (
    None
):
    for annotation in ("os.PathLike[str]", "pathlib.Path", "PathLike[str]", "Popen"):
        code = f"""
from __future__ import annotations
import dspy

class UnsafeSig(dspy.Signature):
    text: {annotation} = dspy.InputField()
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


def test_generated_module_guard_allows_input_argument_name() -> None:
    code = """
import dspy

class MySignature(dspy.Signature):
    input: str = dspy.InputField()
    answer: str = dspy.OutputField()

class MyModule(dspy.Module):
    def forward(self, input: str) -> dict[str, str]:
        return {"answer": input}

def build_student(use_cot=False):
    return MyModule()

def io_spec():
    return {"inputs": ["input"], "outputs": ["answer"]}

def output_weights():
    return {"answer": 1.0}

def normalize_output(key, gold, pred, pred_name=None, pred_trace=None):
    return (gold, pred)
"""

    errors = _validate_module_source(code)

    assert errors == []


def test_generated_module_guard_still_rejects_input_builtin_call() -> None:
    code = """
import dspy

class MyModule(dspy.Module):
    def forward(self, x: str) -> str:
        return input("secret: ")

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

    assert "method_name_not_allowed:forward:input" in errors
    assert "method_call_not_allowed:forward:input" in errors


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


def test_generated_module_guard_rejects_effect_root_return_annotations() -> None:
    for annotation in ("subprocess.Popen", "Popen", "Path", "PurePath"):
        code = f"""
from __future__ import annotations
import dspy

class MyModule(dspy.Module):
    def __init__(self):
        self.predict = dspy.Predict("x -> y")

    def forward(self, x: str) -> {annotation}:
        return self.predict(x=x)

def build_student(use_cot=False):
    return MyModule()

def io_spec():
    return {{"inputs": ["x"], "outputs": ["y"]}}

def output_weights():
    return {{"y": 1.0}}

def normalize_output(key, gold, pred, pred_name=None, pred_trace=None):
    return (gold, pred)
"""

        errors = _validate_module_source(code)

        assert "method_return_annotation_not_allowed:forward" in errors


def test_generated_module_guard_rejects_top_level_effect_annotations() -> None:
    code = """
import dspy

class MyModule(dspy.Module):
    def forward(self, x: str) -> str:
        return x

def build_student(use_cot=False):
    return MyModule()

def io_spec() -> open:
    return {"inputs": ["x"], "outputs": ["y"]}

def output_weights():
    return {"y": 1.0}

def normalize_output(key, gold, pred, pred_name=None, pred_trace=None):
    return (gold, pred)
"""

    errors = _validate_module_source(code)

    assert "top_level_function_return_annotation_not_allowed:io_spec" in errors


def test_generated_module_guard_rejects_top_level_annassign_effect_annotations() -> (
    None
):
    for annotation in ("os.PathLike[str]", "PathLike[str]", "open"):
        code = f"""
from __future__ import annotations
import dspy

EFFECT_HINT: {annotation} = None

class MyModule(dspy.Module):
    def forward(self, x: str) -> str:
        return x

def build_student(use_cot=False):
    return MyModule()

def io_spec():
    return {{"inputs": ["x"], "outputs": ["y"]}}

def output_weights():
    return {{"y": 1.0}}

def normalize_output(key, gold, pred, pred_name=None, pred_trace=None):
    return (gold, pred)
"""

        errors = _validate_module_source(code)

        assert "top_level_annotation_not_allowed:EFFECT_HINT" in errors


def test_generated_module_smoke_does_not_allow_annotation_effect_root_file_read() -> (
    None
):
    probe = Path("/tmp/dspx_annotation_escape_probe")
    probe.unlink(missing_ok=True)
    code = """
from __future__ import annotations
import dspy

class MyModule(dspy.Module):
    def __init__(self):
        self.predict = dspy.Predict("x -> y")

    def forward(self, x: os.PathLike[str]) -> str:
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
    assert "method_annotation_not_allowed:forward.x" in errors
    assert not probe.exists()


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


def test_generated_module_guard_rejects_builtins_import_subscript_escape() -> None:
    code = """
import dspy

class MyModule(dspy.Module):
    def __init__(self):
        self.predict = dspy.Predict("x -> y")

    def forward(self, x):
        tempfile = __builtins__["__import__"]("tempfile")
        fd = tempfile._os.open("/tmp/dspx_osopen_escape_probe", tempfile._os.O_WRONLY | tempfile._os.O_CREAT, 0o600)
        tempfile._os.write(fd, b"owned")
        tempfile._os.close(fd)
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

    assert "method_builtins_subscript_not_allowed:forward" in errors
    assert "method_name_not_allowed:forward:__builtins__" in errors


def test_generated_module_guard_rejects_builtins_alias_file_read_escape() -> None:
    code = """
import dspy

class MyModule(dspy.Module):
    def __init__(self):
        self.predict = dspy.Predict("x -> y")

    def forward(self, x):
        b = __builtins__
        o = b["open"]
        raise Exception(o("/etc/hostname").read().strip())

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

    assert "method_name_not_allowed:forward:__builtins__" in errors


def test_generated_module_smoke_does_not_allow_low_level_os_write_escape() -> None:
    probe = Path("/tmp/dspx_osopen_escape_probe")
    probe.unlink(missing_ok=True)
    code = """
import dspy

class MyModule(dspy.Module):
    def __init__(self):
        self.predict = dspy.Predict("x -> y")

    def forward(self, x):
        tempfile = __builtins__["__import__"]("tempfile")
        fd = tempfile._os.open("/tmp/dspx_osopen_escape_probe", tempfile._os.O_WRONLY | tempfile._os.O_CREAT, 0o600)
        tempfile._os.write(fd, b"owned")
        tempfile._os.close(fd)
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
    assert "method_builtins_subscript_not_allowed:forward" in errors
    assert not probe.exists()


def test_generated_module_smoke_redacts_generated_exception_contents() -> None:
    code = """
import dspy

class MyModule(dspy.Module):
    def __init__(self):
        self.predict = dspy.Predict("x -> y")

    def forward(self, x):
        raise Exception("api_key=supersecret-value")

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
    assert errors == ["forward_error:Exception"]


def test_generated_module_smoke_handles_base_exception_without_raw_stderr() -> None:
    code = """
import dspy

class MyModule(dspy.Module):
    def __init__(self):
        self.predict = dspy.Predict("x -> y")

    def forward(self, x):
        raise SystemExit("api_key=supersecret-value")

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
    assert errors == ["forward_error:SystemExit"]


def test_generated_module_smoke_timeout_returns_structured_failure() -> None:
    code = """
import dspy

class MyModule(dspy.Module):
    def __init__(self):
        self.predict = dspy.Predict("x -> y")

    def forward(self, x):
        while True:
            pass
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
        timeout=1,
    )

    assert ok is False
    assert checks["module-smoke"] is False
    assert errors == ["smoke_runner_timeout:1s"]
