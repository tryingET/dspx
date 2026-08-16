from __future__ import annotations

import ast
import ctypes
import importlib
import importlib.abc
import importlib.machinery
import importlib.util
import os
import signal
import subprocess
import stat
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Iterator, Mapping

from dspx.services.run_replay_service import check_run_receipt
from dspx.services.soomfon_evaluation_contract import (
    PROTECTED_MODULE_ATTRIBUTES,
    protected_declared_call_names,
)
from dspx.services.soomfon_evaluation_schema import PROTECTED_DENIED_ATTRIBUTES
from dspx.security import confine_path


def create_child_runtime_directory(
    *, raw_root_fd: int, inputs_path: Path, outdir: Path
) -> tuple[Path, int]:
    info = os.fstat(raw_root_fd)
    raw_path = Path(f"/proc/self/fd/{raw_root_fd}").resolve(strict=True)
    entries = set(os.listdir(f"/proc/self/fd/{raw_root_fd}"))
    failures = [
        label
        for label, valid in (
            ("type", stat.S_ISDIR(info.st_mode)),
            ("owner", info.st_uid == os.geteuid()),
            ("mode", stat.S_IMODE(info.st_mode) == 0o700),
            ("inputs", inputs_path.parent.resolve() == raw_path),
            ("outdir", outdir.parent.resolve() == raw_path),
            ("entries", entries == {"inputs.json", "empty-cwd"}),
        )
        if not valid
    ]
    if failures:
        raise ValueError(
            "raw child custody identity drifts: "
            + ",".join(failures)
            + f" entries={sorted(entries)!r}"
        )
    os.mkdir("runtime", 0o700, dir_fd=raw_root_fd)
    runtime_fd = os.open(
        "runtime",
        os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
        dir_fd=raw_root_fd,
    )
    runtime_info = os.fstat(runtime_fd)
    runtime_path = Path(f"/proc/self/fd/{runtime_fd}")
    try:
        if (
            not stat.S_ISDIR(runtime_info.st_mode)
            or runtime_info.st_uid != os.geteuid()
            or stat.S_IMODE(runtime_info.st_mode) != 0o700
            or runtime_path.resolve(strict=True) != outdir.resolve(strict=True)
        ):
            raise ValueError("runtime directory custody identity drifts")
        os.fsync(runtime_fd)
        os.fsync(raw_root_fd)
        return runtime_path, runtime_fd
    except Exception:
        os.close(runtime_fd)
        raise


def validate_child_working_directory(*, cwd_fd: int, raw_root_fd: int) -> None:
    cwd_info = os.fstat(cwd_fd)
    raw_path = Path(f"/proc/self/fd/{raw_root_fd}").resolve(strict=True)
    cwd_path = Path(f"/proc/self/fd/{cwd_fd}").resolve(strict=True)
    current_info = os.stat(".")
    if (
        not stat.S_ISDIR(cwd_info.st_mode)
        or cwd_info.st_uid != os.geteuid()
        or stat.S_IMODE(cwd_info.st_mode) != 0o700
        or (cwd_info.st_dev, cwd_info.st_ino)
        != (current_info.st_dev, current_info.st_ino)
        or cwd_path != raw_path / "empty-cwd"
        or os.listdir(f"/proc/self/fd/{cwd_fd}")
    ):
        raise ValueError("child working directory custody drifts")


def terminate_child_group(process: subprocess.Popen[bytes]) -> None:
    previous_mask = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT})
    try:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        finally:
            process.wait()
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)


def assert_child_group_quiescent(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, 0)
    except ProcessLookupError:
        return
    raise RuntimeError("child process group outlived its leader")


def arm_parent_death(expected_parent_pid: int) -> None:
    if os.getppid() != expected_parent_pid:
        raise RuntimeError("executor parent identity drifted")
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0:
        raise RuntimeError("parent-death custody is unavailable")
    if os.getppid() != expected_parent_pid:
        raise RuntimeError("executor parent exited during custody")


@dataclass(frozen=True)
class SoomfonRuntimeSnapshot:
    manifest_path: Path
    manifest_sha256: str
    manifest_payload: dict[str, Any]
    receipt_sha256: str
    runtime_inputs: dict[str, Any]
    surface_sources: dict[str, str]
    module_surfaces: dict[str, Any]


def verified_surface_declarations(
    manifest: Mapping[str, Any],
) -> list[dict[str, str]]:
    candidate = manifest.get("candidate_assembly")
    surfaces = candidate.get("surfaces") if isinstance(candidate, Mapping) else None
    declarations: list[dict[str, str]] = []
    if not isinstance(surfaces, list):
        return declarations
    for item in surfaces:
        if not isinstance(item, Mapping):
            continue
        path_text = str(item.get("path") or "").strip()
        content_hash = str(item.get("content_hash") or "").strip()
        if path_text and content_hash:
            declarations.append(
                {
                    "kind": str(item.get("kind") or path_text),
                    "path": path_text,
                    "content_hash": content_hash,
                }
            )
    return declarations


