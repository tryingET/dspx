# summary: "Exact source and fixture-runtime identity for the accepted receipt producer."
from __future__ import annotations

import base64
import csv
import hashlib
import importlib.metadata
import importlib.util
import inspect
import json
import os
import stat
import subprocess
import tomllib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dspx.services.provider_outcome_receipt_contract import (
    EVENT_FIELDS,
    ProviderOutcomeConsumerError,
    canonical_json,
    sha256,
)

OWNER_COMMIT = "40dd8c0be1bdd48d1b296297c89613931c033239"
OWNER_TREE = "5d980c2849685d24166d5f6924f82b9defaf1393"
OWNER_VERSION = "0.1.5"
OWNER_LOCK_SHA256 = "0d6c79b4b5d70f7a11a879b0bb26dc61dce064fe8dd2ca7e694a9099b43e90e1"
OWNER_MODULES: dict[str, tuple[str, str]] = {
    "package_init": (
        "src/dspy_lm_auth/__init__.py",
        "5fce1f73b46996390379ca7a4bf86a3b73fa47809aaf68ee6822ee39c4702a38",
    ),
    "lm": (
        "src/dspy_lm_auth/lm.py",
        "85f7c5a5b72c2062ba628827b609671299867b9ff5f1ee7ff96410c6e70e77a1",
    ),
    "codex_stream": (
        "src/dspy_lm_auth/codex_stream.py",
        "edb153d6f6e4615624c9688716f4b2bd02e32ac1d9794b1355190e62af1be3c4",
    ),
    "codex_stream_support": (
        "src/dspy_lm_auth/codex_stream_support.py",
        "a8804500abbf481346e833da727679472b477fcc8a6c39c3ba299c51e2f632cd",
    ),
    "outcome_receipt": (
        "src/dspy_lm_auth/outcome_receipt.py",
        "cd46faf242a2696fe4322aaee961e2b383d944f663a08959dbcb7a143e282899",
    ),
    "outcome_receipt_state": (
        "src/dspy_lm_auth/outcome_receipt_state.py",
        "79d9262a3f40690a3fa4fe49721bc49d984f842fd1681039b92e6629a9adc1fa",
    ),
    "outcome_receipt_runtime": (
        "src/dspy_lm_auth/outcome_receipt_runtime.py",
        "950745532b1481c850e8144c9c7c56c622ca3ce275bda8167a6a93a33fc55a5c",
    ),
    "outcome_receipt_transport": (
        "src/dspy_lm_auth/outcome_receipt_transport.py",
        "846fd6a7e0c368e9a2a5ce72f6354d324fb61ea06663d4c04cdb7595cf022e49",
    ),
}


@dataclass(frozen=True, slots=True)
class ExpectedDependency:
    module_name: str
    version: str
    wheel_sha256: str
    payload_count: int
    payload_sha256: str
    record_sha256: str


EXPECTED_DEPENDENCIES: dict[str, ExpectedDependency] = {
    "dspy": ExpectedDependency(
        "dspy",
        "3.1.3",
        "26f983372ebb284324cc2162458f7bce509ef5ef7b48be4c9f490fa06ea73e37",
        139,
        "e0d6a2a7cf2363b3c581a74bae5ea0f391cef631bda00e4b5fcc77e39b80270b",
        "96d7152d6535f744dba11cec3cdb1c037f6539570043173ac521e0893a1948d5",
    ),
    "litellm": ExpectedDependency(
        "litellm",
        "1.82.1",
        "a9ec3fe42eccb1611883caaf8b1bf33c9f4e12163f94c7d1004095b14c379eb2",
        2532,
        "b7b99502fcf3b3a78271d973233b8f25d3b812b92a060b58eb68964f8fa3a025",
        "459b41009766c4fbbe8dc89f7c670acf8ab4d78f22adc57d2cbbafde5ffa579c",
    ),
    "httpx": ExpectedDependency(
        "httpx",
        "0.28.1",
        "d909fcccc110f8c7faf814ca82a9a4d816bc5a6dbfea25d6591d6985b8ba59ad",
        24,
        "07414d29fb1941459875ce8779ba8b64ffb35df39b38cccbb81db96aceb23ed3",
        "2bf47a837bca4b5497bf86d9b2d2c15db8af63581511d70b3450c21e42ae0234",
    ),
    "httpcore": ExpectedDependency(
        "httpcore",
        "1.0.9",
        "2d400746a40668fc9dec9810239072b40b4484b640a8c38fd654a024c7a1bf55",
        32,
        "bb0e6120792945054384bc9e1fa7721211f903245c79c029a648cbf6ff2b0829",
        "67cb4644d84fef1df8c5a0862c57c3380eff058a153bac7a4ba2722779982554",
    ),
}


