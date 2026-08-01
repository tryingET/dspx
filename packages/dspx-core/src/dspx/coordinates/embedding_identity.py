# summary: "Builds and validates hash-bound identity for model-backed Oracle embeddings."
# read_when:
#   - "Changing sentence-transformer artifact, tokenizer, runtime, normalization, or distance identity."

"""Hash-bound identity helpers for production-semantic embedding evaluation."""

from __future__ import annotations

import hashlib
import math
import os
import stat
import sys
import sysconfig
from dataclasses import dataclass
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, distribution, version
from pathlib import Path
from typing import Any, Mapping, Protocol

IDENTITY_SCHEMA = "dspx-sentence-transformer-identity-v1"
_MAX_ARTIFACT_BYTES = 2_000_000_000


class EmbeddingIdentityError(ValueError):
    """Raised when model-backed embedding identity is incomplete or inconsistent."""


class TokenizerIdentityProtocol(Protocol):
    model_max_length: int
    padding_side: str
    truncation_side: str

    def __len__(self) -> int: ...


@dataclass(frozen=True)
class ModelArtifactExpectation:
    """Precommitted repository identity for one loader-relevant artifact."""

    path: str
    size: int
    source_git_oid: str
    lfs_sha256: str | None = None

    def __post_init__(self) -> None:
        parsed = Path(self.path)
        if (
            parsed.is_absolute()
            or ".." in parsed.parts
            or self.path != parsed.as_posix()
        ):
            raise EmbeddingIdentityError(
                f"invalid relative artifact path: {self.path!r}"
            )
        if type(self.size) is not int or self.size <= 0:
            raise EmbeddingIdentityError("artifact size must be a positive integer")
        if len(self.source_git_oid) != 40 or any(
            character not in "0123456789abcdef" for character in self.source_git_oid
        ):
            raise EmbeddingIdentityError(
                "artifact source Git OID must be lowercase 40-hex"
            )
        if self.lfs_sha256 is not None and (
            len(self.lfs_sha256) != 64
            or any(character not in "0123456789abcdef" for character in self.lfs_sha256)
        ):
            raise EmbeddingIdentityError(
                "artifact LFS SHA-256 must be lowercase 64-hex"
            )


