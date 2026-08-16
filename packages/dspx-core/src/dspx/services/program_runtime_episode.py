from __future__ import annotations

import ast
import hashlib
import importlib
import json
import os
import sys
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, Iterator, Mapping, TypeGuard, cast

from dspx.cache import make_key
from dspx.run_receipts import (
    build_run_receipt,
    canonical_replay_identity_hash,
    write_run_receipt,
)
from dspx.services.program_oracle_index import index_program_oracle_evidence_path
from dspx.services.program_oracle_publication_preflight import (
    build_program_oracle_publication_preflight,
    write_program_oracle_publication_preflight,
)
from dspx.services.python_import_guard import suppress_bytecode_writes
from dspx.security import confine_path, confine_relative_path
from dspx.services.program_artifact_names import PROTECTED_PROGRAM_ARTIFACT_NAMES
from dspx.services.program_oracle_report import build_program_oracle_evidence_report
from dspx.services.program_quality_evaluation import (
    evaluate_declared_quality,
    normalize_quality_criteria,
    runtime_status_with_declared_quality,
)
from dspx.services.program_runtime_traces import (
    build_program_runtime_traces,
    validate_program_runtime_traces,
)
from dspx.services.run_replay_service import check_run_receipt
from dspx.services.soomfon_evaluation_filesystem import (
    stable_source_bytes as _stable_source_bytes,
    write_private_bytes_exclusive as _write_private_bytes_exclusive,
)
from dspx.services.soomfon_evaluation_runtime import (
    SoomfonRuntimeSnapshot,
    generated_program_module_from_snapshot,
    verify_candidate_integrity,
)
from dspx.redaction import sanitize_diagnostic_text

PROGRAM_RUNTIME_EPISODE_SCHEMA = "program-runtime-episode-v1"
PROGRAM_BEHAVIOR_RESULTS_SCHEMA = "program-behavior-results-v1"
PROGRAM_ORACLE_EVIDENCE_SCHEMA = "program-oracle-evidence-v1"
PROGRAM_MANIFEST_SCHEMA = "program-candidate-assembly-v1"
PROGRAM_RUNTIME_RECEIPT_TEMPLATE = "program-runtime-v1"
PROGRAM_RUNTIME_REPLAY_FIXTURE_SCHEMA = "program-runtime-replay-fixture-v1"
_RUNTIME_EPISODE_PROTECTED_ARTIFACT_NAMES = {
    *PROTECTED_PROGRAM_ARTIFACT_NAMES,
    "runtime_inputs.json",
    "runtime_episode.json",
    "runtime_replay_fixture.json",
    "program_oracle_report.json",
    "program_oracle_semantic.json",
}

CONTRACT_MODES = {"none", "pdf_transition_review"}
RUNTIME_EXECUTION_STATUSES = {
    "executed",
    "executed_valid_review_only",
    "failed",
    "failed_boundary",
    "failed_exception",
    "failed_missing_inputs",
    "error",
    "degraded_exception",
    "degraded_contract_violation",
    "degraded_missing_outputs",
    "degraded_pdf_contract_violation",
}
RUNTIME_EPISODE_STATUSES = {
    *RUNTIME_EXECUTION_STATUSES,
    "executed_quality_passed",
    "failed_quality",
}


@dataclass(frozen=True)
class ProgramRuntimeEpisodeBundle:
    runtime_episode: dict[str, Any]
    behavior_results: dict[str, Any]
    runtime_episode_path: Path
    runtime_episode_sha256: str
    behavior_results_path: Path
    behavior_results_sha256: str
    runtime_receipt_sha256: str = ""


_GENERATED_PROGRAM_IMPORT_LOCK = threading.RLock()
_ALLOWED_GENERATED_PROGRAM_IMPORT_ROOTS = {
    "__future__",
    "dspy",
    "dspx.tracing",
    "hashlib",
    "json",
    "module",
    "os",
    "pathlib",
    "signature",
    "typing",
}
_ALLOWED_GENERATED_PROGRAM_TOP_LEVEL_NODES = (
    ast.Assign,
    ast.AnnAssign,
    ast.Expr,
    ast.FunctionDef,
    ast.Import,
    ast.ImportFrom,
)
_ALLOWED_GENERATED_SIBLING_TOP_LEVEL_NODES = (
    *_ALLOWED_GENERATED_PROGRAM_TOP_LEVEL_NODES,
    ast.ClassDef,
)
_GENERATED_SURFACE_TOP_LEVEL_NODES = {
    "program.py": _ALLOWED_GENERATED_SIBLING_TOP_LEVEL_NODES,
    "module.py": _ALLOWED_GENERATED_SIBLING_TOP_LEVEL_NODES,
    "signature.py": _ALLOWED_GENERATED_SIBLING_TOP_LEVEL_NODES,
}
_DENIED_GENERATED_PROGRAM_CALLS = {
    "__import__",
    "compile",
    "eval",
    "exec",
    "globals",
    "locals",
    "open",
    "setattr",
    "vars",
}
_DENIED_GENERATED_PROGRAM_ALIAS_CALLS = {"getattr"}

_DENIED_GENERATED_PROGRAM_METHODS = set(
    "Popen _exit abort check_call check_output chdir chmod chown close closerange "
    "copy_file_range dup dup2 execl execle execlp execlpe execv execve execvp execvpe "
    "fchdir fchmod fchown fdopen fork forkpty ftruncate hardlink_to kill killpg link "
    "lchown lchmod makedirs memfd_create mkdir mkfifo mknod open pipe pipe2 popen "
    "posix_spawn posix_spawnp putenv pwrite remove removedirs rename renames replace "
    "rmdir run sendfile setpgid setsid spawnl spawnle spawnlp spawnlpe spawnv spawnve "
    "spawnvp spawnvpe splice symlink symlink_to system touch truncate unlink unsetenv "
    "utime write write_bytes "
    "write_text writev".split()
)


