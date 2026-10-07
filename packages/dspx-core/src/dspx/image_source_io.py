# summary: "Shared bounded source/URI/fd primitives; no fetch or upstream image materialization."
# read_when:
#   - "Changing generation refusal or bounded source reads; see AK6607 for unfinished orchestration."

from __future__ import annotations

import base64
import json
import hashlib
import os
from pathlib import Path
import re
import stat
from typing import Any, Callable, Mapping, TypeVar, cast

from pydantic import ValidationError

from .image_admission import (
    ImageContractError,
    require,
)

_T = TypeVar("_T")
IDENTIFIER_ERROR_CODE = "program_field_identifier"
IDENTIFIER_ERROR_MESSAGE = "program intent fields must be valid Python identifiers"


def identifier_validation_message(error: ValidationError) -> str | None:
    """Closed error-type mapping; never expose Pydantic input/context/message."""
    if any(
        row["type"] == IDENTIFIER_ERROR_CODE
        for row in error.errors(
            include_input=False, include_context=False, include_url=False
        )
    ):
        return IDENTIFIER_ERROR_MESSAGE
    return None


def load_generation_document(path: Path) -> Any:
    from .image_input_contract import safe_generation_document

    return safe_generation_document(path.expanduser().absolute())


def load_intent_document(path: Path, validate: Callable[[dict[str, Any]], _T]) -> _T:
    """Image-bearing documents fail with fixed codes; text intents keep validator text."""
    from .image_input_contract import generation_preflight

    safe_message: str | None = None
    payload: dict[str, Any] | None = None
    try:
        source = path.expanduser().absolute()
        loaded = load_generation_document(source)
        require(isinstance(loaded, Mapping), "image_input_invalid")
        payload = dict(loaded)
        resolve_generation_examples(payload, source=source)
        return validate(payload)
    except ImageContractError as error:
        code = error.code
    except ValidationError as error:
        safe_message = identifier_validation_message(error)
        if safe_message is None and payload is not None:
            try:
                text_only = not generation_preflight(payload)
            except Exception:
                text_only = False  # image material or unbounded: fixed code only
            if text_only:
                safe_message = validation_messages(error)
        code = "image_input_invalid"
    except Exception:
        code = "image_input_invalid"
    # Leave the handler before raising so neither raw values nor context survive.
    if safe_message is not None:
        raise ValueError(safe_message) from None
    raise ImageContractError(code) from None


def resolve_generation_examples(payload: dict[str, Any], *, source: Path) -> None:
    examples_path_raw = payload.get("examples_path")
    if not examples_path_raw:
        return
    examples_path = Path(str(examples_path_raw)).expanduser()
    if not examples_path.is_absolute():
        examples_path = source.parent / examples_path
    examples_payload = load_generation_document(examples_path)
    if not isinstance(examples_payload, list) or not all(
        isinstance(item, Mapping) for item in examples_payload
    ):
        raise ValueError("program intent examples_path must contain a list of objects")
    payload["examples"] = [dict(item) for item in examples_payload]
    payload["examples_path"] = str(examples_path.resolve())


START = "<<CUSTOM-TYPE-START-IDENTIFIER>>"
END = "<<CUSTOM-TYPE-END-IDENTIFIER>>"
_RESERVED = frozenset(
    {
        "imageDataBase64",
        "imageDataMimeType",
        "pixelInspectionInputStatus",
        "modelImageInput",
        "image_file",
        "image_base64",
        "image_url",
    }
)
_UNSAFE_TEXT = re.compile(
    r"data:image/|<<CUSTOM-TYPE-(?:START|END)-IDENTIFIER>>|"
    r"imageDataBase64|available_bounded_inline_image_payload|modelImageInput"
)


def image_generation_profile(intent: object) -> bool:
    """Only a ProgramIntent or a mapping can declare an image profile; others are text."""
    from .image_input_contract import generation_preflight, intent_document

    document = intent_document(intent)
    return False if document is None else generation_preflight(document)