@dataclass(frozen=True, slots=True)
class ExpectedOwnerSource:
    commit: str
    tree: str
    version: str
    lock_sha256: str
    modules: Mapping[str, tuple[str, str]]
    dependencies: Mapping[str, ExpectedDependency]


ACCEPTED_OWNER_SOURCE = ExpectedOwnerSource(
    commit=OWNER_COMMIT,
    tree=OWNER_TREE,
    version=OWNER_VERSION,
    lock_sha256=OWNER_LOCK_SHA256,
    modules=OWNER_MODULES,
    dependencies=EXPECTED_DEPENDENCIES,
)

_ARTIFACT_TOKEN = object()
_RECEIPT_FIELDS = (
    "logical_request_id",
    "semantic_request_sha256",
    "sink",
    "_lock",
    "_used",
)


class VerifiedOwnerArtifact:
    """Opaque result of exact artifact verification, not caller-authored metadata."""

    __slots__ = (
        "_accepted",
        "_dependency_raw",
        "_event_type",
        "_receipt_type",
        "_revalidator",
        "_sealed",
        "_source_raw",
    )
    _accepted: bool
    _dependency_raw: bytes
    _event_type: type[Any]
    _receipt_type: type[Any]
    _revalidator: Callable[[], None]
    _sealed: bool
    _source_raw: bytes

    def __init__(
        self,
        *,
        source_identity: Mapping[str, Any],
        dependency_identity: Mapping[str, Any],
        event_type: type[Any],
        receipt_type: type[Any],
        revalidator: Callable[[], None],
        accepted: bool,
        token: object,
    ) -> None:
        if token is not _ARTIFACT_TOKEN:
            raise TypeError("VerifiedOwnerArtifact is created by the verifier")
        object.__setattr__(self, "_source_raw", canonical_json(source_identity))
        object.__setattr__(self, "_dependency_raw", canonical_json(dependency_identity))
        object.__setattr__(self, "_event_type", event_type)
        object.__setattr__(self, "_receipt_type", receipt_type)
        object.__setattr__(self, "_revalidator", revalidator)
        object.__setattr__(self, "_accepted", accepted)
        object.__setattr__(self, "_sealed", True)

    def __setattr__(self, name: str, value: Any) -> None:
        if getattr(self, "_sealed", False):
            raise TypeError("VerifiedOwnerArtifact is immutable")
        object.__setattr__(self, name, value)

    @property
    def source_identity(self) -> Mapping[str, Any]:
        return json.loads(self._source_raw)

    @property
    def dependency_identity(self) -> Mapping[str, Any]:
        return json.loads(self._dependency_raw)

    @property
    def event_type(self) -> type[Any]:
        return self._event_type

    @property
    def receipt_type(self) -> type[Any]:
        return self._receipt_type

    @property
    def accepted(self) -> bool:
        return self._accepted

    def revalidate(self) -> None:
        self._revalidator()


def _fixture_owner_artifact(
    *,
    source_identity: Mapping[str, Any],
    dependency_identity: Mapping[str, Any],
    event_type: type[Any],
    receipt_type: type[Any],
    revalidator: Callable[[], None] = lambda: None,
) -> VerifiedOwnerArtifact:
    """Test-only artifact; standalone accepted reduction rejects it."""

    return VerifiedOwnerArtifact(
        source_identity=source_identity,
        dependency_identity=dependency_identity,
        event_type=event_type,
        receipt_type=receipt_type,
        revalidator=revalidator,
        accepted=False,
        token=_ARTIFACT_TOKEN,
    )


def _git_env() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith("GIT_")
    }


def _git(root: Path, *args: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        check=False,
        env=_git_env(),
    )
    if completed.returncode:
        raise ProviderOutcomeConsumerError("owner_git_identity_drift")
    return completed.stdout


def _git_text(root: Path, *args: str) -> str:
    try:
        return _git(root, *args).decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise ProviderOutcomeConsumerError("owner_git_identity_drift") from exc