def verify_candidate_integrity(
    manifest_path: Path, manifest: Mapping[str, Any]
) -> None:
    candidate_root = manifest_path.parent.resolve()
    receipt_path = manifest_path.with_name(f"{manifest_path.name}.meta.json")
    replay = check_run_receipt(receipt_path)
    if replay.get("status") != "ok":
        raw_errors = replay.get("errors")
        errors: list[Any] = raw_errors if isinstance(raw_errors, list) else []
        detail = "; ".join(str(item) for item in errors[:3]) or str(
            replay.get("status")
        )
        raise ValueError(f"program candidate integrity check failed: {detail}")
    declarations = verified_surface_declarations(manifest)
    if not declarations:
        raise ValueError("program candidate manifest declares no hashable surfaces")
    for declaration in declarations:
        rel_path = declaration["path"]
        if rel_path == manifest_path.name:
            continue
        artifact_path = confine_path(candidate_root, rel_path)
        if not artifact_path.is_file():
            raise ValueError(f"program candidate artifact missing: {rel_path}")
        import hashlib

        actual_hash = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        expected_hash = declaration["content_hash"]
        if actual_hash != expected_hash:
            raise ValueError(
                "program candidate artifact hash mismatch for "
                f"{rel_path}: expected={expected_hash} actual={actual_hash}"
            )


class _SnapshotLoader(importlib.abc.Loader):
    def __init__(self, sources: Mapping[str, str]) -> None:
        self._sources = sources

    def exec_module(self, module: ModuleType) -> None:
        name = module.__name__
        source = self._sources[name]
        filename = f"<soomfon-snapshot:{name}.py>"
        module.__file__ = filename
        exec(compile(source, filename, "exec"), module.__dict__)


class _SnapshotFinder(importlib.abc.MetaPathFinder):
    def __init__(self, sources: Mapping[str, str]) -> None:
        self._sources = sources
        self._loader = _SnapshotLoader(sources)

    def find_spec(
        self,
        fullname: str,
        path: object = None,
        target: ModuleType | None = None,
    ) -> importlib.machinery.ModuleSpec | None:
        del path, target
        if fullname not in self._sources:
            return None
        return importlib.util.spec_from_loader(fullname, self._loader)


