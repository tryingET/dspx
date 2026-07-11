# summary: "Safely validates and snapshots the complete candidate artifact closure declared by a program manifest."
# read_when:
#   - "Changing candidate artifact path confinement, hash validation, or snapshot reads."

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

_SHA256 = re.compile(r"[0-9a-f]{64}")
_DIRECTORY_FLAGS = (
    os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
)


@dataclass(frozen=True)
class CandidateArtifactDeclaration:
    """One candidate-local artifact declared by the manifest surface graph."""

    kind: str
    path: str
    sha256: str


@dataclass(frozen=True)
class ValidatedCandidateArtifact:
    """A manifest declaration rebound to its current candidate-local file."""

    kind: str
    path: Path
    sha256: str


@dataclass(frozen=True)
class CandidateArtifactSnapshot:
    """One descriptor-validated manifest and its complete concrete surface closure."""

    manifest: dict[str, Any]
    manifest_path: Path
    manifest_sha256: str
    artifacts: tuple[ValidatedCandidateArtifact, ...]


def collect_candidate_artifact_declarations(
    manifest: Mapping[str, Any],
) -> tuple[CandidateArtifactDeclaration, ...]:
    """Collect every concrete candidate surface instead of filtering by kind."""

    assembly = manifest.get("candidate_assembly")
    if not isinstance(assembly, Mapping):
        raise ValueError("candidate manifest is missing candidate_assembly")
    raw_surfaces = assembly.get("surfaces")
    if not isinstance(raw_surfaces, list):
        raise ValueError("candidate manifest surfaces must be a list")

    declarations: list[CandidateArtifactDeclaration] = []
    seen_kinds: set[str] = set()
    seen_paths: set[str] = set()
    for index, raw in enumerate(raw_surfaces):
        if not isinstance(raw, Mapping):
            raise ValueError(f"candidate surface {index} must be an object")
        kind = str(raw.get("kind") or "").strip()
        if not kind:
            raise ValueError(f"candidate surface {index} has no kind")
        raw_path = raw.get("path")
        raw_hash = raw.get("content_hash")
        if (raw_path is None or raw_path == "") and (
            raw_hash is None or raw_hash == ""
        ):
            continue
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError(f"candidate surface {kind} has no artifact path")
        if not isinstance(raw_hash, str) or _SHA256.fullmatch(raw_hash) is None:
            raise ValueError(f"candidate surface {kind} has an invalid content hash")
        if kind in seen_kinds:
            raise ValueError(f"candidate surface kind is duplicated: {kind}")
        normalized_path = raw_path.strip()
        if normalized_path in seen_paths:
            raise ValueError("candidate surface path is duplicated: " + normalized_path)
        seen_kinds.add(kind)
        seen_paths.add(normalized_path)
        declarations.append(
            CandidateArtifactDeclaration(
                kind=kind,
                path=normalized_path,
                sha256=raw_hash,
            )
        )
    if not declarations:
        raise ValueError("candidate manifest has no concrete artifact surfaces")
    return tuple(declarations)


