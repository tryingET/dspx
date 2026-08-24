# summary: "Gate-5 source/origin binding, AK command reader, and exact owner check."
from __future__ import annotations

import hashlib
import importlib
import inspect
import json
import os
import stat
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import Any

from dspx.services.program_oracle_semantic_gate4_contract_v11 import (
    CANDIDATE_SOURCE_PATHS,
    REVIEWED_RUNTIME_MODULES,
    RUNTIME_SUPPORT_SOURCE_PATHS,
    SemanticV11Error,
)
from dspx.services.provider_outcome_receipt_identity import (
    VerifiedOwnerArtifact,
    verify_owner_artifact,
)

_AK = Path.home() / ".local/bin/ak"


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise SemanticV11Error("Gate-5 value is not canonical JSON") from exc


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise SemanticV11Error(f"Gate-5 {label} must be an object")
    return {str(key): item for key, item in value.items()}


def source_manifest(repo_root: Path) -> dict[str, str]:
    try:
        root = repo_root.expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise SemanticV11Error("Gate-5 candidate source root unavailable") from exc
    paths = tuple(
        dict.fromkeys((*CANDIDATE_SOURCE_PATHS, *RUNTIME_SUPPORT_SOURCE_PATHS))
    )
    result: dict[str, str] = {}
    for relative in paths:
        path = root / relative
        try:
            info = path.lstat()
            raw = path.read_bytes()
        except OSError as exc:
            raise SemanticV11Error("Gate-5 candidate source unavailable") from exc
        if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
            raise SemanticV11Error("Gate-5 candidate source posture drift")
        result[relative] = _sha(raw)
    return result


def git_identity(repo_root: Path) -> tuple[str, str]:
    try:
        root = repo_root.expanduser().resolve(strict=True)
        values: list[str] = []
        for expression in ("HEAD", "HEAD^{tree}"):
            completed = subprocess.run(
                ["git", "-C", str(root), "rev-parse", expression],
                check=False,
                capture_output=True,
                timeout=30,
                env={"HOME": str(Path.home()), "PATH": "/usr/bin:/bin"},
            )
            if completed.returncode:
                raise SemanticV11Error("Gate-5 Git identity unavailable")
            values.append(completed.stdout.decode("ascii").strip())
    except SemanticV11Error:
        raise
    except (OSError, RuntimeError, UnicodeError, subprocess.SubprocessError) as exc:
        raise SemanticV11Error("Gate-5 Git identity unavailable") from exc
    if any(
        len(value) != 40 or any(char not in "0123456789abcdef" for char in value)
        for value in values
    ):
        raise SemanticV11Error("Gate-5 Git identity drift")
    return values[0], values[1]


def _verify_loaded_origins(repo_root: Path, manifest: Mapping[str, str]) -> None:
    root = repo_root.expanduser().resolve(strict=True)
    for package_name, relative_root in {
        "dspx": "packages/dspx-core/src/dspx",
        "dspx.services": "packages/dspx-core/src/dspx/services",
    }.items():
        package = sys.modules.get(package_name)
        search = getattr(package, "__path__", None) if package is not None else None
        if search is None or {Path(item).resolve(strict=True) for item in search} != {
            (root / relative_root).resolve(strict=True)
        }:
            raise SemanticV11Error("Gate-5 package search path drift")
    loaded = {
        name for name in sys.modules if name == "dspx" or name.startswith("dspx.")
    }
    if loaded - set(REVIEWED_RUNTIME_MODULES):
        raise SemanticV11Error("Gate-5 unreviewed DSPx module loaded")
    for name, relative in REVIEWED_RUNTIME_MODULES.items():
        module = sys.modules.get(name)
        if module is None:
            continue
        origin = getattr(module, "__file__", None)
        expected = (root / relative).resolve(strict=True)
        if (
            not isinstance(module, ModuleType)
            or not isinstance(origin, str)
            or origin.endswith((".pyc", ".pyo"))
            or getattr(module, "__cached__", None) is not None
            or Path(origin).resolve(strict=True) != expected
            or manifest.get(relative) != _sha(expected.read_bytes())
        ):
            raise SemanticV11Error("Gate-5 loaded module origin/hash drift")


def verify_loaded_origins(repo_root: Path, manifest: Mapping[str, str]) -> None:
    try:
        _verify_loaded_origins(repo_root, manifest)
    except SemanticV11Error:
        raise
    except (OSError, RuntimeError) as exc:
        raise SemanticV11Error("Gate-5 loaded module origin unavailable") from exc


def _run_ak(*args: str) -> dict[str, Any]:
    try:
        info = _AK.resolve(strict=True).stat()
    except OSError as exc:
        raise SemanticV11Error("canonical AK executable unavailable") from exc
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.getuid()
        or not info.st_mode & stat.S_IXUSR
    ):
        raise SemanticV11Error("canonical AK executable posture drift")
    try:
        completed = subprocess.run(
            [str(_AK), *args],
            check=False,
            capture_output=True,
            timeout=30,
            env={
                "HOME": str(Path.home()),
                "PATH": "/usr/bin:/bin",
                "XDG_CONFIG_HOME": str(Path.home() / ".config"),
                "XDG_DATA_HOME": str(Path.home() / ".local/share"),
                "XDG_STATE_HOME": str(Path.home() / ".local/state"),
            },
        )
        if completed.returncode or completed.stderr:
            raise SemanticV11Error("canonical AK authority read failed")
        return _mapping(json.loads(completed.stdout), "canonical AK output")
    except SemanticV11Error:
        raise
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        subprocess.SubprocessError,
    ) as exc:
        raise SemanticV11Error("canonical AK authority read failed") from exc


def _verify_owner(owner_source_root: Path) -> VerifiedOwnerArtifact:
    package = importlib.import_module("dspy_lm_auth")
    lm_module = importlib.import_module("dspy_lm_auth.lm")
    event_type = getattr(package, "OutcomeReceiptEvent", None)
    receipt_type = getattr(package, "ProviderOutcomeReceipt", None)
    lm_type = getattr(lm_module, "LM", None)
    if (
        not isinstance(event_type, type)
        or not isinstance(receipt_type, type)
        or not isinstance(lm_type, type)
    ):
        raise SemanticV11Error("Gate-5 owner API drift")
    artifact = verify_owner_artifact(owner_source_root, event_type, receipt_type)
    source = inspect.getsourcefile(lm_type)
    expected = (
        owner_source_root.expanduser().resolve(strict=True) / "src/dspy_lm_auth/lm.py"
    ).resolve(strict=True)
    if source is None or Path(source).resolve(strict=True) != expected:
        raise SemanticV11Error("Gate-5 owner LM origin drift")
    return artifact


def verify_owner(owner_source_root: Path) -> VerifiedOwnerArtifact:
    try:
        return _verify_owner(owner_source_root)
    except SemanticV11Error:
        raise
    except (ImportError, OSError, TypeError, ValueError) as exc:
        raise SemanticV11Error("Gate-5 owner verification rejected") from exc