def validation_messages(error: ValidationError) -> str:
    """Validator messages only: never Pydantic input values, context or URLs."""
    rows = error.errors(include_input=False, include_context=False, include_url=False)
    return "; ".join(str(row["msg"]) for row in rows) or "invalid program intent"


def validate_contract_verification_payload(
    payload: Mapping[str, object],
    *,
    intent_source: Path | None,
) -> None:
    if payload.get("schema_version") != "program-architecture-contract-verification-v1":
        raise ValueError("invalid contract verification schema_version")
    if payload.get("status") != "verified_contract_intent":
        raise ValueError("contract verification is not verified")
    if payload.get("materialization_allowed_by_contract_verification") is not True:
        raise ValueError("contract verification does not allow materialization")
    gate = payload.get("materialization_gate")
    if not isinstance(gate, Mapping) or not all(type(key) is str for key in gate):
        raise ValueError("contract verification materialization gate is not open")
    gate = cast(Mapping[str, object], gate)
    if gate.get("status") != "verified_for_explicit_program_gen_materialization":
        raise ValueError("contract verification materialization gate is not open")
    if any(
        gate.get(key)
        for key in (
            "allows_live_tools",
            "allows_custom_imports",
            "allows_external_retrievers",
        )
    ):
        raise ValueError("contract verification unexpectedly allows live effects")
    if intent_source is not None:
        expected_hash = str(
            gate.get("program_gen_must_match_intent_hash") or ""
        ).strip()
        if not expected_hash:
            raise ValueError("contract verification missing intent hash")
        actual_hash = hashlib.sha256(
            intent_source.expanduser()
            .resolve()
            .read_text(encoding="utf-8")
            .encode("utf-8")
        ).hexdigest()
        if actual_hash != expected_hash:
            raise ValueError("contract verification intent_hash_mismatch")


def contract_verification_metadata(
    path: Path | None,
    *,
    root: Path,
    intent_source: Path | None,
    image_profile: bool = False,
) -> dict[str, object] | None:
    # This unconditional generation hook also precedes normalization persistence.
    # Provenance is a separate caller input, not covered by guarding the intent.
    if image_profile:
        from .image_input_contract import generation_preflight

        if intent_source is not None:
            generation_preflight(str(intent_source.expanduser().resolve()))
        if path is not None:
            generation_preflight(str(path.expanduser().absolute()))
    if path is None:
        return None
    if image_profile:
        from .image_admission import parse_json

        source = path.expanduser().absolute()
        fd = open_root(source.parent)
        try:
            raw = read_relative(fd, source.name, limit=41_943_040)
        finally:
            os.close(fd)
        payload = parse_json(raw)
        generation_preflight(payload)
        text = raw.decode("utf-8")
    else:
        source = path.expanduser().resolve()
        text = source.read_text(encoding="utf-8")
        payload = json.loads(text)
    validate_contract_verification_payload(payload, intent_source=intent_source)
    candidate_path = root / "program_architecture_contract_verification.json"
    candidate_path.write_text(text, encoding="utf-8")
    return {
        "path": "program_architecture_contract_verification.json",
        "source_path": str(source),
        "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "schema_version": str(
            payload.get("schema_version")
            or "program-architecture-contract-verification-v1"
        ),
        "status": str(payload.get("status") or "unknown"),
        "materialization_gate": dict(payload.get("materialization_gate") or {}),
        "non_authority": dict(payload.get("non_authority") or {}),
    }