def open_directory_no_symlinks(path: Path, *, create: bool = False) -> int:
    """Open an absolute directory component-by-component without following symlinks."""

    lexical = Path(os.path.abspath(path.expanduser()))
    descriptor = os.open(lexical.anchor, _DIRECTORY_FLAGS)
    try:
        for component in lexical.parts[1:]:
            try:
                child = os.open(component, _DIRECTORY_FLAGS, dir_fd=descriptor)
            except FileNotFoundError:
                if not create:
                    raise
                os.mkdir(component, mode=0o700, dir_fd=descriptor)
                child = os.open(component, _DIRECTORY_FLAGS, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _read_regular_descriptor(
    descriptor: int, *, path: Path, capture: bool
) -> tuple[str, bytes | None]:
    before = os.fstat(descriptor)
    if not stat.S_ISREG(before.st_mode):
        raise ValueError(f"candidate artifact must be a regular file: {path}")
    digest = hashlib.sha256()
    chunks: list[bytes] | None = [] if capture else None
    while chunk := os.read(descriptor, 64 * 1024):
        digest.update(chunk)
        if chunks is not None:
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
        raise ValueError(f"candidate artifact changed while reading: {path}")
    return digest.hexdigest(), b"".join(chunks) if chunks is not None else None


def _open_relative_file(root_fd: int, relative: Path, *, display_path: Path) -> int:
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise ValueError(f"candidate artifact escapes candidate root: {display_path}")
    directory_fd = os.dup(root_fd)
    try:
        for component in relative.parts[:-1]:
            child = os.open(component, _DIRECTORY_FLAGS, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = child
        descriptor = os.open(
            relative.parts[-1],
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=directory_fd,
        )
        return descriptor
    finally:
        os.close(directory_fd)


def _candidate_relative_path(root: Path, raw_path: str, *, kind: str) -> Path:
    path = Path(raw_path).expanduser()
    lexical = Path(os.path.abspath(path if path.is_absolute() else root / path))
    try:
        return lexical.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"candidate surface {kind} escapes candidate root") from exc


def snapshot_candidate_artifact_closure(
    manifest_path: Path,
) -> CandidateArtifactSnapshot:
    """Read one manifest and hash its complete surface closure through safe descriptors."""

    lexical_manifest = Path(os.path.abspath(manifest_path.expanduser()))
    root = lexical_manifest.parent
    try:
        root_fd = open_directory_no_symlinks(root)
    except OSError as exc:
        raise ValueError(
            f"candidate artifact root contains a symlink component or is not a directory: {root}"
        ) from exc
    try:
        try:
            manifest_fd = os.open(
                lexical_manifest.name,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=root_fd,
            )
        except OSError as exc:
            raise ValueError(
                "candidate manifest must be a regular non-symlink file"
            ) from exc
        try:
            manifest_hash, manifest_bytes = _read_regular_descriptor(
                manifest_fd,
                path=lexical_manifest,
                capture=True,
            )
        finally:
            os.close(manifest_fd)
        assert manifest_bytes is not None
        try:
            manifest = json.loads(manifest_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(
                "candidate manifest must contain valid UTF-8 JSON"
            ) from exc
        if not isinstance(manifest, dict):
            raise ValueError("candidate manifest must contain a JSON object")

        validated: list[ValidatedCandidateArtifact] = []
        seen_relative_paths: set[Path] = set()
        for declaration in collect_candidate_artifact_declarations(manifest):
            relative = _candidate_relative_path(
                root,
                declaration.path,
                kind=declaration.kind,
            )
            if relative in seen_relative_paths:
                raise ValueError(
                    "candidate surface path is duplicated after normalization: "
                    + declaration.path
                )
            seen_relative_paths.add(relative)
            lexical = root / relative
            try:
                descriptor = _open_relative_file(
                    root_fd,
                    relative,
                    display_path=lexical,
                )
            except OSError as exc:
                raise ValueError(
                    f"candidate surface {declaration.kind} artifact is missing or contains a symlink component: {lexical}"
                ) from exc
            try:
                actual_hash, _ = _read_regular_descriptor(
                    descriptor,
                    path=lexical,
                    capture=False,
                )
            finally:
                os.close(descriptor)
            if actual_hash != declaration.sha256:
                raise ValueError(
                    f"candidate surface {declaration.kind} hash does not match current file: {lexical}"
                )
            validated.append(
                ValidatedCandidateArtifact(
                    kind=declaration.kind,
                    path=lexical,
                    sha256=actual_hash,
                )
            )
        return CandidateArtifactSnapshot(
            manifest=manifest,
            manifest_path=lexical_manifest,
            manifest_sha256=manifest_hash,
            artifacts=tuple(validated),
        )
    finally:
        os.close(root_fd)


def read_candidate_snapshot_artifact(
    snapshot: CandidateArtifactSnapshot,
    *,
    kind: str,
) -> tuple[ValidatedCandidateArtifact, bytes]:
    """Read one snapshot artifact through confined descriptors and rebind its hash."""

    artifact = next(
        (candidate for candidate in snapshot.artifacts if candidate.kind == kind),
        None,
    )
    if artifact is None:
        raise ValueError(f"candidate snapshot has no artifact surface of kind: {kind}")
    root = snapshot.manifest_path.parent
    try:
        relative = artifact.path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"candidate surface {kind} escapes candidate root") from exc
    try:
        root_fd = open_directory_no_symlinks(root)
    except OSError as exc:
        raise ValueError(
            f"candidate artifact root contains a symlink component or is not a directory: {root}"
        ) from exc
    try:
        try:
            descriptor = _open_relative_file(
                root_fd,
                relative,
                display_path=artifact.path,
            )
        except OSError as exc:
            raise ValueError(
                f"candidate surface {kind} artifact is missing or contains a symlink component: {artifact.path}"
            ) from exc
        try:
            actual_hash, content = _read_regular_descriptor(
                descriptor,
                path=artifact.path,
                capture=True,
            )
        finally:
            os.close(descriptor)
    finally:
        os.close(root_fd)
    if actual_hash != artifact.sha256:
        raise ValueError(
            f"candidate surface {kind} hash changed after snapshot: {artifact.path}"
        )
    assert content is not None
    return artifact, content


def validate_candidate_artifact_closure(
    manifest: Mapping[str, Any],
    *,
    manifest_path: Path,
) -> tuple[ValidatedCandidateArtifact, ...]:
    """Fail closed unless the supplied manifest and every concrete surface are current."""

    snapshot = snapshot_candidate_artifact_closure(manifest_path)
    if snapshot.manifest != dict(manifest):
        raise ValueError("candidate manifest changed after it was loaded")
    return snapshot.artifacts
