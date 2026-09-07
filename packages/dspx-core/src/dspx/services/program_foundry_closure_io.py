"""Stdlib-only, descriptor-confined immutable reads for the closure protocol."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import PurePosixPath
import re
import stat
from typing import Any

REQUEST_SCHEMA = "dspx-foundry-closure-check-request-v1"
RESPONSE_SCHEMA = "dspx-foundry-closure-verification-v1"
LIMITS = {
    "request_bytes": 262144,
    "json_bytes": 2097152,
    "artifact_bytes": 16777216,
    "closure_bytes": 134217728,
    "files": 256,
    "json_depth": 64,
    "path_depth": 16,
    "jurors": 32,
}
EXPECTED = frozenset(
    {
        "package_manifest",
        "import_binding",
        "import_provenance",
        "imported_intent",
        "imported_inputs",
        "jury_receipt",
        "adjudication",
    }
)


class Rejected(ValueError):
    def __init__(self, reason: str, status: str = "invalid") -> None:
        super().__init__(reason)
        self.reason = reason
        self.status = status


def require(condition: Any, reason: str) -> None:
    if not condition:
        raise Rejected(reason)


def closed(value: Any, keys: Any, reason: str = "shape_mismatch") -> dict:
    require(isinstance(value, dict) and set(value) == set(keys), reason)
    return value


def digest(raw: bytes | bytearray) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def equal(left: Any, right: Any, reason: str = "equality_mismatch") -> None:
    # JSON equality, not Python's True == 1 coercion.
    if isinstance(left, (bytes, bytearray, set)) or isinstance(
        right, (bytes, bytearray, set)
    ):
        require(type(left) is type(right) and left == right, reason)
    else:
        require(canonical(left) == canonical(right), reason)


def sha(value: Any) -> str:
    require(
        isinstance(value, str) and re.fullmatch("[0-9a-f]{64}", value), "invalid_digest"
    )
    return value


def integer(value: Any, maximum: int, minimum: int = 0) -> int:
    require(type(value) is int and minimum <= value <= maximum, "invalid_integer")
    return value


def decode(raw: bytes, maximum: int = LIMITS["json_bytes"]) -> Any:
    require(len(raw) <= maximum, "json_too_large")

    def pairs(items: list) -> dict:
        result = {}
        for key, value in items:
            require(key not in result, "duplicate_json_key")
            result[key] = value
        return result

    def bad_constant(_value: str) -> Any:
        raise Rejected("nonfinite_json")

    try:
        value = json.loads(
            raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=bad_constant
        )
        stack = [(value, 0)]
        while stack:
            item, depth = stack.pop()
            require(depth <= LIMITS["json_depth"], "json_depth")
            if isinstance(item, dict):
                stack.extend((x, depth + 1) for x in item.values())
                for key in item:
                    key.encode("utf-8")
            elif isinstance(item, list):
                stack.extend((x, depth + 1) for x in item)
            elif isinstance(item, float):
                require(math.isfinite(item), "nonfinite_json")
            elif isinstance(item, str):
                item.encode("utf-8")  # reject lone surrogate escapes
        return value
    except (UnicodeError, json.JSONDecodeError, RecursionError, OverflowError) as exc:
        raise Rejected("invalid_json") from exc


def path_parts(value: Any, *, absolute: bool) -> tuple[str, ...]:
    require(
        isinstance(value, str) and value and "\\" not in value and "\0" not in value,
        "invalid_path",
    )
    require(len(value.encode("utf-8")) <= 4096, "path_too_long")
    p = PurePosixPath(value)
    require(
        all(len(part.encode("utf-8")) <= 255 for part in p.parts),
        "path_component_too_long",
    )
    require(p.is_absolute() is absolute and str(p) == value, "invalid_path")
    parts = p.parts[1:] if absolute else p.parts
    require(
        parts and len(parts) <= 32 and all(x not in {".", ".."} for x in parts),
        "invalid_path",
    )
    return parts


def sibling(original: str, name: str) -> str:
    path_parts(original, absolute=True)
    path_parts(name, absolute=False)
    return str(PurePosixPath(original).parent / name)


def root_open(path: str) -> int:
    parts = path_parts(path, absolute=True)
    require(len(parts) >= 3, "unsafe_root")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open("/", flags)
    try:
        for part in parts:
            child = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        info = os.fstat(fd)
        require(info.st_uid == os.geteuid() and not info.st_mode & 0o022, "unsafe_root")
        return fd
    except BaseException:
        os.close(fd)
        raise


class Snapshot:
    """Only request-provisioned locators are readable; no inferred on-disk paths."""

    def __init__(self, request: dict) -> None:
        self.request = request
        self.fds: list[int] = []
        self.aliases: dict[str, dict] = {}
        self.cache: dict[tuple[int, str], bytes] = {}
        self.inventory: dict[str, dict] = {}
        self.inodes: set[tuple[int, int]] = set()
        self.total = 0
        closed(
            request,
            {
                "schema_version",
                "phase",
                "verifier_profile_sha256",
                "subject",
                "expected",
                "roots",
                "locators",
                "limits",
            },
        )
        equal(request["schema_version"], REQUEST_SCHEMA)
        equal(request["phase"], "after_jury")
        sha(request["verifier_profile_sha256"])
        equal(request["limits"], LIMITS, "limits_mismatch")
        closed(
            request["subject"], {"schema_version", "package_sha256", "manifest_sha256"}
        )
        equal(request["subject"]["schema_version"], "misegraph-evidence-package-v1")
        sha(request["subject"]["package_sha256"])
        sha(request["subject"]["manifest_sha256"])
        closed(request["expected"], EXPECTED)
        for ref in request["expected"].values():
            closed(ref, {"original_path", "sha256"})
            sha(ref["sha256"])
            path_parts(ref["original_path"], absolute=True)
        roots = request["roots"]
        require(isinstance(roots, list) and 1 <= len(roots) <= 4, "invalid_roots")
        require(len(set(roots)) == len(roots), "duplicate_roots")
        rows = request["locators"]
        require(
            isinstance(rows, list) and 1 <= len(rows) <= LIMITS["files"],
            "locator_limit",
        )
        places: set[tuple[int, str]] = set()
        for row in rows:
            closed(row, {"sha256", "bytes", "root", "path", "aliases"})
            sha(row["sha256"])
            integer(row["bytes"], LIMITS["artifact_bytes"])
            integer(row["root"], len(roots) - 1)
            require(
                len(path_parts(row["path"], absolute=False)) <= LIMITS["path_depth"],
                "path_depth",
            )
            place = (row["root"], row["path"])
            require(place not in places, "duplicate_locator")
            places.add(place)
            require(
                isinstance(row["aliases"], list) and 1 <= len(row["aliases"]) <= 8,
                "alias_limit",
            )
            for alias in row["aliases"]:
                path_parts(alias, absolute=True)
                require(alias not in self.aliases, "conflicting_alias")
                self.aliases[alias] = row
        try:
            self.fds = []
            for root in roots:
                self.fds.append(root_open(root))
        except BaseException:
            self.close()
            raise

    def close(self) -> None:
        for fd in self.fds:
            os.close(fd)
        self.fds = []

    def read(self, alias: str, expected: str | None = None) -> bytes:
        row = self.aliases.get(alias)
        if row is None:
            raise Rejected("missing_locator", "incomplete")
        if expected is not None:
            equal(row["sha256"], sha(expected), "reference_hash_mismatch")
        place = (row["root"], row["path"])
        if place not in self.cache:
            require(
                self.total + row["bytes"] <= LIMITS["closure_bytes"],
                "closure_too_large",
            )
            fd = os.dup(self.fds[row["root"]])
            try:
                parts = path_parts(row["path"], absolute=False)
                for part in parts[:-1]:
                    child = os.open(
                        part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd
                    )
                    os.close(fd)
                    fd = child
                    directory = os.fstat(fd)
                    require(
                        directory.st_uid == os.geteuid()
                        and not directory.st_mode & 0o022,
                        "unsafe_directory",
                    )
                child = os.open(
                    parts[-1], os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=fd
                )
                os.close(fd)
                fd = child
                before = os.fstat(fd)
                require(stat.S_ISREG(before.st_mode), "not_regular")
                inode = (before.st_dev, before.st_ino)
                require(inode not in self.inodes, "duplicate_physical_file")
                require(
                    before.st_uid == os.geteuid() and not before.st_mode & 0o022,
                    "unsafe_file",
                )
                require(before.st_size == row["bytes"], "size_mismatch")
                raw = bytearray()
                while True:
                    chunk = os.read(fd, min(65536, row["bytes"] + 1 - len(raw)))
                    if not chunk:
                        break
                    raw.extend(chunk)
                    require(len(raw) <= row["bytes"], "file_grew")
                after = os.fstat(fd)

                def identity(info: os.stat_result) -> tuple:
                    return (
                        info.st_dev,
                        info.st_ino,
                        info.st_size,
                        info.st_mtime_ns,
                        info.st_ctime_ns,
                    )

                equal(identity(before), identity(after), "file_changed")
                require(
                    len(raw) == row["bytes"] and digest(raw) == row["sha256"],
                    "file_hash_mismatch",
                )
                self.total += len(raw)
                require(self.total <= LIMITS["closure_bytes"], "closure_too_large")
                self.cache[place] = bytes(raw)
                self.inodes.add(inode)
            except FileNotFoundError as exc:
                raise Rejected("missing_file", "incomplete") from exc
            except OSError as exc:
                raise Rejected("unsafe_read") from exc
            finally:
                os.close(fd)
        # Original-path identity is retained; aliases cannot weaken historical hash domains.
        self.inventory[alias] = {
            "original_path": alias,
            "sha256": row["sha256"],
            "bytes": row["bytes"],
        }
        return self.cache[place]

    def json(self, alias: str, expected: str | None = None) -> dict:
        row = self.aliases.get(alias)
        if row is not None:
            require(row["bytes"] <= LIMITS["json_bytes"], "json_too_large")
        value = decode(self.read(alias, expected))
        require(isinstance(value, dict), "object_required")
        return value

    def expected(self, role: str) -> tuple[str, dict]:
        ref = self.request["expected"][role]
        return ref["original_path"], self.json(ref["original_path"], ref["sha256"])

    def hash(self, alias: str) -> str:
        return digest(self.read(alias))

    def inventory_hash(self) -> str:
        rows = [self.inventory[key] for key in sorted(self.inventory)]
        return digest(b"dspx-foundry-captured-closure-v1\0" + canonical(rows))