@dataclass(frozen=True)
class SentenceTransformerIdentitySpec:
    """Frozen inputs needed to identify one sentence-transformer execution."""

    repository_id: str
    revision: str
    artifact_manifest: tuple[ModelArtifactExpectation, ...]
    expected_dimension: int
    normalize_embeddings: bool
    vector_dtype: str
    ranking_metric: str
    reported_distance: str
    runtime_versions: tuple[tuple[str, str], ...]
    runtime_lock_sha256: str
    runtime_wheel_sha256: tuple[tuple[str, str], ...]
    runtime_installer: str
    uv_version: str
    platform: str
    python_implementation: str
    python_major_minor: str
    device: str

    @property
    def artifact_paths(self) -> tuple[str, ...]:
        return tuple(row.path for row in self.artifact_manifest)

    @property
    def runtime_packages(self) -> tuple[str, ...]:
        return tuple(row[0] for row in self.runtime_versions)

    def __post_init__(self) -> None:
        if (
            not self.repository_id
            or len(self.revision) != 40
            or any(character not in "0123456789abcdef" for character in self.revision)
        ):
            raise EmbeddingIdentityError(
                "repository and exact lowercase commit are required"
            )
        paths = self.artifact_paths
        if not paths or len(set(paths)) != len(paths) or tuple(sorted(paths)) != paths:
            raise EmbeddingIdentityError(
                "artifact manifest paths must be non-empty, unique, and sorted"
            )
        if isinstance(self.expected_dimension, bool) or self.expected_dimension <= 0:
            raise EmbeddingIdentityError(
                "expected_dimension must be a positive integer"
            )
        if self.normalize_embeddings is not True or self.vector_dtype != "float32":
            raise EmbeddingIdentityError(
                "evaluation vectors must be normalized float32"
            )
        if self.ranking_metric != "cosine_similarity_descending":
            raise EmbeddingIdentityError(
                "ranking metric must be cosine similarity descending"
            )
        if self.reported_distance != "one_minus_cosine_similarity":
            raise EmbeddingIdentityError(
                "reported distance must be one minus cosine similarity"
            )
        packages = self.runtime_packages
        if (
            not packages
            or len(set(packages)) != len(packages)
            or tuple(sorted(packages)) != packages
        ):
            raise EmbeddingIdentityError(
                "runtime versions must be non-empty, unique, and sorted"
            )
        if any(not name or not value for name, value in self.runtime_versions):
            raise EmbeddingIdentityError(
                "runtime package names and versions must be non-empty"
            )
        if len(self.runtime_lock_sha256) != 64 or any(
            character not in "0123456789abcdef"
            for character in self.runtime_lock_sha256
        ):
            raise EmbeddingIdentityError(
                "runtime lock SHA-256 must be lowercase 64-hex"
            )
        if tuple(
            name for name, _digest in self.runtime_wheel_sha256
        ) != packages or any(
            len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            for _name, digest in self.runtime_wheel_sha256
        ):
            raise EmbeddingIdentityError("runtime wheel hash identity is incomplete")
        if self.runtime_installer != "uv_run_isolated_frozen" or not self.uv_version:
            raise EmbeddingIdentityError(
                "frozen isolated runtime installer is required"
            )
        if self.platform != "linux-x86_64":
            raise EmbeddingIdentityError("evaluation platform must be linux-x86_64")
        if self.python_implementation != "cpython" or self.python_major_minor != "3.13":
            raise EmbeddingIdentityError("evaluation runtime must be CPython 3.13")
        if self.device != "cpu":
            raise EmbeddingIdentityError("evaluation device must be CPU")


def _hash_regular_file(
    root: Path, expected: ModelArtifactExpectation
) -> dict[str, Any]:
    path = root / expected.path
    try:
        before = path.lstat()
    except OSError as exc:
        raise EmbeddingIdentityError(
            f"required model artifact is unavailable: {expected.path}"
        ) from exc
    if path.is_symlink() or not stat.S_ISREG(before.st_mode):
        raise EmbeddingIdentityError(
            f"model artifact must be a retained regular file: {expected.path}"
        )
    if root.resolve() not in path.resolve().parents:
        raise EmbeddingIdentityError(
            f"model artifact escapes retained root: {expected.path}"
        )
    if before.st_size != expected.size or before.st_size > _MAX_ARTIFACT_BYTES:
        raise EmbeddingIdentityError(f"model artifact size drift: {expected.path}")

    sha256 = hashlib.sha256()
    git_blob = hashlib.sha1(usedforsecurity=False)
    git_blob.update(f"blob {expected.size}\0".encode())
    size = 0
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise EmbeddingIdentityError(
            f"cannot open model artifact safely: {expected.path}"
        ) from exc
    try:
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            while chunk := stream.read(1024 * 1024):
                sha256.update(chunk)
                git_blob.update(chunk)
                size += len(chunk)
            after = os.fstat(stream.fileno())
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        raise EmbeddingIdentityError(
            f"model artifact changed while hashing: {expected.path}"
        )
    digest = sha256.hexdigest()
    if expected.lfs_sha256 is not None:
        if digest != expected.lfs_sha256:
            raise EmbeddingIdentityError(
                f"model LFS artifact hash drift: {expected.path}"
            )
    elif git_blob.hexdigest() != expected.source_git_oid:
        raise EmbeddingIdentityError(
            f"model Git artifact identity drift: {expected.path}"
        )
    return {
        "path": expected.path,
        "size": size,
        "sha256": digest,
        "source_git_oid": expected.source_git_oid,
        "lfs_sha256": expected.lfs_sha256,
    }


