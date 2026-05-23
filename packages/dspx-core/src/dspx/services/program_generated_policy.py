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
    "__import__",
    "builtins.__import__",
    "compile",
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
_DENIED_CALL_ROOTS = {
    "__builtins__",
    "builtins",
    "httpx",
    "importlib",
    "os",
    "requests",
    "shutil",
    "socket",
    "subprocess",
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
    "dspy.ProgramOfThought",
    "dspy.ReAct",
    "dspy.Retrieve",
    "dspy.Tool",
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
        elif isinstance(node, ast.Attribute):
            name = _call_name(node)
            if name in _DENIED_DSPY_ATTRS:
                _add_violation(
                    violations,
                    code="dspy_attribute_not_allowed",
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
    surfaces = _module_surfaces(module_surfaces)
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
            str(item.get("code") or "violation")
            for item in policy.get("violations", [])
            if isinstance(item, Mapping)
        )
        raise ProgramGeneratedPolicyError(
            "program generated module policy failed"
            + (f": {details}" if details else "")
        )
    return policy