def _file_sha256(path: Path) -> str:
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or path.is_symlink():
            raise ProviderOutcomeConsumerError("owner_source_file_drift")
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()
    except OSError as exc:
        raise ProviderOutcomeConsumerError("owner_source_file_drift") from exc


def verify_owner_source(
    source_root: Path,
    expected: ExpectedOwnerSource = ACCEPTED_OWNER_SOURCE,
) -> dict[str, Any]:
    try:
        original = source_root.expanduser()
        if original.is_symlink():
            raise ProviderOutcomeConsumerError("owner_source_root_drift")
        root = original.resolve(strict=True)
        if not root.is_dir():
            raise ProviderOutcomeConsumerError("owner_source_root_drift")
    except OSError as exc:
        raise ProviderOutcomeConsumerError("owner_source_root_drift") from exc
    if (
        _git_text(root, "rev-parse", "HEAD^{commit}") != expected.commit
        or _git_text(root, "rev-parse", "HEAD^{tree}") != expected.tree
        or _git_text(root, "rev-parse", f"{expected.commit}^{{commit}}")
        != expected.commit
        or _git_text(root, "rev-parse", f"{expected.commit}^{{tree}}") != expected.tree
        or _git_text(root, "status", "--porcelain", "--untracked-files=normal")
    ):
        raise ProviderOutcomeConsumerError("owner_git_identity_drift")
    observed: dict[str, str] = {}
    for name, (relative, expected_hash) in sorted(expected.modules.items()):
        if "/" not in relative or not relative.startswith("src/dspy_lm_auth/"):
            raise ProviderOutcomeConsumerError("owner_source_manifest_drift")
        committed = _git(root, "show", f"{expected.commit}:{relative}")
        if (
            sha256(committed) != expected_hash
            or _file_sha256(root / relative) != expected_hash
        ):
            raise ProviderOutcomeConsumerError("owner_source_file_drift")
        observed[name] = expected_hash
    if _file_sha256(root / "uv.lock") != expected.lock_sha256:
        raise ProviderOutcomeConsumerError("owner_lock_identity_drift")
    try:
        lock = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))
        project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise ProviderOutcomeConsumerError("owner_lock_identity_drift") from exc
    if project.get("project", {}).get("version") != expected.version:
        raise ProviderOutcomeConsumerError("owner_version_drift")
    packages = {
        str(item.get("name")): item
        for item in lock.get("package", [])
        if isinstance(item, Mapping)
    }
    for distribution, dependency in expected.dependencies.items():
        package = packages.get(distribution)
        wheels = package.get("wheels", []) if isinstance(package, Mapping) else []
        hashes = {
            str(item.get("hash", "")).removeprefix("sha256:")
            for item in wheels
            if isinstance(item, Mapping)
        }
        if (
            not isinstance(package, Mapping)
            or package.get("version") != dependency.version
            or dependency.wheel_sha256 not in hashes
        ):
            raise ProviderOutcomeConsumerError("owner_lock_dependency_drift")
    return {
        "owner": "tryinget-dspy-lm-auth",
        "version": expected.version,
        "commit": expected.commit,
        "tree": expected.tree,
        "lock_sha256": expected.lock_sha256,
        "module_sha256": observed,
    }


def _record_digest(
    distribution: importlib.metadata.Distribution,
    module_name: str,
) -> dict[str, Any]:
    record_raw = (distribution.read_text("RECORD") or "").encode("utf-8")
    if not record_raw:
        raise ProviderOutcomeConsumerError("runtime_distribution_record_missing")
    rows: dict[str, tuple[str, str]] = {}
    try:
        for relative, digest, size in csv.reader(
            record_raw.decode("utf-8").splitlines()
        ):
            rows[relative] = (digest, size)
    except (UnicodeError, ValueError) as exc:
        raise ProviderOutcomeConsumerError("runtime_distribution_record_drift") from exc
    files = list(distribution.files or ())
    selected = [item for item in files if str(item).split("/", 1)[0] == module_name]
    if not selected:
        raise ProviderOutcomeConsumerError("runtime_distribution_payload_missing")
    payload: dict[str, str] = {}
    for item in selected:
        relative = str(item)
        path = Path(str(distribution.locate_file(item)))
        try:
            info = path.lstat()
        except OSError as exc:
            raise ProviderOutcomeConsumerError(
                "runtime_distribution_payload_drift"
            ) from exc
        if not stat.S_ISREG(info.st_mode) or path.is_symlink():
            raise ProviderOutcomeConsumerError("runtime_distribution_payload_drift")
        expected_digest, expected_size = rows.get(relative, ("", ""))
        if not expected_digest.startswith("sha256=") or not expected_size.isdigit():
            raise ProviderOutcomeConsumerError("runtime_distribution_record_drift")
        raw = path.read_bytes()
        encoded = (
            base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).decode().rstrip("=")
        )
        if encoded != expected_digest.removeprefix("sha256=") or len(raw) != int(
            expected_size
        ):
            raise ProviderOutcomeConsumerError("runtime_distribution_payload_drift")
        payload[relative] = hashlib.sha256(raw).hexdigest()
    return {
        "payload_count": len(payload),
        "payload_sha256": sha256(canonical_json(payload)),
        "record_sha256": sha256(record_raw),
    }