def _validate_snapshot_sources(sources: Mapping[str, str]) -> None:
    from dspx.services.program_runtime_episode import (
        _GENERATED_SURFACE_TOP_LEVEL_NODES,
        _DENIED_GENERATED_PROGRAM_ALIAS_CALLS,
        _DENIED_GENERATED_PROGRAM_CALLS,
        _DENIED_GENERATED_PROGRAM_METHODS,
        _generated_surface_static_violations,
        _surface_import_roots,
    )

    violations: list[str] = []
    surface_exports: dict[str, set[str]] = {}
    for module_name, source in sources.items():
        try:
            tree = ast.parse(source, filename=f"{module_name}.py")
        except SyntaxError:
            continue
        exported: set[str] = set()
        for node in tree.body:
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                exported.add(node.name)
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = (
                    node.targets if isinstance(node, ast.Assign) else [node.target]
                )
                exported.update(
                    target.id for target in targets if isinstance(target, ast.Name)
                )
        surface_exports[module_name] = exported
    for filename, allowed_nodes in _GENERATED_SURFACE_TOP_LEVEL_NODES.items():
        module_name = filename.removesuffix(".py")
        source = sources.get(module_name)
        if source is None:
            if filename == "program.py":
                violations.append("program.py is missing")
            continue
        for root in _surface_import_roots(source) & {"module", "signature"}:
            if root not in sources:
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
        tree = ast.parse(source, filename=filename)
        os_aliases = {
            alias.asname or "os"
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
            if alias.name == "os"
        }
        module_targets = {
            alias.asname or alias.name.split(".", 1)[0]: alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        declared_call_names = protected_declared_call_names(tree)
        for node in ast.walk(tree):
            attribute_root: ast.AST | None = None
            attribute_depth = 0
            if isinstance(node, ast.Attribute):
                attribute_root = node.value
                attribute_depth = 1
                while isinstance(attribute_root, ast.Attribute):
                    attribute_depth += 1
                    attribute_root = attribute_root.value
            chained_module_attribute = (
                attribute_depth > 1
                and isinstance(attribute_root, ast.Name)
                and attribute_root.id in module_targets
            )
            direct_module_attribute_denied = False
            if (
                attribute_depth == 1
                and isinstance(attribute_root, ast.Name)
                and attribute_root.id in module_targets
                and isinstance(node, ast.Attribute)
            ):
                target_module = module_targets[attribute_root.id]
                allowed_attributes = PROTECTED_MODULE_ATTRIBUTES.get(
                    target_module, surface_exports.get(target_module)
                )
                direct_module_attribute_denied = (
                    allowed_attributes is None or node.attr not in allowed_attributes
                )
            if (
                isinstance(node, ast.ImportFrom)
                and node.module == "os"
                and any(alias.name != "getenv" for alias in node.names)
            ):
                violations.append(
                    f"{filename} line {node.lineno}: denied os import alias"
                )
            if isinstance(node, ast.ImportFrom) and node.module is not None:
                allowed_imports = PROTECTED_MODULE_ATTRIBUTES.get(
                    node.module, surface_exports.get(node.module)
                )
                if allowed_imports is not None and any(
                    alias.name == "*" or alias.name not in allowed_imports
                    for alias in node.names
                ):
                    violations.append(
                        f"{filename} line {node.lineno}: module import is not allowed"
                    )
            if (
                isinstance(node, ast.ImportFrom)
                and node.module in {"dspy", "typing"}
                and any(
                    alias.name.startswith("_")
                    or alias.name in {"LM", "configure", "context", "settings", "sys"}
                    for alias in node.names
                )
            ):
                violations.append(
                    f"{filename} line {node.lineno}: denied module capability import"
                )
            if isinstance(node, ast.Attribute) and (
                node.attr
                in _DENIED_GENERATED_PROGRAM_METHODS | PROTECTED_DENIED_ATTRIBUTES
                or chained_module_attribute
                or direct_module_attribute_denied
                or node.attr.startswith("co_")
                or (
                    isinstance(node.value, ast.Name)
                    and node.value.id in os_aliases
                    and node.attr != "getenv"
                )
            ):
                violations.append(
                    f"{filename} line {node.lineno}: dangerous attribute capability is denied"
                )
            if (
                isinstance(node, ast.Name)
                and isinstance(node.ctx, ast.Store)
                and node.id in declared_call_names
            ):
                violations.append(
                    f"{filename} line {node.lineno}: callable binding cannot be replaced"
                )
            rebound_name: str | None = None
            if isinstance(node, ast.arg):
                rebound_name = node.arg
            elif isinstance(node, ast.ExceptHandler):
                rebound_name = node.name
            elif isinstance(node, (ast.MatchAs, ast.MatchStar)):
                rebound_name = node.name
            if rebound_name in declared_call_names:
                violations.append(
                    f"{filename} line {getattr(node, 'lineno', '?')}: "
                    "callable parameter cannot shadow"
                )
            if isinstance(node, ast.Name) and node.id in (
                _DENIED_GENERATED_PROGRAM_CALLS
                | _DENIED_GENERATED_PROGRAM_ALIAS_CALLS
                | {
                    "__builtins__",
                    "breakpoint",
                    "builtins",
                    "delattr",
                    "exit",
                    "help",
                    "input",
                    "quit",
                    "subprocess",
                    "sys",
                    "type",
                }
            ):
                violations.append(
                    f"{filename} line {node.lineno}: dangerous callable capability is denied"
                )
            if isinstance(node, ast.Call) and (
                isinstance(node.func, ast.Subscript)
                or (isinstance(node.func, ast.Name) and node.func.id == "getattr")
            ):
                violations.append(
                    f"{filename} line {node.lineno}: dynamic call target is denied"
                )
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id not in declared_call_names
            ):
                violations.append(
                    f"{filename} line {node.lineno}: undeclared callable is denied"
                )
    if set(sources) - {"program", "module", "signature"}:
        violations.append("snapshot exposes an unexpected generated module")
    if violations:
        raise ValueError(
            "generated program snapshot safety policy failed: "
            + "; ".join(violations[:5])
        )


@contextmanager
def generated_program_module_from_snapshot(
    snapshot: SoomfonRuntimeSnapshot,
) -> Iterator[Any]:
    from dspx.services.program_runtime_episode import _GENERATED_PROGRAM_IMPORT_LOCK
    from dspx.services.python_import_guard import suppress_bytecode_writes

    sources = snapshot.surface_sources
    _validate_snapshot_sources(sources)
    names = ("program", "module", "signature")
    finder = _SnapshotFinder(sources)
    with _GENERATED_PROGRAM_IMPORT_LOCK, suppress_bytecode_writes():
        saved = {name: sys.modules.get(name) for name in names}
        for name in names:
            sys.modules.pop(name, None)
        sys.meta_path.insert(0, finder)
        try:
            yield importlib.import_module("program")
        finally:
            try:
                sys.meta_path.remove(finder)
            except ValueError:
                pass
            for name in names:
                sys.modules.pop(name, None)
                saved_module = saved[name]
                if saved_module is not None:
                    sys.modules[name] = saved_module