def _json_text(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    payload = json.loads(path.expanduser().resolve().read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return payload


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _write_private_json_exclusive(path: Path, payload: Mapping[str, Any]) -> None:
    _write_private_bytes_exclusive(path, _json_text(payload).encode("utf-8"))


def _safe_stub_response_for_replay() -> dict[str, Any] | None:
    raw = os.getenv("DSPX_REPLAY_FIXTURE_JSON")
    if raw is None or len(raw) > 20_000:
        return None
    try:
        payload = json.loads(raw)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    if sanitize_diagnostic_text(canonical, limit=len(canonical) + 1) != canonical:
        return None
    return {str(key): _jsonable(value) for key, value in payload.items()}


def _first_text(*values: object) -> str | None:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return None


def _safe_mapping(value: object) -> dict[str, Any]:
    return (
        {str(key): item for key, item in value.items()}
        if isinstance(value, Mapping)
        else {}
    )


def _safe_list(value: object) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _manifest_identity(manifest: Mapping[str, Any]) -> dict[str, str | None]:
    request = _safe_mapping(manifest.get("request"))
    candidate = _safe_mapping(manifest.get("candidate_assembly"))
    execution = _safe_mapping(manifest.get("execution_episode"))
    receipt = _safe_mapping(manifest.get("receipt_bundle"))
    return {
        "request_id": _first_text(
            request.get("request_id"),
            candidate.get("request_id"),
            execution.get("request_id"),
            receipt.get("request_id"),
        ),
        "candidate_id": _first_text(
            candidate.get("candidate_id"),
            execution.get("candidate_id"),
            receipt.get("candidate_id"),
        ),
        "assembly_id": _first_text(
            candidate.get("assembly_id"),
            execution.get("assembly_id"),
            receipt.get("assembly_id"),
        ),
        "episode_id": _first_text(
            execution.get("episode_id"), receipt.get("episode_id")
        ),
        "receipt_bundle_id": _first_text(receipt.get("receipt_bundle_id")),
    }


def _validated_manifest(source: Path | Mapping[str, Any]) -> dict[str, Any]:
    manifest = (
        _load_json_object(source, label="program manifest")
        if isinstance(source, Path)
        else dict(source)
    )
    if manifest.get("schema_version") != PROGRAM_MANIFEST_SCHEMA:
        raise ValueError(
            f"program manifest schema_version must be {PROGRAM_MANIFEST_SCHEMA}"
        )
    candidate = _safe_mapping(manifest.get("candidate_assembly"))
    if candidate.get("artifact_kind") != "program":
        raise ValueError(
            "program manifest candidate_assembly.artifact_kind must be program"
        )
    if not any(_manifest_identity(manifest).values()):
        raise ValueError("program manifest does not expose candidate identity")
    return manifest


def _load_inputs(path: Path) -> dict[str, Any]:
    payload = _load_json_object(path, label="runtime inputs")
    nested = payload.get("inputs")
    if isinstance(nested, Mapping):
        return {str(key): item for key, item in nested.items()}
    return payload


def _data_uri_from_base64(*, data: str, media_type: str) -> str:
    raw = data.strip()
    if raw.startswith("data:"):
        return raw
    return f"data:{media_type};base64,{raw}"


def _materialize_image_descriptor(value: Mapping[str, Any], *, base_dir: Path) -> str:
    descriptor_type = str(value.get("type") or value.get("kind") or "").strip()
    try:
        import dspy
    except (
        Exception
    ) as exc:  # pragma: no cover - import failure is environment-specific
        raise RuntimeError("runtime image descriptors require dspy") from exc

    if descriptor_type == "image_file":
        raw_path = str(value.get("path") or value.get("file") or "").strip()
        if not raw_path:
            raise ValueError("image_file descriptor requires path")
        candidate_path = Path(raw_path).expanduser()
        image_path = confine_path(base_dir, candidate_path)
        if not image_path.is_file():
            raise ValueError(f"image_file path does not exist: {image_path}")
        return str(dspy.Image.from_path(str(image_path)))

    if descriptor_type == "image_base64":
        data = str(value.get("data") or value.get("base64") or "").strip()
        if not data:
            raise ValueError("image_base64 descriptor requires data")
        media_type = str(
            value.get("media_type")
            or value.get("mime_type")
            or value.get("mimeType")
            or "image/png"
        ).strip()
        return str(dspy.Image(_data_uri_from_base64(data=data, media_type=media_type)))

    if descriptor_type == "image_url":
        url = str(value.get("url") or value.get("image_url") or "").strip()
        if not url:
            raise ValueError("image_url descriptor requires url")
        if not url.startswith("data:image/"):
            raise ValueError(
                "image_url descriptor only accepts data:image/* URLs; use image_file for local artifacts"
            )
        return str(dspy.Image(url))

    raise ValueError(f"unsupported image descriptor type: {descriptor_type}")


def _is_image_descriptor(value: object) -> TypeGuard[Mapping[str, Any]]:
    if not isinstance(value, Mapping):
        return False
    payload = cast(Mapping[str, Any], value)
    descriptor_type = str(payload.get("type") or payload.get("kind") or "").strip()
    return descriptor_type in {"image_file", "image_base64", "image_url"}


def _materialize_runtime_input_value(value: object, *, base_dir: Path) -> Any:
    if _is_image_descriptor(value):
        return _materialize_image_descriptor(value, base_dir=base_dir)
    if isinstance(value, list):
        materialized = [
            _materialize_runtime_input_value(item, base_dir=base_dir) for item in value
        ]
        if value and all(_is_image_descriptor(item) for item in value):
            return "\n".join(str(item) for item in materialized)
        return materialized
    if isinstance(value, Mapping):
        return {
            str(key): _materialize_runtime_input_value(item, base_dir=base_dir)
            for key, item in value.items()
        }
    return value


def _materialize_runtime_inputs(
    runtime_inputs: Mapping[str, Any], *, inputs_path: Path
) -> dict[str, Any]:
    base_dir = inputs_path.expanduser().resolve().parent
    return {
        str(key): _materialize_runtime_input_value(item, base_dir=base_dir)
        for key, item in runtime_inputs.items()
    }


def _import_roots(node: ast.Import | ast.ImportFrom) -> list[str]:
    if isinstance(node, ast.ImportFrom):
        return [str(node.module or "")]
    return [str(alias.name).split(".", 1)[0] for alias in node.names]


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    if isinstance(node, ast.Subscript):
        return _call_name(node.value)
    return None


def _target_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            names.add(child.id)
    return names


def _denied_generated_call_target(value: ast.AST | None) -> str | None:
    if value is None or isinstance(value, ast.Call):
        return None
    name = _call_name(value)
    if name is None:
        return None
    if name in _DENIED_GENERATED_PROGRAM_CALLS | _DENIED_GENERATED_PROGRAM_ALIAS_CALLS:
        return name
    if name.rsplit(".", 1)[-1] in _DENIED_GENERATED_PROGRAM_METHODS:
        return name
    return None


def _is_path_constructor_call(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and _call_name(node.func) in {
        "Path",
        "pathlib.Path",
    }


def _assigned_denied_generated_call_aliases(tree: ast.AST) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        value: ast.AST | None = None
        targets: list[ast.AST] = []
        if isinstance(node, ast.Assign):
            value = node.value
            targets = list(node.targets)
        elif isinstance(node, ast.AnnAssign):
            value = node.value
            targets = [node.target]
        denied_target = _denied_generated_call_target(value)
        if denied_target is None:
            continue
        for target in targets:
            for name in _target_names(target):
                aliases[name] = denied_target
    return aliases


def _literal_only(node: ast.AST | None) -> bool:
    if node is None:
        return True
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return all(_literal_only(item) for item in node.elts)
    if isinstance(node, ast.Dict):
        return all(_literal_only(item) for item in [*node.keys, *node.values])
    if isinstance(node, ast.UnaryOp):
        return _literal_only(node.operand)
    return False


_SAFE_ANNOTATION_NAMES = {
    "Any",
    "Exception",
    "Path",
    "bool",
    "dict",
    "float",
    "int",
    "list",
    "None",
    "object",
    "set",
    "str",
    "tuple",
}


def _safe_annotation(node: ast.AST | None) -> bool:
    if node is None:
        return True
    if isinstance(node, ast.Constant):
        if node.value is None:
            return True
        if isinstance(node.value, str):
            text = node.value.strip()
            if text in _SAFE_ANNOTATION_NAMES:
                return True
            try:
                parsed = ast.parse(text, mode="eval")
            except SyntaxError:
                return False
            return not isinstance(parsed.body, ast.Constant) and _safe_annotation(
                parsed.body
            )
        return False
    if isinstance(node, ast.Name):
        return node.id in _SAFE_ANNOTATION_NAMES
    if isinstance(node, ast.Attribute):
        return isinstance(node.value, ast.Name) and node.value.id == "dspy"
    if isinstance(node, ast.Subscript):
        return _safe_annotation(node.value) and _safe_annotation(node.slice)
    if isinstance(node, ast.Tuple):
        return all(_safe_annotation(item) for item in node.elts)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return _safe_annotation(node.left) and _safe_annotation(node.right)
    return False


def _safe_dspy_field_call(node: ast.AST | None) -> bool:
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return False
    if not isinstance(node.func.value, ast.Name) or node.func.value.id != "dspy":
        return False
    if node.func.attr not in {"InputField", "OutputField"}:
        return False
    return all(_literal_only(arg) for arg in node.args) and all(
        _literal_only(keyword.value) for keyword in node.keywords
    )


def _safe_class_assignment_value(node: ast.AST | None) -> bool:
    return _literal_only(node) or _safe_dspy_field_call(node)


def _safe_assignment_target(node: ast.AST) -> bool:
    if isinstance(node, ast.Name):
        return True
    if isinstance(node, (ast.Tuple, ast.List)):
        return all(_safe_assignment_target(item) for item in node.elts)
    return False


def _safe_assignment_targets(nodes: list[ast.expr]) -> bool:
    return all(_safe_assignment_target(node) for node in nodes)


def _safe_class_base(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "dspy"
        and node.attr in {"Module", "Signature"}
    )


def _function_header_violations(
    node: ast.FunctionDef | ast.AsyncFunctionDef, *, filename: str
) -> list[str]:
    violations: list[str] = []
    if node.decorator_list:
        violations.append(
            f"{filename} line {node.lineno}: decorators are not import-safe"
        )
    defaults: list[ast.AST | None] = [*node.args.defaults, *node.args.kw_defaults]
    if any(not _literal_only(default) for default in defaults):
        violations.append(
            f"{filename} line {node.lineno}: function defaults must be literal"
        )
    args = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
    if node.args.vararg is not None:
        args.append(node.args.vararg)
    if node.args.kwarg is not None:
        args.append(node.args.kwarg)
    annotations = [arg.annotation for arg in args]
    annotations.append(node.returns)
    if any(not _safe_annotation(annotation) for annotation in annotations):
        violations.append(
            f"{filename} line {node.lineno}: function annotations are not import-safe"
        )
    return violations


def _class_header_violations(node: ast.ClassDef, *, filename: str) -> list[str]:
    violations: list[str] = []
    if node.decorator_list:
        violations.append(
            f"{filename} line {node.lineno}: decorators are not import-safe"
        )
    if any(not _safe_class_base(base) for base in node.bases):
        violations.append(
            f"{filename} line {node.lineno}: class bases must be dspy.Module or dspy.Signature"
        )
    if node.keywords:
        violations.append(
            f"{filename} line {node.lineno}: class keywords are not import-safe"
        )
    return violations


def _class_body_violations(node: ast.ClassDef, *, filename: str) -> list[str]:
    violations: list[str] = []
    for item in node.body:
        if isinstance(item, ast.Expr) and isinstance(item.value, ast.Constant):
            continue
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            violations.extend(_function_header_violations(item, filename=filename))
            continue
        if (
            isinstance(item, ast.Assign)
            and _safe_assignment_targets(item.targets)
            and _safe_class_assignment_value(item.value)
        ):
            continue
        if (
            isinstance(item, ast.AnnAssign)
            and _safe_assignment_target(item.target)
            and _safe_annotation(item.annotation)
            and _safe_class_assignment_value(item.value)
        ):
            continue
        violations.append(
            f"{filename} line {getattr(item, 'lineno', '?')}: class body "
            f"{type(item).__name__} is not import-safe"
        )
    return violations


def _generated_surface_static_violations(
    source: str,
    *,
    filename: str,
    allowed_top_level_nodes: tuple[type[ast.AST], ...],
) -> list[str]:
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as exc:
        return [f"{filename} syntax error at line {exc.lineno}: {exc.msg}"]

    violations: list[str] = []
    denied_aliases = _assigned_denied_generated_call_aliases(tree)
    top_level_node_ids = {id(node) for node in tree.body}
    for node in tree.body:
        if not isinstance(node, allowed_top_level_nodes):
            violations.append(
                f"{filename} line {getattr(node, 'lineno', '?')}: top-level "
                f"{type(node).__name__} is not allowed"
            )
            continue
        if isinstance(node, ast.Expr) and not isinstance(
            getattr(node, "value", None), ast.Constant
        ):
            violations.append(
                f"{filename} line {node.lineno}: top-level expression is not allowed"
            )
        if isinstance(node, ast.Assign):
            if not _safe_assignment_targets(node.targets):
                violations.append(
                    f"{filename} line {node.lineno}: assignment target is not import-safe"
                )
            if not _literal_only(node.value):
                violations.append(
                    f"{filename} line {node.lineno}: top-level assignment must be literal"
                )
        if isinstance(node, ast.AnnAssign):
            if not _safe_assignment_target(node.target):
                violations.append(
                    f"{filename} line {node.lineno}: assignment target is not import-safe"
                )
            if not _literal_only(node.value):
                violations.append(
                    f"{filename} line {node.lineno}: top-level assignment must be literal"
                )
            if not _safe_annotation(node.annotation):
                violations.append(
                    f"{filename} line {node.lineno}: annotation is not import-safe"
                )
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            denied_target = _denied_generated_call_target(node.value)
            if denied_target is not None:
                violations.append(
                    f"{filename} line {node.lineno}: denied call alias is not allowed: {denied_target}"
                )
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for root in _import_roots(node):
                if root not in _ALLOWED_GENERATED_PROGRAM_IMPORT_ROOTS:
                    violations.append(
                        f"{filename} line {node.lineno}: import is not allowed: {root}"
                    )
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            violations.extend(_function_header_violations(node, filename=filename))
        if isinstance(node, ast.ClassDef):
            violations.extend(_class_header_violations(node, filename=filename))
            violations.extend(_class_body_violations(node, filename=filename))

    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.Import, ast.ImportFrom))
            and id(node) not in top_level_node_ids
        ):
            for root in _import_roots(node):
                if root not in _ALLOWED_GENERATED_PROGRAM_IMPORT_ROOTS:
                    violations.append(
                        f"{filename} line {node.lineno}: import is not allowed: {root}"
                    )
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id in _DENIED_GENERATED_PROGRAM_CALLS:
            violations.append(
                f"{filename} line {node.lineno}: call is not allowed: {func.id}"
            )
        if isinstance(func, ast.Name) and func.id == "getattr" and len(node.args) >= 2:
            if _is_path_constructor_call(node.args[0]):
                violations.append(
                    f"{filename} line {node.lineno}: dynamic filesystem lookup is not allowed: getattr(Path(...), ...)"
                )
            elif (
                isinstance(node.args[1], ast.Constant)
                and isinstance(node.args[1].value, str)
                and node.args[1].value in _DENIED_GENERATED_PROGRAM_METHODS
            ):
                violations.append(
                    f"{filename} line {node.lineno}: dynamic method lookup is not allowed: getattr(..., {node.args[1].value!r})"
                )
        if isinstance(func, ast.Name) and func.id in denied_aliases:
            violations.append(
                f"{filename} line {node.lineno}: denied call alias is not allowed: {func.id}->{denied_aliases[func.id]}"
            )
        if (
            isinstance(func, ast.Attribute)
            and func.attr in _DENIED_GENERATED_PROGRAM_METHODS
        ):
            violations.append(
                f"{filename} line {node.lineno}: method is not allowed: {func.attr}"
            )
    return violations


