"""Confined immutable production source snapshots and native field shape checks."""

from __future__ import annotations

import ast
import builtins
import types
import typing
from dataclasses import dataclass
from typing import cast

import dspy

from .image_admission import ImageContractError, digest, parse_json, require, sha
from .image_source_io import image_generation_profile, plain_text, read_relative
from .image_privacy import require_privacy


def image_program_code(summary: dict[str, object]) -> str:
    code = """from __future__ import annotations
from module import build_student as build_module_student, io_spec
PROGRAM_TEMPLATE_VERSION = "program-image-assembly-v1"
def build_program():
    return build_module_student()
def build_student(*, use_cot: bool = False):
    return build_module_student(use_cot=use_cot)
def configure_observability(**kwargs):
    return False
def end_observability_run(*args, **kwargs):
    return None
"""
    return code + "def intent_summary():\n    return " + repr(summary) + "\n"


def image_module_code(code: str) -> str:
    """Production image template variant: standard COT, not a second LM."""
    tree = ast.parse(code)
    edits = []
    lines = code.splitlines(keepends=True)
    for cls in tree.body:
        if not isinstance(cls, ast.ClassDef):
            continue
        for method in cls.body:
            if not isinstance(method, ast.FunctionDef) or method.name != "__init__":
                continue
            for statement in method.body:
                if not isinstance(statement, ast.Assign) or not isinstance(
                    statement.value, ast.Call
                ):
                    continue
                call = statement.value
                if not (
                    isinstance(call.func, ast.Attribute)
                    and isinstance(call.func.value, ast.Name)
                    and call.func.value.id == "dspy"
                    and call.func.attr == "Predict"
                ):
                    continue
                target = ast.unparse(statement.targets[0])
                arguments = ", ".join(ast.unparse(arg) for arg in call.args)
                edits.append(
                    (
                        statement.lineno - 1,
                        statement.end_lineno,
                        f"        {target} = dspy.ChainOfThought({arguments}) if use_cot else dspy.Predict({arguments})\n",
                    )
                )
    require(bool(edits), "image_privacy")
    for first, last, replacement in reversed(edits):
        if last is None:
            raise ImageContractError("image_privacy") from None
        lines[first:last] = [replacement]
    return "".join(lines)


def valid_annotation(annotation: object, depth: int = 0) -> bool:
    if depth > 16:
        return False
    if any(annotation is kind for kind in (str, int, float, bool, type(None))):
        return True
    origin, args = typing.get_origin(annotation), typing.get_args(annotation)
    if origin is typing.Union or origin is types.UnionType:
        return 1 < len(args) <= 8 and all(
            valid_annotation(arg, depth + 1) for arg in args
        )
    if origin is typing.Literal:
        return bool(args) and all(
            type(arg) in (str, int, float, bool, type(None)) for arg in args
        )
    if origin is list or origin is tuple:
        return bool(args) and all(
            arg is Ellipsis or valid_annotation(arg, depth + 1) for arg in args
        )
    if origin is dict:
        return (
            len(args) == 2 and args[0] is str and valid_annotation(args[1], depth + 1)
        )
    return False


def valid_value(annotation: object, value: object, depth: int = 0) -> bool:
    if depth > 16 or not valid_annotation(annotation):
        return False
    if any(annotation is kind for kind in (str, int, float, bool, type(None))):
        return type(value) is annotation
    origin, args = typing.get_origin(annotation), typing.get_args(annotation)
    if origin is typing.Union or origin is types.UnionType:
        return any(valid_value(arg, value, depth + 1) for arg in args)
    if origin is typing.Literal:
        return any(type(value) is type(arg) and value == arg for arg in args)
    if origin is list:
        return (
            type(value) is list
            and len(args) == 1
            and all(valid_value(args[0], item, depth + 1) for item in value)
        )
    if origin is tuple and type(value) is tuple:
        if len(args) == 2 and args[1] is Ellipsis:
            return all(valid_value(args[0], item, depth + 1) for item in value)
        return len(args) == len(value) and all(
            valid_value(arg, item, depth + 1)
            for arg, item in zip(args, value, strict=True)
        )
    if origin is dict and type(value) is dict:
        return all(
            type(key) is str and valid_value(args[1], item, depth + 1)
            for key, item in value.items()
        )
    return False


