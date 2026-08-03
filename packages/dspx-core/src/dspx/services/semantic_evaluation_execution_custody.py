"""Decision 105 synthetic execution-attempt custody primitive.

This module is intentionally not wired into the DSPx runtime or CLI.  It owns a
local SQLite attempt/evidence lifecycle and only attests effects observed at its
call boundary.
"""

from __future__ import annotations

import fcntl

import hashlib
import json
import os
import re
import sqlite3
import stat
import unicodedata
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, cast
from uuid import UUID, uuid4

SCHEMA_VERSION = "dspx-semantic-evaluation-execution-custody-store-v1"
PROJECTION_SCHEMA_VERSION = "dspx-semantic-evaluation-evidence-projection-v1"
EFFECT_INVENTORY_VERSION = "dspx-semantic-evaluation-execution-effect-inventory-v1"
RECEIPT_SCHEMA_VERSION = "dspx-semantic-evaluation-execution-receipt-v1"
SEAL_SCHEMA_VERSION = "dspx-semantic-evaluation-execution-seal-v1"
NON_AUTHORITY = MappingProxyType(
    {
        "executed_identity": False,
        "semantic_meaning": False,
        "deterministic_verdict": False,
        "publication": False,
        "currentness": False,
        "promotion": False,
        "governance": False,
        "ak_mutation": False,
        "external_authority": False,
    }
)
PROJECTION_KEYS = frozenset(
    {
        "schema_version",
        "episode_id",
        "attempt_id",
        "attempt_kind",
        "source_receipt_digest",
        "candidate_coordinate",
        "input_coordinate",
        "evaluation_request_digest",
        "effect_inventory_version",
        "runtime_observation",
        "outcome_evidence",
        "episode_evidence_manifest_digest",
        "receipt_digest",
        "state_trace_digest",
        "non_authority",
    }
)
TERMINAL_STATES = frozenset({"rejected", "indeterminate", "closed"})


class CustodyError(ValueError):
    """The requested custody operation violates the accepted contract."""


@dataclass(frozen=True)
class AttemptRequest:
    episode_id: str
    attempt_kind: Literal["original", "replay"]
    source_receipt_digest: str | None
    source_manifest_digest: str
    candidate_receipt_digest: str
    normalized_input_digest: str
    evaluation_request_digest: str
    configured_runtime_digest: str
    configured_provider: str | None = None
    configured_model: str | None = None
    effect_inventory_version: str = EFFECT_INVENTORY_VERSION
    disclosure_posture: str = "digest_only_no_raw_access_right"


@dataclass(frozen=True)
class AllocationMaterial:
    candidate_manifest_path: Path
    candidate_receipt_path: Path
    input_source_path: Path


@dataclass(frozen=True)
class SnapshotView:
    bytes: bytes
    sha256: str


@dataclass(frozen=True)
class AttemptDisposition:
    attempt_id: str
    state: str
    terminal_reason: str | None
    invoked: bool = False


@dataclass(frozen=True)
class RejectionDisposition:
    rejection_id: str
    state: str
    terminal_reason: str


FaultBarrier = Callable[[str, str], None]


def _nfc(value: object) -> str:
    if not isinstance(value, str):
        raise CustodyError("JSON strings must have string type")
    normalized = unicodedata.normalize("NFC", value)
    if value != normalized or any(ord(char) < 0x20 for char in value):
        raise CustodyError("strings must be NFC and contain no control characters")
    return value


def _validate_json_strings(value: object) -> None:
    if isinstance(value, str):
        _nfc(value)
    elif isinstance(value, Mapping):
        for key, member in value.items():
            _nfc(key)
            _validate_json_strings(member)
    elif isinstance(value, (list, tuple)):
        for member in value:
            _validate_json_strings(member)


def canonical_json_bytes(value: object) -> bytes:
    """Return the one stored/hashed canonical JSON encoding."""
    _validate_json_strings(value)
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CustodyError("value is not canonical JSON") from exc


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _invalid_value_fingerprint(value: object) -> dict[str, Any]:
    if value is None:
        return {"type": "null"}
    if isinstance(value, bool):
        return {"type": "bool", "value": value}
    if isinstance(value, int):
        return {"type": "int", "value": str(value)}
    if isinstance(value, float):
        return {"type": "float", "value": value.hex()}
    if isinstance(value, str):
        return {
            "type": "str",
            "utf8_digest": _sha256(value.encode("utf-8", errors="surrogatepass")),
        }
    if isinstance(value, Path):
        return {"type": "path", "path_digest": _path_digest(_absolute_path(value))}
    if isinstance(value, (list, tuple)):
        return {
            "type": "list" if isinstance(value, list) else "tuple",
            "members": [_invalid_value_fingerprint(member) for member in value],
        }
    if isinstance(value, (set, frozenset)):
        members = [_invalid_value_fingerprint(member) for member in value]
        members.sort(key=canonical_json_bytes)
        return {"type": "set", "members": members}
    if isinstance(value, Mapping):
        members = [
            {
                "key": _invalid_value_fingerprint(key),
                "value": _invalid_value_fingerprint(member),
            }
            for key, member in value.items()
        ]
        members.sort(key=canonical_json_bytes)
        return {"type": "mapping", "members": members}
    raise CustodyError(
        "invalid request contains a value that cannot be fingerprinted safely"
    )


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


def _require_sha256(value: object, label: str) -> str:
    if not _is_sha256(value):
        raise CustodyError(f"{label} must be a lowercase SHA-256 digest")
    return str(value)


def _configured_label(value: object, label: str) -> str | None:
    if value is None:
        return None
    text = _nfc(value)
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/+\-]{0,127}", text) is None:
        raise CustodyError(f"{label} is invalid")
    return text


def _request_payload(request: AttemptRequest) -> dict[str, Any]:
    episode_id = _nfc(request.episode_id)
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:\-]{0,127}", episode_id) is None:
        raise CustodyError("episode_id is invalid")
    if request.attempt_kind not in {"original", "replay"}:
        raise CustodyError("attempt_kind is invalid")
    if request.attempt_kind == "original":
        if request.source_receipt_digest is not None:
            raise CustodyError("original attempts require null source receipt")
    else:
        _require_sha256(request.source_receipt_digest, "source_receipt_digest")
    for label, value in (
        ("source_manifest_digest", request.source_manifest_digest),
        ("candidate_receipt_digest", request.candidate_receipt_digest),
        ("normalized_input_digest", request.normalized_input_digest),
        ("evaluation_request_digest", request.evaluation_request_digest),
        ("configured_runtime_digest", request.configured_runtime_digest),
    ):
        _require_sha256(value, label)
    if request.effect_inventory_version != EFFECT_INVENTORY_VERSION:
        raise CustodyError("effect inventory is not accepted v1")
    if request.disclosure_posture != "digest_only_no_raw_access_right":
        raise CustodyError("input disclosure posture is invalid")
    return {
        "episode_id": episode_id,
        "attempt_kind": request.attempt_kind,
        "source_receipt_digest": request.source_receipt_digest,
        "candidate_coordinate": {
            "source_manifest_digest": request.source_manifest_digest,
            "candidate_receipt_digest": request.candidate_receipt_digest,
        },
        "input_coordinate": {
            "normalized_input_digest": request.normalized_input_digest,
            "disclosure_posture": request.disclosure_posture,
        },
        "evaluation_request_digest": request.evaluation_request_digest,
        "effect_inventory_version": request.effect_inventory_version,
        "configured_runtime_digest": request.configured_runtime_digest,
        "configured_provider": _configured_label(
            request.configured_provider, "configured_provider"
        ),
        "configured_model": _configured_label(
            request.configured_model, "configured_model"
        ),
    }


def _path_digest(path: Path) -> str:
    return _sha256(os.fsencode(str(path)))


_DIRECTORY_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_DIRECTORY", 0)
    | getattr(os, "O_CLOEXEC", 0)
    | getattr(os, "O_NOFOLLOW", 0)
)
_FILE_FLAGS = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
_APPROVED_LOCAL_FILESYSTEMS = frozenset(
    {
        "aufs",
        "bcachefs",
        "btrfs",
        "erofs",
        "ext2",
        "ext3",
        "ext4",
        "f2fs",
        "hfs",
        "hfsplus",
        "jfs",
        "nilfs2",
        "overlay",
        "ramfs",
        "reiserfs",
        "squashfs",
        "tmpfs",
        "ubifs",
        "xfs",
        "zfs",
    }
)


def _require_posix_open_guards() -> None:
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise CustodyError("custody stores require POSIX no-follow directory opens")


def _absolute_path(path: Path) -> Path:
    return Path(os.path.abspath(path.expanduser()))


def _sqlite_descriptor_path(descriptor: int) -> str:
    descriptor_info = os.fstat(descriptor)
    for directory in ("/proc/self/fd", "/dev/fd"):
        candidate = Path(directory) / str(descriptor)
        try:
            candidate_info = os.stat(candidate)
        except OSError:
            continue
        if (candidate_info.st_dev, candidate_info.st_ino) == (
            descriptor_info.st_dev,
            descriptor_info.st_ino,
        ):
            return str(candidate)
    raise CustodyError("SQLite descriptor path is unavailable on this platform")


def _open_directory_chain(path: Path, label: str) -> tuple[Path, int]:
    """Open every component without following symlinks and return the final fd."""
    _require_posix_open_guards()
    absolute = _absolute_path(path)
    descriptor = os.open(absolute.anchor, _DIRECTORY_FLAGS)
    current = Path(absolute.anchor)
    try:
        for component in absolute.parts[1:]:
            current /= component
            try:
                next_descriptor = os.open(
                    component, _DIRECTORY_FLAGS, dir_fd=descriptor
                )
            except (FileNotFoundError, NotADirectoryError) as exc:
                try:
                    component_info = os.stat(
                        component, dir_fd=descriptor, follow_symlinks=False
                    )
                except OSError:
                    raise CustodyError(f"{label} path does not exist") from exc
                if stat.S_ISLNK(component_info.st_mode):
                    raise CustodyError(f"{label} path contains a symlink") from exc
                raise CustodyError(f"{label} path is not a directory") from exc
            except OSError as exc:
                raise CustodyError(
                    f"{label} path contains a symlink or unsafe component"
                ) from exc
            os.close(descriptor)
            descriptor = next_descriptor
            path_info = os.stat(current, follow_symlinks=False)
            fd_info = os.fstat(descriptor)
            if not stat.S_ISDIR(fd_info.st_mode) or (
                path_info.st_dev,
                path_info.st_ino,
            ) != (fd_info.st_dev, fd_info.st_ino):
                raise CustodyError(f"{label} descriptor/path binding changed")
        return absolute, descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _reject_symlink_components(path: Path, label: str) -> Path:
    absolute, descriptor = _open_directory_chain(path, label)
    os.close(descriptor)
    return absolute


def _validate_owned_store_chain(path: Path) -> None:
    absolute = _reject_symlink_components(path, "store path")
    current = Path(absolute.anchor)
    owner_root_seen = False
    for component in absolute.parts[1:]:
        current /= component
        info = os.stat(current, follow_symlinks=False)
        if info.st_uid == os.geteuid():
            owner_root_seen = True
        if owner_root_seen:
            if info.st_uid != os.geteuid():
                raise CustodyError("store path leaves its owner-controlled root")
            if stat.S_IMODE(info.st_mode) & 0o022:
                raise CustodyError("store owner path must not be group/world writable")
    if not owner_root_seen:
        raise CustodyError("store path has no owner-controlled root")


def _mountinfo_unescape(value: str) -> str:
    for escaped, literal in (
        ("\\134", "\\"),
        ("\\040", " "),
        ("\\011", "\t"),
        ("\\012", "\n"),
    ):
        value = value.replace(escaped, literal)
    return value


def _filesystem_type(path: Path) -> str | None:
    mountinfo = Path("/proc/self/mountinfo")
    if not mountinfo.exists():
        return None
    try:
        lines = mountinfo.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise CustodyError("cannot inspect filesystem type") from exc
    selected: tuple[int, str] | None = None
    absolute = str(_absolute_path(path))
    for line in lines:
        before, separator, after = line.partition(" - ")
        if not separator:
            raise CustodyError("malformed mountinfo prevents filesystem verification")
        fields = before.split()
        after_fields = after.split()
        if len(fields) < 5 or not after_fields:
            raise CustodyError("malformed mountinfo prevents filesystem verification")
        mountpoint = _mountinfo_unescape(fields[4])
        if absolute == mountpoint or absolute.startswith(mountpoint.rstrip("/") + "/"):
            candidate = (len(mountpoint), after_fields[0].lower())
            if selected is None or candidate[0] > selected[0]:
                selected = candidate
    if selected is None:
        raise CustodyError("filesystem mount could not be identified")
    return selected[1]


