from __future__ import annotations

import ast
from typing import Any, Mapping

PROGRAM_GENERATED_MODULE_POLICY_SCHEMA = "program-generated-module-policy-v1"
_PROGRAM_MODULE_POLICY_VERSION = "program-module-surface-strict-v1"

_EFFECT_KEYS = {
    "provider_called",
    "tool_called",
    "custom_import_loaded",
    "network",
    "filesystem_read",
    "filesystem_write",
    "subprocess",
    "external_authority",
}
_ALLOWED_IMPORTS = {"json", "dspy"}
_ALLOWED_FROM_IMPORTS = {"signature", "typing"}
_ALLOWED_DUNDER_ATTRS = {"__init__", "__name__"}
_DENIED_IMPORT_ROOTS = {
    "builtins",
    "ctypes",
    "httpx",
    "importlib",
    "io",
    "multiprocessing",
    "os",
    "pathlib",
    "requests",
    "runpy",
    "shutil",
    "socket",
    "subprocess",
    "sys",
    "urllib",
}
_DENIED_CALL_NAMES = {
    "__getattribute__",
    "__import__",
    "builtins.__import__",
    "compile",
    "eval",
    "exec",
    "object.__getattribute__",
    "getattr",
    "globals",
    "input",
    "locals",
    "open",
    "setattr",
    "type.__getattribute__",
    "vars",
}
_DENIED_CALL_ROOTS = {
    "__builtins__",
    "builtins",
    "httpx",
    "importlib",
    "object",
    "os",
    "requests",
    "shutil",
    "socket",
    "subprocess",
    "type",
    "urllib",
}
_DENIED_CALL_SUFFIXES = {
    "Path",
    "Path.open",
    "Path.read_bytes",
    "Path.read_text",
    "Path.write_bytes",
    "Path.write_text",
    "read_bytes",
    "read_text",
    "write_bytes",
    "write_text",
}
_DENIED_DSPY_CALLS = {
    "dspy.ColBERTv2",
    "dspy.LM",
    "dspy.Retrieve",
    "dspy.Tool",
    "dspy.configure",
    "dspy.settings.configure",
}
_DENIED_DSPY_ATTRS = {
    "dspy.settings",
    "dspy.settings.rm",
}


class ProgramGeneratedPolicyError(ValueError):
    """Raised when a generated program surface violates static policy."""


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    if isinstance(node, ast.Subscript):
        return _call_name(node.value)
    return None


def _root_name(name: str) -> str:
    return name.split(".", 1)[0]


def _has_dunder_segment(name: str) -> bool:
    return any(
        segment.startswith("__") and segment.endswith("__")
        for segment in name.split(".")
    )


def _add_violation(
    violations: list[dict[str, Any]], *, code: str, node: ast.AST, detail: str
) -> None:
    violations.append(
        {
            "code": code,
            "line": getattr(node, "lineno", None),
            "detail": detail,
        }
    )


def _module_surfaces(value: Mapping[str, Any]) -> list[dict[str, Any]]:
    surfaces = value.get("module_surfaces")
    if not isinstance(surfaces, list):
        return []
    return [dict(item) for item in surfaces if isinstance(item, Mapping)]


def _surface_primitives(surfaces: list[dict[str, Any]]) -> set[str]:
    return {str(surface.get("primitive") or "") for surface in surfaces}


def _keyword(node: ast.Call, name: str) -> ast.AST | None:
    for keyword in node.keywords:
        if keyword.arg == name:
            return keyword.value
    return None


def _int_constant(node: ast.AST | None) -> int | None:
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, int)
        and not isinstance(node.value, bool)
    ):
        return node.value
    if isinstance(node, ast.Attribute):
        return None
    return None


def _is_empty_list(node: ast.AST | None) -> bool:
    return isinstance(node, ast.List) and not node.elts


