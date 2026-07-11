from __future__ import annotations

import hashlib
import json
import os
import secrets
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Literal, Mapping

from dspx.services.program_artifact_names import PROTECTED_PROGRAM_ARTIFACT_NAMES
from dspx.services.program_evidence_closure import open_directory_no_symlinks

PayloadArtifactRootPolicy = Literal["ignore", "forbid", "allow_named"]


@dataclass(frozen=True)
class ArtifactEnvelopePolicy:
    """Typed policy for the common, authority-safe artifact envelope fields."""

    schema_version: str
    required_false_authority: tuple[str, ...] = ()
    required_false_effect: tuple[str, ...] = ()


@dataclass(frozen=True)
class ConfinedArtifact:
    """A resolved artifact proven to be confined and hash-current."""

    path: Path
    sha256: str


@dataclass(frozen=True)
class StableJsonArtifact:
    """One exact-byte, descriptor-read local JSON object observation."""

    path: Path
    sha256: str
    payload: dict[str, Any]


def read_stable_json_artifact(
    path: Path,
    *,
    label: str,
    error_type: type[ValueError] = ValueError,
    max_bytes: int = 16 * 1024 * 1024,
) -> StableJsonArtifact:
    """Read, bind, and parse one regular JSON file without following symlinks."""

    lexical = Path(os.path.abspath(path.expanduser()))
    if max_bytes <= 0:
        raise error_type(f"{label} maximum size must be positive")
    try:
        parent_fd = open_directory_no_symlinks(lexical.parent)
    except OSError as exc:
        raise error_type(f"{label} parent could not be opened safely: {exc}") from exc
    descriptor = -1
    failure: BaseException | None = None
    cleanup_errors: list[OSError] = []
    digest = hashlib.sha256()
    chunks: list[bytes] = []
    try:
        descriptor = os.open(
            lexical.name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_fd,
        )
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise error_type(f"{label} must be a regular file: {lexical}")
        if before.st_size > max_bytes:
            raise error_type(f"{label} exceeds the {max_bytes}-byte size limit")
        total = 0
        while chunk := os.read(descriptor, min(64 * 1024, max_bytes + 1 - total)):
            total += len(chunk)
            if total > max_bytes:
                raise error_type(f"{label} exceeds the {max_bytes}-byte size limit")
            digest.update(chunk)
            chunks.append(chunk)
        after = os.fstat(descriptor)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise error_type(f"{label} changed while reading: {lexical}")
    except BaseException as exc:
        failure = exc
    finally:
        for candidate in (descriptor, parent_fd):
            if candidate < 0:
                continue
            try:
                os.close(candidate)
            except OSError as exc:
                cleanup_errors.append(exc)
    if failure is not None:
        if isinstance(failure, OSError):
            message = f"{label} descriptor read failed: {failure}"
            if cleanup_errors:
                message += f"; cleanup also failed: {cleanup_errors[0]}"
            raise error_type(message) from failure
        if cleanup_errors:
            raise error_type(
                f"{label} validation failed and descriptor cleanup also failed: {cleanup_errors[0]}"
            ) from failure
        raise failure
    if cleanup_errors:
        raise error_type(f"{label} descriptor cleanup failed: {cleanup_errors[0]}")
    raw = b"".join(chunks)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise error_type(f"{label} must contain valid UTF-8 JSON: {lexical}") from exc
    if not isinstance(payload, dict):
        raise error_type(f"{label} must contain a JSON object: {lexical}")
    return StableJsonArtifact(
        path=lexical,
        sha256=digest.hexdigest(),
        payload=payload,
    )


