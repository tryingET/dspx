from __future__ import annotations

import hashlib
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

_SHA256 = re.compile(r"[0-9a-f]{64}")


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
    seen_paths: dict[str, str] = {}
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
        previous_hash = seen_paths.get(normalized_path)
        if previous_hash is not None:
            raise ValueError("candidate surface path is duplicated: " + normalized_path)
        seen_kinds.add(kind)
        seen_paths[normalized_path] = raw_hash
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


def _sha256_file(path: Path) -> str:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError(f"candidate artifact must be a regular file: {path}")
        digest = hashlib.sha256()
        while chunk := os.read(descriptor, 64 * 1024):
            digest.update(chunk)
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
            raise ValueError(f"candidate artifact changed while hashing: {path}")
        return digest.hexdigest()
    finally:
        os.close(descriptor)


def _reject_symlink_components(root: Path, path: Path, *, kind: str) -> None:
    relative = path.relative_to(root)
    root_parts = root.parts
    current = Path(root_parts[0])
    for component in root_parts[1:]:
        current /= component
        if current.is_symlink():
            raise ValueError(
                f"candidate artifact root contains a symlink component: {current}"
            )
    current = root
    for component in relative.parts:
        current /= component
        if current.is_symlink():
            raise ValueError(
                f"candidate surface {kind} contains a symlink component: {current}"
            )


def validate_candidate_artifact_closure(
    manifest: Mapping[str, Any],
    *,
    manifest_path: Path,
) -> tuple[ValidatedCandidateArtifact, ...]:
    """Fail closed unless every concrete manifest surface is current and confined."""

    lexical_manifest = Path(os.path.abspath(manifest_path.expanduser()))
    if lexical_manifest.is_symlink() or not lexical_manifest.is_file():
        raise ValueError("candidate manifest must be a regular non-symlink file")
    root = lexical_manifest.parent
    declarations = collect_candidate_artifact_declarations(manifest)
    validated: list[ValidatedCandidateArtifact] = []
    for declaration in declarations:
        raw_path = Path(declaration.path).expanduser()
        lexical = raw_path if raw_path.is_absolute() else root / raw_path
        lexical = Path(os.path.abspath(lexical))
        try:
            lexical.relative_to(root)
        except ValueError as exc:
            raise ValueError(
                f"candidate surface {declaration.kind} escapes candidate root"
            ) from exc
        _reject_symlink_components(root, lexical, kind=declaration.kind)
        if not lexical.is_file():
            raise ValueError(
                f"candidate surface {declaration.kind} artifact is missing: {lexical}"
            )
        actual_hash = _sha256_file(lexical)
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
    return tuple(validated)