def check_signature(context, signature, inputs: dict | None) -> None:
    """Helper shape tree against signature descriptors, then strict marker slots."""
    plain_text(signature.instructions)
    require(
        not set(signature.input_fields)
        & {"signature", "demos", "config", "lm", "new_signature"},
        "signature_input_shape",
    )
    for name, info in signature.fields.items():
        require(valid_annotation(info.annotation), "signature_input_shape")
        plain_text(name)
        if info.description:
            plain_text(info.description)
    if inputs is None:
        return
    require(tuple(inputs) == tuple(signature.input_fields), "signature_input_shape")
    for name, value in inputs.items():
        require(
            valid_value(signature.input_fields[name].annotation, value),
            "signature_input_shape",
        )
        if context is not None and type(value) is str:
            slot = context.fields.index(name)
            parts = context.split(value, slot=slot)
            expected = [
                row.occurrence_id
                for row in context.occurrences
                if row.field_slot == slot
            ]
            actual = [row.occurrence_id for row in parts if type(row) is not str]
            require(actual == expected, "image_marker_invalid")


def convert_value(annotation: object, value: object) -> object:
    """Only JSON list-to-declared-tuple conversion; never stringification/coercion."""
    origin, args = typing.get_origin(annotation), typing.get_args(annotation)
    if origin in (typing.Union, types.UnionType):
        for arg in args:
            converted = convert_value(arg, value)
            if valid_value(arg, converted):
                return converted
        return value
    if origin is tuple and type(value) is list:
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(convert_value(args[0], item) for item in value)
        if len(args) == len(value):
            return tuple(
                convert_value(arg, item) for arg, item in zip(args, value, strict=True)
            )
    if origin is list and type(value) is list and len(args) == 1:
        return [convert_value(args[0], item) for item in value]
    if origin is dict and type(value) is dict and len(args) == 2:
        return {key: convert_value(args[1], item) for key, item in value.items()}
    return value


def parse_image_completion(
    signature: type[dspy.Signature], completion: str
) -> dict[str, object]:
    """Strict installed ChatAdapter section syntax; no repair, fallback or repr."""
    import re
    from .image_input_contract import reject_output

    active = require_privacy()
    active.check()
    reject_output(completion, active.context)
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in completion.splitlines():
        match = re.fullmatch(
            r"\[\[ ## ([A-Za-z_][A-Za-z_0-9]*) ## \]\](.*)", line.strip()
        )
        if match:
            current = match.group(1)
            require(
                current in (*signature.output_fields, "completed")
                and current not in sections,
                "image_finalization",
            )
            sections[current] = [match.group(2).strip()]
        elif current is None:
            require(not line.strip(), "image_finalization")
        else:
            sections[current].append(line)
    require(
        "completed" in sections and not "\n".join(sections.pop("completed")).strip(),
        "image_finalization",
    )
    result: dict[str, object] = {}
    for key, info in signature.output_fields.items():
        require(key in sections, "image_finalization")
        raw = "\n".join(sections[key]).strip()
        value = (
            raw
            if info.annotation is str
            else parse_json(raw.encode("utf-8"), limit=2_000_000)
        )
        converted = convert_value(info.annotation, value)
        require(valid_value(info.annotation, converted), "image_finalization")
        reject_output(converted, active.context)
        result[key] = converted
    require(set(sections) == set(result), "image_finalization")
    return result