@lru_cache(maxsize=32)
def _is_stable_distribution_path(relative_path: Path) -> bool:
    return ".." not in relative_path.parts and not any(
        part.endswith(".dist-info") for part in relative_path.parts
    )


def _distribution_content_sha256(package_name: str) -> str:
    """Hash stable imported wheel payload, excluding generated install projections."""

    try:
        installed = distribution(package_name)
    except PackageNotFoundError as exc:
        raise EmbeddingIdentityError(
            f"required runtime distribution is unavailable: {package_name}"
        ) from exc
    files = installed.files
    if not files:
        raise EmbeddingIdentityError(
            f"runtime distribution file manifest is unavailable: {package_name}"
        )
    digest = hashlib.sha256()
    base = Path(str(installed.locate_file(""))).resolve()
    retained_count = 0
    for relative in sorted(files, key=str):
        relative_path = Path(str(relative))
        path = Path(str(installed.locate_file(relative))).resolve()
        if not _is_stable_distribution_path(relative_path) or base not in path.parents:
            continue
        if path.is_symlink() or not path.is_file():
            raise EmbeddingIdentityError(
                f"runtime distribution payload is unavailable: {package_name}:{relative}"
            )
        retained_count += 1
        digest.update(str(relative).encode())
        digest.update(b"\0")
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        digest.update(b"\0")
    if retained_count == 0:
        raise EmbeddingIdentityError(
            f"runtime distribution has no stable imported payload: {package_name}"
        )
    return digest.hexdigest()


def runtime_distribution_hashes(package_names: tuple[str, ...]) -> dict[str, str]:
    return {name: _distribution_content_sha256(name) for name in package_names}


def runtime_package_versions(package_names: tuple[str, ...]) -> dict[str, str]:
    """Return exact installed versions for every required runtime package."""

    resolved: dict[str, str] = {}
    for package_name in package_names:
        try:
            resolved[package_name] = version(package_name)
        except PackageNotFoundError as exc:
            raise EmbeddingIdentityError(
                f"required runtime package identity is unavailable: {package_name}"
            ) from exc
    return resolved


