"""Exact maintained-fork identity for foundry-only dspy-lm-auth jury calls."""

from __future__ import annotations

import hashlib
import inspect
import os
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from dspy import BaseLM

from dspx.services.soomfon_provider_outcome_receipt_contract import (
    ProviderOutcomeConsumerError,
)
from dspx.services.soomfon_provider_outcome_receipt_identity import (
    ExpectedDependency,
    ExpectedOwnerSource,
    VerifiedOwnerArtifact,
    verify_owner_artifact,
    verify_owner_source,
)

OWNER_COMMIT = "755a378757c3f863b0ac3e534a4205729506dbd7"
OWNER_TREE = "a4630f403b90e89d61b99368ef88581a1924a418"
OWNER_VERSION = "0.1.6.dev0"
OWNER_LOCK_SHA256 = "e7d9eae5753be3fbf5ea4fc8e88380aeefecd74e5dccaf341fe362281d3c6889"

_OWNER_MODULES: dict[str, tuple[str, str]] = {
    "package_init": (
        "src/dspy_lm_auth/__init__.py",
        "0591c12d885e56ae2d9c97526add39d7dcd72e2bcf8dbb3e614297af1812578c",
    ),
    "lm": (
        "src/dspy_lm_auth/lm.py",
        "45c11c0ac5b0de9a7e95c1d2f436f73243678585720bcdddb07b5f5f133d8165",
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
        "dd8b2ff9279d0098e40d04d486a9aa550328650a57d5205971df240bcd4b4d0d",
    ),
    "outcome_receipt_state": (
        "src/dspy_lm_auth/outcome_receipt_state.py",
        "0f6686b3204df451044f391c66e48ab78a867d997f48fba958d0a1068b9a6f26",
    ),
    "outcome_receipt_runtime": (
        "src/dspy_lm_auth/outcome_receipt_runtime.py",
        "637606bb8a4ce5da5843fae7130f829abf561c65dbafbb98eba4a356c6315338",
    ),
    "outcome_receipt_transport": (
        "src/dspy_lm_auth/outcome_receipt_transport.py",
        "e8e03c81ffb0f767233b4f1ae8c0b750c5284c13b20eafafbdb9fa268d43b34a",
    ),
}