@dataclass(frozen=True, slots=True)
class SourceSnapshot:
    signature: bytes
    module: bytes
    program: bytes
    intent: bytes
    manifest_sha256: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]

    @property
    def sha256(self) -> str:
        return digest(
            "generated-image-source-v1",
            {
                "signature": sha(self.signature),
                "module": sha(self.module),
                "program": sha(self.program),
                "intent": sha(self.intent),
                "candidate_manifest_sha256": self.manifest_sha256,
            },
        )


def _members(values: dict[str, object]) -> tuple[tuple[str, int], ...]:
    return tuple((key, id(value)) for key, value in values.items())


def _signature_state(signature: object) -> tuple[object, ...]:
    require(
        isinstance(signature, type) and issubclass(signature, dspy.Signature),
        "image_privacy",
    )
    checked = cast(type[dspy.Signature], signature)
    return (
        checked.instructions,
        tuple(
            (
                key,
                info.annotation,
                info.default,
                info.description,
                dict(info.json_schema_extra)
                if type(info.json_schema_extra) is dict
                else None,
            )
            for key, info in checked.fields.items()
        ),
    )


class RootBinding:
    """Retain concrete executable objects, not caller types or mutable hashes."""

    def __init__(
        self,
        root: object,
        modules: dict[str, types.ModuleType],
        leaves: list[dspy.Predict],
    ):
        self.root = root
        self.classes = [(type(root), _members(dict(vars(type(root)))))]
        self.globals = [
            (vars(module), _members(vars(module))) for module in modules.values()
        ]
        self.graph = {
            key: value
            for key, value in vars(root).items()
            if key in {"predict", "focused_predict"}
        }
        self.leaves = [
            (leaf, leaf.signature, _signature_state(leaf.signature)) for leaf in leaves
        ]
        pending = [
            value for module in modules.values() for value in vars(module).values()
        ]
        pending.extend(vars(type(root)).values())
        self.functions: list[tuple[types.FunctionType, tuple[object, ...]]] = []
        seen: set[int] = set()
        while pending:
            value = pending.pop()
            if type(value) is not types.FunctionType or id(value) in seen:
                continue
            seen.add(id(value))
            require(len(seen) <= 4096, "image_budget")
            self.functions.append((value, self.function_state(value)))
            if value.__closure__:
                pending.extend(cell.cell_contents for cell in value.__closure__)
            pending.append(getattr(value, "__wrapped__", None))

    @staticmethod
    def function_state(fn: types.FunctionType) -> tuple[object, ...]:
        return (
            fn.__code__,
            fn.__defaults__,
            dict(fn.__kwdefaults__ or {}),
            dict(fn.__annotations__),
            getattr(fn, "__wrapped__", None),
            tuple(id(cell.cell_contents) for cell in fn.__closure__ or ()),
        )

    def matches(self) -> bool:
        return (
            all(_members(dict(vars(cls))) == members for cls, members in self.classes)
            and all(_members(values) == members for values, members in self.globals)
            and all(self.function_state(fn) == state for fn, state in self.functions)
            and not any(
                key in vars(self.root) for key in ("forward", "__call__", "__init__")
            )
            and all(
                vars(self.root).get(key) is value for key, value in self.graph.items()
            )
            and all(
                leaf.signature is signature and _signature_state(signature) == state
                for leaf, signature, state in self.leaves
            )
        )