def atomic_publish_bytes(
    target: Path,
    content: bytes,
    *,
    label: str,
    precommit: Callable[[], None],
    error_type: type[ValueError] = ValueError,
    indeterminate_error_type: type[ValueError] | None = None,
) -> None:
    """Stage bytes safely, run final validation, then atomically replace the target."""

    lexical = Path(os.path.abspath(target.expanduser()))
    try:
        parent_fd = open_directory_no_symlinks(lexical.parent, create=True)
    except OSError as exc:
        raise error_type(
            f"{label} output directory could not be opened safely: {exc}"
        ) from exc
    temporary_name = f".{lexical.name}.{secrets.token_hex(12)}.tmp"
    descriptor = -1
    replaced = False
    primary_error: BaseException | None = None
    cleanup_errors: list[OSError] = []
    try:
        try:
            descriptor = os.open(
                temporary_name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
                dir_fd=parent_fd,
            )
            offset = 0
            while offset < len(content):
                written = os.write(descriptor, content[offset:])
                if written <= 0:
                    raise OSError(f"{label} write made no progress")
                offset += written
            os.fsync(descriptor)
            os.close(descriptor)
            descriptor = -1
        except OSError as exc:
            raise error_type(
                f"{label} failed before atomic replacement: {exc}"
            ) from exc
        precommit()
        verification_fd = -1
        try:
            verification_fd = open_directory_no_symlinks(lexical.parent)
            pinned = os.fstat(parent_fd)
            current = os.fstat(verification_fd)
            if (pinned.st_dev, pinned.st_ino) != (current.st_dev, current.st_ino):
                raise OSError(f"{label} output directory changed before replacement")
        except OSError as exc:
            raise error_type(
                f"{label} failed before atomic replacement: {exc}"
            ) from exc
        finally:
            if verification_fd >= 0:
                try:
                    os.close(verification_fd)
                except OSError as exc:
                    cleanup_errors.append(exc)
        if cleanup_errors:
            raise error_type(
                f"{label} failed before atomic replacement: {cleanup_errors[0]}"
            )
        try:
            os.replace(
                temporary_name,
                lexical.name,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
            )
            replaced = True
        except OSError as exc:
            raise error_type(
                f"{label} failed before atomic replacement: {exc}"
            ) from exc
        try:
            os.fsync(parent_fd)
        except OSError as exc:
            commit_error = indeterminate_error_type or error_type
            raise commit_error(
                f"{label} replacement committed but directory durability could not be confirmed: {exc}"
            ) from exc
    except BaseException as exc:
        primary_error = exc
    finally:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError as exc:
                cleanup_errors.append(exc)
        if not replaced:
            try:
                os.unlink(temporary_name, dir_fd=parent_fd)
            except OSError as exc:
                cleanup_errors.append(exc)
        try:
            os.close(parent_fd)
        except OSError as exc:
            cleanup_errors.append(exc)
    if primary_error is not None:
        if cleanup_errors:
            message = f"{primary_error}; cleanup also failed: {cleanup_errors[0]}"
            if isinstance(primary_error, ValueError):
                raise type(primary_error)(message) from primary_error
            raise error_type(message) from primary_error
        raise primary_error
    if cleanup_errors:
        raise error_type(f"{label} cleanup failed: {cleanup_errors[0]}")


def sha256_file(path: Path) -> str:
    """Return the content digest used by DSPx artifact references."""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def require_artifact_schema(
    payload: Mapping[str, Any],
    *,
    label: str,
    schema_version: str,
    error_type: type[ValueError] = ValueError,
) -> None:
    if payload.get("schema_version") != schema_version:
        raise error_type(f"{label} schema_version must be {schema_version}")


def require_false_envelope_flags(
    payload: Mapping[str, Any],
    *,
    section: Literal["non_authority", "effect"],
    keys: Iterable[str],
    label: str,
    error_type: type[ValueError] = ValueError,
) -> None:
    raw_flags = payload.get(section)
    flags = raw_flags if isinstance(raw_flags, Mapping) else {}
    invalid = [key for key in keys if flags.get(key) is not False]
    if invalid:
        display = "non-authority" if section == "non_authority" else "effect"
        raise error_type(f"{label} widens {display} flags: " + ", ".join(invalid))


def identity_missing_keys(
    expected: Mapping[str, Any], actual: Mapping[str, Any]
) -> list[str]:
    """Return required identity keys omitted by an artifact envelope."""

    return [
        str(key)
        for key, expected_value in expected.items()
        if expected_value is not None
        and expected_value != ""
        and (actual.get(key) is None or actual.get(key) == "")
    ]


def identity_mismatch_keys(
    expected: Mapping[str, Any],
    actual: Mapping[str, Any],
    *,
    require_complete: bool,
    compare_as_text: bool,
) -> list[str]:
    """Return identity keys that drift from the expected artifact identity."""

    mismatched: list[str] = []
    for key, expected_value in expected.items():
        if expected_value is None or expected_value == "":
            continue
        actual_value = actual.get(key)
        if actual_value is None or actual_value == "":
            if require_complete:
                mismatched.append(str(key))
            continue
        values_match = (
            str(actual_value) == str(expected_value)
            if compare_as_text
            else actual_value == expected_value
        )
        if not values_match:
            mismatched.append(str(key))
    return mismatched


def identity_matches_exactly(
    actual: Mapping[str, Any], expected: Mapping[str, Any]
) -> bool:
    """Return whether all populated expected identity fields match exactly."""

    return bool(actual) and not identity_mismatch_keys(
        expected,
        actual,
        require_complete=True,
        compare_as_text=False,
    )


