# summary: "Validates and smoke-tests generated DSPy code in an isolated, capability-denied subprocess."
# read_when:
#   - "Changing generated-code AST policy, runtime guards, smoke workers, or isolation behavior."

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

from dspx.redaction import sanitize_diagnostic_text

_SAFE_IMPORT_MODULES = frozenset(
    {
        "__future__",
        "dspy",
        "json",
        "typing",
        "typing_extensions",
    }
)

_OS_PROCESS_FUNCTIONS = (
    "execl",
    "execle",
    "execlp",
    "execlpe",
    "execv",
    "execve",
    "execvp",
    "execvpe",
    "fork",
    "forkpty",
    "popen",
    "posix_spawn",
    "posix_spawnp",
    "spawnl",
    "spawnle",
    "spawnlp",
    "spawnlpe",
    "spawnv",
    "spawnve",
    "spawnvp",
    "spawnvpe",
    "startfile",
    "system",
)

_DENIED_DYNAMIC_IMPORT_ROOTS = frozenset(
    {
        "builtins",
        "ctypes",
        "importlib",
        "io",
        "multiprocessing",
        "os",
        "pathlib",
        "runpy",
        "shutil",
        "socket",
        "subprocess",
        "sys",
    }
)

_DENIED_FUNCTION_CALLS = frozenset(
    {
        "__import__",
        "breakpoint",
        "compile",
        "delattr",
        "dir",
        "eval",
        "exec",
        "getattr",
        "globals",
        "input",
        "locals",
        "open",
        "setattr",
        "vars",
    }
)

_DENIED_CALL_ROOTS = _DENIED_DYNAMIC_IMPORT_ROOTS | {"__builtins__"}
_DENIED_ANNOTATION_NAMES = (
    _DENIED_FUNCTION_CALLS
    | _DENIED_CALL_ROOTS
    | {
        "BufferedReader",
        "BufferedWriter",
        "FileIO",
        "Path",
        "PathLike",
        "Popen",
        "PosixPath",
        "PurePath",
        "TextIOWrapper",
        "WindowsPath",
    }
)

_FORBIDDEN_FUNCTION_BODY_NODES = (
    ast.AsyncWith,
    ast.Await,
    ast.Delete,
    ast.Global,
    ast.Import,
    ast.ImportFrom,
    ast.Lambda,
    ast.Nonlocal,
    ast.Try,
    ast.With,
    ast.Yield,
    ast.YieldFrom,
)


def _smoke_exception_marker(prefix: str, exc: BaseException) -> str:
    """Return a bounded generated-code smoke error without exception contents."""

    return f"{prefix}:{exc.__class__.__name__}"


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
    return sanitize_diagnostic_text(str(text or "").strip(), limit=limit)


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
        try:
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
        except subprocess.TimeoutExpired:
            return {
                "ok": False,
                "checks": {"module-smoke": False} if mode == "module" else {},
                "errors": [f"smoke_runner_timeout:{timeout}s"],
            }
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


def _annotationish(
    node: ast.AST | None, *, literal_value_context: bool = False
) -> bool:
    """Return True for passive type syntax that cannot execute code.

    Python evaluates annotations at class/function definition time unless a
    future-annotations import is present. Generated-code smoke checks therefore
    treat annotations as a separate executable surface instead of relying on the
    runtime guard to catch dangerous calls after the AST gate has passed.
    """
    if node is None:
        return True
    if isinstance(node, ast.Name):
        return not node.id.startswith("__") and node.id not in _DENIED_ANNOTATION_NAMES
    if isinstance(node, ast.Attribute):
        return (
            not node.attr.startswith("__")
            and node.attr not in _DENIED_ANNOTATION_NAMES
            and _annotationish(node.value)
        )
    if isinstance(node, ast.Subscript):
        value_name = _call_name(node.value)
        literal_context = value_name in {"Literal", "typing.Literal"}
        return _annotationish(node.value) and _annotationish(
            node.slice, literal_value_context=literal_context
        )
    if isinstance(node, ast.Tuple | ast.List):
        return all(
            _annotationish(item, literal_value_context=literal_value_context)
            for item in node.elts
        )
    if isinstance(node, ast.Constant):
        if literal_value_context:
            return node.value is None or isinstance(node.value, (str, int, float, bool))
        return node.value is None
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return _annotationish(node.left) and _annotationish(node.right)
    return False


