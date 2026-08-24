"""Executing DSPx origin and payload binding for Soomfon authorization."""

from __future__ import annotations

import importlib
import importlib.metadata
import json
import os
import pwd
import stat
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping, NoReturn

from dspx.services.provider_outcome_receipt_identity import _record_digest

_SECURITY_CRITICAL_MODULES = (
    "dspx.services.program_runtime_episode",
    "dspx.services.soomfon_evaluation_ak_authorization",
    "dspx.services.soomfon_evaluation_auth_provider",
    "dspx.services.soomfon_evaluation_authorization",
    "dspx.services.soomfon_evaluation_candidates",
    "dspx.services.soomfon_evaluation_child",
    "dspx.services.soomfon_evaluation_contract",
    "dspx.services.soomfon_evaluation_custody",
    "dspx.services.soomfon_evaluation_dspx_identity",
    "dspx.services.soomfon_evaluation_executor",
    "dspx.services.soomfon_evaluation_filesystem",
    "dspx.services.soomfon_evaluation_ledger",
    "dspx.services.soomfon_evaluation_owner",
    "dspx.services.soomfon_evaluation_provider",
    "dspx.services.soomfon_evaluation_runtime",
    "dspx.services.soomfon_evaluation_schema",
    "dspx.services.soomfon_evaluation_snapshot",
)
_MAX_GIT_BLOB_BYTES = 2 * 1024 * 1024


class SoomfonDSPxIdentityError(RuntimeError):
    """Executing DSPx code does not match its authorized artifact."""


def _reject() -> NoReturn:
    raise SoomfonDSPxIdentityError("executing DSPx identity rejected")


def _critical_module(name: str) -> bool:
    return (
        name in {"dspx", "dspx.services", "dspx.cli", "dspx.cli.commands"}
        or name == "dspx.services.program_runtime_episode"
        or name == "dspx.cli.commands.soomfon_evaluation"
        or name.startswith("dspx.services.soomfon_evaluation_")
        or name.startswith("dspx.services.provider_outcome_receipt_")
    )


def _loaded_critical_modules() -> tuple[tuple[str, ModuleType], ...]:
    modules = tuple(
        (name, module)
        for name, module in sorted(sys.modules.items())
        if _critical_module(name) and isinstance(module, ModuleType)
    )
    names = {name for name, _ in modules}
    if (
        "dspx" not in names
        or "dspx.services.soomfon_evaluation_authorization" not in names
    ):
        _reject()
    return modules


def _module_relative_path(name: str, module: ModuleType) -> Path:
    suffix = Path(*name.split("."))
    return (
        suffix / "__init__.py"
        if hasattr(module, "__path__")
        else suffix.with_suffix(".py")
    )


def _module_origin(module: ModuleType) -> Path:
    source = getattr(module, "__file__", None)
    spec_origin = getattr(getattr(module, "__spec__", None), "origin", None)
    if not isinstance(source, str) or not isinstance(spec_origin, str):
        _reject()
    try:
        source_path = Path(source).resolve(strict=True)
        spec_path = Path(spec_origin).resolve(strict=True)
        info = source_path.lstat()
    except OSError:
        _reject()
    if (
        source_path != spec_path
        or not stat.S_ISREG(info.st_mode)
        or source_path.suffix != ".py"
    ):
        _reject()
    return source_path


def _verify_no_bytecode(
    package_root: Path, modules: tuple[tuple[str, ModuleType], ...]
) -> None:
    try:
        root = package_root.resolve(strict=True)
    except OSError:
        _reject()
    if not root.is_dir():
        _reject()
    for current, directories, files in os.walk(root, followlinks=False):
        if "__pycache__" in directories or any(name.endswith(".pyc") for name in files):
            _reject()
        if any((Path(current) / name).is_symlink() for name in directories):
            _reject()
    for _name, module in modules:
        cached = getattr(module, "__cached__", None)
        if isinstance(cached, str) and Path(cached).exists():
            _reject()