_OWNER_DEPENDENCIES: dict[str, ExpectedDependency] = {
    "dspy": ExpectedDependency(
        "dspy",
        "3.3.1",
        "250049f565f52c014609ce2d3ca0de17a6c9449ac961492d61a009aa30dceabf",
        157,
        "a8bb038956606f4bf85b274c9d24daf5b1b59a2f598541c15e926793e629ee0c",
        "4f79ddd18e0a8280dce2d38904d430c18be4d067d759fe78725996e989d66489",
    ),
    "litellm": ExpectedDependency(
        "litellm",
        "1.82.1",
        "a9ec3fe42eccb1611883caaf8b1bf33c9f4e12163f94c7d1004095b14c379eb2",
        2532,
        "b7b99502fcf3b3a78271d973233b8f25d3b812b92a060b58eb68964f8fa3a025",
        "09836432e6f009684a7d6d43cf088ead28217f28974417c60b1002f01bbac353",
    ),
    "httpx": ExpectedDependency(
        "httpx",
        "0.28.1",
        "d909fcccc110f8c7faf814ca82a9a4d816bc5a6dbfea25d6591d6985b8ba59ad",
        24,
        "07414d29fb1941459875ce8779ba8b64ffb35df39b38cccbb81db96aceb23ed3",
        "b71ee1676eeed3f56f5f9a0f3fe50f1247dd856618d6782b8384574da3d31450",
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

FOUNDRY_JURY_OWNER_SOURCE = ExpectedOwnerSource(
    commit=OWNER_COMMIT,
    tree=OWNER_TREE,
    version=OWNER_VERSION,
    lock_sha256=OWNER_LOCK_SHA256,
    modules=_OWNER_MODULES,
    dependencies=_OWNER_DEPENDENCIES,
)

_EXTRA_OWNER_FILES = {
    "src/dspy_lm_auth/codex_backend.py": "23040fd3da20633074adb3abf2fe009309ae9c169c5e4909cdf19b150e496b7a",
    "src/dspy_lm_auth/codex_backend_contract.py": "c1df45aed46ed65ef80e95035cbac591e386d537970c8c5d12d648ab3fbb7ea6",
    "src/dspy_lm_auth/_route_policy.py": "7dece27cc0bf8e3cad087f6d476ea44f9db6331195fe606c50c688a40b80ec12",
    "src/dspy_lm_auth/auth.py": "b46b390a292ddb8eb6ab22c6a26958644047ca31cc121d773af3bf9cc7f75e7e",
}


def expected_foundry_jury_source_identity() -> dict[str, Any]:
    return {
        "owner": "tryinget-dspy-lm-auth",
        "version": FOUNDRY_JURY_OWNER_SOURCE.version,
        "commit": FOUNDRY_JURY_OWNER_SOURCE.commit,
        "tree": FOUNDRY_JURY_OWNER_SOURCE.tree,
        "lock_sha256": FOUNDRY_JURY_OWNER_SOURCE.lock_sha256,
        "module_sha256": {
            name: digest
            for name, (_, digest) in sorted(FOUNDRY_JURY_OWNER_SOURCE.modules.items())
        },
    }


def expected_foundry_jury_dependency_identity() -> dict[str, Any]:
    return {
        name: {
            "version": item.version,
            "locked_wheel_sha256": item.wheel_sha256,
            "payload_count": item.payload_count,
            "payload_sha256": item.payload_sha256,
            "record_sha256": item.record_sha256,
        }
        for name, item in sorted(FOUNDRY_JURY_OWNER_SOURCE.dependencies.items())
    }


def _verify_no_bytecode(source_root: Path) -> None:
    if sys.dont_write_bytecode is not True:
        raise ProviderOutcomeConsumerError("owner_bytecode_posture_drift")
    package_root = source_root.expanduser().resolve(strict=True) / "src/dspy_lm_auth"
    for current, directories, files in os.walk(package_root, followlinks=False):
        if "__pycache__" in directories or any(name.endswith(".pyc") for name in files):
            raise ProviderOutcomeConsumerError("owner_bytecode_posture_drift")
        if any((Path(current) / name).is_symlink() for name in directories):
            raise ProviderOutcomeConsumerError("owner_bytecode_posture_drift")


def verify_foundry_jury_owner_source(source_root: Path) -> dict[str, Any]:
    """Verify the exact clean maintained-fork source without importing it."""

    root = source_root.expanduser().resolve(strict=True)
    _verify_no_bytecode(root)
    identity = verify_owner_source(root, FOUNDRY_JURY_OWNER_SOURCE)
    for relative, expected_sha256 in _EXTRA_OWNER_FILES.items():
        path = root / relative
        try:
            info = path.lstat()
            raw = path.read_bytes()
        except OSError as exc:
            raise ProviderOutcomeConsumerError("owner_source_file_drift") from exc
        if (
            path.is_symlink()
            or not stat.S_ISREG(info.st_mode)
            or hashlib.sha256(raw).hexdigest() != expected_sha256
        ):
            raise ProviderOutcomeConsumerError("owner_source_file_drift")
    return identity


@dataclass(frozen=True, slots=True)
class VerifiedFoundryJuryOwner:
    artifact: VerifiedOwnerArtifact
    backend_type: type[Any]
    message_type: type[Any]
    request_type: type[Any]
    response_type: type[Any]
    backend_module: Any
    receipt_module: Any
    source_root: Path

    def revalidate(self) -> None:
        verify_foundry_jury_owner_source(self.source_root)
        self.artifact.revalidate()
        source = inspect.getsourcefile(self.backend_type)
        expected = self.source_root / "src/dspy_lm_auth/codex_backend.py"
        if (
            self.backend_type.__module__ != "dspy_lm_auth.codex_backend"
            or self.backend_type.__name__ != "CodexBackend"
            or issubclass(self.backend_type, BaseLM)
            or source is None
            or Path(source).resolve(strict=True) != expected.resolve(strict=True)
            or self.message_type.__module__ != "dspy_lm_auth.codex_backend_contract"
            or self.message_type.__name__ != "CodexBackendMessage"
            or self.request_type.__module__ != "dspy_lm_auth.codex_backend_contract"
            or self.request_type.__name__ != "CodexBackendRequest"
            or self.response_type.__module__ != "dspy_lm_auth.codex_backend_contract"
            or self.response_type.__name__ != "CodexBackendResponse"
        ):
            raise ProviderOutcomeConsumerError("loaded_owner_backend_type_drift")


def verify_loaded_foundry_jury_owner(source_root: Path) -> VerifiedFoundryJuryOwner:
    """Import only after the outer attempt marker and bind exact loaded owner types."""

    import importlib

    root = source_root.expanduser().resolve(strict=True)
    if any(
        name == "dspy_lm_auth" or name.startswith("dspy_lm_auth.")
        for name in sys.modules
    ):
        raise ProviderOutcomeConsumerError("owner_module_preloaded")
    source_path = root / "src"
    sys.path.insert(0, str(source_path))
    try:
        package = importlib.import_module("dspy_lm_auth")
        backend_module = importlib.import_module("dspy_lm_auth.codex_backend")
        receipt_module = importlib.import_module("dspy_lm_auth.outcome_receipt")
        if "dspy_lm_auth.lm" in sys.modules:
            raise ProviderOutcomeConsumerError("loaded_owner_legacy_lm_present")
        event_type = getattr(package, "OutcomeReceiptEvent", None)
        receipt_type = getattr(package, "ProviderOutcomeReceipt", None)
        backend_type = getattr(package, "CodexBackend", None)
        message_type = getattr(package, "CodexBackendMessage", None)
        request_type = getattr(package, "CodexBackendRequest", None)
        response_type = getattr(package, "CodexBackendResponse", None)
        owner_types = (
            event_type,
            receipt_type,
            backend_type,
            message_type,
            request_type,
            response_type,
        )
        if not all(isinstance(item, type) for item in owner_types):
            raise ProviderOutcomeConsumerError("loaded_owner_api_drift")
        artifact = verify_owner_artifact(
            root,
            cast(type[Any], event_type),
            cast(type[Any], receipt_type),
            FOUNDRY_JURY_OWNER_SOURCE,
        )
        owner = VerifiedFoundryJuryOwner(
            artifact=artifact,
            backend_type=cast(type[Any], backend_type),
            message_type=cast(type[Any], message_type),
            request_type=cast(type[Any], request_type),
            response_type=cast(type[Any], response_type),
            backend_module=backend_module,
            receipt_module=receipt_module,
            source_root=root,
        )
        owner.revalidate()
        return owner
    except BaseException:
        for name in tuple(sys.modules):
            if name == "dspy_lm_auth" or name.startswith("dspy_lm_auth."):
                sys.modules.pop(name, None)
        raise
    finally:
        try:
            sys.path.remove(str(source_path))
        except ValueError:
            pass