def _validate_signature_field(node: ast.stmt, *, errors: list[str]) -> None:
    if isinstance(node, ast.Pass):
        return
    if _expr_is_docstring(node):
        return
    if not isinstance(node, ast.AnnAssign) or not isinstance(node.target, ast.Name):
        errors.append(f"signature_stmt_not_allowed:{node.__class__.__name__}")
        return
    if not _annotationish(node.annotation):
        errors.append(f"signature_annotation_not_allowed:{node.target.id}")
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


def _validate_function_annotations(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    errors: list[str],
    label: str,
) -> None:
    args = [
        *node.args.posonlyargs,
        *node.args.args,
        *node.args.kwonlyargs,
    ]
    if node.args.vararg is not None:
        args.append(node.args.vararg)
    if node.args.kwarg is not None:
        args.append(node.args.kwarg)
    for arg in args:
        if not _annotationish(arg.annotation):
            errors.append(f"{label}_annotation_not_allowed:{node.name}.{arg.arg}")
    if not _annotationish(node.returns):
        errors.append(f"{label}_return_annotation_not_allowed:{node.name}")


def _function_argument_names(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    args = [
        *node.args.posonlyargs,
        *node.args.args,
        *node.args.kwonlyargs,
    ]
    if node.args.vararg is not None:
        args.append(node.args.vararg)
    if node.args.kwarg is not None:
        args.append(node.args.kwarg)
    return {arg.arg for arg in args}


def _validate_generated_function_body(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    errors: list[str],
    label: str,
) -> None:
    argument_names = _function_argument_names(node)
    for child in ast.walk(node):
        if child is node:
            continue
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            errors.append(f"{label}_nested_definition_not_allowed:{node.name}")
            continue
        if isinstance(child, _FORBIDDEN_FUNCTION_BODY_NODES):
            errors.append(
                f"{label}_body_node_not_allowed:{node.name}:{child.__class__.__name__}"
            )
            continue
        if isinstance(child, ast.Attribute):
            if child.attr.startswith("__") and child.attr != "__init__":
                errors.append(
                    f"{label}_dunder_attribute_not_allowed:{node.name}:{child.attr}"
                )
                continue
        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
            if child.id == "__builtins__" or (
                child.id in _DENIED_FUNCTION_CALLS and child.id not in argument_names
            ):
                errors.append(f"{label}_name_not_allowed:{node.name}:{child.id}")
                continue
        if isinstance(child, ast.Subscript):
            value_name = _call_name(child.value)
            if value_name == "__builtins__":
                errors.append(f"{label}_builtins_subscript_not_allowed:{node.name}")
                continue
        if isinstance(child, ast.Call):
            callee = _call_name(child.func)
            if callee is None:
                errors.append(f"{label}_call_not_allowed:{node.name}:unknown")
                continue
            root = callee.split(".", 1)[0]
            if callee in _DENIED_FUNCTION_CALLS or root in _DENIED_CALL_ROOTS:
                errors.append(f"{label}_call_not_allowed:{node.name}:{callee}")
                continue
            if callee.startswith("__") and callee != "__init__":
                errors.append(f"{label}_call_not_allowed:{node.name}:{callee}")


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
        _validate_function_annotations(
            child,
            errors=errors,
            label="method",
        )
        _validate_generated_function_body(
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
            if not _annotationish(node.annotation):
                errors.append(f"top_level_annotation_not_allowed:{node.target.id}")
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
                _validate_function_annotations(
                    node,
                    errors=errors,
                    label="top_level_function",
                )
                _validate_generated_function_body(
                    node,
                    errors=errors,
                    label="top_level_function",
                )
            continue
        errors.append(f"top_level_stmt_not_allowed:{node.__class__.__name__}")
    return errors


def _install_runtime_guards() -> Mapping[str, Any]:
    original_import = builtins.__import__
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
    original_os_open = os.open
    original_os_write = os.write
    original_os_process_functions = {
        name: getattr(os, name) for name in _OS_PROCESS_FUNCTIONS if hasattr(os, name)
    }
    original_socket_create_connection = socket.create_connection
    original_socket_connect = socket.socket.connect
    original_socket_connect_ex = socket.socket.connect_ex
    original_subprocess_run = subprocess.run
    original_subprocess_popen = subprocess.Popen

    def _deny(message: str):
        def _inner(*args, **kwargs):
            raise PermissionError(message)

        return _inner

    def _guard_import(name, globals=None, locals=None, fromlist=(), level=0):
        if level:
            return original_import(name, globals, locals, fromlist, level)
        root = str(name or "").split(".", 1)[0]
        if root in _DENIED_DYNAMIC_IMPORT_ROOTS:
            raise PermissionError(f"dynamic_import_denied_during_smoke:{root}")
        if root in _SAFE_IMPORT_MODULES or root in sys.modules:
            return original_import(name, globals, locals, fromlist, level)
        raise PermissionError(f"dynamic_import_denied_during_smoke:{root or 'unknown'}")

    def _guard_open(file, mode="r", *args, **kwargs):
        raise PermissionError("filesystem_access_denied_during_smoke")

    def _guard_io_open(file, mode="r", *args, **kwargs):
        raise PermissionError("filesystem_access_denied_during_smoke")

    def _guard_path_open(self, mode="r", *args, **kwargs):
        raise PermissionError("filesystem_access_denied_during_smoke")

    builtins.__import__ = cast(Any, _guard_import)
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
    os.open = _deny("filesystem_write_denied_during_smoke")
    os.write = _deny("filesystem_write_denied_during_smoke")
    for name in original_os_process_functions:
        setattr(os, name, _deny("subprocess_denied_during_smoke"))
    socket.create_connection = _deny("network_access_denied_during_smoke")
    socket.socket.connect = _deny("network_access_denied_during_smoke")
    socket.socket.connect_ex = _deny("network_access_denied_during_smoke")
    subprocess.run = _deny("subprocess_denied_during_smoke")
    subprocess.Popen = _deny("subprocess_denied_during_smoke")

    return {
        "import": original_import,
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
        "os_open": original_os_open,
        "os_write": original_os_write,
        "os_process_functions": original_os_process_functions,
        "socket_create_connection": original_socket_create_connection,
        "socket_connect": original_socket_connect,
        "socket_connect_ex": original_socket_connect_ex,
        "subprocess_run": original_subprocess_run,
        "subprocess_popen": original_subprocess_popen,
    }


def _restore_runtime_guards(originals: Mapping[str, Any]) -> None:
    builtins.__import__ = originals["import"]
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
    os.open = originals["os_open"]
    os.write = originals["os_write"]
    for name, value in originals["os_process_functions"].items():
        setattr(os, name, value)
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
        except BaseException as exc:
            return {"ok": False, "errors": [_smoke_exception_marker("exec_error", exc)]}
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
    except BaseException as exc:
        return {
            "ok": False,
            "checks": checks,
            "errors": [_smoke_exception_marker("dspy_import_error", exc)],
        }

    namespace: dict[str, Any] = {}
    originals = _install_runtime_guards()
    try:
        try:
            exec(code, namespace, namespace)
        except BaseException as exc:
            return {
                "ok": False,
                "checks": checks,
                "errors": [_smoke_exception_marker("exec_error", exc)],
            }

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
            except BaseException as exc:
                errors.append(_smoke_exception_marker("build_student_error", exc))
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
                    self._dspx_capture_predict = True

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
            except BaseException as exc:
                errors.append(_smoke_exception_marker("forward_error", exc))

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
            except BaseException as exc:
                errors.append(_smoke_exception_marker("io_spec_error", exc))

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
            except BaseException as exc:
                errors.append(_smoke_exception_marker("output_weights_error", exc))

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
            except BaseException as exc:
                errors.append(_smoke_exception_marker("normalize_output_error", exc))
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
