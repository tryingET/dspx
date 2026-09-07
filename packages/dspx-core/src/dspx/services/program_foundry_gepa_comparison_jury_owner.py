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

from dspx.services.program_foundry_gepa_comparison_jury_provider_family import (
    CODEX_FAMILY,
    FoundryJuryProviderFamily,
)
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

# ---------------------------------------------------------------------------
# BEGIN OWNER PIN BLOCK
# Regenerate with:
#   uv run --no-sync python tests/foundry_jury_owner_repin.py --print-pins <root>
# _OWNER_MODULES is the closed 8-name set bound into every receipt's
# source_identity (provider_outcome_receipt_contract); every other reviewed
# owner file is hash-pinned through _EXTRA_OWNER_FILES.
# ---------------------------------------------------------------------------
OWNER_COMMIT = "a893382e3a7abc06de0814f29709b9143b930826"
OWNER_TREE = "a4c4b050e2bace57586119d2e8ae9865511484d8"
OWNER_VERSION = "0.1.6"
OWNER_LOCK_SHA256 = "d24ee392e2846b3baac33e16a67ff3e9094b3b021c67e32e50a1f1d11b077648"

_OWNER_MODULES: dict[str, tuple[str, str]] = {
    "package_init": (
        "src/dspy_lm_auth/__init__.py",
        "5f180cf9f7c44a894b0b51c91ba4765b55d71c036b5f49ea2b0a97823803b844",
    ),
    "lm": (
        "src/dspy_lm_auth/lm.py",
        "debdc961e777c12fcdfecdbdd5291e47c05af8fcb14acaa057197ce2676f7794",
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
        "75f03052f5f4ca3cc7f35476fca213efead3622edf698a070cd432883ba581c4",
    ),
    "outcome_receipt_state": (
        "src/dspy_lm_auth/outcome_receipt_state.py",
        "8bef689cd29fd201973ad357056b8f82a307e002e9d59c39e04f38dd65f1a06f",
    ),
    "outcome_receipt_runtime": (
        "src/dspy_lm_auth/outcome_receipt_runtime.py",
        "fd6ce57588809547db492605b6b13c5ac2dd2f21df4796b156dff454816a3f29",
    ),
    "outcome_receipt_transport": (
        "src/dspy_lm_auth/outcome_receipt_transport.py",
        "e8e03c81ffb0f767233b4f1ae8c0b750c5284c13b20eafafbdb9fa268d43b34a",
    ),
}