def _is_empty_dict(node: ast.AST | None) -> bool:
    return isinstance(node, ast.Dict) and not node.keys and not node.values


def _is_false(node: ast.AST | None) -> bool:
    return isinstance(node, ast.Constant) and node.value is False


def _is_safe_python_interpreter_call(node: ast.AST | None) -> bool:
    if (
        not isinstance(node, ast.Call)
        or _call_name(node.func) != "dspy.PythonInterpreter"
    ):
        return False
    allowed = {
        "enable_read_paths": _is_empty_list,
        "enable_write_paths": _is_empty_list,
        "enable_env_vars": _is_empty_list,
        "enable_network_access": _is_empty_list,
        "tools": _is_empty_dict,
        "sync_files": _is_false,
    }
    seen = {keyword.arg for keyword in node.keywords}
    if seen != set(allowed):
        return False
    return all(allowed[str(keyword.arg)](keyword.value) for keyword in node.keywords)


_SENSITIVE_DSPY_CONSTRUCTORS = {
    "dspy.ReAct",
    "dspy.ReActV2",
    "dspy.ProgramOfThought",
    "dspy.PythonInterpreter",
}


def _contains_sensitive_dspy_constructor(node: ast.AST | None) -> bool:
    if node is None:
        return False
    return any(
        _call_name(child) in _SENSITIVE_DSPY_CONSTRUCTORS for child in ast.walk(node)
    )


def _target_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            names.add(child.id)
    return names


def _assigned_sensitive_dspy_aliases(tree: ast.AST) -> set[str]:
    aliases: set[str] = set()
    for node in ast.walk(tree):
        value: ast.AST | None = None
        targets: list[ast.AST] = []
        if isinstance(node, ast.Assign):
            value = node.value
            targets = list(node.targets)
        elif isinstance(node, ast.AnnAssign):
            value = node.value
            targets = [node.target]
        if (
            value is None
            or isinstance(value, ast.Call)
            or not _contains_sensitive_dspy_constructor(value)
        ):
            continue
        for target in targets:
            aliases.update(_target_names(target))
    return aliases


def _validate_special_dspy_call(
    node: ast.Call,
    *,
    name: str,
    primitives: set[str],
    violations: list[dict[str, Any]],
) -> None:
    if name in {"dspy.ReAct", "dspy.ReActV2"}:
        primitive = "ReActV2" if name == "dspy.ReActV2" else "ReAct"
        if primitive not in primitives:
            _add_violation(
                violations,
                code="dspy_call_not_allowed",
                node=node,
                detail=name,
            )
            return
        max_iters = _int_constant(_keyword(node, "max_iters"))
        if (
            not _is_empty_list(_keyword(node, "tools"))
            or max_iters is None
            or max_iters < 1
            or max_iters > 5
        ):
            _add_violation(
                violations,
                code="unsafe_react_call",
                node=node,
                detail="ReAct/ReActV2 requires tools=[] and max_iters between 1 and 5",
            )
    elif name == "dspy.ProgramOfThought":
        if "ProgramOfThought" not in primitives:
            _add_violation(
                violations,
                code="dspy_call_not_allowed",
                node=node,
                detail=name,
            )
            return
        max_iters = _int_constant(_keyword(node, "max_iters"))
        if max_iters is None or max_iters < 1 or max_iters > 3:
            _add_violation(
                violations,
                code="unsafe_program_of_thought_call",
                node=node,
                detail="ProgramOfThought requires max_iters between 1 and 3",
            )
        interpreter = _keyword(node, "interpreter")
        if not _is_safe_python_interpreter_call(interpreter):
            _add_violation(
                violations,
                code="unsafe_program_of_thought_call",
                node=node,
                detail="ProgramOfThought requires the generated safe interpreter binding",
            )