def open_root(path: Path) -> int:
    """Open concrete absolute ancestry component-by-component, never resolve links."""
    require(path.is_absolute(), "image_input_invalid")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
    fd = os.open("/", flags)
    try:
        for component in path.parts[1:]:
            require(component not in {"", ".", ".."}, "image_input_invalid")
            child = os.open(component, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise ImageContractError("image_input_invalid") from None


def _contained_fd(root_fd: int, target_fd: int) -> None:
    root_name = os.readlink(f"/proc/self/fd/{root_fd}")
    target_name = os.readlink(f"/proc/self/fd/{target_fd}")
    require(
        root_name.startswith("/")
        and target_name.startswith("/")
        and not root_name.endswith(" (deleted)")
        and not target_name.endswith(" (deleted)"),
        "image_input_invalid",
    )
    Path(target_name).relative_to(Path(root_name))


def read_relative(root_fd: int, name: str, *, limit: int) -> bytes:
    require(
        type(name) is str
        and len(name) > 0
        and not name.startswith("/")
        and "\\" not in name
        and "\0" not in name
        and ":" not in name,
        "image_input_invalid",
    )
    components = name.split("/")
    require(
        len(name.encode("utf-8")) <= 4096 and len(components) <= 16,
        "image_input_invalid",
    )
    require(
        all(
            item not in {"", ".", ".."} and not item.startswith("~")
            for item in components
        ),
        "image_input_invalid",
    )
    fd = os.dup(root_fd)
    leaf = -1
    try:
        for item in components[:-1]:
            child = os.open(
                item,
                os.O_RDONLY
                | os.O_DIRECTORY
                | os.O_CLOEXEC
                | os.O_NOFOLLOW
                | os.O_NONBLOCK,
                dir_fd=fd,
            )
            os.close(fd)
            fd = child
            _contained_fd(root_fd, fd)
        leaf = os.open(
            components[-1],
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=fd,
        )
        _contained_fd(root_fd, leaf)
        before = os.fstat(leaf)
        require(
            stat.S_ISREG(before.st_mode) and 0 < before.st_size <= limit, "image_budget"
        )
        chunks = []
        size = 0
        while size <= limit:
            block = os.read(leaf, min(65_536, limit + 1 - size))
            if not block:
                break
            size += len(block)
            chunks.append(block)
        _contained_fd(root_fd, leaf)
        after = os.fstat(leaf)
        require(size <= limit and size == before.st_size, "image_budget")
        require(
            (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
                before.st_ctime_ns,
            )
            == (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            ),
            "image_input_invalid",
        )
        return b"".join(chunks)
    except Exception:
        pass  # normalize outside the caught exception scope, never return a fallback
    finally:
        if leaf >= 0:
            os.close(leaf)
        os.close(fd)
    raise ImageContractError("image_input_invalid") from None


def plain_text(value: object) -> str:
    require(
        type(value) is str
        and len(value) <= 1_000_000
        and _UNSAFE_TEXT.search(value) is None,
        "image_marker_invalid",
    )
    return cast(str, value)


def image_bytes(source: str, media_type: str) -> bytes:
    require(
        type(source) is str and media_type in {"image/png", "image/jpeg"},
        "image_input_invalid",
    )
    if source.startswith("data:"):
        prefix = f"data:{media_type};base64,"
        require(source.startswith(prefix), "image_input_invalid")
        source = source[len(prefix) :]
    require(0 < len(source) <= 4 * ((8_388_608 + 2) // 3), "image_budget")
    try:
        raw = base64.b64decode(source, validate=True)
        require(
            0 < len(raw) <= 8_388_608
            and base64.b64encode(raw).decode("ascii") == source,
            "image_input_invalid",
        )
        return raw
    except Exception:
        raise ImageContractError("image_input_invalid") from None


def image_annotation(source: str) -> str:
    """Call-free bounded annotation grammar, without silent coercion to str."""
    import ast

    require(type(source) is str and len(source) <= 4096, "signature_input_shape")
    tree = ast.parse(source, mode="eval").body

    def check(node: ast.AST, depth: int = 0) -> None:
        require(depth <= 16, "signature_input_shape")
        if isinstance(node, ast.Name):
            require(node.id in {"str", "int", "float", "bool"}, "signature_input_shape")
        elif isinstance(node, ast.Constant):
            require(node.value is None, "signature_input_shape")
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            check(node.left, depth + 1)
            check(node.right, depth + 1)
        elif isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
            name = node.value.id
            args = (
                list(node.slice.elts)
                if isinstance(node.slice, ast.Tuple)
                else [node.slice]
            )
            if name == "Literal":
                require(0 < len(args) <= 64, "signature_input_shape")
                for item in args:
                    value = ast.literal_eval(item)
                    require(
                        type(value) in (str, int, float, bool, type(None)),
                        "signature_input_shape",
                    )
                    if type(value) is str:
                        plain_text(value)
            elif name in {"Optional", "list"}:
                require(len(args) == 1, "signature_input_shape")
                check(args[0], depth + 1)
            elif name in {"Union", "tuple"}:
                require(0 < len(args) <= 64, "signature_input_shape")
                for index, item in enumerate(args):
                    if isinstance(item, ast.Constant) and item.value is Ellipsis:
                        require(
                            name == "tuple" and index == 1 and len(args) == 2,
                            "signature_input_shape",
                        )
                    else:
                        check(item, depth + 1)
            elif name == "dict":
                require(
                    len(args) == 2
                    and isinstance(args[0], ast.Name)
                    and args[0].id == "str",
                    "signature_input_shape",
                )
                check(args[1], depth + 1)
            else:
                require(False, "signature_input_shape")
        else:
            require(False, "signature_input_shape")

    check(tree)
    return ast.unparse(tree)


def image_surface_sources(intent: object) -> tuple[str, str]:
    """The shipped image signature/module renderer and source attestation share bytes."""
    from .services.program_intent import ProgramIntent
    from .services.program_contracts import intent_surface_names, intent_field_specs

    require(
        type(intent) is ProgramIntent and image_generation_profile(intent),
        "image_privacy",
    )
    checked = cast(ProgramIntent, intent)
    require(not checked.options.get("focused_json_bundle_runtime"), "image_privacy")
    names = intent_surface_names(checked)
    lines = [
        "import dspy",
        "from typing import Optional, Literal, Union",
        "",
        f"class {names['signature_class']}(dspy.Signature):",
        f"    {plain_text(checked.objective)!r}",
    ]
    for role in ("input", "output"):
        fields = intent_field_specs(checked, role=role)
        for spec in fields:
            require(
                set(spec) <= {"name", "type", "desc", "description", "default"},
                "signature_input_shape",
            )
            name = plain_text(spec["name"])
            require(name.isidentifier(), "signature_input_shape")
            annotation = image_annotation(spec.get("type") or "str")
            description = plain_text(
                spec.get("desc") or spec.get("description") or name
            )
            default = ""
            if "default" in spec:
                from .image_admission import bounded_tree

                bounded_tree(spec["default"])
                default = ", default=" + repr(spec["default"])
            lines.append(
                f"    {name}: {annotation} = dspy.{role.title()}Field(desc={description!r}{default})"
            )
    signature = "\n".join(lines) + "\n"
    arguments = ", ".join(checked.inputs)
    calls = ", ".join(f"{name}={name}" for name in checked.inputs)
    module = (
        "import dspy\n"
        f"from signature import {names['signature_class']}\n\n"
        f"class {names['module_class']}(dspy.Module):\n"
        f"    {plain_text(checked.objective)!r}\n"
        "    def __init__(self, use_cot: bool = False) -> None:\n"
        "        super().__init__()\n"
        f"        self.predict = dspy.ChainOfThought({names['signature_class']}) if use_cot else dspy.Predict({names['signature_class']})\n"
        f"    def forward(self, {arguments}):\n        return self.predict({calls})\n\n"
        "def build_student(*, use_cot: bool = False):\n"
        f"    return {names['module_class']}(use_cot=use_cot)\n"
        "def io_spec():\n"
        f"    return {{'inputs': {checked.inputs!r}, 'outputs': {checked.outputs!r}}}\n"
        "def output_weights():\n"
        f"    return {dict.fromkeys(checked.outputs, 1.0)!r}\n"
        "def normalize_output(key, gold, pred, pred_name=None, pred_trace=None):\n"
        "    return gold, pred\n"
    )
    return signature, module