def _git(root: Path, *arguments: str) -> bytes:
    environment = {
        "HOME": pwd.getpwuid(os.geteuid()).pw_dir,
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
    }
    try:
        result = subprocess.run(
            ["/usr/bin/git", "-C", str(root), *arguments],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=environment,
            check=False,
            timeout=5.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        _reject()
    if result.returncode or len(result.stdout) > _MAX_GIT_BLOB_BYTES:
        _reject()
    return result.stdout


def _git_text(root: Path, *arguments: str) -> str:
    try:
        return _git(root, *arguments).decode().strip()
    except UnicodeError:
        _reject()


def _verify_source(repo_root: Path, artifact: Mapping[str, Any]) -> None:
    try:
        root = repo_root.expanduser().resolve(strict=True)
    except OSError:
        _reject()
    if (
        _git_text(root, "rev-parse", "HEAD^{commit}") != artifact.get("commit")
        or _git_text(root, "rev-parse", "HEAD^{tree}") != artifact.get("tree")
        or _git_text(root, "status", "--porcelain", "--untracked-files=normal")
    ):
        _reject()
    source_root = root / "packages/dspx-core/src"
    modules = _loaded_critical_modules()
    _verify_no_bytecode(source_root / "dspx", modules)
    for name, module in modules:
        relative = _module_relative_path(name, module)
        expected = source_root / relative
        origin = _module_origin(module)
        try:
            lexical_info = expected.lstat()
            raw = expected.read_bytes()
        except OSError:
            _reject()
        if (
            not stat.S_ISREG(lexical_info.st_mode)
            or expected.is_symlink()
            or origin != expected.resolve(strict=True)
            or raw
            != _git(root, "show", f"HEAD:packages/dspx-core/src/{relative.as_posix()}")
        ):
            _reject()


def _verify_installed(artifact: Mapping[str, Any]) -> None:
    try:
        distribution = importlib.metadata.distribution("dspx-core")
    except importlib.metadata.PackageNotFoundError:
        _reject()
    direct_raw = distribution.read_text("direct_url.json") or ""
    try:
        direct = json.loads(direct_raw)
    except json.JSONDecodeError:
        _reject()
    archive_hash = direct.get("archive_info", {}).get("hash")
    observed = _record_digest(distribution, "dspx")
    if (
        distribution.version != artifact.get("version")
        or archive_hash != f"sha256={artifact.get('wheel_sha256')}"
        or observed.get("payload_sha256") != artifact.get("installed_payload_sha256")
    ):
        _reject()
    files = {str(item) for item in distribution.files or ()}
    modules = _loaded_critical_modules()
    try:
        package_root = Path(str(distribution.locate_file("dspx")))
    except Exception:
        _reject()
    _verify_no_bytecode(package_root, modules)
    for name, module in modules:
        relative = _module_relative_path(name, module)
        try:
            expected = Path(str(distribution.locate_file(relative))).resolve(
                strict=True
            )
        except OSError:
            _reject()
        if str(relative) not in files or _module_origin(module) != expected:
            _reject()


def preload_security_critical_dspx_modules() -> None:
    """Load the closed task-local code set before byte/origin verification."""

    for name in _SECURITY_CRITICAL_MODULES:
        importlib.import_module(name)


def verify_executing_dspx_artifact(
    *, repo_root: Path, artifact: Mapping[str, Any]
) -> None:
    """Bind every currently loaded security-critical DSPx module."""

    if sys.dont_write_bytecode is not True:
        _reject()
    kind = artifact.get("kind")
    try:
        if kind == "reviewed_source_commit_tree":
            _verify_source(repo_root, artifact)
        elif kind == "installed_wheel_payload":
            _verify_installed(artifact)
        else:
            _reject()
    except SoomfonDSPxIdentityError:
        raise
    except Exception:
        _reject()


__all__ = [
    "SoomfonDSPxIdentityError",
    "preload_security_critical_dspx_modules",
    "verify_executing_dspx_artifact",
]