_EXTRA_OWNER_FILES = {
    "src/dspy_lm_auth/codex_backend.py": "afe459aec9ab2b28a6bf5535781cbcf0df71d38cbd047d1593837c2e2d9a3679",
    "src/dspy_lm_auth/codex_backend_contract.py": "c1df45aed46ed65ef80e95035cbac591e386d537970c8c5d12d648ab3fbb7ea6",
    "src/dspy_lm_auth/_codex_credential.py": "10cbf50b66b610d1ba76806a16f943779148f7aecd4a7a0ac2f2ba0cfc4e5264",
    "src/dspy_lm_auth/codex_request.py": "d8c8cce159daf757ab3bd4e13341f26df87448128ecd77171f87864b585f9ba3",
    "src/dspy_lm_auth/outcome_receipt_chat.py": "0d38f0d11fcfef1672c8fbb26a9bfbeb165b300d948acc65210897f257d33b56",
    "src/dspy_lm_auth/copilot_backend.py": "7e7185bc2b551c7191f524619afa63b555e8819436005f24a3aa5e4df71dbf7e",
    "src/dspy_lm_auth/copilot_backend_contract.py": "9625a7bf3b090b73bb8922f8197745d6e4155cbcd52dea82b33c2af5c8d233a4",
    "src/dspy_lm_auth/_copilot_credential.py": "3aeca6578ea7164c879e29bf32286a575daab85a4aa373084b9710a7f654023a",
    "src/dspy_lm_auth/copilot_receipt_transport.py": "052b2f0a966bac2986bbe7f274e272f396ccd5fb2c611d5dd7709ae0092ae61f",
    "src/dspy_lm_auth/copilot_receipt_runtime.py": "888f993678e9183dfcd622f8df8dcdaad7b4b2a4d86576af8df65b0069739241",
    "src/dspy_lm_auth/_route_policy.py": "7dece27cc0bf8e3cad087f6d476ea44f9db6331195fe606c50c688a40b80ec12",
    "src/dspy_lm_auth/auth.py": "b46b390a292ddb8eb6ab22c6a26958644047ca31cc121d773af3bf9cc7f75e7e",
    "src/dspy_lm_auth/chat_backend.py": "d907e2cbef270f49e8cc26bdffd8628195ea9e1d59bb739b774bd9eab7a41c9d",
    "src/dspy_lm_auth/chat_backend_contract.py": "fa0db50ef75591e66dc1cc9ddb1b1bac78570228ca221ef07ff820c502218f63",
    "src/dspy_lm_auth/chat_backend_runtime.py": "aea8be12952e13a8ce6de8a3bdb7c706ee1652e0e874e1d28b90066227f0c638",
    "src/dspy_lm_auth/chat_backend_transport.py": "13f32784ce2b5f6422674f977bc3ab97c356d2e1eeede71a9501d490e27099fe",
    "src/dspy_lm_auth/_chat_credential.py": "e34c49e76ae94b129e190549959780126750e0faf5eff831c6ae90648f4648f5",
    "src/dspy_lm_auth/xai_backend.py": "a3c30358b3b669a250aa58fe3e5b3b2fc48a2210dddb4321935a093b2f49767a",
    "src/dspy_lm_auth/local_vllm_backend.py": "992108f9895ddfc09c09ec4993c6fd69d37c91887466e71faeda05717481172d",
    "src/dspy_lm_auth/opencode_go_backend.py": "8337aee715f1dcada81b8d25bb8ca6eca2edbae00d218705df0039a7285c723d",
    "src/dspy_lm_auth/zai_backend.py": "c993c6bbea73f153fbc8a82b6fc86d602349f5a6e9039b00016cd9a0552cac35",
}
# ---------------------------------------------------------------------------
# END OWNER PIN BLOCK
# ---------------------------------------------------------------------------

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
    family: FoundryJuryProviderFamily = CODEX_FAMILY

    def revalidate(self) -> None:
        verify_foundry_jury_owner_source(self.source_root)
        self.artifact.revalidate()
        family = self.family
        try:
            source = inspect.getsourcefile(self.backend_type)
        except (TypeError, OSError):
            source = None
        expected = (
            self.source_root / "src" / (family.backend_module.replace(".", "/") + ".py")
        )
        contract = family.contract_module
        if (
            self.backend_type.__module__ != family.backend_module
            or self.backend_type.__name__ != family.backend_class
            or issubclass(self.backend_type, BaseLM)
            or "dspy_lm_auth.lm" in sys.modules
            or source is None
            or Path(source).resolve(strict=True) != expected.resolve(strict=True)
            or self.message_type.__module__ != contract
            or self.message_type.__name__ != family.message_class
            or self.request_type.__module__ != contract
            or self.request_type.__name__ != family.request_class
            or self.response_type.__module__ != contract
            or self.response_type.__name__ != family.response_class
        ):
            raise ProviderOutcomeConsumerError("loaded_owner_backend_type_drift")


def verify_loaded_foundry_jury_owner(
    source_root: Path,
    family: FoundryJuryProviderFamily = CODEX_FAMILY,
) -> VerifiedFoundryJuryOwner:
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
        backend_module = importlib.import_module(family.backend_module)
        receipt_module = importlib.import_module("dspy_lm_auth.outcome_receipt")
        if "dspy_lm_auth.lm" in sys.modules:
            raise ProviderOutcomeConsumerError("loaded_owner_legacy_lm_present")
        event_type = getattr(package, "OutcomeReceiptEvent", None)
        receipt_type = getattr(package, "ProviderOutcomeReceipt", None)
        backend_type = getattr(package, family.backend_class, None)
        message_type = getattr(package, family.message_class, None)
        request_type = getattr(package, family.request_class, None)
        response_type = getattr(package, family.response_class, None)
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
            family=family,
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