def _surface_import_roots(source: str) -> set[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            roots.update(_import_roots(node))
    return roots


def _candidate_shadowing_violations(candidate_root: Path) -> list[str]:
    violations: list[str] = []
    sibling_roots = {"module", "signature"}
    for root in _ALLOWED_GENERATED_PROGRAM_IMPORT_ROOTS:
        segment = root.split(".", 1)[0]
        if segment == "__future__":
            continue
        if segment in sibling_roots:
            if (candidate_root / segment).exists():
                violations.append(
                    f"candidate artifact shadows generated sibling module file: {segment}"
                )
            continue
        if (candidate_root / f"{segment}.py").exists() or (
            candidate_root / segment
        ).exists():
            violations.append(
                f"candidate artifact shadows allowed external import root: {segment}"
            )
    return violations


def _verify_generated_program_surfaces_safety(candidate_root: Path) -> None:
    violations: list[str] = _candidate_shadowing_violations(candidate_root)
    for filename, allowed_nodes in _GENERATED_SURFACE_TOP_LEVEL_NODES.items():
        surface_path = candidate_root / filename
        if not surface_path.exists():
            if filename == "program.py":
                violations.append("program.py is missing")
            continue
        source = surface_path.read_text(encoding="utf-8")
        for root in _surface_import_roots(source) & {"module", "signature"}:
            if not (candidate_root / f"{root}.py").is_file():
                violations.append(
                    f"{filename} imports generated sibling {root}, but {root}.py is missing"
                )
        violations.extend(
            _generated_surface_static_violations(
                source,
                filename=filename,
                allowed_top_level_nodes=allowed_nodes,
            )
        )
    if violations:
        raise ValueError(
            "generated program surface safety policy failed: "
            + "; ".join(violations[:5])
        )


@contextmanager
def _generated_program_module(candidate_root: Path) -> Iterator[Any]:
    names = ("program", "module", "signature")
    _verify_generated_program_surfaces_safety(candidate_root)
    root_text = str(candidate_root)
    # Generated program candidates import sibling modules by process-global names
    # (program/module/signature). Keep the whole candidate context serialized so
    # concurrent runtime episodes cannot pop or replace each other's modules.
    with _GENERATED_PROGRAM_IMPORT_LOCK, suppress_bytecode_writes():
        saved: dict[str, ModuleType | None] = {
            name: sys.modules.get(name) for name in names
        }
        for name in names:
            sys.modules.pop(name, None)
        sys.path.insert(0, root_text)
        try:
            yield importlib.import_module("program")
        finally:
            try:
                sys.path.remove(root_text)
            except ValueError:
                pass
            for name in names:
                sys.modules.pop(name, None)
                saved_module = saved[name]
                if saved_module is not None:
                    sys.modules[name] = saved_module


def _sanitize_runtime_diagnostic(value: object, *, limit: int = 2000) -> str:
    return sanitize_diagnostic_text("" if value is None else str(value), limit=limit)


def _jsonable(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return str(value)


def _prediction_mapping(prediction: object) -> dict[str, object]:
    if isinstance(prediction, Mapping):
        return {str(key): item for key, item in prediction.items()}
    for method_name in ("toDict", "to_dict", "model_dump"):
        method = getattr(prediction, method_name, None)
        if callable(method):
            try:
                payload = method()
            except Exception:
                continue
            if isinstance(payload, Mapping):
                return dict(payload)
    return {}


def _configure_provider() -> tuple[dict[str, object], object | None, object | None]:
    lm: object | None = None
    previous_lm: object | None = None
    try:
        import dspy
        from dspx.provider_registry import create_from_env
        from dspx.provider_runtime import (
            provider_effect_evidence_from_instance,
            provider_metadata_from_instance,
        )

        previous_lm = getattr(dspy.settings, "lm", None)
        lm = create_from_env()
        provider_name = str(os.getenv("DSPX_PROVIDER") or "")
        metadata = provider_metadata_from_instance(provider_name, lm)
        evidence = provider_effect_evidence_from_instance(lm)
        dspy.configure(lm=lm)
        return (
            {
                "status": "configured",
                "metadata": metadata,
                "effect_evidence": evidence,
            },
            lm,
            previous_lm,
        )
    except Exception as exc:
        if lm is not None:
            _close_runtime_provider(lm, previous_lm)
        return (
            {
                "status": "unavailable",
                "error": {
                    "type": type(exc).__name__,
                    "message": _sanitize_runtime_diagnostic(exc),
                },
            },
            None,
            previous_lm,
        )


def _provider_effect_evidence(lm: object | None) -> dict[str, object]:
    if lm is None:
        raise ValueError("provider adapter is unavailable")
    from dspx.dspy_typed_lm import DSPyTypedLMAdapter
    from dspx.provider_runtime import provider_effect_evidence_from_instance

    adapter = cast(DSPyTypedLMAdapter, lm)
    if type(adapter) is not DSPyTypedLMAdapter:
        raise TypeError("provider adapter has an invalid type")
    return provider_effect_evidence_from_instance(adapter)


def _close_runtime_provider(lm: object | None, previous_lm: object | None) -> None:
    if lm is None:
        return
    import dspy
    from dspx.dspy_typed_lm import DSPyTypedLMAdapter
    from dspx.openai_compatible_provider import OpenAICompatibleProvider

    try:
        dspy.configure(lm=previous_lm)
    finally:
        if (
            type(lm) is DSPyTypedLMAdapter
            and type(lm.provider) is OpenAICompatibleProvider
        ):
            lm.provider.close()


def _receipt_provider_details(provider: Mapping[str, object]) -> dict[str, object]:
    if provider.get("status") != "configured":
        return {
            "provider": "unavailable",
            "provider_family": "unavailable",
            "model": None,
            "effect_contract": "dspx-provider-effect-v1",
            "runtime": {"configuration_status": "unavailable"},
        }
    metadata = _safe_mapping(provider.get("metadata"))
    runtime = _safe_mapping(metadata.get("runtime"))
    name = str(metadata.get("provider") or "")
    return {
        "provider": name,
        "provider_family": name,
        "model": metadata.get("model"),
        "effect_contract": "dspx-provider-effect-v1",
        "runtime": {
            "provider_kind": runtime.get("provider_kind"),
            "base_endpoint": runtime.get("base_endpoint"),
            "effective_timeout": runtime.get("effective_timeout"),
        },
    }


def _safe_lm_error_code(exc: Exception) -> str | None:
    from dspx.provider_contract import EffectDisposition

    code = getattr(exc, "code", None)
    allowed = {item.value for item in EffectDisposition}
    return code if isinstance(code, str) and code in allowed else None


def _strip_json_fence(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        if len(lines) >= 2:
            return "\n".join(lines[1:-1]).strip()
    return text


def _parse_generated_json(raw: object, *, field: str) -> Any:
    if not isinstance(raw, str):
        return raw
    text = _strip_json_fence(raw)
    if not text:
        raise ValueError(f"{field} is empty")
    return json.loads(text)


def _validate_pdf_transition_review_outputs(
    observed: Mapping[str, object],
) -> list[str]:
    errors: list[str] = []
    parsed: dict[str, Any] = {}
    for field in (
        "section_units_json",
        "distillation_frames_json",
        "evidence_cards_json",
        "merge_create_proposals_json",
        "review_packet_json",
        "artifact_contract_manifest_json",
    ):
        if field not in observed:
            errors.append(f"missing required PDF transition output: {field}")
            continue
        try:
            parsed[field] = _parse_generated_json(observed[field], field=field)
        except Exception as exc:
            errors.append(
                f"{field} is not valid JSON: {type(exc).__name__}: "
                f"{_sanitize_runtime_diagnostic(exc)}"
            )
    contract = parsed.get("artifact_contract_manifest_json")
    if (
        not isinstance(contract, Mapping)
        or contract.get("canonical_mutation_performed") is not False
    ):
        errors.append(
            "artifact_contract_manifest_json must state canonical_mutation_performed=false"
        )
    review = parsed.get("review_packet_json")
    if (
        isinstance(review, Mapping)
        and review.get("canonical_mutation_performed") is not False
    ):
        errors.append(
            "review_packet_json must state canonical_mutation_performed=false"
        )
    proposals = parsed.get("merge_create_proposals_json")
    if not isinstance(proposals, list):
        errors.append("merge_create_proposals_json must be a JSON array")
    else:
        for index, proposal in enumerate(proposals):
            if not isinstance(proposal, Mapping):
                errors.append(f"proposal {index} is not an object")
                continue
            proposal_payload = cast(Mapping[str, Any], proposal)
            if proposal_payload.get("canonical_mutation_allowed") is not False:
                errors.append(
                    f"proposal {index} must state canonical_mutation_allowed=false"
                )
            if proposal_payload.get("review_required") is not True:
                errors.append(f"proposal {index} must state review_required=true")
    return errors


def _write_observed_output_files(
    outdir: Path, observed: Mapping[str, object]
) -> list[str]:
    written: list[str] = []
    outdir_parts = outdir.parts
    descriptor_bound = (
        len(outdir_parts) == 5
        and outdir_parts[:4] == ("/", "proc", "self", "fd")
        and outdir_parts[4].isdigit()
    )
    for field, value in observed.items():
        output_name = str(field).strip()
        path_parts = Path(output_name).parts
        protected_parts = [
            part
            for part in path_parts
            if part in _RUNTIME_EPISODE_PROTECTED_ARTIFACT_NAMES
        ]
        if protected_parts:
            raise ValueError(
                "runtime observed output field would overwrite protected artifact: "
                + ", ".join(protected_parts)
            )
        if descriptor_bound:
            if len(path_parts) != 1 or path_parts[0] in {"", ".", ".."}:
                raise ValueError("descriptor-bound observed output must be flat")
            path = outdir / output_name
        else:
            path = confine_relative_path(outdir, output_name)
            path.parent.mkdir(parents=True, exist_ok=True)
        text = (
            value
            if isinstance(value, str)
            else json.dumps(value, ensure_ascii=False, indent=2)
        )
        _write_private_bytes_exclusive(
            path, (str(text).rstrip() + "\n").encode("utf-8")
        )
        written.append(
            output_name
            if descriptor_bound
            else path.relative_to(outdir.resolve()).as_posix()
        )
    return sorted(written)


def _runtime_id(*, manifest_hash: str, inputs_hash: str, contract_mode: str) -> str:
    return (
        "prog-run-"
        + _sha256_text(
            json.dumps(
                {
                    "manifest_hash": manifest_hash,
                    "inputs_hash": inputs_hash,
                    "contract_mode": contract_mode,
                },
                sort_keys=True,
            )
        )[:16]
    )


def _runtime_trace_summary(
    runtime_traces: Mapping[str, Any], *, content_hash: str
) -> dict[str, Any]:
    coverage = _safe_mapping(runtime_traces.get("coverage"))
    return {
        "schema_version": runtime_traces.get("schema_version"),
        "path": "program_runtime_traces.json",
        "content_hash": content_hash,
        "status": runtime_traces.get("status"),
        "source_count": runtime_traces.get("source_count"),
        "module_call_count": runtime_traces.get("module_call_count"),
        "final_output_trace_count": runtime_traces.get("final_output_trace_count"),
        "coverage": {
            "schema_version": coverage.get("schema_version"),
            "status": coverage.get("status"),
            "source_record_coverage_status": coverage.get(
                "source_record_coverage_status"
            ),
        },
        "non_authority": _safe_mapping(runtime_traces.get("non_authority")),
    }


def _oracle_evidence(
    *,
    manifest_identity: Mapping[str, str | None],
    runtime_episode_id: str,
    behavior_results: Mapping[str, Any],
    behavior_results_hash: str,
    runtime_traces: Mapping[str, Any],
    runtime_traces_hash: str,
    inputs_hash: str,
    contract_mode: str,
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    intent = _safe_mapping(manifest.get("intent"))
    raw_summary = behavior_results.get("summary")
    summary = _safe_mapping(raw_summary)
    raw_inputs = behavior_results.get("input_fields")
    raw_outputs = behavior_results.get("output_fields")
    input_fields = (
        [str(item) for item in raw_inputs] if isinstance(raw_inputs, list) else []
    )
    output_fields = (
        [str(item) for item in raw_outputs] if isinstance(raw_outputs, list) else []
    )
    status = str(summary.get("status") or "unknown")
    failure_modes: list[dict[str, Any]] = []
    if status not in {
        "executed",
        "executed_quality_passed",
        "executed_valid_review_only",
        "passed",
    }:
        failure_modes.append(
            {
                "index": 0,
                "status": status,
                "signals": [str(item) for item in behavior_results.get("notes") or []]
                if isinstance(behavior_results.get("notes"), list)
                else [],
                "mismatched_outputs": [],
                "missing_observed_outputs": [],
            }
        )
    identity = {key: value for key, value in manifest_identity.items() if value}
    identity["runtime_episode_id"] = runtime_episode_id
    runtime_trace_summary = _runtime_trace_summary(
        runtime_traces, content_hash=runtime_traces_hash
    )
    runtime_trace_coverage = _safe_mapping(runtime_trace_summary.get("coverage"))
    oracle_facets = {
        "task_type": str(intent.get("task_type") or "single_module"),
        "metric": f"runtime_episode:{contract_mode}",
        "input_fields": input_fields,
        "output_fields": output_fields,
        "behavior_status": status,
        "status_counts": _safe_mapping(summary.get("status_counts")),
        "has_examples": True,
        "example_count": 1,
        "has_dataset_splits": False,
        "dataset_split_count": 0,
        "evidence_source_count": 1,
        "behavior_source_kinds": ["runtime_inputs"],
        "total_evaluation_count": 1,
        "failure_mode_count": len(failure_modes),
        "has_failures": bool(failure_modes),
        "runtime_episode_id": runtime_episode_id,
        "contract_mode": contract_mode,
        "runtime_trace_status": runtime_trace_summary.get("status"),
        "runtime_trace_coverage_status": runtime_trace_coverage.get("status"),
        "runtime_trace_source_record_coverage_status": runtime_trace_coverage.get(
            "source_record_coverage_status"
        ),
        "runtime_trace_module_call_count": runtime_trace_summary.get(
            "module_call_count"
        ),
        "runtime_trace_final_output_trace_count": runtime_trace_summary.get(
            "final_output_trace_count"
        ),
    }
    objective = str(
        intent.get("objective")
        or _safe_mapping(behavior_results.get("intent")).get("objective")
        or ""
    )
    oracle_text = "\n".join(
        [
            "schema_version=program-oracle-evidence-v1",
            "evidence_kind=program_execution_episode",
            f"intent.name={intent.get('name') or behavior_results.get('intent_name') or ''}",
            f"intent.objective={objective}",
            f"intent.task_type={oracle_facets['task_type']}",
            f"intent.metric={oracle_facets['metric']}",
            "io.inputs=" + ",".join(input_fields),
            "io.outputs=" + ",".join(output_fields),
            f"identity.runtime_episode_id={runtime_episode_id}",
            f"identity.candidate_id={identity.get('candidate_id')}",
            f"identity.assembly_id={identity.get('assembly_id')}",
            f"behavior.status={status}",
            "behavior.source_kinds=runtime_inputs",
            "behavior.example_count=1",
            f"runtime_traces.status={oracle_facets.get('runtime_trace_status')}",
            f"runtime_traces.coverage_status={oracle_facets.get('runtime_trace_coverage_status')}",
            f"runtime_traces.source_record_coverage_status={oracle_facets.get('runtime_trace_source_record_coverage_status')}",
            f"runtime_traces.module_call_count={oracle_facets.get('runtime_trace_module_call_count')}",
            f"runtime_traces.final_output_trace_count={oracle_facets.get('runtime_trace_final_output_trace_count')}",
            "authority=oracle_readability_only_non_authoritative; oracle_ranking=false; "
            "oracle_pruning=false; oracle_promotion=false; governance_authority=false; external_mutation=false",
        ]
    )
    return {
        "schema_version": PROGRAM_ORACLE_EVIDENCE_SCHEMA,
        "evidence_kind": "program_execution_episode",
        "authority": "oracle_readability_only_non_authoritative",
        "non_authority": {
            "oracle_ranking": False,
            "oracle_pruning": False,
            "oracle_promotion": False,
            "governance_authority": False,
            "external_mutation": False,
        },
        "identity": identity,
        "intent": {
            "name": intent.get("name") or behavior_results.get("intent_name"),
            "objective": objective,
            "task_type": oracle_facets["task_type"],
            "metric": oracle_facets["metric"],
            "constraints": list(
                intent.get("constraints")
                or _safe_mapping(behavior_results.get("intent")).get("constraints")
                or []
            ),
        },
        "io": {"inputs": input_fields, "outputs": output_fields},
        "behavior": {
            "result_path": "behavior_results.json",
            "result_hash": behavior_results_hash,
            "summary": dict(summary),
            "statuses": _safe_mapping(summary.get("status_counts")),
            "example_count": 1,
            "evaluation_sources": [
                {
                    "kind": "runtime_inputs",
                    "source_kind": "runtime_inputs",
                    "input_artifact_path": "runtime_inputs.json",
                    "input_artifact_hash": inputs_hash,
                    "behavior_results_path": "behavior_results.json",
                    "behavior_results_hash": behavior_results_hash,
                }
            ],
            "evidence_summary": dict(summary),
            "source_statuses": [status],
            "failure_modes": failure_modes,
        },
        "runtime_traces": runtime_trace_summary,
        "oracle_facets": oracle_facets,
        "oracle_text": oracle_text,
        "source_artifacts": [
            {
                "kind": "runtime_inputs",
                "path": "runtime_inputs.json",
                "content_hash": inputs_hash,
                "source_kind": "runtime_inputs",
            },
            {
                "kind": "behavior_results",
                "path": "behavior_results.json",
                "content_hash": behavior_results_hash,
                "source_kind": "runtime_inputs",
            },
            {
                "kind": "runtime_traces",
                "path": "program_runtime_traces.json",
                "content_hash": runtime_traces_hash,
            },
        ],
    }


def _resolve_episode_artifact(root: Path, relative_path: str, *, label: str) -> Path:
    path = Path(relative_path)
    if path.is_absolute():
        raise ValueError(f"{label} path must be runtime-episode-relative")
    try:
        return confine_path(root, path, strict=True)
    except ValueError as exc:
        raise ValueError(f"{label} path escapes runtime episode root") from exc


def _assert_false_flags(
    payload: Mapping[str, Any], *, section: str, keys: tuple[str, ...]
) -> None:
    raw = _safe_mapping(payload.get(section))
    invalid = [key for key in keys if raw.get(key) is not False]
    if invalid:
        raise ValueError(
            f"runtime episode {section} widens flags: " + ", ".join(invalid)
        )


def _assert_identity_matches(
    actual: Mapping[str, Any], expected: Mapping[str, Any], *, label: str
) -> None:
    mismatches = [
        key
        for key in (
            "request_id",
            "candidate_id",
            "assembly_id",
            "episode_id",
            "receipt_bundle_id",
        )
        if expected.get(key) is not None and actual.get(key) != expected.get(key)
    ]
    if mismatches:
        raise ValueError(f"{label} identity mismatch: " + ", ".join(mismatches))


_LEGACY_STUB_RECEIPT_PROVIDER_DETAILS: dict[str, object] = {
    "provider": "stub",
    "provider_family": "stub",
    "model": "stub/echo",
    "effect_contract": "dspx-provider-effect-v1",
}


def _legacy_receipt_matches_stub_provider(receipt: Mapping[str, object]) -> bool:
    expected_identity = {
        "provider": "stub",
        "provider_details": _LEGACY_STUB_RECEIPT_PROVIDER_DETAILS,
    }
    replay = _safe_mapping(receipt.get("execution_replay"))
    replay_identity = _safe_mapping(replay.get("provider_identity"))
    return (
        receipt.get("provider") == "stub"
        and receipt.get("provider_details") == _LEGACY_STUB_RECEIPT_PROVIDER_DETAILS
        and set(replay_identity) == {"provider", "provider_details", "hash"}
        and replay_identity.get("provider") == expected_identity["provider"]
        and replay_identity.get("provider_details")
        == expected_identity["provider_details"]
        and replay_identity.get("hash")
        == canonical_replay_identity_hash(expected_identity)
    )


def _is_legacy_provider_evidence(value: object) -> bool:
    evidence = _safe_mapping(value)
    if evidence == {"status": "configured", "provider": "stub/echo"}:
        return True
    error = evidence.get("error")
    return (
        set(evidence) == {"status", "error"}
        and evidence.get("status") == "unavailable"
        and isinstance(error, Mapping)
        and set(error) == {"type", "message"}
        and all(isinstance(error.get(key), str) for key in ("type", "message"))
    )


def _validate_provider_evidence(value: object) -> dict[str, Any]:
    evidence = _safe_mapping(value)
    if evidence.get("status") == "unavailable":
        if not _is_legacy_provider_evidence(evidence):
            raise ValueError("unavailable provider evidence shape is invalid")
        return evidence
    if set(evidence) != {"status", "metadata", "effect_evidence"}:
        raise ValueError("configured provider evidence shape is invalid")
    if evidence.get("status") != "configured":
        raise ValueError("provider evidence status is invalid")

    metadata = _safe_mapping(evidence.get("metadata"))
    if set(metadata) != {
        "provider",
        "model",
        "model_type",
        "typed_contract",
        "capabilities",
        "runtime",
    }:
        raise ValueError("provider runtime metadata shape is invalid")
    kind = metadata.get("provider")
    if kind not in {"stub", "openai-compatible"}:
        raise ValueError("provider runtime identity is invalid")
    if (
        metadata.get("model_type") != "text"
        or metadata.get("typed_contract") != "typed_lm"
    ):
        raise ValueError("provider typed metadata is invalid")
    if metadata.get("capabilities") != {
        "supports_tools": False,
        "code_exec": False,
        "json_mode": False,
        "multi_turn": True,
        "structured_output_format": "none",
        "supports_vision": False,
        "supports_audio": False,
    }:
        raise ValueError("provider capabilities metadata is invalid")

    from dspx.openai_compatible_provider import _validated_model

    model = metadata.get("model")
    if not isinstance(model, str):
        raise ValueError("provider runtime model is invalid")
    try:
        canonical_model = _validated_model(model)
    except (TypeError, ValueError):
        raise ValueError("provider runtime model is invalid") from None
    if model != canonical_model:
        raise ValueError("provider runtime model is not canonical")
    runtime = _safe_mapping(metadata.get("runtime"))
    if set(runtime) != {"provider_kind", "base_endpoint", "effective_timeout"}:
        raise ValueError("provider runtime details shape is invalid")
    if runtime.get("provider_kind") != kind:
        raise ValueError("provider runtime kind is inconsistent")
    if kind == "stub":
        if (
            model != "stub/echo"
            or runtime.get("base_endpoint") is not None
            or runtime.get("effective_timeout") is not None
        ):
            raise ValueError("stub runtime metadata contains HTTP fields")
    else:
        from dspx.openai_compatible_provider import (
            _validated_endpoint,
            _validated_timeout,
        )

        base_endpoint = runtime.get("base_endpoint")
        if not isinstance(base_endpoint, str):
            raise ValueError("provider runtime endpoint is invalid")
        canonical_base, _ = _validated_endpoint(base_endpoint)
        if base_endpoint != canonical_base:
            raise ValueError("provider runtime endpoint is not canonical")
        timeout = runtime.get("effective_timeout")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise ValueError("provider runtime timeout is invalid")
        try:
            canonical_timeout = _validated_timeout(timeout)
        except (TypeError, ValueError):
            raise ValueError("provider runtime timeout is invalid") from None
        if timeout != canonical_timeout:
            raise ValueError("provider runtime timeout is not canonical")

    effect_evidence = _safe_mapping(evidence.get("effect_evidence"))
    if (
        set(effect_evidence)
        != {
            "schema_version",
            "attempt_total",
            "attempts_truncated",
            "terminal_effect",
            "attempts",
        }
        or effect_evidence.get("schema_version") != "dspx-provider-effect-evidence-v1"
    ):
        raise ValueError("provider effect evidence envelope is invalid")
    attempts = effect_evidence.get("attempts")
    total = effect_evidence.get("attempt_total")
    truncated = effect_evidence.get("attempts_truncated")
    terminal = effect_evidence.get("terminal_effect")
    if (
        not isinstance(attempts, list)
        or len(attempts) > 64
        or isinstance(total, bool)
        or not isinstance(total, int)
        or total < len(attempts)
        or not isinstance(truncated, bool)
        or truncated != (total > len(attempts))
        or (truncated and len(attempts) != 64)
    ):
        raise ValueError("provider attempt counts are inconsistent")
    allowed_dispositions = {
        "preflight_rejected",
        "completed_success",
        "completed_failure",
        "effect_indeterminate",
    }
    for index, attempt in enumerate(attempts):
        if not isinstance(attempt, Mapping) or set(attempt) != {
            "provider_kind",
            "requested_model",
            "observed_model",
            "dispatch_count",
            "effect_disposition",
        }:
            raise ValueError("provider attempt shape is invalid")
        disposition = attempt.get("effect_disposition")
        dispatch_count = attempt.get("dispatch_count")
        if (
            attempt.get("provider_kind") != kind
            or attempt.get("requested_model") != model
            or (
                attempt.get("observed_model") is not None
                and (
                    not isinstance(attempt.get("observed_model"), str)
                    or _validated_model(cast(str, attempt.get("observed_model")))
                    != attempt.get("observed_model")
                )
            )
            or disposition not in allowed_dispositions
            or dispatch_count not in {0, 1}
            or (disposition == "preflight_rejected" and dispatch_count != 0)
            or (disposition != "preflight_rejected" and dispatch_count != 1)
            or (
                disposition == "completed_success"
                and attempt.get("observed_model") != model
            )
            or (disposition == "effect_indeterminate" and index != len(attempts) - 1)
        ):
            raise ValueError("provider attempt fields are inconsistent")
    expected_terminal = attempts[-1].get("effect_disposition") if attempts else None
    if terminal != expected_terminal or (total == 0) != (terminal is None):
        raise ValueError("provider terminal effect is inconsistent")
    if terminal not in allowed_dispositions | {None}:
        raise ValueError("provider terminal effect is invalid")
    return evidence


def validate_program_runtime_episode_contract(
    runtime_episode: Mapping[str, Any],
    *,
    runtime_episode_path: Path,
    expected_manifest_path: Path,
    expected_manifest: Mapping[str, Any],
    expected_manifest_sha256: str,
    error_type: type[Exception] = ValueError,
) -> None:
    """Validate a program-run runtime episode at final-consumer time.

    The runtime episode bundle is caller-controlled local evidence.  Status and
    workflow summaries must therefore re-bind every referenced artifact to the
    current manifest and current bytes before mirroring it.
    """

    def fail(message: str) -> None:
        raise error_type(message)

    try:
        if runtime_episode.get("schema_version") != PROGRAM_RUNTIME_EPISODE_SCHEMA:
            fail(
                f"runtime episode schema_version must be {PROGRAM_RUNTIME_EPISODE_SCHEMA}"
            )
        if runtime_episode.get("status") not in RUNTIME_EPISODE_STATUSES:
            fail("runtime episode status is unsupported")
        execution_status = str(runtime_episode.get("execution_status") or "")
        if (
            not execution_status
            and runtime_episode.get("status") in RUNTIME_EXECUTION_STATUSES
        ):
            execution_status = str(runtime_episode.get("status"))
        if execution_status not in RUNTIME_EXECUTION_STATUSES:
            fail("runtime episode execution_status is unsupported")
        runtime_episode_id = str(
            runtime_episode.get("runtime_episode_id") or ""
        ).strip()
        if not runtime_episode_id:
            fail("runtime episode must include runtime_episode_id")

        episode_root = runtime_episode_path.expanduser().resolve().parent
        expected_manifest_resolved = expected_manifest_path.expanduser().resolve()
        candidate_manifest = (
            Path(str(runtime_episode.get("candidate_manifest_path") or ""))
            .expanduser()
            .resolve()
        )
        if candidate_manifest != expected_manifest_resolved:
            fail(
                "runtime episode candidate_manifest_path does not match current manifest"
            )
        if _sha256_file(expected_manifest_resolved) != expected_manifest_sha256:
            fail("runtime episode expected manifest hash is stale")

        artifact_hashes = _safe_mapping(runtime_episode.get("artifact_hashes"))
        if artifact_hashes.get("source_manifest_sha256") != expected_manifest_sha256:
            fail(
                "runtime episode source_manifest_sha256 does not match current manifest"
            )

        declared_manifest_path = (
            Path(str(runtime_episode.get("manifest_path") or "")).expanduser().resolve()
        )
        runtime_manifest_path = _resolve_episode_artifact(
            episode_root,
            "manifest.json",
            label="runtime episode manifest",
        )
        if declared_manifest_path != runtime_manifest_path:
            fail("runtime episode manifest_path must point at its manifest.json")
        runtime_manifest = _load_json_object(
            runtime_manifest_path, label="runtime episode manifest"
        )
        if runtime_manifest.get("schema_version") != PROGRAM_MANIFEST_SCHEMA:
            fail(
                "runtime episode manifest schema_version must be program-candidate-assembly-v1"
            )
        _assert_identity_matches(
            _manifest_identity(runtime_manifest),
            _manifest_identity(expected_manifest),
            label="runtime episode manifest",
        )
        source_ref = _safe_mapping(runtime_manifest.get("source_candidate_manifest"))
        source_ref_path = Path(str(source_ref.get("path") or "")).expanduser().resolve()
        if source_ref_path != expected_manifest_resolved:
            fail(
                "runtime episode manifest source_candidate_manifest.path does not match current manifest"
            )
        if source_ref.get("sha256") != expected_manifest_sha256:
            fail("runtime episode manifest source_candidate_manifest.sha256 is stale")

        runtime_manifest_episode = _safe_mapping(
            runtime_manifest.get("runtime_episode")
        )
        if (
            runtime_manifest_episode.get("schema_version")
            != PROGRAM_RUNTIME_EPISODE_SCHEMA
        ):
            fail("runtime episode manifest runtime_episode schema is invalid")
        if runtime_manifest_episode.get("runtime_episode_id") != runtime_episode_id:
            fail("runtime episode id mismatch between episode and manifest")
        if runtime_manifest_episode.get("contract_mode") != runtime_episode.get(
            "contract_mode"
        ):
            fail("runtime episode contract_mode mismatch between episode and manifest")

        if runtime_manifest_episode.get("inputs_path") != "runtime_inputs.json":
            fail("runtime episode manifest inputs_path must be runtime_inputs.json")
        if (
            runtime_manifest_episode.get("behavior_results_path")
            != "behavior_results.json"
        ):
            fail(
                "runtime episode manifest behavior_results_path must be behavior_results.json"
            )
        inputs_path = _resolve_episode_artifact(
            episode_root,
            "runtime_inputs.json",
            label="runtime inputs",
        )
        behavior_path = _resolve_episode_artifact(
            episode_root,
            "behavior_results.json",
            label="runtime behavior results",
        )
        traces_path = _resolve_episode_artifact(
            episode_root,
            "program_runtime_traces.json",
            label="program runtime traces",
        )
        oracle_path = _resolve_episode_artifact(
            episode_root,
            "oracle_evidence.json",
            label="runtime Oracle evidence",
        )

        current_hashes = {
            "runtime_inputs_sha256": _sha256_file(inputs_path),
            "behavior_results_sha256": _sha256_file(behavior_path),
            "program_runtime_traces_sha256": _sha256_file(traces_path),
            "oracle_evidence_sha256": _sha256_file(oracle_path),
        }
        for key, actual in current_hashes.items():
            if artifact_hashes.get(key) != actual:
                fail(f"runtime episode {key} does not match current file")
        if (
            runtime_manifest_episode.get("inputs_sha256")
            != current_hashes["runtime_inputs_sha256"]
        ):
            fail("runtime episode manifest inputs hash is stale")
        if (
            runtime_manifest_episode.get("behavior_results_sha256")
            != current_hashes["behavior_results_sha256"]
        ):
            fail("runtime episode manifest behavior results hash is stale")

        behavior = _load_json_object(behavior_path, label="runtime behavior results")
        if behavior.get("schema_version") != PROGRAM_BEHAVIOR_RESULTS_SCHEMA:
            fail(
                "runtime behavior results schema_version must be program-behavior-results-v1"
            )
        if behavior.get("runtime_episode_id") != runtime_episode_id:
            fail("runtime behavior results runtime_episode_id mismatch")
        if behavior.get("authority") != "behavior_evidence_only_non_authoritative":
            fail("runtime behavior results authority must remain evidence-only")
        behavior_intent = _safe_mapping(behavior.get("intent"))
        manifest_intent = _safe_mapping(expected_manifest.get("intent"))
        manifest_outputs = [
            str(item) for item in _safe_list(manifest_intent.get("outputs"))
        ]
        manifest_quality = normalize_quality_criteria(
            manifest_intent.get("quality_criteria", []), outputs=manifest_outputs
        )
        if behavior_intent.get("quality_criteria", []) != manifest_quality:
            fail("runtime behavior quality criteria drift from current manifest")
        behavior_examples = _safe_list(behavior.get("examples"))
        if len(behavior_examples) != 1 or not isinstance(behavior_examples[0], Mapping):
            fail("runtime behavior results must contain exactly one record")
        behavior_record = dict(behavior_examples[0])
        observed_outputs = _safe_mapping(behavior_record.get("observed_outputs"))
        expected_quality = evaluate_declared_quality(manifest_quality, observed_outputs)
        if behavior.get("quality_evaluation") != expected_quality:
            fail("runtime behavior quality evaluation is stale or inconsistent")
        if behavior_record.get("quality_evaluation") != expected_quality:
            fail("runtime behavior record quality evaluation is inconsistent")
        if expected_quality.get("status") != "not_declared":
            if behavior.get("execution_status") != execution_status:
                fail("runtime behavior execution_status is inconsistent")
            if behavior_record.get("execution_status") != execution_status:
                fail("runtime behavior record execution_status is inconsistent")
            expected_runtime_status = runtime_status_with_declared_quality(
                execution_status, expected_quality.get("status")
            )
            if runtime_episode.get("status") != expected_runtime_status:
                fail("runtime episode declared quality status is inconsistent")
            if behavior_record.get("status") != expected_runtime_status:
                fail("runtime behavior record status hides declared quality result")
            summary = _safe_mapping(behavior.get("summary"))
            expected_counts = {
                "total": 1,
                "passed": 1
                if expected_runtime_status == "executed_quality_passed"
                else 0,
                "failed": 1
                if expected_runtime_status.startswith("failed")
                or expected_runtime_status == "error"
                else 0,
                "error": 1 if expected_runtime_status == "error" else 0,
                "degraded": 1 if expected_runtime_status.startswith("degraded") else 0,
                "executed": 1
                if expected_runtime_status
                in {
                    "executed",
                    "executed_quality_passed",
                    "executed_valid_review_only",
                }
                else 0,
                "status_counts": {expected_runtime_status: 1},
                "status": expected_runtime_status,
            }
            if summary != expected_counts:
                fail("runtime behavior summary hides declared quality result")
        _assert_false_flags(
            behavior,
            section="non_authority",
            keys=(
                "optimization_authority",
                "promotion_authority",
                "oracle_ranking",
                "oracle_pruning",
                "oracle_promotion",
                "governance_authority",
                "external_mutation",
                "external_authority_mutated",
                "winner_selection",
            ),
        )

        traces = _load_json_object(traces_path, label="program runtime traces")
        if not validate_program_runtime_traces(traces):
            fail("program runtime traces contract validation failed")
        for source in _safe_list(traces.get("sources")):
            if not isinstance(source, Mapping):
                fail("program runtime traces sources must be objects")
            if (
                source.get("path") == "behavior_results.json"
                and source.get("content_hash")
                != current_hashes["behavior_results_sha256"]
            ):
                fail("program runtime traces behavior_results source hash is stale")

        oracle = _load_json_object(oracle_path, label="runtime Oracle evidence")
        if oracle.get("schema_version") != PROGRAM_ORACLE_EVIDENCE_SCHEMA:
            fail(
                "runtime Oracle evidence schema_version must be program-oracle-evidence-v1"
            )
        if oracle.get("evidence_kind") != "program_execution_episode":
            fail("runtime Oracle evidence kind must be program_execution_episode")
        if oracle.get("authority") != "oracle_readability_only_non_authoritative":
            fail("runtime Oracle evidence authority must remain readability-only")
        oracle_identity = _safe_mapping(oracle.get("identity"))
        _assert_identity_matches(
            oracle_identity,
            _manifest_identity(expected_manifest),
            label="runtime Oracle evidence",
        )
        if oracle_identity.get("runtime_episode_id") != runtime_episode_id:
            fail("runtime Oracle evidence runtime_episode_id mismatch")
        _assert_false_flags(
            oracle,
            section="non_authority",
            keys=(
                "oracle_ranking",
                "oracle_pruning",
                "oracle_promotion",
                "governance_authority",
                "external_mutation",
            ),
        )
        source_artifacts = _safe_list(oracle.get("source_artifacts"))
        expected_source_hashes = {
            "runtime_inputs.json": current_hashes["runtime_inputs_sha256"],
            "behavior_results.json": current_hashes["behavior_results_sha256"],
            "program_runtime_traces.json": current_hashes[
                "program_runtime_traces_sha256"
            ],
        }
        seen_source_paths: set[str] = set()
        for ref in source_artifacts:
            if not isinstance(ref, Mapping):
                fail("runtime Oracle evidence source_artifacts must be objects")
            path_text = str(ref.get("path") or "")
            if path_text not in expected_source_hashes:
                fail("runtime Oracle evidence has unexpected source artifact path")
            seen_source_paths.add(path_text)
            if ref.get("content_hash") != expected_source_hashes[path_text]:
                fail("runtime Oracle evidence source artifact hash is stale")
        if seen_source_paths != set(expected_source_hashes):
            fail("runtime Oracle evidence source_artifacts are incomplete")
        behavior_section = _safe_mapping(oracle.get("behavior"))
        if (
            behavior_section.get("result_path") != "behavior_results.json"
            or behavior_section.get("result_hash")
            != current_hashes["behavior_results_sha256"]
        ):
            fail("runtime Oracle evidence behavior result ref is stale")
        behavior_summary = _safe_mapping(behavior.get("summary"))
        oracle_facets = _safe_mapping(oracle.get("oracle_facets"))
        if behavior_section.get("summary") != behavior_summary:
            fail("runtime Oracle evidence behavior summary drifts from current results")
        if behavior_section.get("statuses") != behavior_summary.get("status_counts"):
            fail("runtime Oracle evidence status counts drift from current results")
        if oracle_facets.get("behavior_status") != behavior_summary.get("status"):
            fail("runtime Oracle evidence behavior status drifts from current results")
        if oracle_facets.get("status_counts") != behavior_summary.get("status_counts"):
            fail(
                "runtime Oracle evidence facet status counts drift from current results"
            )

        _assert_false_flags(
            runtime_episode,
            section="non_authority",
            keys=(
                "promotion_authority",
                "activation_authority",
                "governance_mutated",
                "external_authority_mutated",
                "shared_oracle_mutated",
            ),
        )

        receipt_path = _resolve_episode_artifact(
            episode_root,
            f"{runtime_episode_path.name}.meta.json",
            label="runtime receipt",
        )
        receipt_check = check_run_receipt(receipt_path)
        if receipt_check.get("status") != "ok":
            fail("runtime receipt must pass replay validation")
        receipt = _load_json_object(receipt_path, label="runtime receipt")
        behavior_provider_raw = behavior.get("provider")
        runtime_provider_raw = runtime_episode.get("provider")
        if runtime_provider_raw is None:
            if not _is_legacy_provider_evidence(behavior_provider_raw):
                fail("runtime provider evidence is missing for non-legacy behavior")
            if not _legacy_receipt_matches_stub_provider(receipt):
                fail(
                    "legacy runtime receipt provider identity drifts from behavior results"
                )
        else:
            behavior_provider = _validate_provider_evidence(behavior_provider_raw)
            runtime_provider = _validate_provider_evidence(runtime_provider_raw)
            if runtime_provider != behavior_provider:
                fail("runtime provider evidence drifts from behavior results")
            receipt_provider = _safe_mapping(receipt.get("run_summary")).get("provider")
            if _validate_provider_evidence(receipt_provider) != behavior_provider:
                fail("runtime receipt provider evidence drifts from behavior results")
            expected_details = _receipt_provider_details(behavior_provider)
            if receipt.get("provider_details") != expected_details or receipt.get(
                "provider"
            ) != expected_details.get("provider"):
                fail("runtime receipt provider details drift from provider evidence")
    except error_type:
        raise
    except Exception as exc:
        fail(str(exc))


def load_validated_program_runtime_episode_bundle(
    *,
    runtime_episode_path: Path,
    expected_manifest_path: Path,
    expected_manifest: Mapping[str, Any],
    expected_manifest_sha256: str,
    label: str = "runtime episode",
    error_type: type[Exception] = ValueError,
) -> ProgramRuntimeEpisodeBundle:
    episode_path = runtime_episode_path.expanduser().resolve()
    try:
        behavior_path = _resolve_episode_artifact(
            episode_path.parent,
            "behavior_results.json",
            label=f"{label} behavior results",
        )
        receipt_path = _resolve_episode_artifact(
            episode_path.parent,
            f"{episode_path.name}.meta.json",
            label=f"{label} receipt",
        )
        episode_raw = _stable_source_bytes(episode_path)
        behavior_raw = _stable_source_bytes(behavior_path)
        receipt_raw = _stable_source_bytes(receipt_path)
        runtime_episode = json.loads(episode_raw)
        behavior_results = json.loads(behavior_raw)
        if not isinstance(runtime_episode, dict) or not isinstance(
            behavior_results, dict
        ):
            raise ValueError(f"{label} evidence must contain JSON objects")
        validate_program_runtime_episode_contract(
            runtime_episode,
            runtime_episode_path=episode_path,
            expected_manifest_path=expected_manifest_path,
            expected_manifest=expected_manifest,
            expected_manifest_sha256=expected_manifest_sha256,
            error_type=error_type,
        )
        if (
            _stable_source_bytes(episode_path) != episode_raw
            or _stable_source_bytes(behavior_path) != behavior_raw
            or _stable_source_bytes(receipt_path) != receipt_raw
        ):
            raise ValueError(f"{label} evidence changed during validation")
    except error_type:
        raise
    except Exception as exc:
        raise error_type(str(exc)) from exc
    return ProgramRuntimeEpisodeBundle(
        runtime_episode=runtime_episode,
        behavior_results=behavior_results,
        runtime_episode_path=episode_path,
        runtime_episode_sha256=hashlib.sha256(episode_raw).hexdigest(),
        runtime_receipt_sha256=hashlib.sha256(receipt_raw).hexdigest(),
        behavior_results_path=behavior_path,
        behavior_results_sha256=hashlib.sha256(behavior_raw).hexdigest(),
    )


def run_program_runtime_episode(
    *,
    manifest_path: Path,
    inputs_path: Path,
    outdir: Path,
    contract_mode: str = "none",
    skip_oracle_index: bool = False,
    publication_preflight_out: Path | None = None,
    publication_target: str | None = None,
    publication_label: str | None = None,
    publisher_id: str | None = None,
    publisher_role: str | None = None,
    publisher_assertion: str | None = None,
    redaction_status: str | None = None,
    retention_class: str | None = None,
    capture_replay_fixture: bool = False,
    run_oracle_semantic: bool = False,
    soomfon_custody: object | None = None,
) -> dict[str, Any]:
    if contract_mode not in CONTRACT_MODES:
        raise ValueError(
            "contract_mode must be one of: " + ", ".join(sorted(CONTRACT_MODES))
        )
    if publication_preflight_out is not None and not all(
        [
            publication_target,
            publication_label,
            publisher_id,
            publisher_role,
            publisher_assertion,
            redaction_status,
            retention_class,
        ]
    ):
        raise ValueError(
            "publication preflight requires target, label, publisher fields, redaction_status, and retention_class"
        )
    source_manifest_path = manifest_path.expanduser().resolve()
    manifest_raw = _stable_source_bytes(source_manifest_path)
    manifest_hash = hashlib.sha256(manifest_raw).hexdigest()
    from dspx.services.soomfon_evaluation_custody import (
        SoomfonRuntimeCustody,
        validate_runtime_custody,
    )

    if soomfon_custody is not None and not isinstance(
        soomfon_custody, SoomfonRuntimeCustody
    ):
        raise ValueError("Soomfon runtime custody object is invalid")
    snapshot = validate_runtime_custody(
        manifest_path=source_manifest_path,
        manifest_sha256=manifest_hash,
        inputs_path=inputs_path.expanduser().resolve(),
        outdir=outdir.expanduser().resolve(),
        custody=soomfon_custody,
    )
    candidate_root = source_manifest_path.parent
    candidate_receipt_path = source_manifest_path.with_name(
        f"{source_manifest_path.name}.meta.json"
    )
    runtime_snapshot: SoomfonRuntimeSnapshot | None = None
    if snapshot is None:
        manifest_payload = json.loads(manifest_raw)
        if not isinstance(manifest_payload, Mapping):
            raise ValueError("program manifest must contain a JSON object")
        manifest = _validated_manifest(manifest_payload)
        verify_candidate_integrity(source_manifest_path, manifest)
        candidate_receipt_hash = _sha256_file(candidate_receipt_path)
        runtime_inputs = _load_inputs(inputs_path)
    elif isinstance(snapshot, SoomfonRuntimeSnapshot):
        runtime_snapshot = snapshot
        manifest = snapshot.manifest_payload
        candidate_receipt_hash = snapshot.receipt_sha256
        runtime_inputs = snapshot.runtime_inputs
    else:
        raise ValueError("Soomfon runtime snapshot is invalid")
    manifest_identity = _manifest_identity(manifest)
    materialized_runtime_inputs = _materialize_runtime_inputs(
        runtime_inputs, inputs_path=inputs_path
    )
    source_inputs_text = _json_text({"inputs": runtime_inputs})
    inputs_hash = _sha256_text(source_inputs_text)
    runtime_episode_id = _runtime_id(
        manifest_hash=manifest_hash,
        inputs_hash=inputs_hash,
        contract_mode=contract_mode,
    )

    replay_fixture_payload: dict[str, Any] | None = None
    if capture_replay_fixture:
        stub_response = _safe_stub_response_for_replay()
        serialized_inputs = json.dumps(
            runtime_inputs, ensure_ascii=False, sort_keys=True
        )
        if stub_response is None:
            raise ValueError(
                "replay fixture capture requires a bounded redaction-safe stub response"
            )
        if (
            sanitize_diagnostic_text(
                serialized_inputs, limit=len(serialized_inputs) + 1
            )
            != serialized_inputs
        ):
            raise ValueError(
                "replay fixture capture rejects secret-shaped runtime inputs"
            )
        replay_fixture_payload = {
            "schema_version": PROGRAM_RUNTIME_REPLAY_FIXTURE_SCHEMA,
            "runtime_inputs": _jsonable(runtime_inputs),
            "stub_response": stub_response,
            "redaction_status": "checked",
            "retention_class": "explicit_local_replay_fixture",
            "authority": "local_replay_input_only",
        }

    resolved_root = outdir.expanduser().resolve()
    if (
        resolved_root == candidate_root
        or resolved_root in candidate_root.parents
        or candidate_root in resolved_root.parents
    ):
        raise ValueError(
            "runtime episode output directory must be disjoint from the candidate root"
        )
    if runtime_snapshot is None:
        root = resolved_root
        root.mkdir(parents=True, exist_ok=True)
    else:
        root = outdir.expanduser().absolute()
        if not str(root).startswith("/proc/self/fd/"):
            raise ValueError("protected runtime output is not descriptor-bound")
    _write_private_json_exclusive(
        root / "runtime_inputs.json", {"inputs": runtime_inputs}
    )
    replay_fixture_path: Path | None = None
    replay_fixture_hash: str | None = None
    if replay_fixture_payload is not None:
        replay_fixture_path = root / "runtime_replay_fixture.json"
        _write_private_json_exclusive(replay_fixture_path, replay_fixture_payload)
        replay_fixture_hash = _sha256_file(replay_fixture_path)

    manifest_intent = _safe_mapping(manifest.get("intent"))
    provider, provider_adapter, previous_lm = _configure_provider()
    observed: dict[str, object] = {}
    notes: list[str] = []
    error: dict[str, str] | None = None
    runtime_trace: dict[str, object] | None = None
    status = "error"
    input_fields = [str(item) for item in _safe_list(manifest_intent.get("inputs"))]
    output_fields = [str(item) for item in _safe_list(manifest_intent.get("outputs"))]
    intent_summary: dict[str, object] = dict(manifest_intent)
    try:
        if provider.get("status") != "configured":
            provider_error = _safe_mapping(provider.get("error"))
            message = _first_text(
                provider_error.get("message"),
                "provider configuration unavailable",
            )
            raise RuntimeError(f"provider configuration unavailable: {message}")
        program_context = (
            generated_program_module_from_snapshot(runtime_snapshot)
            if runtime_snapshot is not None
            else _generated_program_module(candidate_root)
        )
        with program_context as program_module:
            spec = program_module.io_spec()
            spec_inputs = [str(item) for item in spec.get("inputs") or []]
            spec_outputs = [str(item) for item in spec.get("outputs") or []]
            if runtime_snapshot is not None and (
                spec_inputs != input_fields or spec_outputs != output_fields
            ):
                raise ValueError("protected runtime IO spec drifts from manifest")
            input_fields, output_fields = spec_inputs, spec_outputs
            if runtime_snapshot is not None and any(
                len(Path(name).parts) != 1 for name in output_fields
            ):
                raise ValueError("protected runtime output field path is invalid")
            intent_summary = dict(program_module.intent_summary())
            missing_inputs = [
                name for name in input_fields if name not in runtime_inputs
            ]
            if missing_inputs:
                raise ValueError(
                    "runtime inputs missing declared fields: "
                    + ", ".join(missing_inputs)
                )
            program = program_module.build_program()
            prediction = program(
                **{name: materialized_runtime_inputs[name] for name in input_fields}
            )
            captured_trace = getattr(program, "_last_runtime_trace", None)
            if isinstance(captured_trace, Mapping):
                runtime_trace = {
                    str(key): _jsonable(value) for key, value in captured_trace.items()
                }
            mapped = _prediction_mapping(prediction)
            for name in output_fields:
                if name in mapped:
                    observed[name] = _jsonable(mapped[name])
                elif hasattr(prediction, name):
                    observed[name] = _jsonable(getattr(prediction, name))
            missing_outputs = [
                name
                for name in output_fields
                if name not in observed or observed[name] in (None, "")
            ]
            if missing_outputs:
                status = "degraded_missing_outputs"
                notes.append("missing outputs: " + ", ".join(missing_outputs))
            elif contract_mode == "pdf_transition_review":
                gate_errors = _validate_pdf_transition_review_outputs(observed)
                if gate_errors:
                    status = "failed_boundary"
                    notes.extend(gate_errors)
                else:
                    status = "executed_valid_review_only"
            else:
                status = "executed"
    except Exception as exc:
        sanitized_error = _sanitize_runtime_diagnostic(exc)
        error = {"type": type(exc).__name__, "message": sanitized_error}
        error_code = _safe_lm_error_code(exc)
        if error_code is not None:
            error["code"] = error_code
        notes.append(sanitized_error)

    if provider.get("status") == "configured":
        try:
            provider["effect_evidence"] = _provider_effect_evidence(provider_adapter)
        finally:
            _close_runtime_provider(provider_adapter, previous_lm)
    execution_status = status
    quality_evaluation = evaluate_declared_quality(
        intent_summary.get("quality_criteria"), observed
    )
    status = runtime_status_with_declared_quality(
        execution_status, quality_evaluation["status"]
    )
    notes = [_sanitize_runtime_diagnostic(note) for note in notes]
    output_files = _write_observed_output_files(root, observed)
    record: dict[str, object] = {
        "index": 0,
        "source_kind": "runtime_inputs",
        "status": status,
        "execution_status": execution_status,
        "inputs": _jsonable(runtime_inputs),
        "observed_outputs": _jsonable(observed),
        "quality_evaluation": quality_evaluation,
        "notes": list(notes),
    }
    if error is not None:
        record["error"] = error
    if runtime_trace is not None:
        record["runtime_trace"] = runtime_trace
    status_counts = {status: 1}
    behavior_results: dict[str, Any] = {
        "schema_version": PROGRAM_BEHAVIOR_RESULTS_SCHEMA,
        "intent": intent_summary,
        "intent_name": intent_summary.get("name"),
        "input_fields": input_fields,
        "output_fields": output_fields,
        "provider": provider,
        "examples": [record],
        "summary": {
            "total": 1,
            "passed": 1 if status == "executed_quality_passed" else 0,
            "failed": 1 if status.startswith("failed") or status == "error" else 0,
            "error": 1 if status == "error" else 0,
            "degraded": 1 if status.startswith("degraded") else 0,
            "executed": 1
            if status
            in {
                "executed",
                "executed_quality_passed",
                "executed_valid_review_only",
            }
            else 0,
            "status_counts": status_counts,
            "status": status,
        },
        "runtime_episode_id": runtime_episode_id,
        "quality_evaluation": quality_evaluation,
        "execution_status": execution_status,
        "authority": "behavior_evidence_only_non_authoritative",
        "non_authority": {
            "optimization_authority": False,
            "promotion_authority": False,
            "oracle_ranking": False,
            "oracle_pruning": False,
            "oracle_promotion": False,
            "governance_authority": False,
            "external_mutation": False,
            "external_authority_mutated": False,
            "winner_selection": False,
        },
    }
    behavior_path = root / "behavior_results.json"
    _write_private_json_exclusive(behavior_path, behavior_results)
    behavior_hash = _sha256_file(behavior_path)

    module_surfaces_path = candidate_root / "module_surfaces.json"
    module_surfaces = (
        runtime_snapshot.module_surfaces
        if runtime_snapshot is not None
        else (
            _load_json_object(module_surfaces_path, label="program module surfaces")
            if module_surfaces_path.exists()
            else {"module_surfaces": []}
        )
    )
    runtime_trace_intent = SimpleNamespace(
        name=str(intent_summary.get("name") or ""),
        objective=str(intent_summary.get("objective") or ""),
        outputs=output_fields,
    )
    runtime_traces = build_program_runtime_traces(
        runtime_trace_intent,
        module_surfaces=module_surfaces,
        behavior_results=behavior_results,
        behavior_results_hash=behavior_hash,
    )
    runtime_traces_path = root / "program_runtime_traces.json"
    _write_private_json_exclusive(runtime_traces_path, runtime_traces)
    runtime_traces_hash = _sha256_file(runtime_traces_path)

    runtime_manifest = dict(manifest)
    runtime_manifest["source_candidate_manifest"] = {
        "path": str(source_manifest_path),
        "sha256": manifest_hash,
    }
    runtime_manifest["runtime_episode"] = {
        "schema_version": PROGRAM_RUNTIME_EPISODE_SCHEMA,
        "runtime_episode_id": runtime_episode_id,
        "inputs_path": "runtime_inputs.json",
        "inputs_sha256": inputs_hash,
        "behavior_results_path": "behavior_results.json",
        "behavior_results_sha256": behavior_hash,
        "contract_mode": contract_mode,
    }
    runtime_manifest["oracle_readability"] = {
        "schema_version": PROGRAM_ORACLE_EVIDENCE_SCHEMA,
        "path": "oracle_evidence.json",
    }
    runtime_manifest_path = root / "manifest.json"
    _write_private_json_exclusive(runtime_manifest_path, runtime_manifest)

    oracle_evidence = _oracle_evidence(
        manifest_identity=manifest_identity,
        runtime_episode_id=runtime_episode_id,
        behavior_results=behavior_results,
        behavior_results_hash=behavior_hash,
        runtime_traces=runtime_traces,
        runtime_traces_hash=runtime_traces_hash,
        inputs_hash=inputs_hash,
        contract_mode=contract_mode,
        manifest=manifest,
    )
    oracle_path = root / "oracle_evidence.json"
    _write_private_json_exclusive(oracle_path, oracle_evidence)

    runtime_episode = {
        "schema_version": PROGRAM_RUNTIME_EPISODE_SCHEMA,
        "runtime_episode_id": runtime_episode_id,
        "status": status,
        "execution_status": execution_status,
        "contract_mode": contract_mode,
        "provider": provider,
        "candidate_manifest_path": str(source_manifest_path),
        "manifest_path": str(runtime_manifest_path.resolve()),
        "input_path": str(inputs_path.expanduser().resolve()),
        "output_files": output_files,
        "artifact_hashes": {
            "source_manifest_sha256": manifest_hash,
            "runtime_inputs_sha256": inputs_hash,
            "behavior_results_sha256": behavior_hash,
            "oracle_evidence_sha256": _sha256_file(oracle_path),
            "program_runtime_traces_sha256": runtime_traces_hash,
        },
        "non_authority": {
            "promotion_authority": False,
            "activation_authority": False,
            "governance_mutated": False,
            "external_authority_mutated": False,
            "shared_oracle_mutated": False,
        },
    }
    runtime_episode_path = root / "runtime_episode.json"
    _write_private_json_exclusive(runtime_episode_path, runtime_episode)
    runtime_episode_hash = _sha256_file(runtime_episode_path)
    replay_inputs: dict[str, Any] = {
        "candidate_manifest_path": str(source_manifest_path),
        "candidate_manifest_sha256": manifest_hash,
        "candidate_receipt_path": str(candidate_receipt_path),
        "candidate_receipt_sha256": candidate_receipt_hash,
        "runtime_inputs_sha256": inputs_hash,
        "replay_fixture_path": str(replay_fixture_path)
        if replay_fixture_path is not None
        else None,
        "replay_fixture_sha256": replay_fixture_hash,
        "contract_mode": contract_mode,
        "skip_oracle_index": skip_oracle_index,
        "publication_preflight_requested": publication_preflight_out is not None,
        "expected_episode": {
            "runtime_episode_id": runtime_episode_id,
            "contract_mode": contract_mode,
            "execution_status": execution_status,
            "status": status,
            "quality_status": quality_evaluation["status"],
            "quality_evaluation_sha256": _canonical_hash(quality_evaluation),
            "observed_outputs_sha256": _canonical_hash(observed),
            "behavior_results_sha256": behavior_hash,
            "oracle_evidence_sha256": _sha256_file(oracle_path),
            "program_runtime_traces_sha256": runtime_traces_hash,
            "runtime_episode_sha256": runtime_episode_hash,
        },
    }
    cache_payload = {"kind": "program-runtime", "replay_inputs": replay_inputs}
    cache_key = make_key(cache_payload)
    receipt = build_run_receipt(
        output_path=runtime_episode_path,
        output_hash=runtime_episode_hash,
        run_kind="program-runtime",
        template_version=PROGRAM_RUNTIME_RECEIPT_TEMPLATE,
        cache_key=cache_key,
        cache_file=str(root / ".cache" / "program-runtime" / f"{cache_key}.json"),
        cache_enabled=False,
        provider_details_override=_receipt_provider_details(provider),
        replay_inputs=replay_inputs,
        run_summary={
            "runtime_episode_id": runtime_episode_id,
            "runtime_status": status,
            "provider": provider,
            "behavior_results_sha256": behavior_hash,
            "program_runtime_traces_sha256": runtime_traces_hash,
            "oracle_evidence_sha256": _sha256_file(oracle_path),
            "replay_fixture_captured": replay_fixture_path is not None,
            "evidence_only": True,
        },
        outcome="success"
        if status
        in {
            "executed",
            "executed_quality_passed",
            "executed_valid_review_only",
        }
        else "failure",
    )
    if runtime_snapshot is None:
        runtime_receipt_path = write_run_receipt(runtime_episode_path, receipt)
    else:
        runtime_receipt_path = runtime_episode_path.with_name(
            f"{runtime_episode_path.name}.meta.json"
        )
        _write_private_json_exclusive(runtime_receipt_path, receipt)

    oracle_semantic_payload: dict[str, Any] | None = None
    oracle_semantic_path: Path | None = None
    if run_oracle_semantic:
        from dspx.services.program_runtime_oracle_semantic import (
            DEFAULT_PROGRAM_RUNTIME_ORACLE_SEMANTIC_NAME,
            run_program_runtime_oracle_semantics,
        )

        oracle_semantic_path = root / DEFAULT_PROGRAM_RUNTIME_ORACLE_SEMANTIC_NAME
        try:
            oracle_semantic_payload = run_program_runtime_oracle_semantics(
                runtime_episode_path=runtime_episode_path,
                out_path=oracle_semantic_path,
            )
        except Exception as exc:
            effect_indeterminate = oracle_semantic_path.exists()
            oracle_semantic_payload = {
                "status": "degraded",
                "semantic_result": {
                    "execution_status": "effect_indeterminate"
                    if effect_indeterminate
                    else "failed_before_attempt",
                    "executed_provider": None,
                    "executed_model": None,
                    "live_call_succeeded": False,
                    "error": sanitize_diagnostic_text(str(exc)),
                },
                "effect": {
                    "semantic_backend_invoked": None if effect_indeterminate else False,
                    "effect_disposition": "indeterminate"
                    if effect_indeterminate
                    else "not_started",
                    "live_call_succeeded": None if effect_indeterminate else False,
                    "sidecar_written": effect_indeterminate,
                    "runtime_evidence_mutated": False,
                    "shared_oracle_mutated": False,
                    "external_authority_mutated": False,
                },
            }

    oracle_index_result: dict[str, Any] | None = None
    oracle_report: dict[str, Any] | None = None
    index_path = root / "oracle" / "coordinates.db"
    if not skip_oracle_index:
        oracle_index_result = index_program_oracle_evidence_path(
            root, index_path=index_path, limit=1000
        )
        oracle_report = build_program_oracle_evidence_report(
            index_path=index_path, limit=1000
        )
        (root / "program_oracle_report.json").write_text(
            _json_text(oracle_report), encoding="utf-8"
        )

    publication_preflight: dict[str, Any] | None = None
    if publication_preflight_out is not None:
        publication_preflight = build_program_oracle_publication_preflight(
            manifest_path=runtime_manifest_path,
            target=str(publication_target),
            publication_label=str(publication_label),
            publisher_id=str(publisher_id),
            publisher_role=str(publisher_role),
            publisher_assertion=str(publisher_assertion),
            redaction_status=str(redaction_status),
            retention_class=str(retention_class),
        )
        write_program_oracle_publication_preflight(
            publication_preflight, publication_preflight_out
        )

    return {
        "schema_version": "program-runtime-episode-workflow-v1",
        "status": "ok"
        if status
        in {
            "executed",
            "executed_quality_passed",
            "executed_valid_review_only",
        }
        and (skip_oracle_index or (oracle_index_result or {}).get("errors") == 0)
        and (
            not run_oracle_semantic
            or (oracle_semantic_payload or {}).get("status") == "ok"
        )
        else "degraded",
        "runtime_episode_id": runtime_episode_id,
        "candidate_manifest_path": str(source_manifest_path),
        "runtime_root": str(root),
        "runtime_episode_path": str(runtime_episode_path),
        "runtime_receipt_path": str(runtime_receipt_path),
        "manifest_path": str(runtime_manifest_path),
        "behavior_results_path": str(behavior_path),
        "oracle_evidence_path": str(oracle_path),
        "oracle_semantic_path": str(oracle_semantic_path)
        if oracle_semantic_path is not None
        else None,
        "oracle_index_path": str(index_path) if not skip_oracle_index else None,
        "oracle_report_path": str(root / "program_oracle_report.json")
        if oracle_report is not None
        else None,
        "publication_preflight_path": str(publication_preflight_out)
        if publication_preflight_out is not None
        else None,
        "steps": {
            "runtime_execution": {
                "status": status,
                "provider": provider,
                "notes": notes,
                "output_files": output_files,
            },
            "runtime_receipt": {
                "status": "written",
                "path": str(runtime_receipt_path),
                "execution_replay_supported": bool(
                    _safe_mapping(receipt.get("execution_replay")).get("supported")
                ),
                "evidence_only": True,
            },
            "oracle_semantic": {
                "status": "skipped"
                if oracle_semantic_payload is None
                else oracle_semantic_payload.get("status"),
                "path": str(oracle_semantic_path)
                if oracle_semantic_path is not None
                else None,
                "execution_status": (
                    (oracle_semantic_payload or {}).get("semantic_result") or {}
                ).get("execution_status"),
                "preferred_model": (
                    (oracle_semantic_payload or {}).get("semantic_result") or {}
                ).get("preferred_model"),
                "executed_model": (
                    (oracle_semantic_payload or {}).get("semantic_result") or {}
                ).get("executed_model"),
                "advisory_only": oracle_semantic_payload is not None,
            },
            "oracle_index": {
                "status": "skipped"
                if skip_oracle_index
                else (
                    "ok"
                    if (oracle_index_result or {}).get("errors") == 0
                    else "degraded"
                ),
                "result": oracle_index_result,
            },
            "oracle_report": {
                "status": "skipped"
                if oracle_report is None
                else oracle_report.get("status"),
                "total_records": None
                if oracle_report is None
                else oracle_report.get("total_records"),
            },
            "publication_preflight": {
                "status": "skipped"
                if publication_preflight is None
                else publication_preflight.get("status")
            },
        },
        "effect": {
            "candidate_manifest_mutated": False,
            "runtime_episode_written": True,
            "runtime_receipt_written": True,
            "runtime_replay_fixture_written": replay_fixture_path is not None,
            "behavior_results_written": True,
            "oracle_evidence_written": True,
            "oracle_semantic_written": oracle_semantic_payload is not None,
            "oracle_semantic_live_call_succeeded": (
                (oracle_semantic_payload or {}).get("effect") or {}
            ).get("live_call_succeeded", False),
            "oracle_index_mutated": not skip_oracle_index,
            "oracle_index_scope": "runtime-episode local explicit path"
            if not skip_oracle_index
            else "none",
            "oracle_report_written": oracle_report is not None,
            "oracle_publication_preflight_written": publication_preflight is not None,
            "shared_oracle_mutated": False,
            "ak_called": False,
            "external_authority_mutated": False,
            "governance_mutated": False,
            "canonical_notes_mutated": False,
            "promotion_applied": False,
        },
        "non_authority": runtime_episode["non_authority"],
    }