def validate_artifact_envelope(
    payload: Mapping[str, Any],
    *,
    label: str,
    policy: ArtifactEnvelopePolicy,
    error_type: type[ValueError] = ValueError,
) -> None:
    """Validate schema plus fail-closed authority/effect claims."""

    require_artifact_schema(
        payload,
        label=label,
        schema_version=policy.schema_version,
        error_type=error_type,
    )
    require_false_envelope_flags(
        payload,
        section="non_authority",
        keys=policy.required_false_authority,
        label=label,
        error_type=error_type,
    )
    require_false_envelope_flags(
        payload,
        section="effect",
        keys=policy.required_false_effect,
        label=label,
        error_type=error_type,
    )


def validate_confined_artifact(
    path: Path,
    *,
    root: Path,
    label: str,
    expected_sha256: str,
    expected_name: str | None = None,
    error_type: type[ValueError] = ValueError,
    outside_root_message: str = "outside the confined artifact root",
) -> ConfinedArtifact:
    """Resolve a path, reject traversal/symlink escape, and verify its digest."""

    resolved = path.expanduser().resolve()
    confined_root = root.expanduser().resolve()
    if expected_name is not None and resolved.name != expected_name:
        raise error_type(f"{label} path must be {expected_name}")
    if not _is_relative_to(resolved, confined_root):
        raise error_type(f"{label} path is {outside_root_message}")
    if not resolved.exists():
        raise error_type(f"{label} path is missing: {resolved}")
    digest = sha256_file(resolved)
    if digest != expected_sha256:
        raise error_type(f"{label} sha256 does not match current file")
    return ConfinedArtifact(path=resolved, sha256=digest)


def _iter_path_values(value: object) -> Iterable[str]:
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key)
            if (
                (key_text == "path" or key_text.endswith("_path"))
                and isinstance(item, str)
                and item.strip()
            ):
                yield item
            else:
                yield from _iter_path_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_path_values(item)


def protected_paths_from_payload(payload: Mapping[str, Any]) -> set[Path]:
    """Return resolved input/control paths declared by a sidecar payload."""

    paths: set[Path] = set()
    for raw_path in _iter_path_values(payload):
        try:
            paths.add(Path(raw_path).expanduser().resolve())
        except (OSError, RuntimeError, ValueError):
            continue
    return paths


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def protected_artifact_roots_from_payload(payload: Mapping[str, Any]) -> set[Path]:
    """Return generated-artifact roots implied by manifest paths in a payload."""

    roots: set[Path] = set()
    for path in protected_paths_from_payload(payload):
        if path.name == "manifest.json":
            roots.add(path.parent)
    return roots


def prepare_sidecar_output_path(
    out_path: Path,
    *,
    payload: Mapping[str, Any],
    artifact_label: str,
    protected_names: Iterable[str] = PROTECTED_PROGRAM_ARTIFACT_NAMES,
    payload_artifact_root_policy: PayloadArtifactRootPolicy,
    extra_protected_paths: Iterable[Path] = (),
    extra_protected_roots: Iterable[Path] = (),
    allowed_names_in_protected_roots: Iterable[str] = (),
) -> Path:
    """Resolve and validate a local sidecar output path before writing.

    Sidecars summarize or adjudicate generated artifacts. They must not overwrite
    producer/control artifacts, any input path recorded in their own payload, or
    arbitrary files inside protected generated-artifact roots. Callers must
    explicitly choose whether manifest paths declared in the payload imply
    protected artifact roots, preventing security policy from becoming an omitted
    optional keyword. Use ``allow_named`` only for documented canonical in-root
    exceptions such as ``program_candidate_state.json``.
    """

    resolved = out_path.expanduser().resolve()
    protected_name_set = {str(name) for name in protected_names}
    if resolved.name in protected_name_set:
        raise ValueError(f"{artifact_label} must not overwrite {resolved.name}")

    protected_paths = protected_paths_from_payload(payload)
    protected_paths.update(
        path.expanduser().resolve() for path in extra_protected_paths
    )
    if resolved in protected_paths:
        raise ValueError(
            f"{artifact_label} output must not overwrite an input artifact: {resolved}"
        )

    protected_roots = {root.expanduser().resolve() for root in extra_protected_roots}
    if payload_artifact_root_policy not in {"ignore", "forbid", "allow_named"}:
        raise ValueError(
            f"{artifact_label} has unsupported payload artifact root policy: {payload_artifact_root_policy}"
        )
    if payload_artifact_root_policy in {"forbid", "allow_named"}:
        protected_roots.update(protected_artifact_roots_from_payload(payload))
    allowed_root_names = (
        {str(name) for name in allowed_names_in_protected_roots}
        if payload_artifact_root_policy == "allow_named"
        else set()
    )
    for protected_root in protected_roots:
        if resolved == protected_root or _is_relative_to(resolved, protected_root):
            if resolved.name in allowed_root_names:
                continue
            raise ValueError(
                f"{artifact_label} output must not be written inside a protected artifact root: {protected_root}"
            )

    return resolved