def _reject_network_filesystem(path: Path) -> None:
    filesystem_type = _filesystem_type(path)
    if filesystem_type is None:
        raise CustodyError("local filesystem type cannot be verified on this platform")
    if filesystem_type not in _APPROVED_LOCAL_FILESYSTEMS:
        raise CustodyError(
            "network filesystems and unapproved local filesystem types are unsupported: "
            f"{filesystem_type!r}"
        )


def _reject_network_descriptor(descriptor: int, label: str) -> None:
    for directory in ("/proc/self/fd", "/dev/fd"):
        candidate = Path(directory) / str(descriptor)
        try:
            target = os.readlink(candidate)
        except OSError:
            continue
        if target.endswith(" (deleted)"):
            raise CustodyError(f"{label} descriptor target was deleted")
        _reject_network_filesystem(Path(target))
        return
    raise CustodyError(f"{label} descriptor filesystem cannot be verified")


def _read_stable_regular(path: Path, label: str) -> tuple[Path, bytes]:
    absolute = _absolute_path(path)
    _reject_network_filesystem(absolute.parent)
    parent, parent_fd = _open_directory_chain(absolute.parent, label)
    descriptor = -1
    try:
        try:
            descriptor = os.open(absolute.name, _FILE_FLAGS, dir_fd=parent_fd)
        except OSError as exc:
            raise CustodyError(f"{label} must be a non-symlink regular file") from exc
        before = os.fstat(descriptor)
        _reject_network_descriptor(descriptor, label)
        bound_before = os.stat(absolute.name, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode) or (
            before.st_dev,
            before.st_ino,
        ) != (bound_before.st_dev, bound_before.st_ino):
            raise CustodyError(f"{label} must be a descriptor-bound regular file")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
        bound_after = os.stat(absolute.name, dir_fd=parent_fd, follow_symlinks=False)
        if (before.st_dev, before.st_ino, before.st_size) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
        ) or (after.st_dev, after.st_ino) != (
            bound_after.st_dev,
            bound_after.st_ino,
        ):
            raise CustodyError(f"{label} changed during read")
        return parent / absolute.name, b"".join(chunks)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(parent_fd)


def _canonical_input_bytes(raw: bytes) -> bytes:
    try:
        text = raw.decode("utf-8")
        loaded = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CustodyError("input source must be canonical UTF-8 JSON") from exc
    if not isinstance(loaded, dict):
        raise CustodyError("input source must contain a JSON object")
    if canonical_json_bytes(loaded) != raw:
        raise CustodyError("input source bytes are not canonical JSON")
    return raw


def _disjoint(store: Path, candidate_root: Path, *files: Path) -> None:
    def related(left: Path, right: Path) -> bool:
        return left == right or left in right.parents or right in left.parents

    if related(store, candidate_root):
        raise CustodyError("store must be disjoint from candidate root")
    if any(related(store, file) for file in files):
        raise CustodyError("store must be disjoint from source files")


def _validate_projection(value: Mapping[str, Any]) -> None:
    if set(value) != PROJECTION_KEYS:
        raise CustodyError("projection top-level members are not exact")
    if value.get("schema_version") != PROJECTION_SCHEMA_VERSION:
        raise CustodyError("projection schema version is invalid")
    episode_id = value.get("episode_id")
    if not isinstance(episode_id, str) or (
        re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:\-]{0,127}", episode_id) is None
    ):
        raise CustodyError("projection episode_id is invalid")
    _nfc(episode_id)
    try:
        parsed_attempt = UUID(str(value["attempt_id"]), version=4)
    except ValueError as exc:
        raise CustodyError("projection attempt_id is not UUID4") from exc
    if str(parsed_attempt) != value["attempt_id"]:
        raise CustodyError("projection attempt_id is not canonical UUID4")
    kind = value.get("attempt_kind")
    source = value.get("source_receipt_digest")
    if kind == "original" and source is not None:
        raise CustodyError("original projection source receipt must be null")
    if kind == "replay" and not _is_sha256(source):
        raise CustodyError("replay projection source receipt is invalid")
    if kind not in {"original", "replay"}:
        raise CustodyError("projection attempt kind is invalid")
    candidate = value.get("candidate_coordinate")
    if not isinstance(candidate, Mapping) or set(candidate) != {
        "source_manifest_digest",
        "candidate_receipt_digest",
    }:
        raise CustodyError("candidate coordinate is not closed")
    input_coordinate = value.get("input_coordinate")
    if not isinstance(input_coordinate, Mapping) or set(input_coordinate) != {
        "normalized_input_digest",
        "disclosure_posture",
    }:
        raise CustodyError("input coordinate is not closed")
    runtime = value.get("runtime_observation")
    if not isinstance(runtime, Mapping) or set(runtime) != {
        "configured_runtime_digest",
        "configured_provider",
        "configured_model",
        "executed_provider_identity",
        "executed_model_identity",
        "attempt_start_digest",
        "outcome_kind",
    }:
        raise CustodyError("runtime observation is not closed")
    outcome = value.get("outcome_evidence")
    if not isinstance(outcome, Mapping) or set(outcome) != {
        "observation_kind",
        "normalized_return_digest",
        "sanitized_failure_digest",
    }:
        raise CustodyError("outcome evidence is not closed")
    outcome_kind = runtime.get("outcome_kind")
    if outcome.get("observation_kind") != outcome_kind:
        raise CustodyError("projection outcome kinds differ")
    if outcome_kind == "return":
        _require_sha256(outcome.get("normalized_return_digest"), "return digest")
        if outcome.get("sanitized_failure_digest") is not None:
            raise CustodyError("return projection has failure digest")
    elif outcome_kind == "failure":
        _require_sha256(outcome.get("sanitized_failure_digest"), "failure digest")
        if outcome.get("normalized_return_digest") is not None:
            raise CustodyError("failure projection has return digest")
    else:
        raise CustodyError("projection outcome kind is invalid")
    for label in (
        "evaluation_request_digest",
        "episode_evidence_manifest_digest",
        "receipt_digest",
        "state_trace_digest",
    ):
        _require_sha256(value.get(label), label)
    for label in candidate:
        _require_sha256(candidate[label], label)
    _require_sha256(input_coordinate.get("normalized_input_digest"), "input digest")
    if input_coordinate.get("disclosure_posture") != "digest_only_no_raw_access_right":
        raise CustodyError("projection disclosure posture is invalid")
    if value.get("effect_inventory_version") != EFFECT_INVENTORY_VERSION:
        raise CustodyError("projection effect inventory is invalid")
    if (
        runtime.get("executed_provider_identity") is not None
        or runtime.get("executed_model_identity") is not None
    ):
        raise CustodyError("executed identity must be null")
    _require_sha256(runtime.get("configured_runtime_digest"), "runtime digest")
    _configured_label(runtime.get("configured_provider"), "configured_provider")
    _configured_label(runtime.get("configured_model"), "configured_model")
    _require_sha256(runtime.get("attempt_start_digest"), "start digest")
    non_authority = value.get("non_authority")
    if (
        not isinstance(non_authority, Mapping)
        or set(non_authority) != set(NON_AUTHORITY)
        or any(non_authority[key] is not False for key in NON_AUTHORITY)
    ):
        raise CustodyError("projection non-authority claims are invalid")


