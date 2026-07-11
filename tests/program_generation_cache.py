# summary: "Run-scoped cache that replays deterministic generated-program harness and module-smoke validation effects."
# read_when:
#   - "Changing generated-program test caching, cache keys, or replayed file-effect isolation."

from __future__ import annotations

import base64
import copy
import fcntl
import hashlib
import inspect
import json
import os
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_ROOT_TOKEN = b"$DSPX_TEST_GENERATION_ROOT$"
_CACHE_SCHEMA = "dspx-test-generation-validation-cache-v1"
HarnessResult = dict[str, Any]
SmokeResult = tuple[bool, dict[str, bool], list[str]]


@dataclass(frozen=True, slots=True)
class _FileEffect:
    content_base64: str
    mode: int

    @classmethod
    def from_bytes(cls, content: bytes, *, mode: int) -> _FileEffect:
        return cls(
            content_base64=base64.b64encode(content).decode("ascii"),
            mode=mode,
        )

    def content(self) -> bytes:
        return base64.b64decode(self.content_base64, validate=True)


class ProgramGenerationValidationCache:
    """Run-scoped cache for deterministic generated-code validation.

    Cache hits replay the exact file effects into a newly materialized private
    program tree. The key binds the complete pre-validation tree, relevant
    environment, executable, and execution implementation.
    """

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def run_harness(
        self,
        program_root: Path,
        filename: str,
        *,
        label: str,
        execute: Callable[[Path, str], HarnessResult],
        execution_token: str,
    ) -> HarnessResult:
        program_root = program_root.resolve()
        test_root = self._test_root(program_root)
        before = self._snapshot(program_root)
        if self._contains_token(before.values()):
            return execute(program_root, filename)
        key = self._harness_key(
            before,
            test_root=test_root,
            filename=filename,
            label=label,
            execution_token=execution_token,
        )

        def build() -> dict[str, Any]:
            result = execute(program_root, filename)
            after = self._snapshot(program_root)
            changed: dict[str, dict[str, str | int]] = {}
            for relative, content in after.items():
                if before.get(relative) == content:
                    continue
                effect = _FileEffect.from_bytes(
                    self._canonicalize(content, test_root),
                    mode=(program_root / relative).stat().st_mode & 0o777,
                )
                changed[relative] = {
                    "content_base64": effect.content_base64,
                    "mode": effect.mode,
                }
            return {
                "schema_version": _CACHE_SCHEMA,
                "kind": "program_harness",
                "result": self._replace_strings(
                    copy.deepcopy(result), str(test_root), _ROOT_TOKEN.decode()
                ),
                "changed": changed,
                "deleted": sorted(set(before) - set(after)),
            }

        record = self._load_or_build("harness", key, build)
        self._apply_effects(program_root, test_root=test_root, record=record)
        return self._replace_strings(
            copy.deepcopy(record["result"]),
            _ROOT_TOKEN.decode(),
            str(test_root),
        )

    def run_module_smoke(
        self,
        code: str,
        *,
        payload: Mapping[str, Any],
        timeout: int | None,
        execute: Callable[[str, Mapping[str, Any], int | None], SmokeResult],
        execution_token: str,
    ) -> SmokeResult:
        serialized_payload = json.dumps(
            dict(payload), sort_keys=True, separators=(",", ":")
        )
        key = self._digest(
            "module-smoke",
            code,
            serialized_payload,
            str(timeout),
            execution_token,
            sys.executable,
            sys.version,
        )

        def build() -> dict[str, Any]:
            ok, checks, errors = execute(code, payload, timeout)
            return {
                "schema_version": _CACHE_SCHEMA,
                "kind": "module_smoke",
                "result": [ok, checks, errors],
            }

        record = self._load_or_build("module-smoke", key, build)
        result = record["result"]
        return bool(result[0]), dict(result[1]), list(result[2])

    def _test_root(self, program_root: Path) -> Path:
        raw_cache_dir = os.environ.get("DSPX_CACHE_DIR")
        if raw_cache_dir:
            candidate = Path(raw_cache_dir).expanduser().resolve().parent
            if program_root.is_relative_to(candidate):
                return candidate
        return program_root.parent

    @staticmethod
    def _snapshot(root: Path) -> dict[str, bytes]:
        return {
            str(path.relative_to(root)): path.read_bytes()
            for path in sorted(root.rglob("*"))
            if path.is_file()
            and "__pycache__" not in path.parts
            and path.suffix not in {".pyc", ".pyo"}
        }

    @staticmethod
    def _contains_token(contents: Any) -> bool:
        return any(_ROOT_TOKEN in content for content in contents)

    @staticmethod
    def _canonicalize(content: bytes, test_root: Path) -> bytes:
        return content.replace(str(test_root).encode(), _ROOT_TOKEN)

    def _harness_key(
        self,
        snapshot: Mapping[str, bytes],
        *,
        test_root: Path,
        filename: str,
        label: str,
        execution_token: str,
    ) -> str:
        digest = hashlib.sha256()
        for part in (
            "program-harness",
            filename,
            label,
            execution_token,
            sys.executable,
            sys.version,
        ):
            digest.update(part.encode())
            digest.update(b"\0")
        for relative, content in sorted(snapshot.items()):
            digest.update(relative.encode())
            digest.update(b"\0")
            digest.update(self._canonicalize(content, test_root))
            digest.update(b"\0")
        mlflow_disabled = os.environ.get("MLFLOW_ENABLE", "").strip().lower() in {
            "0",
            "false",
            "no",
            "off",
        }
        for key, value in sorted(os.environ.items()):
            if key == "MLFLOW_TRACKING_URI" and mlflow_disabled:
                continue
            if key.startswith("DSPX_") or key.startswith("MLFLOW_"):
                digest.update(key.encode())
                digest.update(b"=")
                digest.update(
                    value.replace(str(test_root), _ROOT_TOKEN.decode()).encode()
                )
                digest.update(b"\0")
        return digest.hexdigest()

    def _load_or_build(
        self,
        kind: str,
        key: str,
        build: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        kind_root = self.root / kind
        kind_root.mkdir(parents=True, exist_ok=True)
        record_path = kind_root / f"{key}.json"
        with (kind_root / f"{key}.lock").open("a+b") as lock_file:
            fcntl.flock(lock_file, fcntl.LOCK_EX)
            if record_path.exists():
                record = json.loads(record_path.read_text(encoding="utf-8"))
            else:
                record = build()
                pending = record_path.with_suffix(".json.pending")
                pending.write_text(
                    json.dumps(record, sort_keys=True, separators=(",", ":")),
                    encoding="utf-8",
                )
                os.replace(pending, record_path)
        if record.get("schema_version") != _CACHE_SCHEMA:
            raise AssertionError("invalid program-generation validation cache record")
        return record

    def _apply_effects(
        self,
        program_root: Path,
        *,
        test_root: Path,
        record: Mapping[str, Any],
    ) -> None:
        for relative in record.get("deleted", []):
            self._effect_path(program_root, str(relative)).unlink(missing_ok=True)
        raw_changed = record.get("changed", {})
        if not isinstance(raw_changed, Mapping):
            raise AssertionError("invalid cached program harness file effects")
        for relative, raw_effect in raw_changed.items():
            if not isinstance(raw_effect, Mapping):
                raise AssertionError("invalid cached program harness file effect")
            effect = _FileEffect(
                content_base64=str(raw_effect["content_base64"]),
                mode=int(raw_effect["mode"]),
            )
            destination = self._effect_path(program_root, str(relative))
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(
                effect.content().replace(_ROOT_TOKEN, str(test_root).encode())
            )
            destination.chmod(effect.mode)

    @staticmethod
    def _effect_path(program_root: Path, relative: str) -> Path:
        candidate = (program_root / relative).resolve()
        if not candidate.is_relative_to(program_root):
            raise AssertionError("cached program harness effect escapes program root")
        return candidate

    @classmethod
    def _replace_strings(cls, value: Any, old: str, new: str) -> Any:
        if isinstance(value, str):
            return value.replace(old, new)
        if isinstance(value, list):
            return [cls._replace_strings(item, old, new) for item in value]
        if isinstance(value, tuple):
            return tuple(cls._replace_strings(item, old, new) for item in value)
        if isinstance(value, dict):
            return {
                key: cls._replace_strings(item, old, new) for key, item in value.items()
            }
        return value

    @staticmethod
    def _digest(*parts: str) -> str:
        digest = hashlib.sha256()
        for part in parts:
            digest.update(part.encode())
            digest.update(b"\0")
        return digest.hexdigest()


def callable_fingerprint(value: Callable[..., Any]) -> str:
    """Stable for ordinary functions; safely distinct for monkeypatched closures."""

    code = getattr(value, "__code__", None)
    parts = [
        str(getattr(value, "__module__", type(value).__module__)),
        str(getattr(value, "__qualname__", type(value).__qualname__)),
    ]
    if code is not None:
        parts.extend(
            [
                str(code.co_filename),
                str(code.co_firstlineno),
                hashlib.sha256(code.co_code).hexdigest(),
            ]
        )
    closure = getattr(value, "__closure__", None)
    if closure:
        parts.extend(repr(cell.cell_contents) for cell in closure)
    try:
        parts.append(inspect.getsourcefile(value) or "")
    except TypeError:
        pass
    return "|".join(parts)