def build_program_generated_module_policy(
    module_code: str,
    *,
    module_surfaces: Mapping[str, Any],
) -> dict[str, Any]:
    """Return static policy evidence for generated program module.py.

    This is intentionally scoped to generated module surfaces. Harnesses and
    program.py have broader IO/observability behavior and are not checked by this
    strict module-surface policy.
    """

    violations: list[dict[str, Any]] = []
    try:
        tree = ast.parse(module_code, filename="module.py")
    except SyntaxError as exc:
        return {
            "schema_version": PROGRAM_GENERATED_MODULE_POLICY_SCHEMA,
            "policy_version": _PROGRAM_MODULE_POLICY_VERSION,
            "checked_surface": "module.py",
            "status": "failed",
            "violations": [
                {
                    "code": "syntax_error",
                    "line": exc.lineno,
                    "detail": str(exc),
                }
            ],
            "effects": {key: False for key in sorted(_EFFECT_KEYS)},
        }

    surfaces = _module_surfaces(module_surfaces)
    primitives = _surface_primitives(surfaces)
    sensitive_aliases = _assigned_sensitive_dspy_aliases(tree)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = _root_name(str(alias.name))
                if alias.asname:
                    _add_violation(
                        violations,
                        code="import_alias_not_allowed",
                        node=node,
                        detail=str(alias.name),
                    )
                if root not in _ALLOWED_IMPORTS:
                    _add_violation(
                        violations,
                        code="import_not_allowed",
                        node=node,
                        detail=str(alias.name),
                    )
                if root in _DENIED_IMPORT_ROOTS:
                    _add_violation(
                        violations,
                        code="denied_import",
                        node=node,
                        detail=str(alias.name),
                    )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defaults = [
                *node.args.defaults,
                *[item for item in node.args.kw_defaults if item is not None],
            ]
            if any(
                _contains_sensitive_dspy_constructor(default) for default in defaults
            ):
                _add_violation(
                    violations,
                    code="sensitive_dspy_default_not_allowed",
                    node=node,
                    detail=node.name,
                )
        elif isinstance(node, ast.Lambda):
            defaults = [
                *node.args.defaults,
                *[item for item in node.args.kw_defaults if item is not None],
            ]
            if any(
                _contains_sensitive_dspy_constructor(default) for default in defaults
            ):
                _add_violation(
                    violations,
                    code="sensitive_dspy_default_not_allowed",
                    node=node,
                    detail="lambda",
                )
        elif isinstance(node, ast.ImportFrom):
            module = str(node.module or "")
            root = _root_name(module)
            if module not in _ALLOWED_FROM_IMPORTS:
                _add_violation(
                    violations,
                    code="from_import_not_allowed",
                    node=node,
                    detail=module,
                )
            if root in _DENIED_IMPORT_ROOTS:
                _add_violation(
                    violations,
                    code="denied_import",
                    node=node,
                    detail=module,
                )
            for alias in node.names:
                if alias.name == "*":
                    _add_violation(
                        violations,
                        code="star_import_not_allowed",
                        node=node,
                        detail=module,
                    )
                if alias.asname:
                    _add_violation(
                        violations,
                        code="import_alias_not_allowed",
                        node=node,
                        detail=f"{module}.{alias.name}",
                    )
        elif isinstance(node, ast.Call):
            name = _call_name(node.func)
            if not name:
                continue
            if name in sensitive_aliases:
                _add_violation(
                    violations,
                    code="sensitive_dspy_alias_call_not_allowed",
                    node=node,
                    detail=name,
                )
                continue
            root = _root_name(name)
            if name in _DENIED_CALL_NAMES:
                _add_violation(
                    violations,
                    code="call_not_allowed",
                    node=node,
                    detail=name,
                )
            if root in _DENIED_CALL_ROOTS:
                _add_violation(
                    violations,
                    code="call_root_not_allowed",
                    node=node,
                    detail=name,
                )
            if name in _DENIED_DSPY_CALLS:
                _add_violation(
                    violations,
                    code="dspy_call_not_allowed",
                    node=node,
                    detail=name,
                )
            if name in {"dspy.ReAct", "dspy.ReActV2", "dspy.ProgramOfThought"}:
                _validate_special_dspy_call(
                    node,
                    name=name,
                    primitives=primitives,
                    violations=violations,
                )
            if (
                name == "dspy.PythonInterpreter"
                and not _is_safe_python_interpreter_call(node)
            ):
                _add_violation(
                    violations,
                    code="unsafe_python_interpreter_call",
                    node=node,
                    detail="PythonInterpreter requires empty read/write/env/network/tools and sync_files=False",
                )
            if any(
                name == suffix or name.endswith(f".{suffix}")
                for suffix in _DENIED_CALL_SUFFIXES
            ):
                _add_violation(
                    violations,
                    code="effect_call_not_allowed",
                    node=node,
                    detail=name,
                )
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            value = node.value
            if (
                value is not None
                and not isinstance(value, ast.Call)
                and _contains_sensitive_dspy_constructor(value)
            ):
                _add_violation(
                    violations,
                    code="sensitive_dspy_alias_not_allowed",
                    node=node,
                    detail=str(_call_name(value)),
                )
        elif isinstance(node, ast.Attribute):
            name = _call_name(node)
            if name in _DENIED_DSPY_ATTRS:
                _add_violation(
                    violations,
                    code="dspy_attribute_not_allowed",
                    node=node,
                    detail=name,
                )
            elif name is not None and _has_dunder_segment(name):
                tail = name.rsplit(".", 1)[-1]
                if tail not in _ALLOWED_DUNDER_ATTRS:
                    _add_violation(
                        violations,
                        code="dunder_attribute_not_allowed",
                        node=node,
                        detail=name,
                    )

    raw_surfaces = module_surfaces.get("module_surfaces")
    if not isinstance(raw_surfaces, list) or not raw_surfaces:
        _add_violation(
            violations,
            code="module_surfaces_missing",
            node=tree,
            detail="module_surfaces must contain at least one surface",
        )
    for surface in surfaces:
        effects = surface.get("effects")
        if not isinstance(effects, Mapping):
            _add_violation(
                violations,
                code="module_surface_effects_missing",
                node=tree,
                detail=str(surface.get("module_id") or "<unknown>"),
            )
            continue
        for key in sorted(_EFFECT_KEYS):
            if bool(effects.get(key)):
                _add_violation(
                    violations,
                    code="module_surface_effect_not_allowed",
                    node=tree,
                    detail=f"{surface.get('module_id')}:{key}",
                )

    return {
        "schema_version": PROGRAM_GENERATED_MODULE_POLICY_SCHEMA,
        "policy_version": _PROGRAM_MODULE_POLICY_VERSION,
        "checked_surface": "module.py",
        "status": "passed" if not violations else "failed",
        "allowed_imports": sorted(_ALLOWED_IMPORTS),
        "allowed_from_imports": sorted(_ALLOWED_FROM_IMPORTS),
        "denied_dspy_calls": sorted(_DENIED_DSPY_CALLS),
        "checked_module_surface_count": len(surfaces),
        "effects": {key: False for key in sorted(_EFFECT_KEYS)},
        "violations": violations,
    }


def verify_program_generated_module_policy(
    module_code: str,
    *,
    module_surfaces: Mapping[str, Any],
) -> dict[str, Any]:
    policy = build_program_generated_module_policy(
        module_code,
        module_surfaces=module_surfaces,
    )
    if policy.get("status") != "passed":
        details = ", ".join(
            (
                str(item.get("code") or "violation")
                + (f":{item.get('detail')}" if item.get("detail") else "")
            )
            for item in policy.get("violations", [])
            if isinstance(item, Mapping)
        )
        raise ProgramGeneratedPolicyError(
            "program generated module policy failed"
            + (f": {details}" if details else "")
        )
    return policy