class ExecutionCustodyStore:
    """Owner-local unactivated Decision 105 attempt store."""

    def __init__(
        self,
        root: Path,
        *,
        fault_barrier: FaultBarrier | None = None,
        _expected_binding: tuple[int, int, int, int] | None = None,
    ):
        self.root = _reject_symlink_components(root, "store")
        _validate_owned_store_chain(self.root)
        _reject_network_filesystem(self.root)
        self.db_path = self.root / "custody.sqlite3"
        self._fault_barrier = fault_barrier
        self._parent_fd = -1
        self._root_fd = -1
        self._db_fd = -1
        self._closed = False
        self._execution_lock_depth = 0
        self._callable_active = False
        connection: sqlite3.Connection | None = None
        try:
            parent, self._parent_fd = _open_directory_chain(
                self.root.parent, "store parent"
            )
            self.root = parent / self.root.name
            self.db_path = self.root / "custody.sqlite3"
            self._root_fd = os.open(
                self.root.name, _DIRECTORY_FLAGS, dir_fd=self._parent_fd
            )
            self._db_fd = os.open("custody.sqlite3", _FILE_FLAGS, dir_fd=self._root_fd)
            if _expected_binding is not None:
                root_binding = os.fstat(self._root_fd)
                database_binding = os.fstat(self._db_fd)
                actual_binding = (
                    root_binding.st_dev,
                    root_binding.st_ino,
                    database_binding.st_dev,
                    database_binding.st_ino,
                )
                if actual_binding != _expected_binding:
                    raise CustodyError("created store binding changed before reopen")
            self._verify_store()
            journal_state = self._verify_preopen_sidecars()
            descriptor_path = _sqlite_descriptor_path(self._db_fd)
            immutable_option = "&immutable=1"
            preflight = sqlite3.connect(
                f"file:{descriptor_path}?mode=ro{immutable_option}",
                timeout=10,
                isolation_level=None,
                uri=True,
            )
            try:
                preflight.row_factory = sqlite3.Row
                preflight.execute("PRAGMA foreign_keys=ON")
                self._verify_schema_connection(
                    preflight,
                    require_durability_configuration=False,
                    require_integrity_checks=journal_state != "hot",
                )
            finally:
                preflight.close()
            connection = sqlite3.connect(
                descriptor_path, timeout=10, isolation_level=None
            )
            connection.row_factory = sqlite3.Row
            self._connection = connection
            self._configure()
            try:
                self._connection.execute("BEGIN EXCLUSIVE")
                self._remove_cold_rollback_journal()
                self._connection.execute("COMMIT")
            except BaseException:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise
            self._verify_schema()
            self._verify_store()
            self._reject_clean_sidecars()
        except BaseException:
            if connection is not None:
                connection.close()
            for descriptor in (self._db_fd, self._root_fd, self._parent_fd):
                if descriptor >= 0:
                    os.close(descriptor)
            raise

    @classmethod
    def create(
        cls,
        parent: Path,
        *,
        name: str = "semantic-evaluation-custody-v1",
        fault_barrier: FaultBarrier | None = None,
    ) -> ExecutionCustodyStore:
        parent = _reject_symlink_components(parent, "store parent")
        _validate_owned_store_chain(parent)
        _reject_network_filesystem(parent)
        if not name or name in {".", ".."} or Path(name).name != name:
            raise CustodyError("store name must be one path component")
        parent_path, parent_fd = _open_directory_chain(parent, "store parent")
        root_fd = -1
        descriptor = -1
        try:
            info = os.fstat(parent_fd)
            _reject_network_descriptor(parent_fd, "store parent")
            path_info = os.stat(parent_path, follow_symlinks=False)
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid():
                raise CustodyError("store parent must be an owner directory")
            if stat.S_IMODE(info.st_mode) & 0o077:
                raise CustodyError("store parent must not be group/world accessible")
            if (info.st_dev, info.st_ino) != (path_info.st_dev, path_info.st_ino):
                raise CustodyError("store parent descriptor/path binding changed")
            os.mkdir(name, 0o700, dir_fd=parent_fd)
            root_fd = os.open(name, _DIRECTORY_FLAGS, dir_fd=parent_fd)
            root_info = os.fstat(root_fd)
            _reject_network_descriptor(root_fd, "new store directory")
            root_path_info = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if (root_info.st_dev, root_info.st_ino) != (
                root_path_info.st_dev,
                root_path_info.st_ino,
            ):
                raise CustodyError("new store descriptor/path binding changed")
            descriptor = os.open(
                "custody.sqlite3",
                os.O_CREAT
                | os.O_EXCL
                | os.O_WRONLY
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                0o600,
                dir_fd=root_fd,
            )
            db_info = os.fstat(descriptor)
            _reject_network_descriptor(descriptor, "new store database")
            db_path_info = os.stat(
                "custody.sqlite3", dir_fd=root_fd, follow_symlinks=False
            )
            if (db_info.st_dev, db_info.st_ino) != (
                db_path_info.st_dev,
                db_path_info.st_ino,
            ):
                raise CustodyError("new database descriptor/path binding changed")
            connection = sqlite3.connect(
                _sqlite_descriptor_path(descriptor), isolation_level=None
            )
            try:
                _initialize_schema(connection)
            finally:
                connection.close()
            final_db_info = os.stat(
                "custody.sqlite3", dir_fd=root_fd, follow_symlinks=False
            )
            if (db_info.st_dev, db_info.st_ino) != (
                final_db_info.st_dev,
                final_db_info.st_ino,
            ):
                raise CustodyError("database binding changed during schema creation")
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if root_fd >= 0:
                os.close(root_fd)
            os.close(parent_fd)
        return cls(
            parent_path / name,
            fault_barrier=fault_barrier,
            _expected_binding=(
                root_info.st_dev,
                root_info.st_ino,
                db_info.st_dev,
                db_info.st_ino,
            ),
        )

    @classmethod
    def open(
        cls, root: Path, *, fault_barrier: FaultBarrier | None = None
    ) -> ExecutionCustodyStore:
        return cls(
            _reject_symlink_components(root, "store"), fault_barrier=fault_barrier
        )

    def close(self) -> None:
        if self._closed:
            return
        if self._callable_active or self._execution_lock_depth:
            raise CustodyError("cannot close while attempt execution is active")
        self._closed = True
        error: CustodyError | None = None
        try:
            self._connection.close()
            try:
                self._verify_quiescent_clean_close()
            except CustodyError as exc:
                error = exc
        finally:
            for descriptor in (self._db_fd, self._root_fd, self._parent_fd):
                if descriptor >= 0:
                    os.close(descriptor)
        if error is not None:
            raise error

    def __enter__(self) -> ExecutionCustodyStore:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _verify_store(self) -> None:
        parent = os.fstat(self._parent_fd)
        parent_path = os.stat(self.root.parent, follow_symlinks=False)
        root = os.fstat(self._root_fd)
        root_path = os.stat(
            self.root.name, dir_fd=self._parent_fd, follow_symlinks=False
        )
        db = os.fstat(self._db_fd)
        db_path = os.stat(
            "custody.sqlite3", dir_fd=self._root_fd, follow_symlinks=False
        )
        _reject_network_descriptor(self._parent_fd, "store parent")
        _reject_network_descriptor(self._root_fd, "store directory")
        _reject_network_descriptor(self._db_fd, "store database")
        if (parent.st_dev, parent.st_ino) != (parent_path.st_dev, parent_path.st_ino):
            raise CustodyError("store parent descriptor/path binding changed")
        if (root.st_dev, root.st_ino) != (root_path.st_dev, root_path.st_ino):
            raise CustodyError("store directory descriptor/path binding changed")
        if (db.st_dev, db.st_ino) != (db_path.st_dev, db_path.st_ino):
            raise CustodyError("store database descriptor/path binding changed")
        if not stat.S_ISDIR(root.st_mode) or stat.S_IMODE(root.st_mode) != 0o700:
            raise CustodyError("store directory must be mode 0700")
        if root.st_uid != os.geteuid():
            raise CustodyError("store directory owner is invalid")
        if not stat.S_ISREG(db.st_mode) or stat.S_IMODE(db.st_mode) != 0o600:
            raise CustodyError("store database must be a mode-0600 regular file")
        if db.st_uid != os.geteuid() or db.st_nlink != 1:
            raise CustodyError("store database owner/link count is invalid")
        _validate_owned_store_chain(self.root)
        _reject_network_filesystem(self.root)

    def _reject_clean_sidecars(self) -> None:
        self._verify_preopen_sidecars()

    def _verify_preopen_sidecars(self) -> Literal["absent", "cold", "hot"]:
        for suffix in ("-wal", "-shm"):
            try:
                os.stat(
                    f"custody.sqlite3{suffix}",
                    dir_fd=self._root_fd,
                    follow_symlinks=False,
                )
            except FileNotFoundError:
                continue
            raise CustodyError(
                "unexpected SQLite sidecar (WAL/SHM) exists before validation"
            )
        try:
            journal_fd = os.open(
                "custody.sqlite3-journal", _FILE_FLAGS, dir_fd=self._root_fd
            )
        except FileNotFoundError:
            return "absent"
        try:
            journal = os.fstat(journal_fd)
            _reject_network_descriptor(journal_fd, "SQLite rollback journal")
            header = os.read(journal_fd, 8)
            journal_path = os.stat(
                "custody.sqlite3-journal",
                dir_fd=self._root_fd,
                follow_symlinks=False,
            )
            if (
                not stat.S_ISREG(journal.st_mode)
                or journal.st_uid != os.geteuid()
                or stat.S_IMODE(journal.st_mode) != 0o600
                or journal.st_nlink != 1
                or (journal.st_dev, journal.st_ino)
                != (journal_path.st_dev, journal_path.st_ino)
            ):
                raise CustodyError("preopen SQLite rollback journal is unsafe")
        finally:
            os.close(journal_fd)
        if header == b"\xd9\xd5\x05\xf9\x20\xa1\x63\xd7":
            return "hot"
        if header == b"\x00" * 8:
            return "cold"
        raise CustodyError("SQLite rollback journal header is invalid")

    def _remove_cold_rollback_journal(self) -> None:
        try:
            journal_fd = os.open(
                "custody.sqlite3-journal", _FILE_FLAGS, dir_fd=self._root_fd
            )
        except FileNotFoundError:
            return
        try:
            journal = os.fstat(journal_fd)
            _reject_network_descriptor(journal_fd, "cold SQLite rollback journal")
            path_info = os.stat(
                "custody.sqlite3-journal",
                dir_fd=self._root_fd,
                follow_symlinks=False,
            )
            header = os.read(journal_fd, 8)
            if (
                (journal.st_dev, journal.st_ino) != (path_info.st_dev, path_info.st_ino)
                or journal.st_uid != os.geteuid()
                or stat.S_IMODE(journal.st_mode) != 0o600
                or journal.st_nlink != 1
            ):
                raise CustodyError("cold SQLite rollback journal binding is unsafe")
        finally:
            os.close(journal_fd)
        if header == b"\x00" * 8:
            os.unlink("custody.sqlite3-journal", dir_fd=self._root_fd)
            os.fsync(self._root_fd)

    def _verify_quiescent_clean_close(self) -> None:
        try:
            journal_fd = os.open(
                "custody.sqlite3-journal", _FILE_FLAGS, dir_fd=self._root_fd
            )
        except FileNotFoundError:
            journal_fd = -1
        if journal_fd >= 0:
            try:
                _reject_network_descriptor(journal_fd, "clean-close rollback journal")
                header = os.read(journal_fd, 8)
            finally:
                os.close(journal_fd)
            if header != b"\xd9\xd5\x05\xf9\x20\xa1\x63\xd7":
                raise CustodyError(
                    "unexpected SQLite sidecar remains after clean close"
                )
        probe = sqlite3.connect(
            _sqlite_descriptor_path(self._db_fd), timeout=0, isolation_level=None
        )
        exclusive = False
        try:
            try:
                probe.execute("BEGIN EXCLUSIVE")
                exclusive = True
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc).lower():
                    raise CustodyError("clean-close SQLite probe failed") from exc
                return
            for suffix in ("-journal", "-wal", "-shm"):
                try:
                    os.stat(
                        f"custody.sqlite3{suffix}",
                        dir_fd=self._root_fd,
                        follow_symlinks=False,
                    )
                except FileNotFoundError:
                    continue
                raise CustodyError(
                    "unexpected SQLite sidecar remains after clean close"
                )
            probe.execute("ROLLBACK")
            exclusive = False
        finally:
            if exclusive and probe.in_transaction:
                probe.execute("ROLLBACK")
            probe.close()

    def _configure(self) -> None:
        self._connection.execute("PRAGMA foreign_keys=ON")
        mode = self._connection.execute("PRAGMA journal_mode=DELETE").fetchone()[0]
        if str(mode).lower() != "delete":
            raise CustodyError("SQLite DELETE journal mode is required")
        self._connection.execute("PRAGMA synchronous=FULL")

    def _verify_schema_connection(
        self,
        connection: sqlite3.Connection,
        *,
        require_durability_configuration: bool,
        require_integrity_checks: bool = True,
    ) -> None:
        try:
            meta = connection.execute(
                "SELECT key, value FROM meta ORDER BY key"
            ).fetchall()
            actual_schema = _schema_objects(connection)
            integrity = (
                connection.execute("PRAGMA integrity_check").fetchall()
                if require_integrity_checks
                else []
            )
            foreign_keys = (
                connection.execute("PRAGMA foreign_key_check").fetchall()
                if require_integrity_checks
                else []
            )
            foreign_keys_enabled = connection.execute("PRAGMA foreign_keys").fetchone()[
                0
            ]
            journal_mode = str(
                connection.execute("PRAGMA journal_mode").fetchone()[0]
            ).lower()
            synchronous = connection.execute("PRAGMA synchronous").fetchone()[0]
            database_list = connection.execute("PRAGMA database_list").fetchall()
        except sqlite3.DatabaseError as exc:
            raise CustodyError(
                "custody store schema or integrity verification failed"
            ) from exc
        if [(row[0], row[1]) for row in meta] != [("schema_version", SCHEMA_VERSION)]:
            raise CustodyError("unknown custody store schema")
        if actual_schema != _expected_schema_objects():
            raise CustodyError("custody store schema objects differ from exact v1")
        if require_integrity_checks:
            if len(integrity) != 1 or integrity[0][0] != "ok":
                raise CustodyError("custody store integrity check failed")
            if foreign_keys:
                raise CustodyError("custody store foreign-key check failed")
        if foreign_keys_enabled != 1:
            raise CustodyError("custody store foreign-key enforcement is disabled")
        if require_durability_configuration and (
            journal_mode != "delete" or synchronous != 2
        ):
            raise CustodyError(
                "custody store SQLite durability configuration is invalid"
            )
        main_databases = [row for row in database_list if row[1] == "main"]
        unexpected_databases = [
            row
            for row in database_list
            if row[1] not in {"main", "temp"} or (row[1] == "temp" and row[2])
        ]
        if len(main_databases) != 1 or unexpected_databases:
            raise CustodyError("SQLite has an unexpected attached database")
        try:
            sqlite_database = os.stat(main_databases[0][2], follow_symlinks=False)
        except OSError as exc:
            raise CustodyError("SQLite main database path is unavailable") from exc
        verified_database = os.fstat(self._db_fd)
        if (sqlite_database.st_dev, sqlite_database.st_ino) != (
            verified_database.st_dev,
            verified_database.st_ino,
        ):
            raise CustodyError("SQLite main database inode binding is invalid")

    def _verify_schema(self) -> None:
        self._verify_schema_connection(
            self._connection, require_durability_configuration=True
        )

    def _barrier(self, operation: str, phase: str) -> None:
        if self._fault_barrier is not None:
            self._fault_barrier(operation, phase)

    def _acquire_execution_lock(self) -> bool:
        if self._execution_lock_depth:
            self._execution_lock_depth += 1
            return True
        try:
            fcntl.flock(self._db_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        except OSError as exc:
            raise CustodyError("attempt execution lock failed") from exc
        self._execution_lock_depth = 1
        return True

    def _release_execution_lock(self) -> None:
        if self._execution_lock_depth <= 0:
            raise CustodyError("attempt execution lock is not held")
        self._execution_lock_depth -= 1
        if self._execution_lock_depth == 0:
            fcntl.flock(self._db_fd, fcntl.LOCK_UN)

    def _execution_transaction(
        self, operation: str, work: Callable[[sqlite3.Connection], Any]
    ) -> Any:
        if self._callable_active:
            raise CustodyError("active callable cannot mutate custody state")
        if not self._acquire_execution_lock():
            raise CustodyError("attempt execution is still active")
        try:
            return self._transaction(operation, work)
        finally:
            self._release_execution_lock()

    def _transaction(
        self, operation: str, work: Callable[[sqlite3.Connection], Any]
    ) -> Any:
        self._verify_store()
        self._reject_clean_sidecars()
        self._verify_schema()
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            result = work(self._connection)
            self._barrier(operation, "before_commit")
            self._connection.execute("COMMIT")
        except BaseException:
            if self._connection.in_transaction:
                self._connection.execute("ROLLBACK")
            raise
        self._verify_store()
        self._reject_clean_sidecars()
        self._verify_schema()
        self._barrier(operation, "after_commit")
        return result

    def _existing_operation(
        self, connection: sqlite3.Connection, operation_id: str, kind: str, digest: str
    ) -> dict[str, Any] | None:
        if not operation_id:
            raise CustodyError("operation_id is required")
        row = connection.execute(
            "SELECT operation_kind, request_digest, subject_kind, subject_id, result_json, result_digest FROM operations WHERE operation_id=?",
            (operation_id,),
        ).fetchone()
        if row is None:
            return None
        if row["operation_kind"] != kind or row["request_digest"] != digest:
            raise CustodyError("operation ID reuse differs from committed operation")
        result_bytes = row["result_json"].encode("utf-8")
        try:
            result = json.loads(result_bytes)
        except json.JSONDecodeError as exc:
            raise CustodyError("committed operation result is invalid JSON") from exc
        if (
            not isinstance(result, dict)
            or canonical_json_bytes(result) != result_bytes
            or _sha256(result_bytes) != row["result_digest"]
        ):
            raise CustodyError("committed operation result binding is invalid")
        if "attempt_id" in result:
            subject_kind = "attempt"
            subject_id = result["attempt_id"]
        elif "rejection_id" in result:
            subject_kind = "rejection"
            subject_id = result["rejection_id"]
        else:
            raise CustodyError("committed operation result has no subject identity")
        if row["subject_kind"] != subject_kind or row["subject_id"] != subject_id:
            raise CustodyError("committed operation subject binding is invalid")
        return result

    def _record_operation(
        self,
        connection: sqlite3.Connection,
        operation_id: str,
        kind: str,
        digest: str,
        result: Mapping[str, Any],
    ) -> None:
        if not operation_id:
            raise CustodyError("operation_id is required")
        result_value = dict(result)
        if "attempt_id" in result_value:
            subject_kind = "attempt"
            subject_id = result_value["attempt_id"]
        elif "rejection_id" in result_value:
            subject_kind = "rejection"
            subject_id = result_value["rejection_id"]
        else:
            raise CustodyError("operation result has no subject identity")
        if not isinstance(subject_id, str) or not subject_id:
            raise CustodyError("operation subject identity is invalid")
        result_bytes = canonical_json_bytes(result_value)
        connection.execute(
            "INSERT INTO operations(operation_id, operation_kind, request_digest, subject_kind, subject_id, result_json, result_digest) VALUES(?,?,?,?,?,?,?)",
            (
                operation_id,
                kind,
                digest,
                subject_kind,
                subject_id,
                result_bytes.decode(),
                _sha256(result_bytes),
            ),
        )

    def _event(
        self,
        connection: sqlite3.Connection,
        *,
        attempt_id: str,
        operation: str,
        from_state: str,
        to_state: str,
        operation_digest: str,
    ) -> dict[str, Any]:
        sequence = connection.execute(
            "SELECT COUNT(*) FROM events WHERE attempt_id=?", (attempt_id,)
        ).fetchone()[0]
        payload = {
            "sequence": sequence,
            "operation": operation,
            "from_state": from_state,
            "to_state": to_state,
            "operation_digest": operation_digest,
        }
        event_digest = _sha256(canonical_json_bytes(payload))
        payload["event_digest"] = event_digest
        connection.execute(
            "INSERT INTO events(attempt_id, sequence, operation, from_state, to_state, operation_digest, event_digest, event_json) VALUES(?,?,?,?,?,?,?,?)",
            (
                attempt_id,
                sequence,
                operation,
                from_state,
                to_state,
                operation_digest,
                event_digest,
                canonical_json_bytes(payload).decode(),
            ),
        )
        return payload

    def _material(
        self, request: AttemptRequest, material: AllocationMaterial
    ) -> tuple[dict[str, Any], bytes, dict[str, str]]:
        request_payload = _request_payload(request)
        manifest_path, manifest = _read_stable_regular(
            material.candidate_manifest_path, "candidate manifest"
        )
        receipt_path, receipt = _read_stable_regular(
            material.candidate_receipt_path, "candidate receipt"
        )
        input_path, input_bytes = _read_stable_regular(
            material.input_source_path, "input source"
        )
        _canonical_input_bytes(input_bytes)
        if _sha256(manifest) != request.source_manifest_digest:
            raise CustodyError("candidate manifest coordinate mismatch")
        if _sha256(receipt) != request.candidate_receipt_digest:
            raise CustodyError("candidate receipt coordinate mismatch")
        if _sha256(input_bytes) != request.normalized_input_digest:
            raise CustodyError("input coordinate mismatch")
        _disjoint(
            self.root, manifest_path.parent, manifest_path, receipt_path, input_path
        )
        paths = {
            "candidate_manifest_path_digest": _path_digest(manifest_path),
            "candidate_receipt_path_digest": _path_digest(receipt_path),
            "input_source_path_digest": _path_digest(input_path),
        }
        return request_payload, input_bytes, paths

    def _verified_rejection_record(
        self,
        connection: sqlite3.Connection,
        rejection_id: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        row = connection.execute(
            "SELECT terminal_json, terminal_digest FROM terminal_nonseals WHERE terminal_id=? AND attempt_id IS NULL",
            (rejection_id,),
        ).fetchone()
        if row is None:
            raise CustodyError("rejection terminal evidence is missing")
        terminal_bytes = row["terminal_json"].encode("utf-8")
        terminal = self._decode_mapping(terminal_bytes, "rejection terminal")
        expected = {
            "rejection_id": rejection_id,
            "state": "rejected",
            "terminal_reason": "validation_failed",
            "attempt_request_digest": payload["attempt_request_digest"],
            "evaluation_request_digest": payload["evaluation_request_digest"],
            "validation_error_digest": payload["validation_error_digest"],
            "dspx_validation_failed": True,
            "attempt_allocated": False,
            "attempt_start_present": False,
            "projection_available": False,
        }
        if (
            terminal != expected
            or terminal_bytes != canonical_json_bytes(expected)
            or _sha256(terminal_bytes) != row["terminal_digest"]
        ):
            raise CustodyError("rejection terminal evidence binding is invalid")
        return terminal

    def reject_request(
        self,
        operation_id: str,
        request: AttemptRequest,
        material: AllocationMaterial | None = None,
        *,
        rejection_id_factory: Callable[[], Any] = uuid4,
    ) -> RejectionDisposition:
        if self._callable_active:
            raise CustodyError("active callable cannot reject another request")
        try:
            _request_payload(request)
            if material is not None:
                self._material(request, material)
        except CustodyError as validation_error:
            error_digest = _sha256(
                canonical_json_bytes(
                    {
                        "type": type(validation_error).__name__,
                        "message": str(validation_error),
                    }
                )
            )
        else:
            raise CustodyError(
                "reject_request requires a DSPx-observed validation failure"
            )
        raw_request = {
            key: _invalid_value_fingerprint(value)
            for key, value in request.__dict__.items()
        }
        raw_material = (
            None
            if material is None
            else {
                key: _invalid_value_fingerprint(value)
                for key, value in material.__dict__.items()
            }
        )
        payload = {
            "attempt_request_digest": _sha256(canonical_json_bytes(raw_request)),
            "allocation_material_digest": _sha256(canonical_json_bytes(raw_material))
            if raw_material is not None
            else None,
            "evaluation_request_digest": request.evaluation_request_digest
            if _is_sha256(request.evaluation_request_digest)
            else None,
            "validation_error_digest": error_digest,
        }
        digest = _sha256(canonical_json_bytes(payload))

        def work(connection: sqlite3.Connection) -> RejectionDisposition:
            existing = self._existing_operation(
                connection, operation_id, "reject_request", digest
            )
            if existing is not None:
                result = RejectionDisposition(**existing)
                self._verified_rejection_record(
                    connection, result.rejection_id, payload
                )
                return result
            if payload["evaluation_request_digest"] is not None:
                for row in connection.execute("SELECT request_json FROM attempts"):
                    if (
                        json.loads(row[0]).get("evaluation_request_digest")
                        == payload["evaluation_request_digest"]
                    ):
                        raise CustodyError(
                            "cannot reject a request with an allocated attempt"
                        )
            rejection_id = str(rejection_id_factory())
            try:
                parsed = UUID(rejection_id, version=4)
            except ValueError as exc:
                raise CustodyError("rejection ID factory must return UUID4") from exc
            if str(parsed) != rejection_id:
                raise CustodyError("rejection ID must use canonical UUID text")
            terminal = {
                "rejection_id": rejection_id,
                "state": "rejected",
                "terminal_reason": "validation_failed",
                "attempt_request_digest": payload["attempt_request_digest"],
                "evaluation_request_digest": payload["evaluation_request_digest"],
                "validation_error_digest": error_digest,
                "dspx_validation_failed": True,
                "attempt_allocated": False,
                "attempt_start_present": False,
                "projection_available": False,
            }
            terminal_bytes = canonical_json_bytes(terminal)
            connection.execute(
                "INSERT INTO terminal_nonseals(terminal_id, attempt_id, terminal_json, terminal_digest) VALUES(?,NULL,?,?)",
                (rejection_id, terminal_bytes.decode(), _sha256(terminal_bytes)),
            )
            result = RejectionDisposition(rejection_id, "rejected", "validation_failed")
            self._record_operation(
                connection, operation_id, "reject_request", digest, result.__dict__
            )
            return result

        return self._execution_transaction("reject_request", work)

    def allocate_attempt(
        self,
        operation_id: str,
        request: AttemptRequest,
        material: AllocationMaterial,
        *,
        attempt_id_factory: Callable[[], Any] = uuid4,
    ) -> AttemptDisposition:
        payload, input_bytes, paths = self._material(request, material)
        if self._callable_active:
            raise CustodyError("active callable cannot allocate another attempt")
        operation_digest = _sha256(
            canonical_json_bytes({"request": payload, "paths": paths})
        )

        def work(connection: sqlite3.Connection) -> AttemptDisposition:
            existing = self._existing_operation(
                connection, operation_id, "allocate_episode", operation_digest
            )
            if existing is not None:
                return AttemptDisposition(**existing)
            attempt_id = str(attempt_id_factory())
            try:
                parsed = UUID(attempt_id, version=4)
            except ValueError as exc:
                raise CustodyError("attempt ID factory must return UUID4") from exc
            if str(parsed) != attempt_id:
                raise CustodyError("attempt ID must use canonical UUID text")
            connection.execute(
                "INSERT INTO attempts(attempt_id, request_json, request_digest, path_digests_json, state, terminal_reason) VALUES(?,?,?,?,?,NULL)",
                (
                    attempt_id,
                    canonical_json_bytes(payload).decode(),
                    _sha256(canonical_json_bytes(payload)),
                    canonical_json_bytes(paths).decode(),
                    "allocated",
                ),
            )
            connection.execute(
                "INSERT INTO input_snapshots(attempt_id, snapshot, snapshot_digest) VALUES(?,?,?)",
                (attempt_id, input_bytes, _sha256(input_bytes)),
            )
            self._event(
                connection,
                attempt_id=attempt_id,
                operation="allocate_episode",
                from_state="requested",
                to_state="allocated",
                operation_digest=operation_digest,
            )
            result = AttemptDisposition(attempt_id, "allocated", None)
            self._record_operation(
                connection,
                operation_id,
                "allocate_episode",
                operation_digest,
                result.__dict__,
            )
            return result

        return self._execution_transaction("allocate_episode", work)

    def _attempt(self, connection: sqlite3.Connection, attempt_id: str) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)
        ).fetchone()
        if row is None:
            raise CustodyError("attempt does not exist")
        return row

    def _simple_terminal(
        self,
        operation_id: str,
        attempt_id: str,
        *,
        operation: str,
        expected: str,
        state: str,
        reason: str,
    ) -> AttemptDisposition:
        digest = _sha256(
            canonical_json_bytes(
                {"attempt_id": attempt_id, "operation": operation, "reason": reason}
            )
        )

        def work(connection: sqlite3.Connection) -> AttemptDisposition:
            existing = self._existing_operation(
                connection, operation_id, operation, digest
            )
            if existing is not None:
                result = AttemptDisposition(**existing)
                self._verified_terminal_record(connection, attempt_id)
                if result != AttemptDisposition(attempt_id, state, reason):
                    raise CustodyError(
                        "terminal operation result differs from terminal state"
                    )
                return result
            row = self._attempt(connection, attempt_id)
            if row["state"] != expected:
                raise CustodyError(f"{operation} requires state {expected}")
            prefix = (
                ("allocate_episode",)
                if expected == "allocated"
                else ("allocate_episode", "start_attempt")
            )
            self._verified_history(connection, row, prefix)
            if (
                connection.execute(
                    "SELECT 1 FROM terminal_seals WHERE attempt_id=? UNION ALL SELECT 1 FROM terminal_nonseals WHERE attempt_id=?",
                    (attempt_id, attempt_id),
                ).fetchone()
                is not None
            ):
                raise CustodyError("terminal evidence already exists")
            event = self._event(
                connection,
                attempt_id=attempt_id,
                operation=operation,
                from_state=expected,
                to_state=state,
                operation_digest=digest,
            )
            terminal = {
                "attempt_id": attempt_id,
                "state": state,
                "terminal_reason": reason,
                "event_digest": event["event_digest"],
                "projection_available": False,
            }
            terminal_bytes = canonical_json_bytes(terminal)
            connection.execute(
                "INSERT INTO terminal_nonseals(terminal_id, attempt_id, terminal_json, terminal_digest) VALUES(?,?,?,?)",
                (
                    attempt_id,
                    attempt_id,
                    terminal_bytes.decode(),
                    _sha256(terminal_bytes),
                ),
            )
            connection.execute(
                "UPDATE attempts SET state=?, terminal_reason=? WHERE attempt_id=?",
                (state, reason, attempt_id),
            )
            result = AttemptDisposition(attempt_id, state, reason)
            self._record_operation(
                connection, operation_id, operation, digest, result.__dict__
            )
            return result

        return self._execution_transaction(operation, work)

    def cancel_before_attempt(
        self, operation_id: str, attempt_id: str
    ) -> AttemptDisposition:
        return self._simple_terminal(
            operation_id,
            attempt_id,
            operation="cancel_before_attempt",
            expected="allocated",
            state="closed",
            reason="cancelled_before_attempt",
        )

    def recover_unstarted_allocation(
        self, operation_id: str, attempt_id: str
    ) -> AttemptDisposition:
        return self._simple_terminal(
            operation_id,
            attempt_id,
            operation="recover_unstarted_allocation",
            expected="allocated",
            state="closed",
            reason="recovered_unstarted",
        )

    def recover_unknown_attempt(
        self, operation_id: str, attempt_id: str
    ) -> AttemptDisposition:
        return self._simple_terminal(
            operation_id,
            attempt_id,
            operation="recover_unknown_attempt",
            expected="attempting",
            state="indeterminate",
            reason="unknown_after_start",
        )

    def recover_unsealed_outcome(
        self, operation_id: str, attempt_id: str
    ) -> AttemptDisposition:
        operation = "recover_unsealed_outcome"
        digest = _sha256(
            canonical_json_bytes({"attempt_id": attempt_id, "operation": operation})
        )

        def work(connection: sqlite3.Connection) -> AttemptDisposition:
            existing = self._existing_operation(
                connection, operation_id, operation, digest
            )
            if existing is not None:
                result = AttemptDisposition(**existing)
                self._verified_terminal_record(connection, attempt_id)
                return result
            row = self._attempt(connection, attempt_id)
            if row["state"] != "outcome_observed":
                raise CustodyError("recover_unsealed_outcome requires outcome_observed")
            if (
                connection.execute(
                    "SELECT 1 FROM terminal_seals WHERE attempt_id=? UNION ALL SELECT 1 FROM terminal_nonseals WHERE attempt_id=?",
                    (attempt_id, attempt_id),
                ).fetchone()
                is not None
            ):
                raise CustodyError("evidence seal or terminal record already exists")
            try:
                self._verified_observed_state(connection, row)
            except CustodyError as seal_error:
                seal_failure_digest = self._seal_failure_digest(
                    connection, row, seal_error
                )
            else:
                raise CustodyError(
                    "valid seal remains constructible; use seal_and_close without reinvocation"
                )
            outcome_events = connection.execute(
                "SELECT COUNT(*) FROM events WHERE attempt_id=? AND operation IN ('observe_return','observe_failure')",
                (attempt_id,),
            ).fetchone()[0]
            if (
                outcome_events != 1
                or row["outcome_kind"] not in {"return", "failure"}
                or not _is_sha256(row["outcome_digest"])
            ):
                raise CustodyError(
                    "recovery requires exactly one durable outcome observation"
                )
            event = self._event(
                connection,
                attempt_id=attempt_id,
                operation=operation,
                from_state="outcome_observed",
                to_state="indeterminate",
                operation_digest=digest,
            )
            terminal = {
                "attempt_id": attempt_id,
                "state": "indeterminate",
                "terminal_reason": "unsealed_outcome",
                "event_digest": event["event_digest"],
                "seal_failure_digest": seal_failure_digest,
                "projection_available": False,
            }
            terminal_bytes = canonical_json_bytes(terminal)
            connection.execute(
                "INSERT INTO terminal_nonseals(terminal_id, attempt_id, terminal_json, terminal_digest) VALUES(?,?,?,?)",
                (
                    attempt_id,
                    attempt_id,
                    terminal_bytes.decode(),
                    _sha256(terminal_bytes),
                ),
            )
            connection.execute(
                "UPDATE attempts SET state='indeterminate', terminal_reason='unsealed_outcome' WHERE attempt_id=?",
                (attempt_id,),
            )
            result = AttemptDisposition(attempt_id, "indeterminate", "unsealed_outcome")
            self._record_operation(
                connection, operation_id, operation, digest, result.__dict__
            )
            return result

        return self._execution_transaction(operation, work)

    def _start_attempt(
        self,
        operation_id: str,
        attempt_id: str,
        material: AllocationMaterial,
    ) -> SnapshotView | None:
        row = self._connection.execute(
            "SELECT request_json, path_digests_json, state, terminal_reason FROM attempts WHERE attempt_id=?",
            (attempt_id,),
        ).fetchone()
        if row is None:
            raise CustodyError("attempt does not exist")
        if row["state"] != "allocated":
            return None
        request = json.loads(row["request_json"])
        manifest_path, manifest = _read_stable_regular(
            material.candidate_manifest_path, "candidate manifest"
        )
        receipt_path, receipt = _read_stable_regular(
            material.candidate_receipt_path, "candidate receipt"
        )
        input_path, source_input = _read_stable_regular(
            material.input_source_path, "input source"
        )
        paths = {
            "candidate_manifest_path_digest": _path_digest(manifest_path),
            "candidate_receipt_path_digest": _path_digest(receipt_path),
            "input_source_path_digest": _path_digest(input_path),
        }
        if paths != json.loads(row["path_digests_json"]):
            raise CustodyError("source path binding changed before start")
        candidate = request["candidate_coordinate"]
        input_coordinate = request["input_coordinate"]
        if (
            _sha256(manifest) != candidate["source_manifest_digest"]
            or _sha256(receipt) != candidate["candidate_receipt_digest"]
            or _sha256(source_input) != input_coordinate["normalized_input_digest"]
        ):
            raise CustodyError("source content binding changed before start")
        snapshot_row = self._connection.execute(
            "SELECT snapshot, snapshot_digest FROM input_snapshots WHERE attempt_id=?",
            (attempt_id,),
        ).fetchone()
        if (
            snapshot_row is None
            or _sha256(snapshot_row["snapshot"]) != snapshot_row["snapshot_digest"]
        ):
            raise CustodyError("stored input snapshot is invalid")
        if (
            snapshot_row["snapshot_digest"]
            != input_coordinate["normalized_input_digest"]
        ):
            raise CustodyError("stored input snapshot binding changed")
        digest = _sha256(
            canonical_json_bytes(
                {
                    "attempt_id": attempt_id,
                    "request_digest": _sha256(row["request_json"].encode()),
                    "snapshot_digest": snapshot_row["snapshot_digest"],
                }
            )
        )

        def work(connection: sqlite3.Connection) -> SnapshotView | None:
            existing = self._existing_operation(
                connection, operation_id, "start_attempt", digest
            )
            if existing is not None:
                return None
            current = self._attempt(connection, attempt_id)
            if current["state"] != "allocated":
                return None
            self._verified_history(connection, current, ("allocate_episode",))
            current_request = self._decode_mapping(
                current["request_json"], "immutable request"
            )
            current_paths = self._decode_mapping(
                current["path_digests_json"], "source path bindings"
            )
            current_manifest_path, current_manifest = _read_stable_regular(
                material.candidate_manifest_path, "candidate manifest"
            )
            current_receipt_path, current_receipt = _read_stable_regular(
                material.candidate_receipt_path, "candidate receipt"
            )
            current_input_path, current_input = _read_stable_regular(
                material.input_source_path, "input source"
            )
            rebound_paths = {
                "candidate_manifest_path_digest": _path_digest(current_manifest_path),
                "candidate_receipt_path_digest": _path_digest(current_receipt_path),
                "input_source_path_digest": _path_digest(current_input_path),
            }
            current_candidate = current_request["candidate_coordinate"]
            current_input_coordinate = current_request["input_coordinate"]
            if rebound_paths != current_paths or (
                _sha256(current_manifest) != current_candidate["source_manifest_digest"]
                or _sha256(current_receipt)
                != current_candidate["candidate_receipt_digest"]
                or _sha256(current_input)
                != current_input_coordinate["normalized_input_digest"]
            ):
                raise CustodyError("source binding changed during start transaction")
            current_snapshot = connection.execute(
                "SELECT snapshot, snapshot_digest FROM input_snapshots WHERE attempt_id=?",
                (attempt_id,),
            ).fetchone()
            if (
                current_snapshot is None
                or _sha256(bytes(current_snapshot["snapshot"]))
                != current_snapshot["snapshot_digest"]
                or current_snapshot["snapshot_digest"]
                != current_input_coordinate["normalized_input_digest"]
            ):
                raise CustodyError(
                    "stored input snapshot changed during start transaction"
                )
            event = self._event(
                connection,
                attempt_id=attempt_id,
                operation="start_attempt",
                from_state="allocated",
                to_state="attempting",
                operation_digest=digest,
            )
            connection.execute(
                "UPDATE attempts SET state='attempting' WHERE attempt_id=?",
                (attempt_id,),
            )
            self._record_operation(
                connection,
                operation_id,
                "start_attempt",
                digest,
                {"attempt_id": attempt_id, "event_digest": event["event_digest"]},
            )
            return SnapshotView(
                bytes(current_snapshot["snapshot"]), current_snapshot["snapshot_digest"]
            )

        return self._transaction("start_attempt", work)

    def _observe(
        self,
        operation_id: str,
        attempt_id: str,
        kind: Literal["return", "failure"],
        evidence_digest: str,
    ) -> AttemptDisposition:
        operation = "observe_return" if kind == "return" else "observe_failure"
        digest = _sha256(
            canonical_json_bytes(
                {
                    "attempt_id": attempt_id,
                    "kind": kind,
                    "evidence_digest": evidence_digest,
                }
            )
        )

        def work(connection: sqlite3.Connection) -> AttemptDisposition:
            existing = self._existing_operation(
                connection, operation_id, operation, digest
            )
            if existing is not None:
                return AttemptDisposition(**existing)
            row = self._attempt(connection, attempt_id)
            if row["state"] != "attempting":
                raise CustodyError("outcome observation requires attempting")
            self._event(
                connection,
                attempt_id=attempt_id,
                operation=operation,
                from_state="attempting",
                to_state="outcome_observed",
                operation_digest=digest,
            )
            connection.execute(
                "UPDATE attempts SET state='outcome_observed', outcome_kind=?, outcome_digest=? WHERE attempt_id=?",
                (kind, evidence_digest, attempt_id),
            )
            result = AttemptDisposition(attempt_id, "outcome_observed", None, True)
            self._record_operation(
                connection, operation_id, operation, digest, result.__dict__
            )
            return result

        return self._transaction(operation, work)

    def run_attempt(
        self,
        operation_id: str,
        attempt_id: str,
        material: AllocationMaterial,
        callable_: Callable[[SnapshotView], object],
    ) -> AttemptDisposition:
        if not operation_id:
            raise CustodyError("operation_id is required")
        if self._callable_active:
            raise CustodyError("active callable cannot start another attempt")
        if not self._acquire_execution_lock():
            self._verify_store()
            self._verify_schema()
            row = self._connection.execute(
                "SELECT state, terminal_reason FROM attempts WHERE attempt_id=?",
                (attempt_id,),
            ).fetchone()
            if row is None:
                raise CustodyError("attempt does not exist")
            return AttemptDisposition(
                attempt_id, row["state"], row["terminal_reason"], False
            )
        try:
            start_id = f"{operation_id}:start_attempt"
            snapshot = self._start_attempt(start_id, attempt_id, material)
            if snapshot is None:
                self._verify_store()
                self._verify_schema()
                row = self._connection.execute(
                    "SELECT state, terminal_reason FROM attempts WHERE attempt_id=?",
                    (attempt_id,),
                ).fetchone()
                if row is None:
                    raise CustodyError("attempt does not exist")
                if row["state"] in TERMINAL_STATES:
                    self._verified_terminal(attempt_id)
                return AttemptDisposition(
                    attempt_id, row["state"], row["terminal_reason"], False
                )
            self._barrier("start_attempt", "before_callable")
            callable_failure: Exception | None = None
            self._callable_active = True
            try:
                self._barrier("start_attempt", "during_callable")
                try:
                    returned = callable_(snapshot)
                except Exception as exc:
                    callable_failure = exc
            finally:
                self._callable_active = False
            if callable_failure is None:
                returned_bytes = canonical_json_bytes(returned)
                self._observe(
                    f"{operation_id}:observe_return",
                    attempt_id,
                    "return",
                    _sha256(returned_bytes),
                )
            else:
                failure = {
                    "type": type(callable_failure).__name__,
                    "message": str(callable_failure)[:1000],
                }
                failure_bytes = canonical_json_bytes(failure)
                self._observe(
                    f"{operation_id}:observe_failure",
                    attempt_id,
                    "failure",
                    _sha256(failure_bytes),
                )
            result = self.seal_and_close(f"{operation_id}:seal_and_close", attempt_id)
            return AttemptDisposition(
                result.attempt_id, result.state, result.terminal_reason, True
            )
        finally:
            self._release_execution_lock()

    @staticmethod
    def _decode_mapping(raw: str | bytes, label: str) -> dict[str, Any]:
        encoded = raw.encode("utf-8") if isinstance(raw, str) else bytes(raw)
        try:
            value = json.loads(encoded)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CustodyError(f"{label} is invalid canonical JSON") from exc
        if not isinstance(value, dict) or canonical_json_bytes(value) != encoded:
            raise CustodyError(f"{label} is not an exact canonical object")
        return value

    def _verified_history(
        self,
        connection: sqlite3.Connection,
        row: sqlite3.Row,
        expected_operations: tuple[str, ...],
        *,
        trailing_operations: tuple[str, ...] = (),
    ) -> tuple[dict[str, Any], list[dict[str, Any]], sqlite3.Row]:
        request_bytes = row["request_json"].encode("utf-8")
        request = self._decode_mapping(request_bytes, "immutable request")
        if _sha256(request_bytes) != row["request_digest"]:
            raise CustodyError("immutable request binding failed verification")
        if set(request) != {
            "episode_id",
            "attempt_kind",
            "source_receipt_digest",
            "candidate_coordinate",
            "input_coordinate",
            "evaluation_request_digest",
            "effect_inventory_version",
            "configured_runtime_digest",
            "configured_provider",
            "configured_model",
        }:
            raise CustodyError("immutable request members are not exact")
        candidate = request.get("candidate_coordinate")
        input_coordinate = request.get("input_coordinate")
        if not isinstance(candidate, dict) or set(candidate) != {
            "source_manifest_digest",
            "candidate_receipt_digest",
        }:
            raise CustodyError("stored candidate coordinate is not exact")
        if not isinstance(input_coordinate, dict) or set(input_coordinate) != {
            "normalized_input_digest",
            "disclosure_posture",
        }:
            raise CustodyError("stored input coordinate is not exact")
        validated_request = _request_payload(
            AttemptRequest(
                episode_id=cast(str, request["episode_id"]),
                attempt_kind=cast(
                    Literal["original", "replay"], request["attempt_kind"]
                ),
                source_receipt_digest=cast(
                    str | None, request["source_receipt_digest"]
                ),
                source_manifest_digest=cast(str, candidate["source_manifest_digest"]),
                candidate_receipt_digest=cast(
                    str, candidate["candidate_receipt_digest"]
                ),
                normalized_input_digest=cast(
                    str, input_coordinate["normalized_input_digest"]
                ),
                evaluation_request_digest=cast(
                    str, request["evaluation_request_digest"]
                ),
                configured_runtime_digest=cast(
                    str, request["configured_runtime_digest"]
                ),
                configured_provider=cast(str | None, request["configured_provider"]),
                configured_model=cast(str | None, request["configured_model"]),
                effect_inventory_version=cast(str, request["effect_inventory_version"]),
                disclosure_posture=cast(str, input_coordinate["disclosure_posture"]),
            )
        )
        if validated_request != request:
            raise CustodyError(
                "stored request differs from the closed request contract"
            )
        path_bytes = row["path_digests_json"].encode("utf-8")
        path_digests = self._decode_mapping(path_bytes, "source path bindings")
        if set(path_digests) != {
            "candidate_manifest_path_digest",
            "candidate_receipt_path_digest",
            "input_source_path_digest",
        } or any(not _is_sha256(value) for value in path_digests.values()):
            raise CustodyError("source path bindings failed verification")
        snapshot = connection.execute(
            "SELECT snapshot, snapshot_digest FROM input_snapshots WHERE attempt_id=?",
            (row["attempt_id"],),
        ).fetchone()
        if (
            snapshot is None
            or _sha256(bytes(snapshot["snapshot"])) != snapshot["snapshot_digest"]
            or snapshot["snapshot_digest"]
            != input_coordinate["normalized_input_digest"]
        ):
            raise CustodyError("private input snapshot failed verification")
        event_rows = connection.execute(
            "SELECT * FROM events WHERE attempt_id=? ORDER BY sequence",
            (row["attempt_id"],),
        ).fetchall()
        all_expected_operations = expected_operations + trailing_operations
        if len(event_rows) != len(all_expected_operations):
            raise CustodyError("state trace length differs from the canonical path")
        prefix_event_rows = event_rows[: len(expected_operations)]
        transitions = {
            "allocate_episode": ("requested", "allocated"),
            "cancel_before_attempt": ("allocated", "closed"),
            "recover_unstarted_allocation": ("allocated", "closed"),
            "start_attempt": ("allocated", "attempting"),
            "observe_return": ("attempting", "outcome_observed"),
            "observe_failure": ("attempting", "outcome_observed"),
            "recover_unknown_attempt": ("attempting", "indeterminate"),
            "recover_unsealed_outcome": ("outcome_observed", "indeterminate"),
            "seal_and_close": ("outcome_observed", "closed"),
        }
        events: list[dict[str, Any]] = []
        for sequence, (event_row, expected_operation) in enumerate(
            zip(prefix_event_rows, expected_operations, strict=True)
        ):
            event = self._decode_mapping(event_row["event_json"], "state trace event")
            if set(event) != {
                "sequence",
                "operation",
                "from_state",
                "to_state",
                "operation_digest",
                "event_digest",
            }:
                raise CustodyError("state trace event members are not exact")
            expected_from, expected_to = transitions[expected_operation]
            if (
                event["sequence"] != sequence
                or event["operation"] != expected_operation
                or event["from_state"] != expected_from
                or event["to_state"] != expected_to
                or event_row["attempt_id"] != row["attempt_id"]
                or event_row["sequence"] != sequence
                or event_row["operation"] != expected_operation
                or event_row["from_state"] != expected_from
                or event_row["to_state"] != expected_to
                or event_row["operation_digest"] != event["operation_digest"]
                or event_row["event_digest"] != event["event_digest"]
            ):
                raise CustodyError("state trace row differs from its canonical event")
            preimage = {
                key: value for key, value in event.items() if key != "event_digest"
            }
            if (
                not _is_sha256(event["operation_digest"])
                or _sha256(canonical_json_bytes(preimage)) != event["event_digest"]
            ):
                raise CustodyError("state trace digest is invalid")
            operation_rows = connection.execute(
                "SELECT result_json, result_digest FROM operations WHERE operation_kind=? AND request_digest=? AND subject_kind='attempt' AND subject_id=?",
                (expected_operation, event["operation_digest"], row["attempt_id"]),
            ).fetchall()
            bound = False
            for operation_row in operation_rows:
                result_bytes = operation_row["result_json"].encode("utf-8")
                result = self._decode_mapping(result_bytes, "operation result")
                if _sha256(result_bytes) != operation_row["result_digest"]:
                    raise CustodyError("operation result digest is invalid")
                if result.get("attempt_id") == row["attempt_id"]:
                    bound = True
            if not bound:
                raise CustodyError("state trace operation binding is missing")
            events.append(event)
        expected_state = transitions[all_expected_operations[-1]][1]
        expected_allocation_digest = _sha256(
            canonical_json_bytes({"request": request, "paths": path_digests})
        )
        if (
            not events
            or events[0]["operation"] != "allocate_episode"
            or events[0]["operation_digest"] != expected_allocation_digest
        ):
            raise CustodyError("allocation request and source-path binding is invalid")
        if row["state"] != expected_state:
            raise CustodyError("attempt state differs from its canonical trace")
        if len(events) >= 2 and events[1]["operation"] == "start_attempt":
            expected_start_digest = _sha256(
                canonical_json_bytes(
                    {
                        "attempt_id": row["attempt_id"],
                        "request_digest": row["request_digest"],
                        "snapshot_digest": snapshot["snapshot_digest"],
                    }
                )
            )
            if events[1]["operation_digest"] != expected_start_digest:
                raise CustodyError("attempt-start binding is invalid")
        outcome_events = [
            event
            for event in events
            if event["operation"] in {"observe_return", "observe_failure"}
        ]
        if outcome_events:
            if (
                len(outcome_events) != 1
                or row["outcome_kind"] not in {"return", "failure"}
                or not _is_sha256(row["outcome_digest"])
            ):
                raise CustodyError("observed outcome fields are invalid")
            expected_kind = (
                "return"
                if outcome_events[0]["operation"] == "observe_return"
                else "failure"
            )
            expected_outcome_digest = _sha256(
                canonical_json_bytes(
                    {
                        "attempt_id": row["attempt_id"],
                        "kind": expected_kind,
                        "evidence_digest": row["outcome_digest"],
                    }
                )
            )
            if (
                row["outcome_kind"] != expected_kind
                or outcome_events[0]["operation_digest"] != expected_outcome_digest
            ):
                raise CustodyError("observed outcome binding is invalid")
        elif row["outcome_kind"] is not None or row["outcome_digest"] is not None:
            raise CustodyError("outcome fields exist without an observation")
        return request, events, snapshot

    def _verified_observed_state(
        self, connection: sqlite3.Connection, row: sqlite3.Row
    ) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
        if row["state"] != "outcome_observed":
            raise CustodyError("seal verification requires outcome_observed")
        operation = (
            "observe_return" if row["outcome_kind"] == "return" else "observe_failure"
        )
        request, events, _snapshot = self._verified_history(
            connection,
            row,
            ("allocate_episode", "start_attempt", operation),
        )
        return request, events, events[1], events[2]

    def _seal_failure_digest(
        self,
        connection: sqlite3.Connection,
        row: sqlite3.Row,
        error: CustodyError,
        *,
        terminal_recovery: bool = False,
    ) -> str:
        event_rows = connection.execute(
            "SELECT * FROM events WHERE attempt_id=? ORDER BY sequence",
            (row["attempt_id"],),
        ).fetchall()
        if terminal_recovery:
            if not event_rows:
                raise CustodyError("unsealed recovery history is missing")
            event_rows = event_rows[:-1]
        events: list[dict[str, Any]] = []
        operations: list[dict[str, Any]] = []
        for event_row in event_rows:
            events.append(
                {
                    "sequence": event_row["sequence"],
                    "operation": event_row["operation"],
                    "from_state": event_row["from_state"],
                    "to_state": event_row["to_state"],
                    "operation_digest": event_row["operation_digest"],
                    "event_digest": event_row["event_digest"],
                    "event_json_digest": _sha256(
                        event_row["event_json"].encode("utf-8")
                    ),
                }
            )
            for operation_row in connection.execute(
                "SELECT operation_id, operation_kind, request_digest, result_json, result_digest FROM operations WHERE operation_kind=? AND request_digest=? AND subject_kind='attempt' AND subject_id=? ORDER BY operation_id",
                (
                    event_row["operation"],
                    event_row["operation_digest"],
                    row["attempt_id"],
                ),
            ).fetchall():
                operations.append(
                    {
                        "operation_id_digest": _sha256(
                            operation_row["operation_id"].encode("utf-8")
                        ),
                        "operation_kind": operation_row["operation_kind"],
                        "request_digest": operation_row["request_digest"],
                        "result_json_digest": _sha256(
                            operation_row["result_json"].encode("utf-8")
                        ),
                        "result_digest": operation_row["result_digest"],
                    }
                )
        snapshot = connection.execute(
            "SELECT snapshot, snapshot_digest FROM input_snapshots WHERE attempt_id=?",
            (row["attempt_id"],),
        ).fetchone()
        payload = {
            "attempt_id": row["attempt_id"],
            "request_json_digest": _sha256(row["request_json"].encode("utf-8")),
            "stored_request_digest": row["request_digest"],
            "path_digests_json_digest": _sha256(
                row["path_digests_json"].encode("utf-8")
            ),
            "snapshot_bytes_digest": _sha256(bytes(snapshot["snapshot"]))
            if snapshot is not None
            else None,
            "stored_snapshot_digest": snapshot["snapshot_digest"]
            if snapshot is not None
            else None,
            "outcome_kind": row["outcome_kind"],
            "outcome_digest": row["outcome_digest"],
            "events": events,
            "operations": operations,
            "verification_error": {
                "type": type(error).__name__,
                "message": str(error),
            },
        }
        return _sha256(canonical_json_bytes(payload))

    def seal_and_close(self, operation_id: str, attempt_id: str) -> AttemptDisposition:
        digest = _sha256(
            canonical_json_bytes(
                {"attempt_id": attempt_id, "operation": "seal_and_close"}
            )
        )

        def work(connection: sqlite3.Connection) -> AttemptDisposition:
            existing = self._existing_operation(
                connection, operation_id, "seal_and_close", digest
            )
            if existing is not None:
                result = AttemptDisposition(**existing)
                self._verified_terminal_record(connection, attempt_id)
                if result.state != "closed" or result.attempt_id != attempt_id:
                    raise CustodyError(
                        "seal operation result differs from terminal state"
                    )
                return result
            row = self._attempt(connection, attempt_id)
            if row["state"] != "outcome_observed":
                raise CustodyError("seal requires one observed outcome")
            if (
                connection.execute(
                    "SELECT 1 FROM terminal_seals WHERE attempt_id=? UNION ALL SELECT 1 FROM terminal_nonseals WHERE attempt_id=?",
                    (attempt_id, attempt_id),
                ).fetchone()
                is not None
            ):
                raise CustodyError("evidence seal must be absent before seal_and_close")
            request, prior, start_event, outcome_event = self._verified_observed_state(
                connection, row
            )
            outcome_kind = row["outcome_kind"]
            terminal_reason = f"observed_{outcome_kind}"
            sequence = connection.execute(
                "SELECT COUNT(*) FROM events WHERE attempt_id=?", (attempt_id,)
            ).fetchone()[0]
            event_base = {
                "sequence": sequence,
                "operation": "seal_and_close",
                "from_state": "outcome_observed",
                "to_state": "closed",
                "operation_digest": digest,
            }
            event_base["event_digest"] = _sha256(canonical_json_bytes(event_base))
            trace = prior + [event_base]
            trace_bytes = canonical_json_bytes(trace)
            trace_digest = _sha256(trace_bytes)
            manifest = {
                "request_digest": row["request_digest"],
                "start_event_digest": start_event["event_digest"],
                "outcome_event_digest": outcome_event["event_digest"],
                "state_trace_digest": trace_digest,
                "effect_inventory_version": EFFECT_INVENTORY_VERSION,
            }
            manifest_digest = _sha256(canonical_json_bytes(manifest))
            receipt = {
                "schema_version": RECEIPT_SCHEMA_VERSION,
                "attempt_id": attempt_id,
                "attempt_kind": request["attempt_kind"],
                "source_receipt_digest": request["source_receipt_digest"],
                "terminal_reason": terminal_reason,
                "evidence_manifest_digest": manifest_digest,
                "state_trace_digest": trace_digest,
                "non_authority": dict(NON_AUTHORITY),
            }
            receipt_digest = _sha256(canonical_json_bytes(receipt))
            projection = {
                "schema_version": PROJECTION_SCHEMA_VERSION,
                "episode_id": request["episode_id"],
                "attempt_id": attempt_id,
                "attempt_kind": request["attempt_kind"],
                "source_receipt_digest": request["source_receipt_digest"],
                "candidate_coordinate": request["candidate_coordinate"],
                "input_coordinate": request["input_coordinate"],
                "evaluation_request_digest": request["evaluation_request_digest"],
                "effect_inventory_version": EFFECT_INVENTORY_VERSION,
                "runtime_observation": {
                    "configured_runtime_digest": request["configured_runtime_digest"],
                    "configured_provider": request["configured_provider"],
                    "configured_model": request["configured_model"],
                    "executed_provider_identity": None,
                    "executed_model_identity": None,
                    "attempt_start_digest": start_event["event_digest"],
                    "outcome_kind": outcome_kind,
                },
                "outcome_evidence": {
                    "observation_kind": outcome_kind,
                    "normalized_return_digest": row["outcome_digest"]
                    if outcome_kind == "return"
                    else None,
                    "sanitized_failure_digest": row["outcome_digest"]
                    if outcome_kind == "failure"
                    else None,
                },
                "episode_evidence_manifest_digest": manifest_digest,
                "receipt_digest": receipt_digest,
                "state_trace_digest": trace_digest,
                "non_authority": dict(NON_AUTHORITY),
            }
            _validate_projection(projection)
            projection_bytes = canonical_json_bytes(projection)
            outer = {
                "seal_schema_version": SEAL_SCHEMA_VERSION,
                "attempt_id": attempt_id,
                "terminal_reason": terminal_reason,
                "evidence_manifest": manifest,
                "receipt": receipt,
                "state_trace": trace,
                "terminal_marker": {
                    "state": "closed",
                    "terminal_reason": terminal_reason,
                },
                "projection": projection,
                "projection_digest": _sha256(projection_bytes),
            }
            outer_bytes = canonical_json_bytes(outer)
            connection.execute(
                "INSERT INTO events(attempt_id, sequence, operation, from_state, to_state, operation_digest, event_digest, event_json) VALUES(?,?,?,?,?,?,?,?)",
                (
                    attempt_id,
                    sequence,
                    "seal_and_close",
                    "outcome_observed",
                    "closed",
                    digest,
                    event_base["event_digest"],
                    canonical_json_bytes(event_base).decode(),
                ),
            )
            connection.execute(
                "INSERT INTO terminal_seals(attempt_id, seal, seal_digest, projection, projection_digest) VALUES(?,?,?,?,?)",
                (
                    attempt_id,
                    outer_bytes,
                    _sha256(outer_bytes),
                    projection_bytes,
                    _sha256(projection_bytes),
                ),
            )
            connection.execute(
                "UPDATE attempts SET state='closed', terminal_reason=? WHERE attempt_id=?",
                (terminal_reason, attempt_id),
            )
            result = AttemptDisposition(attempt_id, "closed", terminal_reason)
            self._record_operation(
                connection, operation_id, "seal_and_close", digest, result.__dict__
            )
            return result

        return self._execution_transaction("seal_and_close", work)

    def _verified_terminal_record(
        self, connection: sqlite3.Connection, attempt_id: str
    ) -> dict[str, Any]:
        attempt = self._attempt(connection, attempt_id)
        if attempt["state"] not in TERMINAL_STATES:
            raise CustodyError("attempt is not terminal")
        sealed = connection.execute(
            "SELECT seal, seal_digest, projection, projection_digest FROM terminal_seals WHERE attempt_id=?",
            (attempt_id,),
        ).fetchone()
        nonseal = connection.execute(
            "SELECT terminal_json, terminal_digest FROM terminal_nonseals WHERE attempt_id=?",
            (attempt_id,),
        ).fetchone()
        if sealed is not None and nonseal is not None:
            raise CustodyError("attempt has ambiguous terminal records")
        if sealed is not None:
            if attempt["terminal_reason"] not in {
                "observed_return",
                "observed_failure",
            }:
                raise CustodyError("sealed attempt has an ineligible terminal reason")
            outcome_kind = (
                "return"
                if attempt["terminal_reason"] == "observed_return"
                else "failure"
            )
            operation = (
                "observe_return" if outcome_kind == "return" else "observe_failure"
            )
            request, events, _snapshot = self._verified_history(
                connection,
                attempt,
                ("allocate_episode", "start_attempt", operation, "seal_and_close"),
            )
            seal_bytes = bytes(sealed["seal"])
            projection_bytes = bytes(sealed["projection"])
            outer = self._decode_mapping(seal_bytes, "terminal seal")
            projection = self._decode_mapping(projection_bytes, "terminal projection")
            _validate_projection(projection)
            if (
                _sha256(seal_bytes) != sealed["seal_digest"]
                or _sha256(projection_bytes) != sealed["projection_digest"]
            ):
                raise CustodyError("terminal seal or projection digest mismatch")
            trace_digest = _sha256(canonical_json_bytes(events))
            manifest = {
                "request_digest": attempt["request_digest"],
                "start_event_digest": events[1]["event_digest"],
                "outcome_event_digest": events[2]["event_digest"],
                "state_trace_digest": trace_digest,
                "effect_inventory_version": EFFECT_INVENTORY_VERSION,
            }
            manifest_digest = _sha256(canonical_json_bytes(manifest))
            receipt = {
                "schema_version": RECEIPT_SCHEMA_VERSION,
                "attempt_id": attempt_id,
                "attempt_kind": request["attempt_kind"],
                "source_receipt_digest": request["source_receipt_digest"],
                "terminal_reason": attempt["terminal_reason"],
                "evidence_manifest_digest": manifest_digest,
                "state_trace_digest": trace_digest,
                "non_authority": dict(NON_AUTHORITY),
            }
            receipt_digest = _sha256(canonical_json_bytes(receipt))
            expected_projection = {
                "schema_version": PROJECTION_SCHEMA_VERSION,
                "episode_id": request["episode_id"],
                "attempt_id": attempt_id,
                "attempt_kind": request["attempt_kind"],
                "source_receipt_digest": request["source_receipt_digest"],
                "candidate_coordinate": request["candidate_coordinate"],
                "input_coordinate": request["input_coordinate"],
                "evaluation_request_digest": request["evaluation_request_digest"],
                "effect_inventory_version": EFFECT_INVENTORY_VERSION,
                "runtime_observation": {
                    "configured_runtime_digest": request["configured_runtime_digest"],
                    "configured_provider": request["configured_provider"],
                    "configured_model": request["configured_model"],
                    "executed_provider_identity": None,
                    "executed_model_identity": None,
                    "attempt_start_digest": events[1]["event_digest"],
                    "outcome_kind": outcome_kind,
                },
                "outcome_evidence": {
                    "observation_kind": outcome_kind,
                    "normalized_return_digest": attempt["outcome_digest"]
                    if outcome_kind == "return"
                    else None,
                    "sanitized_failure_digest": attempt["outcome_digest"]
                    if outcome_kind == "failure"
                    else None,
                },
                "episode_evidence_manifest_digest": manifest_digest,
                "receipt_digest": receipt_digest,
                "state_trace_digest": trace_digest,
                "non_authority": dict(NON_AUTHORITY),
            }
            expected_projection_bytes = canonical_json_bytes(expected_projection)
            expected_outer = {
                "seal_schema_version": SEAL_SCHEMA_VERSION,
                "attempt_id": attempt_id,
                "terminal_reason": attempt["terminal_reason"],
                "evidence_manifest": manifest,
                "receipt": receipt,
                "state_trace": events,
                "terminal_marker": {
                    "state": "closed",
                    "terminal_reason": attempt["terminal_reason"],
                },
                "projection": expected_projection,
                "projection_digest": _sha256(expected_projection_bytes),
            }
            if (
                projection != expected_projection
                or projection_bytes != expected_projection_bytes
                or outer != expected_outer
                or seal_bytes != canonical_json_bytes(expected_outer)
            ):
                raise CustodyError(
                    "terminal seal artifacts differ from reconstructed evidence"
                )
            return outer
        if nonseal is None:
            raise CustodyError("terminal record is missing")
        terminal_bytes = nonseal["terminal_json"].encode("utf-8")
        terminal = self._decode_mapping(terminal_bytes, "terminal nonseal")
        if _sha256(terminal_bytes) != nonseal["terminal_digest"]:
            raise CustodyError("terminal nonseal digest mismatch")
        reason = attempt["terminal_reason"]
        operation_by_reason = {
            "cancelled_before_attempt": "cancel_before_attempt",
            "recovered_unstarted": "recover_unstarted_allocation",
            "unknown_after_start": "recover_unknown_attempt",
            "unsealed_outcome": "recover_unsealed_outcome",
        }
        operation = operation_by_reason.get(reason)
        if operation is None:
            raise CustodyError("terminal nonseal reason is invalid")
        expected_keys = {
            "attempt_id",
            "state",
            "terminal_reason",
            "event_digest",
            "projection_available",
        }
        if reason == "unsealed_outcome":
            expected_keys.add("seal_failure_digest")
            _require_sha256(terminal.get("seal_failure_digest"), "seal failure digest")
        if set(terminal) != expected_keys or terminal != {
            key: value
            for key, value in {
                "attempt_id": attempt_id,
                "state": attempt["state"],
                "terminal_reason": reason,
                "event_digest": terminal.get("event_digest"),
                "seal_failure_digest": terminal.get("seal_failure_digest"),
                "projection_available": False,
            }.items()
            if key in expected_keys
        }:
            raise CustodyError("terminal nonseal members or values are invalid")
        _require_sha256(terminal["event_digest"], "terminal event digest")
        if reason != "unsealed_outcome":
            prefix = (
                ("allocate_episode", operation)
                if reason in {"cancelled_before_attempt", "recovered_unstarted"}
                else ("allocate_episode", "start_attempt", operation)
            )
            _request, events, _snapshot = self._verified_history(
                connection, attempt, prefix
            )
            if events[-1]["event_digest"] != terminal["event_digest"]:
                raise CustodyError("terminal nonseal event binding is invalid")
        else:
            observed_operation = (
                "observe_return"
                if attempt["outcome_kind"] == "return"
                else "observe_failure"
            )
            try:
                self._verified_history(
                    connection,
                    attempt,
                    ("allocate_episode", "start_attempt", observed_operation),
                    trailing_operations=("recover_unsealed_outcome",),
                )
            except CustodyError as seal_error:
                reconstructed_failure_digest = self._seal_failure_digest(
                    connection, attempt, seal_error, terminal_recovery=True
                )
            else:
                raise CustodyError(
                    "unsealed recovery terminal has constructible evidence"
                )
            if reconstructed_failure_digest != terminal["seal_failure_digest"]:
                raise CustodyError("unsealed recovery failure binding is invalid")
            last_event_row = connection.execute(
                "SELECT * FROM events WHERE attempt_id=? ORDER BY sequence DESC LIMIT 1",
                (attempt_id,),
            ).fetchone()
            if last_event_row is None:
                raise CustodyError("unsealed recovery terminal event is missing")
            last_event = self._decode_mapping(
                last_event_row["event_json"], "unsealed recovery event"
            )
            expected_operation_digest = _sha256(
                canonical_json_bytes({"attempt_id": attempt_id, "operation": operation})
            )
            event_preimage = {
                "sequence": last_event_row["sequence"],
                "operation": operation,
                "from_state": "outcome_observed",
                "to_state": "indeterminate",
                "operation_digest": expected_operation_digest,
            }
            expected_event = {
                **event_preimage,
                "event_digest": _sha256(canonical_json_bytes(event_preimage)),
            }
            if (
                last_event != expected_event
                or last_event_row["attempt_id"] != attempt_id
                or last_event_row["operation"] != operation
                or last_event_row["from_state"] != "outcome_observed"
                or last_event_row["to_state"] != "indeterminate"
                or last_event_row["operation_digest"] != expected_operation_digest
                or last_event_row["event_digest"] != expected_event["event_digest"]
                or expected_event["event_digest"] != terminal["event_digest"]
            ):
                raise CustodyError("unsealed recovery terminal event is invalid")
            operation_rows = connection.execute(
                "SELECT result_json, result_digest FROM operations WHERE operation_kind=? AND request_digest=? AND subject_kind='attempt' AND subject_id=?",
                (operation, expected_operation_digest, attempt_id),
            ).fetchall()
            expected_result = AttemptDisposition(
                attempt_id, "indeterminate", "unsealed_outcome"
            ).__dict__
            bound_operation = False
            for operation_row in operation_rows:
                result_bytes = operation_row["result_json"].encode("utf-8")
                result = self._decode_mapping(
                    result_bytes, "unsealed recovery operation result"
                )
                if _sha256(result_bytes) != operation_row["result_digest"]:
                    raise CustodyError("unsealed recovery result digest is invalid")
                if result == expected_result:
                    bound_operation = True
            if not bound_operation:
                raise CustodyError("unsealed recovery operation binding is missing")
        return terminal

    def _verified_terminal(self, attempt_id: str) -> dict[str, Any]:
        self._verify_store()
        self._reject_clean_sidecars()
        self._verify_schema()
        return self._verified_terminal_record(self._connection, attempt_id)

    def read_terminal(self, attempt_id: str) -> dict[str, Any]:
        return self._verified_terminal(attempt_id)

    def read_projection(self, attempt_id: str) -> bytes:
        self._verified_terminal(attempt_id)
        row = self._connection.execute(
            "SELECT projection FROM terminal_seals WHERE attempt_id=?", (attempt_id,)
        ).fetchone()
        if row is None:
            raise CustodyError("attempt is ineligible for a Decision 106 projection")
        return bytes(row["projection"])

    def list_incomplete(self) -> tuple[str, ...]:
        self._verify_store()
        self._reject_clean_sidecars()
        self._verify_schema()
        return tuple(
            row[0]
            for row in self._connection.execute(
                "SELECT attempt_id FROM attempts WHERE state NOT IN ('closed','indeterminate','rejected') ORDER BY attempt_id"
            ).fetchall()
        )


