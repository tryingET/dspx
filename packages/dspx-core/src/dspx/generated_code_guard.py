from __future__ import annotations

import ast
import builtins
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence, cast

_SAFE_IMPORT_MODULES = frozenset(
    {
        "__future__",
        "dspy",
        "typing",
        "typing_extensions",
    }
)


def isolated_subprocess_env(
    extra_env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Return a minimal environment for generated-code smoke checks."""

    env: dict[str, str] = {
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    }
    for key in (
        "PATH",
        "SYSTEMROOT",
        "WINDIR",
        "HOME",
        "TMPDIR",
        "TEMP",
        "TMP",
        "LANG",
        "LC_ALL",
        "VIRTUAL_ENV",
    ):
        value = os.environ.get(key)
        if value:
            env[key] = value
    if extra_env:
        env.update({str(k): str(v) for k, v in extra_env.items()})
    return env


def _default_smoke_timeout() -> int:
    raw = os.environ.get("DSPX_GENERATED_CODE_GUARD_TIMEOUT") or os.environ.get(
        "DSPX_PROGRAM_HARNESS_TIMEOUT", "30"
    )
    try:
        return max(1, int(float(raw)))
    except ValueError:
        return 30


def smoke_signature_code(
    code: str,
    *,
    expected_class_name: str | None = None,
    timeout: int | None = None,
) -> tuple[bool, list[str]]:
    result = _run_worker(
        mode="signature",
        code=code,
        payload={"expected_class_name": expected_class_name},
        timeout=timeout or _default_smoke_timeout(),
    )
    errors = [str(item) for item in result.get("errors", []) if str(item).strip()]
    return bool(result.get("ok")) and not errors, errors


def smoke_module_code(
    code: str,
    *,
    payload: Mapping[str, Any],
    timeout: int | None = None,
) -> tuple[bool, dict[str, bool], list[str]]:
    result = _run_worker(
        mode="module",
        code=code,
        payload=payload,
        timeout=timeout or _default_smoke_timeout(),
    )
    checks_raw = result.get("checks")
    checks = (
        {str(key): bool(value) for key, value in checks_raw.items()}
        if isinstance(checks_raw, Mapping)
        else {"module-smoke": False}
    )
    errors = [str(item) for item in result.get("errors", []) if str(item).strip()]
    return bool(result.get("ok")) and not errors, checks, errors


def _bounded_worker_error(text: str, *, limit: int = 240) -> str:
    compact = str(text or "").strip()
    if len(compact) <= limit:
        return compact
    return compact[:limit] + "…[truncated]"


def _run_worker(
    *,
    mode: str,
    code: str,
    payload: Mapping[str, Any],
    timeout: int,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix=f"dspx_{mode}_smoke_") as td:
        workdir = Path(td)
        code_path = workdir / "candidate.py"
        payload_path = workdir / "payload.json"
        result_path = workdir / "result.json"
        code_path.write_text(code, encoding="utf-8")
        payload_path.write_text(
            json.dumps(dict(payload), sort_keys=True),
            encoding="utf-8",
        )
        proc = subprocess.run(
            [
                sys.executable,
                "-I",
                "-m",
                "dspx.generated_code_guard",
                mode,
                str(code_path),
                str(payload_path),
                str(result_path),
            ],
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=isolated_subprocess_env(),
        )
        if not result_path.exists():
            errors = [f"smoke_runner_no_result:rc={proc.returncode}"]
            stderr = (proc.stderr or "").strip()
            if stderr:
                errors.append(
                    f"smoke_runner_stderr:{_bounded_worker_error(stderr.splitlines()[-1])}"
                )
            stdout = (proc.stdout or "").strip()
            if stdout:
                errors.append(
                    f"smoke_runner_stdout:{_bounded_worker_error(stdout.splitlines()[-1])}"
                )
            return {
                "ok": False,
                "checks": {"module-smoke": False} if mode == "module" else {},
                "errors": errors,
            }
        try:
            loaded = json.loads(result_path.read_text(encoding="utf-8"))
        except Exception as exc:
            return {
                "ok": False,
                "checks": {"module-smoke": False} if mode == "module" else {},
                "errors": [f"smoke_runner_invalid_result:{exc.__class__.__name__}"],
            }
        if not isinstance(loaded, dict):
            return {
                "ok": False,
                "checks": {"module-smoke": False} if mode == "module" else {},
                "errors": ["smoke_runner_invalid_result:non_object"],
            }
        raw_errors = loaded.get("errors")
        if isinstance(raw_errors, list):
            loaded["errors"] = [
                _bounded_worker_error(str(item)) for item in raw_errors[:20]
            ]
        elif raw_errors is not None:
            loaded["errors"] = [_bounded_worker_error(str(raw_errors))]
        if proc.returncode != 0 and not loaded.get("errors"):
            loaded["errors"] = [f"smoke_runner_failed:rc={proc.returncode}"]
        return loaded


def _expr_is_docstring(node: ast.stmt) -> bool:
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


def _import_module_names(node: ast.stmt) -> tuple[str, ...]:
    if isinstance(node, ast.Import):
        return tuple(str(alias.name) for alias in node.names if alias.name)
    if isinstance(node, ast.ImportFrom):
        if node.module is None:
            return ("",)
        return (str(node.module),)
    return ()


def _disallowed_import_modules(node: ast.stmt) -> tuple[str, ...]:
    modules = _import_module_names(node)
    disallowed: list[str] = []
    for module in modules:
        root = module.split(".", 1)[0]
        if root not in _SAFE_IMPORT_MODULES:
            disallowed.append(module)
    return tuple(disallowed)


def _literalish(node: ast.AST | None) -> bool:
    if node is None:
        return True
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return all(_literalish(item) for item in node.elts)
    if isinstance(node, ast.Dict):
        return all(
            _literalish(key) and _literalish(value)
            for key, value in zip(node.keys, node.values)
        )
    return False


def _validate_signature_field(node: ast.stmt, *, errors: list[str]) -> None:
    if isinstance(node, ast.Pass):
        return
    if _expr_is_docstring(node):
        return
    if not isinstance(node, ast.AnnAssign) or not isinstance(node.target, ast.Name):
        errors.append(f"signature_stmt_not_allowed:{node.__class__.__name__}")
        return
    if not isinstance(node.value, ast.Call):
        errors.append("signature_field_missing_call")
        return
    callee = _call_name(node.value.func)
    if callee not in {
        "InputField",
        "OutputField",
        "dspy.InputField",
        "dspy.OutputField",
    }:
        errors.append(f"signature_field_call_not_allowed:{callee or 'unknown'}")
        return
    if any(not _literalish(arg) for arg in node.value.args):
        errors.append("signature_field_args_not_literal")
        return
    if any(not _literalish(kw.value) for kw in node.value.keywords):
        errors.append("signature_field_kwargs_not_literal")


def _validate_class_keywords(node: ast.ClassDef, *, errors: list[str]) -> None:
    if node.keywords:
        errors.append(f"class_keywords_not_allowed:{node.name}")


def _validate_signature_source(code: str) -> list[str]:
    errors: list[str] = []
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return [f"syntax_error:{exc.msg}"]

    for node in tree.body:
        if _expr_is_docstring(node):
            continue
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for module in _disallowed_import_modules(node):
                errors.append(f"import_not_allowed:{module or 'unknown'}")
            continue
        if not isinstance(node, ast.ClassDef):
            errors.append(f"top_level_stmt_not_allowed:{node.__class__.__name__}")
            continue
        if node.decorator_list:
            errors.append("signature_decorators_not_allowed")
        _validate_class_keywords(node, errors=errors)
        base_names = {_call_name(base) for base in node.bases}
        if not ({"Signature", "dspy.Signature"} & base_names):
            errors.append(f"signature_base_not_allowed:{node.name}")
            continue
        for child in node.body:
            _validate_signature_field(child, errors=errors)
    return errors


def _validate_function_defaults(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    errors: list[str],
    label: str,
) -> None:
    defaults = [
        *node.args.defaults,
        *[item for item in node.args.kw_defaults if item is not None],
    ]
    if any(not _literalish(item) for item in defaults):
        errors.append(f"{label}_defaults_not_literal:{node.name}")


def _validate_module_class(node: ast.ClassDef, *, errors: list[str]) -> None:
    if node.decorator_list:
        errors.append(f"class_decorators_not_allowed:{node.name}")
    _validate_class_keywords(node, errors=errors)
    base_names = {_call_name(base) for base in node.bases}
    if {"Signature", "dspy.Signature"} & base_names:
        for child in node.body:
            _validate_signature_field(child, errors=errors)
        return
    if not ({"Module", "dspy.Module"} & base_names):
        errors.append(f"module_base_not_allowed:{node.name}")
        return
    for child in node.body:
        if _expr_is_docstring(child) or isinstance(child, ast.Pass):
            continue
        if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            errors.append(f"module_class_stmt_not_allowed:{child.__class__.__name__}")
            continue
        if child.decorator_list:
            errors.append(f"method_decorators_not_allowed:{node.name}.{child.name}")
        _validate_function_defaults(
            child,
            errors=errors,
            label="method",
        )


def _validate_module_source(code: str) -> list[str]:
    errors: list[str] = []
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return [f"syntax_error:{exc.msg}"]

    for node in tree.body:
        if _expr_is_docstring(node):
            continue
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for module in _disallowed_import_modules(node):
                errors.append(f"import_not_allowed:{module or 'unknown'}")
            continue
        if isinstance(node, ast.ClassDef):
            _validate_module_class(node, errors=errors)
            continue
        if isinstance(node, ast.Assign):
            if not all(
                isinstance(target, ast.Name) for target in node.targets
            ) or not _literalish(node.value):
                errors.append("top_level_assign_not_allowed")
            continue
        if isinstance(node, ast.AnnAssign):
            if not isinstance(node.target, ast.Name) or not _literalish(node.value):
                errors.append("top_level_annassign_not_allowed")
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Pass)):
            if getattr(node, "decorator_list", None):
                errors.append(
                    f"top_level_decorators_not_allowed:{getattr(node, 'name', 'unknown')}"
                )
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                _validate_function_defaults(
                    node,
                    errors=errors,
                    label="top_level_function",
                )
            continue
        errors.append(f"top_level_stmt_not_allowed:{node.__class__.__name__}")
    return errors


def _install_runtime_guards() -> Mapping[str, Any]:
    original_open = builtins.open
    original_io_open = io.open
    original_path_open = Path.open
    original_path_write_text = Path.write_text
    original_path_write_bytes = Path.write_bytes
    original_path_touch = Path.touch
    original_path_mkdir = Path.mkdir
    original_path_unlink = Path.unlink
    original_path_rename = Path.rename
    original_path_replace = Path.replace
    original_os_remove = os.remove
    original_os_unlink = os.unlink
    original_os_mkdir = os.mkdir
    original_os_makedirs = os.makedirs
    original_os_rmdir = os.rmdir
    original_os_rename = os.rename
    original_os_replace = os.replace
    original_socket_create_connection = socket.create_connection
    original_socket_connect = socket.socket.connect
    original_socket_connect_ex = socket.socket.connect_ex
    original_subprocess_run = subprocess.run
    original_subprocess_popen = subprocess.Popen

    def _deny(message: str):
        def _inner(*args, **kwargs):
            raise PermissionError(message)

        return _inner

    def _guard_open(file, mode="r", *args, **kwargs):
        mode_str = str(mode or "r")
        if any(flag in mode_str for flag in ("w", "a", "x", "+")):
            raise PermissionError("filesystem_write_denied_during_smoke")
        return original_open(file, mode, *args, **kwargs)

    def _guard_io_open(file, mode="r", *args, **kwargs):
        mode_str = str(mode or "r")
        if any(flag in mode_str for flag in ("w", "a", "x", "+")):
            raise PermissionError("filesystem_write_denied_during_smoke")
        return original_io_open(file, mode, *args, **kwargs)

    def _guard_path_open(self, mode="r", *args, **kwargs):
        mode_str = str(mode or "r")
        if any(flag in mode_str for flag in ("w", "a", "x", "+")):
            raise PermissionError("filesystem_write_denied_during_smoke")
        return original_path_open(self, mode, *args, **kwargs)

    builtins.open = cast(Any, _guard_open)
    io.open = cast(Any, _guard_io_open)
    Path.open = cast(Any, _guard_path_open)
    Path.write_text = _deny("filesystem_write_denied_during_smoke")
    Path.write_bytes = _deny("filesystem_write_denied_during_smoke")
    Path.touch = _deny("filesystem_write_denied_during_smoke")
    Path.mkdir = _deny("filesystem_write_denied_during_smoke")
    Path.unlink = _deny("filesystem_write_denied_during_smoke")
    Path.rename = _deny("filesystem_write_denied_during_smoke")
    Path.replace = _deny("filesystem_write_denied_during_smoke")
    os.remove = _deny("filesystem_write_denied_during_smoke")
    os.unlink = _deny("filesystem_write_denied_during_smoke")
    os.mkdir = _deny("filesystem_write_denied_during_smoke")
    os.makedirs = _deny("filesystem_write_denied_during_smoke")
    os.rmdir = _deny("filesystem_write_denied_during_smoke")
    os.rename = _deny("filesystem_write_denied_during_smoke")
    os.replace = _deny("filesystem_write_denied_during_smoke")
    socket.create_connection = _deny("network_access_denied_during_smoke")
    socket.socket.connect = _deny("network_access_denied_during_smoke")
    socket.socket.connect_ex = _deny("network_access_denied_during_smoke")
    subprocess.run = _deny("subprocess_denied_during_smoke")
    subprocess.Popen = _deny("subprocess_denied_during_smoke")

    return {
        "open": original_open,
        "io_open": original_io_open,
        "path_open": original_path_open,
        "path_write_text": original_path_write_text,
        "path_write_bytes": original_path_write_bytes,
        "path_touch": original_path_touch,
        "path_mkdir": original_path_mkdir,
        "path_unlink": original_path_unlink,
        "path_rename": original_path_rename,
        "path_replace": original_path_replace,
        "os_remove": original_os_remove,
        "os_unlink": original_os_unlink,
        "os_mkdir": original_os_mkdir,
        "os_makedirs": original_os_makedirs,
        "os_rmdir": original_os_rmdir,
        "os_rename": original_os_rename,
        "os_replace": original_os_replace,
        "socket_create_connection": original_socket_create_connection,
        "socket_connect": original_socket_connect,
        "socket_connect_ex": original_socket_connect_ex,
        "subprocess_run": original_subprocess_run,
        "subprocess_popen": original_subprocess_popen,
    }


def _restore_runtime_guards(originals: Mapping[str, Any]) -> None:
    builtins.open = originals["open"]
    io.open = originals["io_open"]
    Path.open = originals["path_open"]
    Path.write_text = originals["path_write_text"]
    Path.write_bytes = originals["path_write_bytes"]
    Path.touch = originals["path_touch"]
    Path.mkdir = originals["path_mkdir"]
    Path.unlink = originals["path_unlink"]
    Path.rename = originals["path_rename"]
    Path.replace = originals["path_replace"]
    os.remove = originals["os_remove"]
    os.unlink = originals["os_unlink"]
    os.mkdir = originals["os_mkdir"]
    os.makedirs = originals["os_makedirs"]
    os.rmdir = originals["os_rmdir"]
    os.rename = originals["os_rename"]
    os.replace = originals["os_replace"]
    socket.create_connection = originals["socket_create_connection"]
    socket.socket.connect = originals["socket_connect"]
    socket.socket.connect_ex = originals["socket_connect_ex"]
    subprocess.run = originals["subprocess_run"]
    subprocess.Popen = originals["subprocess_popen"]


def _run_signature_worker(code: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    errors = _validate_signature_source(code)
    if errors:
        return {"ok": False, "errors": errors}

    namespace: dict[str, Any] = {}
    originals = _install_runtime_guards()
    try:
        try:
            exec(code, namespace, namespace)
        except Exception as exc:
            return {"ok": False, "errors": [f"exec_error:{exc}"]}
    finally:
        _restore_runtime_guards(originals)

    expected = payload.get("expected_class_name")
    expected_name = str(expected) if expected not in {None, ""} else None
    class_name = expected_name
    if class_name is None:
        for value in namespace.values():
            if isinstance(value, type):
                try:
                    import dspy

                    if issubclass(value, dspy.Signature):
                        class_name = value.__name__
                        break
                except Exception:
                    continue
    if not class_name:
        return {"ok": False, "errors": ["class_name_unknown"]}

    cls = namespace.get(class_name)
    if not isinstance(cls, type):
        return {"ok": False, "errors": [f"class_not_found:{class_name}"]}

    try:
        import dspy

        if not issubclass(cls, dspy.Signature):
            return {"ok": False, "errors": ["class_not_dspy_signature"]}
    except Exception:
        return {"ok": False, "errors": ["class_not_dspy_signature"]}

    return {"ok": True, "errors": []}


def _run_module_worker(code: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    checks: dict[str, bool] = {"module-smoke": False}
    errors = _validate_module_source(code)
    if errors:
        return {"ok": False, "checks": checks, "errors": errors}

    try:
        import dspy
    except Exception as exc:
        return {"ok": False, "checks": checks, "errors": [f"dspy_import_error:{exc}"]}

    namespace: dict[str, Any] = {}
    originals = _install_runtime_guards()
    try:
        try:
            exec(code, namespace, namespace)
        except Exception as exc:
            return {"ok": False, "checks": checks, "errors": [f"exec_error:{exc}"]}

        expected_module = str(payload.get("expected_module") or "")
        expected_inputs = [str(item) for item in (payload.get("inputs") or [])]
        expected_outputs = [str(item) for item in (payload.get("outputs") or [])]
        if not expected_module:
            errors.append("expected_module_missing")
        else:
            module_cls = namespace.get(expected_module)
            if not isinstance(module_cls, type):
                errors.append(f"class_not_found:{expected_module}")
            else:
                try:
                    if not issubclass(module_cls, dspy.Module):
                        errors.append("class_not_dspy_module")
                except Exception:
                    errors.append("class_not_dspy_module")

        if bool(payload.get("use_signature")):
            expected_signature = str(payload.get("expected_signature") or "")
            if not expected_signature:
                errors.append("expected_signature_missing")
            else:
                signature_cls = namespace.get(expected_signature)
                if not isinstance(signature_cls, type):
                    errors.append(f"signature_not_found:{expected_signature}")
                else:
                    try:
                        if not issubclass(signature_cls, dspy.Signature):
                            errors.append("signature_not_dspy_signature")
                    except Exception:
                        errors.append("signature_not_dspy_signature")

        student = None
        build_student = namespace.get("build_student")
        if not callable(build_student):
            errors.append("build_student_missing")
        else:
            try:
                student = build_student(use_cot=False)
                if not isinstance(student, dspy.Module):
                    errors.append("build_student_not_module")
                if getattr(student, "predict", None) is None:
                    errors.append("predict_missing")
            except Exception as exc:
                errors.append(f"build_student_error:{exc}")
                student = None

        if student is not None:
            predict = getattr(student, "predict", None)
            if bool(payload.get("use_signature")):
                signature = getattr(predict, "signature", None)
                input_fields = getattr(signature, "input_fields", None)
                output_fields = getattr(signature, "output_fields", None)
                if (
                    not isinstance(input_fields, dict)
                    or list(input_fields.keys()) != expected_inputs
                ):
                    errors.append("signature_input_fields_mismatch")
                if (
                    not isinstance(output_fields, dict)
                    or list(output_fields.keys()) != expected_outputs
                ):
                    errors.append("signature_output_fields_mismatch")

            class _CapturePredict:
                def __init__(self) -> None:
                    self.calls: list[dict[str, Any]] = []

                def __call__(self, **kwargs):
                    self.calls.append(dict(kwargs))
                    return dict(kwargs)

            capture = _CapturePredict()
            try:
                student.predict = capture
                sample_inputs = {name: f"sample_{name}" for name in expected_inputs}
                student.forward(**sample_inputs)
                if not capture.calls:
                    errors.append("forward_did_not_call_predict")
                elif capture.calls[-1] != sample_inputs:
                    errors.append("forward_input_mapping_mismatch")
            except Exception as exc:
                errors.append(f"forward_error:{exc}")

        io_spec = namespace.get("io_spec")
        if not callable(io_spec):
            errors.append("io_spec_missing")
        else:
            try:
                if io_spec() != {
                    "inputs": expected_inputs,
                    "outputs": expected_outputs,
                }:
                    errors.append("io_spec_mismatch")
            except Exception as exc:
                errors.append(f"io_spec_error:{exc}")

        output_weights = namespace.get("output_weights")
        if not callable(output_weights):
            errors.append("output_weights_missing")
        else:
            try:
                weights = output_weights()
                if not isinstance(weights, dict) or set(weights.keys()) != set(
                    expected_outputs
                ):
                    errors.append("output_weights_mismatch")
            except Exception as exc:
                errors.append(f"output_weights_error:{exc}")

        normalize_output = namespace.get("normalize_output")
        if not callable(normalize_output):
            errors.append("normalize_output_missing")
        else:
            try:
                normalized = normalize_output(
                    "key",
                    "gold",
                    "pred",
                    pred_name="pred",
                    pred_trace=None,
                )
                if not (
                    isinstance(normalized, tuple)
                    and len(normalized) == 2
                    and normalized == ("gold", "pred")
                ):
                    errors.append("normalize_output_mismatch")
            except Exception as exc:
                errors.append(f"normalize_output_error:{exc}")
    finally:
        _restore_runtime_guards(originals)

    checks["module-smoke"] = len(errors) == 0
    return {"ok": checks["module-smoke"], "checks": checks, "errors": errors}


def _worker(argv: Sequence[str]) -> int:
    if len(argv) != 5:
        raise SystemExit(
            "usage: python -m dspx.generated_code_guard <signature|module> <code_path> <payload_path> <result_path>"
        )

    mode = str(argv[1]).strip().lower()
    code_path = Path(argv[2])
    payload_path = Path(argv[3])
    result_path = Path(argv[4])
    code = code_path.read_text(encoding="utf-8")
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    if mode == "signature":
        result = _run_signature_worker(code, payload)
    elif mode == "module":
        result = _run_module_worker(code, payload)
    else:
        result = {"ok": False, "errors": [f"unknown_mode:{mode}"]}
    result_path.write_text(json.dumps(result, sort_keys=True), encoding="utf-8")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(_worker(sys.argv))