def build_sentence_transformer_identity(
    *,
    spec: SentenceTransformerIdentitySpec,
    model_root: Path,
    tokenizer: TokenizerIdentityProtocol,
    dimension: int,
    observed_vector_dtype: str,
    frozen_runtime_lock_sha256: str,
    runtime_observations: Mapping[str, object],
    runtime_versions: Mapping[str, str] | None = None,
    runtime_distribution_content_sha256: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Validate precommitted artifacts and bind observed runtime/vector semantics."""

    root = model_root.resolve()
    if not root.is_dir() or model_root.is_symlink():
        raise EmbeddingIdentityError(
            "model_root must be a retained non-symlink directory"
        )
    if isinstance(dimension, bool) or dimension != spec.expected_dimension:
        raise EmbeddingIdentityError(
            f"embedding dimension drift: expected {spec.expected_dimension}, observed {dimension!r}"
        )
    if observed_vector_dtype != spec.vector_dtype:
        raise EmbeddingIdentityError(
            f"embedding dtype drift: expected {spec.vector_dtype}, observed {observed_vector_dtype!r}"
        )
    if frozen_runtime_lock_sha256 != spec.runtime_lock_sha256:
        raise EmbeddingIdentityError("isolated frozen runtime lock receipt drift")
    expected_observations = {
        "model_device": "cpu",
        "torch_cuda_available": False,
        "torch_default_dtype": "torch.float32",
        "numpy_output_dtype": "float32",
    }
    if dict(runtime_observations) != expected_observations:
        raise EmbeddingIdentityError("observed CPU runtime execution identity drift")
    versions = (
        runtime_package_versions(spec.runtime_packages)
        if runtime_versions is None
        else dict(runtime_versions)
    )
    if versions != dict(spec.runtime_versions):
        raise EmbeddingIdentityError("runtime package identity drift")
    distribution_hashes = (
        runtime_distribution_hashes(spec.runtime_packages)
        if runtime_distribution_content_sha256 is None
        else dict(runtime_distribution_content_sha256)
    )
    if set(distribution_hashes) != set(spec.runtime_packages) or any(
        len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
        for digest in distribution_hashes.values()
    ):
        raise EmbeddingIdentityError("runtime distribution content identity drift")
    observed_python = f"{sys.version_info.major}.{sys.version_info.minor}"
    if sysconfig.get_platform() != spec.platform:
        raise EmbeddingIdentityError("runtime platform identity drift")
    if (
        sys.implementation.name != spec.python_implementation
        or observed_python != spec.python_major_minor
    ):
        raise EmbeddingIdentityError("Python runtime identity drift")

    retained_paths = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and ".cache" not in path.relative_to(root).parts
    }
    if retained_paths != set(spec.artifact_paths):
        raise EmbeddingIdentityError(
            "retained model root has missing or extra loader-relevant artifacts"
        )

    tokenizer_identity = {
        "implementation": f"{type(tokenizer).__module__}.{type(tokenizer).__qualname__}",
        "model_max_length": tokenizer.model_max_length,
        "padding_side": tokenizer.padding_side,
        "truncation_side": tokenizer.truncation_side,
        "vocabulary_size": len(tokenizer),
    }
    if (
        isinstance(tokenizer_identity["model_max_length"], bool)
        or not isinstance(tokenizer_identity["model_max_length"], int)
        or tokenizer_identity["model_max_length"] <= 0
        or isinstance(tokenizer_identity["vocabulary_size"], bool)
        or not isinstance(tokenizer_identity["vocabulary_size"], int)
        or tokenizer_identity["vocabulary_size"] <= 0
        or not tokenizer_identity["padding_side"]
        or not tokenizer_identity["truncation_side"]
    ):
        raise EmbeddingIdentityError("tokenizer runtime identity is incomplete")

    artifacts = [
        _hash_regular_file(root, expected) for expected in spec.artifact_manifest
    ]
    return {
        "schema_version": IDENTITY_SCHEMA,
        "backend": "sentence-transformers",
        "repository_id": spec.repository_id,
        "revision": spec.revision,
        "artifacts": artifacts,
        "tokenizer": tokenizer_identity,
        "runtime": {
            "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "python_implementation": sys.implementation.name,
            "lock_sha256": spec.runtime_lock_sha256,
            "wheel_sha256": dict(spec.runtime_wheel_sha256),
            "installer": spec.runtime_installer,
            "uv_version": spec.uv_version,
            "isolated_frozen": True,
            "packages": versions,
            "distribution_content_sha256": distribution_hashes,
            "distribution_content_hash_scope": (
                "imported_package_and_library_payload_excluding_dist_info_and_generated_scripts"
            ),
            "platform": sysconfig.get_platform(),
            "device": spec.device,
            "observations": dict(runtime_observations),
        },
        "encoding": {
            "dimension": dimension,
            "vector_dtype": observed_vector_dtype,
            "normalize_embeddings": spec.normalize_embeddings,
            "normalization_postcondition": "finite_l2_unit_vector",
        },
        "distance": {
            "ranking_metric": spec.ranking_metric,
            "reported_distance": spec.reported_distance,
        },
        "identity_complete": True,
        "production_semantic_claim_allowed": False,
    }


def validate_unit_vector(vector: list[float], *, tolerance: float = 1e-5) -> None:
    """Fail closed unless a vector is finite and L2-normalized."""

    if not vector or any(
        not isinstance(value, float) or not math.isfinite(value) for value in vector
    ):
        raise EmbeddingIdentityError("embedding vector must contain finite floats")
    norm = math.sqrt(sum(value * value for value in vector))
    if not math.isclose(norm, 1.0, rel_tol=0.0, abs_tol=tolerance):
        raise EmbeddingIdentityError(
            f"embedding vector is not L2-normalized: norm={norm!r}"
        )