_SCHEMA_DDL = f"""
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT INTO meta VALUES('schema_version', '{SCHEMA_VERSION}');
CREATE TABLE attempts(
  attempt_id TEXT PRIMARY KEY,
  request_json TEXT NOT NULL,
  request_digest TEXT NOT NULL,
  path_digests_json TEXT NOT NULL,
  state TEXT NOT NULL,
  terminal_reason TEXT,
  outcome_kind TEXT,
  outcome_digest TEXT
);
CREATE TABLE input_snapshots(
  attempt_id TEXT PRIMARY KEY REFERENCES attempts(attempt_id),
  snapshot BLOB NOT NULL,
  snapshot_digest TEXT NOT NULL
);
CREATE TABLE operations(
  operation_id TEXT PRIMARY KEY,
  operation_kind TEXT NOT NULL,
  request_digest TEXT NOT NULL,
  subject_kind TEXT NOT NULL CHECK(subject_kind IN ('attempt','rejection')),
  subject_id TEXT NOT NULL,
  result_json TEXT NOT NULL,
  result_digest TEXT NOT NULL
);
CREATE TABLE events(
  attempt_id TEXT NOT NULL REFERENCES attempts(attempt_id),
  sequence INTEGER NOT NULL,
  operation TEXT NOT NULL,
  from_state TEXT NOT NULL,
  to_state TEXT NOT NULL,
  operation_digest TEXT NOT NULL,
  event_digest TEXT NOT NULL,
  event_json TEXT NOT NULL,
  PRIMARY KEY(attempt_id, sequence)
);
CREATE TABLE terminal_seals(
  attempt_id TEXT PRIMARY KEY REFERENCES attempts(attempt_id),
  seal BLOB NOT NULL,
  seal_digest TEXT NOT NULL,
  projection BLOB NOT NULL,
  projection_digest TEXT NOT NULL
);
CREATE TABLE terminal_nonseals(
  terminal_id TEXT PRIMARY KEY,
  attempt_id TEXT UNIQUE REFERENCES attempts(attempt_id),
  terminal_json TEXT NOT NULL,
  terminal_digest TEXT NOT NULL
);
CREATE TRIGGER immutable_input_snapshots_update BEFORE UPDATE ON input_snapshots BEGIN SELECT RAISE(ABORT, 'immutable input snapshot'); END;
CREATE TRIGGER immutable_input_snapshots_delete BEFORE DELETE ON input_snapshots BEGIN SELECT RAISE(ABORT, 'immutable input snapshot'); END;
CREATE TRIGGER immutable_operations_update BEFORE UPDATE ON operations BEGIN SELECT RAISE(ABORT, 'immutable operation'); END;
CREATE TRIGGER immutable_operations_delete BEFORE DELETE ON operations BEGIN SELECT RAISE(ABORT, 'immutable operation'); END;
CREATE TRIGGER immutable_events_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT, 'immutable event'); END;
CREATE TRIGGER immutable_events_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT, 'immutable event'); END;
CREATE TRIGGER immutable_seals_update BEFORE UPDATE ON terminal_seals BEGIN SELECT RAISE(ABORT, 'immutable seal'); END;
CREATE TRIGGER immutable_seals_delete BEFORE DELETE ON terminal_seals BEGIN SELECT RAISE(ABORT, 'immutable seal'); END;
CREATE TRIGGER immutable_nonseals_update BEFORE UPDATE ON terminal_nonseals BEGIN SELECT RAISE(ABORT, 'immutable terminal'); END;
CREATE TRIGGER immutable_nonseals_delete BEFORE DELETE ON terminal_nonseals BEGIN SELECT RAISE(ABORT, 'immutable terminal'); END;
CREATE TRIGGER immutable_attempt_bindings BEFORE UPDATE ON attempts WHEN NEW.request_json IS NOT OLD.request_json OR NEW.request_digest IS NOT OLD.request_digest OR NEW.path_digests_json IS NOT OLD.path_digests_json OR NEW.attempt_id IS NOT OLD.attempt_id BEGIN SELECT RAISE(ABORT, 'immutable attempt binding'); END;
CREATE TRIGGER immutable_observed_outcome BEFORE UPDATE ON attempts WHEN OLD.outcome_kind IS NOT NULL AND (NEW.outcome_kind IS NOT OLD.outcome_kind OR NEW.outcome_digest IS NOT OLD.outcome_digest) BEGIN SELECT RAISE(ABORT, 'immutable observed outcome'); END;
CREATE TRIGGER attempt_transition_requires_event BEFORE UPDATE ON attempts WHEN NEW.state IS NOT OLD.state AND NOT EXISTS (SELECT 1 FROM events WHERE attempt_id=OLD.attempt_id AND from_state=OLD.state AND to_state=NEW.state AND sequence=(SELECT MAX(sequence) FROM events WHERE attempt_id=OLD.attempt_id)) BEGIN SELECT RAISE(ABORT, 'attempt transition requires latest event'); END;
CREATE TRIGGER attempt_terminal_requires_record BEFORE UPDATE ON attempts WHEN NEW.state IN ('closed','indeterminate') AND NOT EXISTS (SELECT 1 FROM terminal_seals WHERE attempt_id=OLD.attempt_id) AND NOT EXISTS (SELECT 1 FROM terminal_nonseals WHERE attempt_id=OLD.attempt_id) BEGIN SELECT RAISE(ABORT, 'terminal transition requires terminal evidence'); END;
CREATE TRIGGER terminal_attempt_immutable BEFORE UPDATE ON attempts WHEN OLD.state IN ('closed','indeterminate','rejected') BEGIN SELECT RAISE(ABORT, 'terminal attempt immutable'); END;
CREATE TRIGGER terminal_no_new_events BEFORE INSERT ON events WHEN (SELECT state FROM attempts WHERE attempt_id=NEW.attempt_id) IN ('closed','indeterminate','rejected') BEGIN SELECT RAISE(ABORT, 'terminal attempt has no outgoing transition'); END;
"""

