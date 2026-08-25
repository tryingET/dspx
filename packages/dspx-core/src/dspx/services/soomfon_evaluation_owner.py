"""Exact AK-5070 provider-owner source and dependency identity."""

from __future__ import annotations

import hashlib
import inspect
import os
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

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

OWNER_CANDIDATE_WHEEL_SHA256: None = None
OWNER_CANDIDATE_INSTALLED_PAYLOAD_SHA256: None = None
REQUESTED_ROUTE = "dspy-lm-auth:codex:gpt-5.6-luna:xhigh"
RESOLVED_ROUTE = "openai:gpt-5.6-luna:responses"
REQUESTED_MODEL = "codex/gpt-5.6-luna"
RESOLVED_MODEL = "openai/gpt-5.6-luna"
OBSERVED_MODEL = "gpt-5.6-luna"
AUTH_PROVIDER = "codex"
CREDENTIAL_MODE = "no-refresh"
REASONING_EFFORT = "xhigh"
TIMEOUT_SECONDS = 60.0
MAX_SUITE_LOGICAL_CALLS = 12
ENDPOINT_ORIGIN_SHA256 = (
    "7d4b206e8a080358f16d8048e0705d8e17c9df9b8968ab150ff73ed1643294c8"
)

_OWNER_MODULES: dict[str, tuple[str, str]] = {
    "package_init": (
        "src/dspy_lm_auth/__init__.py",
        "1a4406dcf9b65ce3eb937ee65541cff3cb10ef77fa5c0f24c1e94755aeafd2ab",
    ),
    "lm": (
        "src/dspy_lm_auth/lm.py",
        "678ee949f285847f92e246a1cc7042de4486c93617c5f24ad472defb65dec6c7",
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
        "f26c675845b3f234c24a868d4a7d6cd13713b26d1ba992a6d28ff2a3b7327293",
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
        "1830d79944869e8916526cf9fbe9adbc429dfaefbb1bf189d26caebbfed84ac6",
    ),
    "httpx": ExpectedDependency(
        "httpx",
        "0.28.1",
        "d909fcccc110f8c7faf814ca82a9a4d816bc5a6dbfea25d6591d6985b8ba59ad",
        24,
        "07414d29fb1941459875ce8779ba8b64ffb35df39b38cccbb81db96aceb23ed3",
        "36876854dd991fdbea093ead83f852baf1d9e777126dac8e5d6b722ce0753e92",
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

SOOMFON_OWNER_SOURCE = ExpectedOwnerSource(
    commit="4bdc3bb2e341b8ebff088828c8604ff8051b5d49",
    tree="816c77372e5e9becd5ecc5b95d336625ceb56815",
    version="0.1.6.dev0",
    lock_sha256="0b18a1759b2507967ed8f2f4918c436e2679e406aafb061620a11954b1550c7c",
    modules=_OWNER_MODULES,
    dependencies=_OWNER_DEPENDENCIES,
)


def _verify_owner_no_bytecode(source_root: Path) -> None:
    if sys.dont_write_bytecode is not True:
        raise ProviderOutcomeConsumerError("owner_bytecode_posture_drift")
    try:
        package_root = (
            source_root.expanduser().resolve(strict=True) / "src/dspy_lm_auth"
        )
        if not package_root.is_dir():
            raise OSError("owner package root is unavailable")
        for current, directories, files in os.walk(package_root, followlinks=False):
            if "__pycache__" in directories or any(
                name.endswith(".pyc") for name in files
            ):
                raise ProviderOutcomeConsumerError("owner_bytecode_posture_drift")
            if any((Path(current) / name).is_symlink() for name in directories):
                raise ProviderOutcomeConsumerError("owner_bytecode_posture_drift")
    except OSError as exc:
        raise ProviderOutcomeConsumerError("owner_bytecode_posture_drift") from exc
    for name, module in tuple(sys.modules.items()):
        if name == "dspy_lm_auth" or name.startswith("dspy_lm_auth."):
            cached = getattr(module, "__cached__", None)
            if isinstance(cached, str) and Path(cached).exists():
                raise ProviderOutcomeConsumerError("owner_bytecode_posture_drift")


def verify_soomfon_owner_source(source_root: Path) -> dict[str, Any]:
    """Verify the exact AK-5070 source worktree without importing it."""

    _verify_owner_no_bytecode(source_root)
    identity = verify_owner_source(source_root, SOOMFON_OWNER_SOURCE)
    auth_path = (
        source_root.expanduser().resolve(strict=True) / "src/dspy_lm_auth/auth.py"
    )
    try:
        info = auth_path.lstat()
        raw = auth_path.read_bytes()
    except OSError as exc:
        raise ProviderOutcomeConsumerError("owner_source_file_drift") from exc
    if (
        auth_path.is_symlink()
        or not stat.S_ISREG(info.st_mode)
        or hashlib.sha256(raw).hexdigest()
        != "e1cfd9add7779e134236c52c047138c4d62944ef928e42e1c9a2fdcb9c916b2c"
    ):
        raise ProviderOutcomeConsumerError("owner_source_file_drift")
    return identity


def expected_owner_source_identity() -> dict[str, Any]:
    return {
        "owner": "tryinget-dspy-lm-auth",
        "version": SOOMFON_OWNER_SOURCE.version,
        "commit": SOOMFON_OWNER_SOURCE.commit,
        "tree": SOOMFON_OWNER_SOURCE.tree,
        "lock_sha256": SOOMFON_OWNER_SOURCE.lock_sha256,
        "module_sha256": {
            name: digest
            for name, (_, digest) in sorted(SOOMFON_OWNER_SOURCE.modules.items())
        },
    }


def expected_owner_dependency_identity() -> dict[str, Any]:
    return {
        name: {
            "version": item.version,
            "locked_wheel_sha256": item.wheel_sha256,
            "payload_count": item.payload_count,
            "payload_sha256": item.payload_sha256,
            "record_sha256": item.record_sha256,
        }
        for name, item in sorted(SOOMFON_OWNER_SOURCE.dependencies.items())
    }


def owner_authorization_identity() -> dict[str, str]:
    return {
        "commit": SOOMFON_OWNER_SOURCE.commit,
        "tree": SOOMFON_OWNER_SOURCE.tree,
        "version": SOOMFON_OWNER_SOURCE.version,
        "lock_sha256": SOOMFON_OWNER_SOURCE.lock_sha256,
    }


@dataclass(frozen=True, slots=True)
class VerifiedSoomfonOwner:
    artifact: VerifiedOwnerArtifact
    lm_type: type[Any]
    lm_module: Any
    receipt_module: Any
    source_root: Path

    def revalidate(self) -> None:
        verify_soomfon_owner_source(self.source_root)
        self.artifact.revalidate()
        source = inspect.getsourcefile(self.lm_type)
        expected = self.source_root / SOOMFON_OWNER_SOURCE.modules["lm"][0]
        if (
            self.lm_type.__module__ != "dspy_lm_auth.lm"
            or self.lm_type.__name__ != "LM"
            or source is None
            or Path(source).resolve(strict=True) != expected.resolve(strict=True)
        ):
            raise ProviderOutcomeConsumerError("loaded_owner_lm_type_drift")


def verify_loaded_soomfon_owner(source_root: Path) -> VerifiedSoomfonOwner:
    """Import only after the suite marker, then bind exact loaded owner types."""

    import importlib
    import sys

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
        lm_module = importlib.import_module("dspy_lm_auth.lm")
        receipt_module = importlib.import_module("dspy_lm_auth.outcome_receipt")
        event_type = getattr(package, "OutcomeReceiptEvent", None)
        receipt_type = getattr(package, "ProviderOutcomeReceipt", None)
        lm_type = getattr(lm_module, "LM", None)
        if not all(
            isinstance(item, type) for item in (event_type, receipt_type, lm_type)
        ):
            raise ProviderOutcomeConsumerError("loaded_owner_api_drift")
        artifact = verify_owner_artifact(
            root,
            cast(type[Any], event_type),
            cast(type[Any], receipt_type),
            SOOMFON_OWNER_SOURCE,
        )
        owner = VerifiedSoomfonOwner(
            artifact=artifact,
            lm_type=cast(type[Any], lm_type),
            lm_module=lm_module,
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