def verify_runtime_identity(
    event_type: type[Any],
    receipt_type: type[Any],
    source_root: Path,
    expected: ExpectedOwnerSource = ACCEPTED_OWNER_SOURCE,
) -> dict[str, Any]:
    expected_event_path = source_root.resolve() / expected.modules["outcome_receipt"][0]
    event_source = inspect.getsourcefile(event_type)
    receipt_source = inspect.getsourcefile(receipt_type)
    if (
        event_type.__module__ != "dspy_lm_auth.outcome_receipt"
        or event_type.__name__ != "OutcomeReceiptEvent"
        or receipt_type.__module__ != "dspy_lm_auth.outcome_receipt"
        or receipt_type.__name__ != "ProviderOutcomeReceipt"
        or event_source is None
        or receipt_source is None
        or Path(event_source).resolve() != expected_event_path
        or Path(receipt_source).resolve() != expected_event_path
        or tuple(getattr(event_type, "__dataclass_fields__", {})) != EVENT_FIELDS
        or tuple(getattr(receipt_type, "__dataclass_fields__", {})) != _RECEIPT_FIELDS
        or _file_sha256(expected_event_path) != expected.modules["outcome_receipt"][1]
    ):
        raise ProviderOutcomeConsumerError("loaded_owner_receipt_api_drift")
    result: dict[str, Any] = {}
    for distribution_name, dependency in sorted(expected.dependencies.items()):
        try:
            distribution = importlib.metadata.distribution(distribution_name)
            spec = importlib.util.find_spec(dependency.module_name)
        except importlib.metadata.PackageNotFoundError as exc:
            raise ProviderOutcomeConsumerError("runtime_dependency_missing") from exc
        if (
            distribution.version != dependency.version
            or spec is None
            or spec.origin is None
        ):
            raise ProviderOutcomeConsumerError("runtime_dependency_version_drift")
        origin = Path(spec.origin).resolve()
        located = {
            Path(str(distribution.locate_file(item))).resolve()
            for item in distribution.files or ()
        }
        if origin not in located:
            raise ProviderOutcomeConsumerError("runtime_dependency_origin_drift")
        observed = _record_digest(distribution, dependency.module_name)
        expected_payload = {
            "payload_count": dependency.payload_count,
            "payload_sha256": dependency.payload_sha256,
            "record_sha256": dependency.record_sha256,
        }
        if observed != expected_payload:
            raise ProviderOutcomeConsumerError("runtime_dependency_payload_drift")
        result[distribution_name] = {
            "version": dependency.version,
            "locked_wheel_sha256": dependency.wheel_sha256,
            **observed,
        }
    return result


def verify_owner_artifact(
    source_root: Path,
    event_type: type[Any],
    receipt_type: type[Any],
    expected: ExpectedOwnerSource = ACCEPTED_OWNER_SOURCE,
) -> VerifiedOwnerArtifact:
    original = source_root.expanduser()
    source_identity = verify_owner_source(original, expected)
    root = original.resolve(strict=True)
    dependency_identity = verify_runtime_identity(
        event_type, receipt_type, root, expected
    )

    def revalidate() -> None:
        if (
            verify_owner_source(original, expected) != source_identity
            or verify_runtime_identity(event_type, receipt_type, root, expected)
            != dependency_identity
        ):
            raise ProviderOutcomeConsumerError("owner_artifact_revalidation_drift")

    return VerifiedOwnerArtifact(
        source_identity=source_identity,
        dependency_identity=dependency_identity,
        event_type=event_type,
        receipt_type=receipt_type,
        revalidator=revalidate,
        accepted=True,
        token=_ARTIFACT_TOKEN,
    )