_SCHEMA_SQL = (
    "PRAGMA foreign_keys=ON;\n"
    "PRAGMA journal_mode=DELETE;\n"
    "PRAGMA synchronous=FULL;\n" + _SCHEMA_DDL
)


def _initialize_schema(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA foreign_keys=ON")
    mode = connection.execute("PRAGMA journal_mode=DELETE").fetchone()[0]
    if str(mode).lower() != "delete":
        raise CustodyError("SQLite DELETE journal mode is required")
    connection.execute("PRAGMA synchronous=FULL")
    try:
        connection.executescript("BEGIN IMMEDIATE;\n" + _SCHEMA_DDL + "\nCOMMIT;")
    except BaseException:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise


def _schema_objects(
    connection: sqlite3.Connection,
) -> tuple[tuple[str, str, str, str], ...]:
    return tuple(
        (str(row[0]), str(row[1]), str(row[2]), str(row[3]))
        for row in connection.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%' AND sql IS NOT NULL ORDER BY type, name"
        ).fetchall()
    )


_EXPECTED_SCHEMA_OBJECTS: tuple[tuple[str, str, str, str], ...] | None = None


def _expected_schema_objects() -> tuple[tuple[str, str, str, str], ...]:
    global _EXPECTED_SCHEMA_OBJECTS
    if _EXPECTED_SCHEMA_OBJECTS is None:
        connection = sqlite3.connect(":memory:", isolation_level=None)
        try:
            connection.executescript(_SCHEMA_SQL)
            _EXPECTED_SCHEMA_OBJECTS = _schema_objects(connection)
        finally:
            connection.close()
    return _EXPECTED_SCHEMA_OBJECTS


__all__ = [
    "AllocationMaterial",
    "AttemptDisposition",
    "AttemptRequest",
    "CustodyError",
    "ExecutionCustodyStore",
    "RejectionDisposition",
    "SnapshotView",
    "canonical_json_bytes",
]