class ImageSourceProfile:
    """Profiles load actual confined roots; asserted hashes/types are not profiles."""

    def __init__(self, root_fd: int) -> None:
        active = require_privacy()
        active.check()
        from .services.program_intent import ProgramIntent
        from .image_source_io import image_surface_sources
        from .services.program_surfaces import render_program_code

        raw_intent = read_relative(root_fd, "intent.json", limit=50_000)
        intent = ProgramIntent.model_validate(parse_json(raw_intent))
        require(image_generation_profile(intent), "image_privacy")
        require(not intent.options.get("signature_import"), "image_privacy")
        signature, module_source = image_surface_sources(intent)
        version = str(intent.options.get("module_template_version") or "simple-v1")
        require(
            version.startswith("simple")
            and str(
                intent.options.get("signature_template_version") or "simple-v1"
            ).startswith("simple"),
            "image_privacy",
        )
        sig_raw = read_relative(root_fd, "signature.py", limit=50_000)
        mod_raw = read_relative(root_fd, "module.py", limit=50_000)
        program_raw = read_relative(root_fd, "program.py", limit=50_000)
        require(
            # ubs:ignore -- public source bytes, not a secret
            sig_raw == signature.encode()
            and mod_raw == module_source.encode()
            and program_raw == render_program_code(intent).encode(),
            "image_privacy",
        )
        # Top-level imports, definitions and literal constants only. This is checked
        # in addition to template identity so a description cannot inject effects.
        for raw in (sig_raw, mod_raw, program_raw):
            tree = ast.parse(raw)
            for node in tree.body:
                if isinstance(
                    node, (ast.Import, ast.ImportFrom, ast.ClassDef, ast.FunctionDef)
                ):
                    require(not getattr(node, "decorator_list", []), "image_privacy")
                elif isinstance(node, ast.Expr):
                    require(
                        isinstance(node.value, ast.Constant)
                        and type(node.value.value) is str,
                        "image_privacy",
                    )
                elif isinstance(node, ast.Assign):
                    ast.literal_eval(node.value)
                else:
                    raise ImageContractError("image_privacy") from None
        manifest = read_relative(root_fd, "manifest.json", limit=4_194_304)
        parse_json(manifest)
        self._snapshot = SourceSnapshot(
            sig_raw,
            mod_raw,
            program_raw,
            raw_intent,
            sha(manifest),
            tuple(intent.inputs),
            tuple(intent.outputs),
        )
        self._roots: dict[int, RootBinding] = {}

    @property
    def snapshot(self) -> SourceSnapshot:
        return self._snapshot

    def build(self, *, use_cot: bool = False) -> dspy.Module:
        require(type(use_cot) is bool, "image_privacy")
        require_privacy().check()
        modules: dict[str, types.ModuleType] = {}
        ordinary_import = builtins.__import__

        def confined_import(name: str, globals=None, locals=None, fromlist=(), level=0):
            require(level == 0, "image_privacy")
            if name in modules:
                return modules[name]
            require(
                name in {"dspy", "json", "re", "typing", "copy", "__future__"},
                "image_privacy",
            )
            return ordinary_import(name, globals, locals, fromlist, level)

        for name, raw in (
            ("signature", self.snapshot.signature),
            ("module", self.snapshot.module),
            ("program", self.snapshot.program),
        ):
            module = types.ModuleType(name)
            module.__dict__["__builtins__"] = {
                **vars(builtins),
                "__import__": confined_import,
            }
            module.__dict__["__file__"] = (
                "<generated-image-" + self.snapshot.sha256 + ">"
            )
            # ubs:ignore -- profile-bound generated program source
            exec(
                compile(raw, module.__dict__["__file__"], "exec", dont_inherit=True),
                module.__dict__,
            )
            modules[name] = module
        build = vars(modules["program"])["build_student"]
        require(type(build) is types.FunctionType, "image_privacy")
        root = build(use_cot=use_cot)
        require(isinstance(root, dspy.Module), "image_privacy")
        leaves = []
        for name in ("predict", "focused_predict"):
            leaf = vars(root).get(name)
            if type(leaf) is dspy.ChainOfThought:
                leaf = vars(leaf).get("predict")
            if leaf is not None:
                require(type(leaf) is dspy.Predict, "image_privacy")
                leaves.append(leaf)
        require(bool(leaves), "image_privacy")
        self._roots[id(root)] = RootBinding(root, modules, leaves)
        return cast(dspy.Module, root)

    def owns(self, root: object) -> bool:
        saved = self._roots.get(id(root))
        return saved is not None and saved.root is root and saved.matches()
