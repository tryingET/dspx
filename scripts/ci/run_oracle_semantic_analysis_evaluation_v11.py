#!/usr/bin/env python3
# summary: "Deterministic stdlib bootstrap into exact-repository v11 gate modules."
from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.machinery
from importlib.abc import Loader, MetaPathFinder
import json
import os
from pathlib import Path
import stat
import sys
import sysconfig
from types import ModuleType

# Updated only after all reviewed entry-module bytes are final.
_ENTRY_SHA256 = {
    "dspx.services.program_oracle_semantic_gate4_v11": "9e60fae9d050220081e77af6dacfe1b60ddb36fa9759a29d52a82c894e105c8a",
    "dspx.services.program_oracle_semantic_gate5_v11": "87d8a0127aa8d010b97d0c651d3f47fb1ad92d63900ab3de1ddc2a45512beb3b",
    "dspx.services.program_oracle_semantic_verification_v11": "c1086235651c02d821225a9655cde5e2375bd4104e35e943c58429e3177de870",
}
_ENTRY_RELATIVE = {
    name: "packages/dspx-core/src/" + name.replace(".", "/") + ".py"
    for name in _ENTRY_SHA256
}

# Complete hardcoded union of every local module transitively importable by any
# entry. All bytes are checked before repository source enters sys.path.
_PRELEDGER_SHA256: dict[str, str] = {
    "packages/dspx-core/src/dspx/__init__.py": "b92564aaa451a55cabd711c2c6c40c4bea5bec4055b2ad05da8f101d3d765109",
    "packages/dspx-core/src/dspx/capabilities.py": "135dd98c17477112dbbf7a4090a068c60a8dc54f5fd825ab73928bdc64dc7bc1",
    "packages/dspx-core/src/dspx/dspy_typed_lm.py": "b4b4127ac151e8fbb6b039d7679cf2169244a37b8fa11e5573843e5b8c64b6f1",
    "packages/dspx-core/src/dspx/model_roles.py": "a7a4dc03afcbc2726d62ab4b11b951bf8d32c069652d34423c3ec08e751015a2",
    "packages/dspx-core/src/dspx/openai_compatible_provider.py": "df4ed50f569b4e04757592468a7f908f940b8629eef796932423357b688e5241",
    "packages/dspx-core/src/dspx/policy.py": "cf7ba7d0919d3e5f15ce4c2a40b59a4bc535eb0eea1851aefe82ccc25057cdbe",
    "packages/dspx-core/src/dspx/provider_contract.py": "b16640fda28a0b8c6188a3781879d44ee4091e27b7968dce6e57e65e7d5f0fb7",
    "packages/dspx-core/src/dspx/provider_registry.py": "237fa4d9aa1b153bc3ccf45f5676c29b3efcac4ae32575e1935557a34361a6cb",
    "packages/dspx-core/src/dspx/redaction.py": "fb9750d8e802c1625400e7819b4a899a0203bff98d9f864c0178bac1e5573058",
    "packages/dspx-core/src/dspx/services/__init__.py": "afcc32ac4e9a017e5fb025cd04ef23435e4adb07460be3d166fce0c66de9946f",
    "packages/dspx-core/src/dspx/services/program_oracle_secret_policy.py": "222e09710780269746a870f85053f47fa0ecd4d81c59df8d46892d9eabd0767a",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_adapter_v11.py": "9ea371db0cb0b750a11416f32a467423e2d88d1fc467c005a46858ca2184d037",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_artifacts_v11.py": "7bcce2dd4da1c63ddcdbcc84d6e38953eb7ca41e1bbd928a91da02285d755f58",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_authority_v11.py": "8044dfe938b768d6df180bfb79c8b8bb46e533f18b9ed736b622af5dd6c62811",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_backend.py": "ba4c983f12f478f58ef17590b22a68ee241fa8a249f79918de8a2622f6dc60f2",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_contract.py": "099ee0a8f208df4e0d6ee3e4295c9dc4459ea00079572661588b9749ace3d8f4",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_contract_v10.py": "a563ec97b6f4864affd290882a3e7aa1d6fd082df5b545422820e6a46bc7f065",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_contract_v11.py": "06ade270323a08aabe4e2b4c48c0208208d9de2a983e9a13fb8e05b654a2df0a",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_evaluation.py": "a3d01f533f21fafd437b681d9cc82b6e0515e1068d680b5ae7c3848f0cd8a6d2",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_evaluation_v11.py": "a7cc4eefe20247c95bf0eb35e688ca999f4e540b9d733b1be02ffc6b8e0252dd",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_evidence_v11.py": "63d8e70185822a06e8d05c9ab0f0552da8bae820a01d96056d50aa27a504d15f",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_gate4_contract_v11.py": "042fd6491306743cb884acdc8cc8792bfc3e2d0ae3a93b02e92f8c6ca1184e4a",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_gate4_v11.py": "9e60fae9d050220081e77af6dacfe1b60ddb36fa9759a29d52a82c894e105c8a",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_gate4_validation_v11.py": "72d686920d0f16546012e1fdddb3914548d49fbd492b7a933b37c1dc19ec69f0",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_gate5_authority_v11.py": "80165a1e54093eed6e41d2602a0c6122ee6ea9184a7b10c170d7a6ba0b234d76",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_gate5_journal_v11.py": "d4d6182441ad6e6e05e055bbed78871e7120cc8e617086a72065f755fbdca9af",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_gate5_persistence_v11.py": "65ada9f6f2e6e2fb6a745c2680844c1beba3bb3a66e58b35520fa5de23ad4c38",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_gate5_result_v11.py": "3a0921988e2281fdf5ecd6b715ccf73cec76f6fa77261b66fc8fd995ac9ad6b9",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_gate5_runtime_v11.py": "a27a92fc38adf5343633a30a00b2b9c043446014a5e8324bf58c3c0dc6e92a6f",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_gate5_semantics_v11.py": "3667ac9a649863bf15d0eee6614f58ac5fafe9c1a03ea99c7f38dff4c32ec30c",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_gate5_v11.py": "87d8a0127aa8d010b97d0c651d3f47fb1ad92d63900ab3de1ddc2a45512beb3b",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_identity_v11.py": "aa078fd65796d1f27d49865c25c05e19e3843999f75ffe4735203600bbfa9897",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_journal_v11.py": "bf4cc01f6dee7c8b51728bc8d024e53ec1d7cfdf21670aae0d2ef5b83ba0dc33",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_owner_bridge_v11.py": "40ad47e50149b1c04dfa14bb56645389d6be45e085674b83d736963be416882d",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_result_artifact_v11.py": "9dc695191f2b9da09c1a53ea618fea5516737caac9b818c7d6ba26c9c3f5a291",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_result_v11.py": "b4aaf996f51f95fd53a01e0d4eaa812ea4495bd493306f8bb68599a1a49c033f",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_review_grammar_v11.py": "9014eb85088bb2fe0cad27ab804305fe7484a412562428443bf3540170e24983",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_scoring.py": "bea8382b431bcf10de5df2854765f48299ae3c63e74a2b0cff04a88c36307e9f",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_state_v11.py": "bbf15471a94f0fea1dd7a4217c1c6a265200b87bae9e78d1a61a2f7254974ea2",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_verification_v11.py": "c1086235651c02d821225a9655cde5e2375bd4104e35e943c58429e3177de870",
    "packages/dspx-core/src/dspx/services/provider_outcome_receipt_contract.py": "08310ff976c47bb2a5a3003131ab4ce4b45787f1380418a96b109de6f1664d30",
    "packages/dspx-core/src/dspx/services/provider_outcome_receipt_identity.py": "9f8a40b1b22f5fc377fb44ceb21919d2c37b48e23c04802bf340cd3fa35fc5a2",
    "packages/dspx-core/src/dspx/services/provider_outcome_receipt_journal.py": "6e2df68d71f081192ac460ecab9acbc0c44445cc5014409279595a87a0a340a5",
    "packages/dspx-core/src/dspx/services/provider_outcome_receipt_reducer.py": "33efcd28db0443c30069bdcb2a77ae6c9772dde25c34b2b411892302d5e48a4c",
    "packages/dspx-core/src/dspx/stub_provider.py": "30d17deba346b69982451448c5bb6c368584a31829e0b708e6f2480271c26e6d",
    "packages/dspx-core/src/dspx/validators.py": "c26ef8318152b07f12edfe082e52663173bace546456be8762b6e9ef2c736737",
}


def _required_path(
    parser: argparse.ArgumentParser, value: Path | None, name: str
) -> Path:
    if value is None:
        parser.error(f"{name} is required for this operation")
    return value


def _required_int(parser: argparse.ArgumentParser, value: int | None, name: str) -> int:
    if value is None:
        parser.error(f"{name} is required for this operation")
    return value


def _source_bytes(path: Path) -> bytes:
    try:
        info = path.lstat()
        raw = path.read_bytes()
    except OSError as exc:
        raise RuntimeError("reviewed bootstrap source unavailable") from exc
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise RuntimeError("reviewed bootstrap source posture drift")
    return raw


def _sha256(path: Path) -> str:
    return hashlib.sha256(_source_bytes(path)).hexdigest()


def _verify_preledger_manifest(repo_root: Path) -> None:
    if not _PRELEDGER_SHA256:
        raise RuntimeError("reviewed preledger manifest unavailable")
    for relative, expected in _PRELEDGER_SHA256.items():
        if _sha256(repo_root / relative) != expected:
            raise RuntimeError(f"reviewed preledger module hash drift: {relative}")


class _VerifiedSourceLoader(MetaPathFinder, Loader):
    """Bounded DSPx finder that verifies and compiles source bytes only."""

    def __init__(self, repo_root: Path) -> None:
        self._root = repo_root
        self._modules: dict[str, tuple[str, Path, str]] = {}
        prefix = "packages/dspx-core/src/"
        for relative, digest in _PRELEDGER_SHA256.items():
            if not relative.startswith(prefix) or not relative.endswith(".py"):
                raise RuntimeError("reviewed source manifest member drift")
            suffix = relative[len(prefix) : -3]
            parts = suffix.split("/")
            if parts[-1] == "__init__":
                parts.pop()
            module_name = ".".join(parts)
            if not module_name.startswith("dspx") or module_name in self._modules:
                raise RuntimeError("reviewed source module identity drift")
            self._modules[module_name] = (
                relative,
                (repo_root / relative).resolve(strict=True),
                digest,
            )

    def find_spec(
        self,
        fullname: str,
        path: object = None,
        target: ModuleType | None = None,
    ) -> importlib.machinery.ModuleSpec | None:
        del path, target
        if fullname in {"dspx", "dspx.services"}:
            return None
        if fullname == "dspx" or fullname.startswith("dspx."):
            if fullname not in self._modules:
                raise ModuleNotFoundError(
                    f"unreviewed target DSPx module rejected: {fullname}"
                )
            _, source, _ = self._modules[fullname]
            return importlib.machinery.ModuleSpec(
                fullname, self, origin=str(source), is_package=False
            )
        return None

    def create_module(self, spec: importlib.machinery.ModuleSpec) -> None:
        del spec
        return None

    def exec_module(self, module: ModuleType) -> None:
        try:
            relative, source, expected = self._modules[module.__name__]
        except KeyError as exc:  # pragma: no cover - import protocol guard
            raise RuntimeError("unreviewed source loader request") from exc
        raw = _source_bytes(source)
        if hashlib.sha256(raw).hexdigest() != expected:
            raise RuntimeError(f"reviewed source hash drift during import: {relative}")
        module.__file__ = str(source)
        module.__cached__ = None
        code = compile(raw, str(source), "exec", dont_inherit=True)
        exec(code, module.__dict__)


def _assert_clean_stdlib_startup(script: Path) -> None:
    contaminated = [
        name for name in sys.modules if name == "dspx" or name.startswith("dspx.")
    ]
    if contaminated:
        raise RuntimeError("preloaded DSPx modules are forbidden")
    stdlib = Path(sysconfig.get_path("stdlib")).resolve(strict=True)
    allowed_files = {script.resolve(strict=True)}
    for name, module in tuple(sys.modules.items()):
        if not isinstance(module, ModuleType):
            raise RuntimeError("pre-entry module table shape drift")
        origin = getattr(module, "__file__", None)
        if origin is None:
            continue
        declared_path = Path(origin).absolute()
        try:
            path = declared_path.resolve(strict=True)
        except OSError as exc:
            raise RuntimeError("pre-entry module origin unavailable") from exc
        virtualenv_bootstrap = (
            name == "_virtualenv"
            and declared_path.name == "_virtualenv.py"
            and declared_path.is_relative_to(Path(sys.prefix).absolute())
        )
        if path in allowed_files or path.is_relative_to(stdlib) or virtualenv_bootstrap:
            continue
        raise RuntimeError(f"non-stdlib pre-entry module rejected: {name}")


def _package_stub(
    name: str,
    directory: Path,
    init_file: Path,
    loader: _VerifiedSourceLoader,
) -> ModuleType:
    # Package initializers are hash-checked and source-compiled too. They are not
    # executed because dspx.__init__ eagerly imports unrelated provider wrappers;
    # the bounded bootstrap needs only structural package namespaces.
    relative = init_file.relative_to(loader._root).as_posix()
    raw = _source_bytes(init_file)
    if hashlib.sha256(raw).hexdigest() != _PRELEDGER_SHA256.get(relative):
        raise RuntimeError("reviewed package source hash drift")
    compile(raw, str(init_file), "exec", dont_inherit=True)
    package = ModuleType(name)
    package.__file__ = str(init_file)
    package.__package__ = name
    package.__cached__ = None
    package.__loader__ = loader
    package.__path__ = [str(directory)]  # type: ignore[attr-defined]
    package.__spec__ = importlib.machinery.ModuleSpec(
        name, loader=loader, is_package=True
    )
    return package


def _prepare_target_packages(repo_root: Path) -> Path:
    root = repo_root.expanduser().resolve(strict=True)
    script = (
        root / "scripts/ci/run_oracle_semantic_analysis_evaluation_v11.py"
    ).resolve(strict=True)
    if Path(__file__).resolve(strict=True) != script:
        raise RuntimeError("bootstrap script is not the target-repository entry")
    _assert_clean_stdlib_startup(script)
    _verify_preledger_manifest(root)
    package_source = (root / "packages/dspx-core/src").resolve(strict=True)
    dspx_root = (package_source / "dspx").resolve(strict=True)
    services_root = (dspx_root / "services").resolve(strict=True)
    if not dspx_root.is_dir() or not services_root.is_dir():
        raise RuntimeError("target DSPx package source unavailable")
    exact = str(package_source)
    sys.path[:] = [item for item in sys.path if str(Path(item).resolve()) != exact]
    sys.dont_write_bytecode = True
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    loader = _VerifiedSourceLoader(root)
    sys.meta_path.insert(0, loader)
    sys.modules["dspx"] = _package_stub(
        "dspx", dspx_root, dspx_root / "__init__.py", loader
    )
    sys.modules["dspx.services"] = _package_stub(
        "dspx.services", services_root, services_root / "__init__.py", loader
    )
    return root


def _load_target_entry(repo_root: Path, module_name: str) -> ModuleType:
    if module_name not in _ENTRY_SHA256:
        raise RuntimeError("unknown reviewed bootstrap entry")
    root = _prepare_target_packages(repo_root)
    expected = (root / _ENTRY_RELATIVE[module_name]).resolve(strict=True)
    if _sha256(expected) != _ENTRY_SHA256[module_name]:
        raise RuntimeError("reviewed bootstrap entry hash drift")
    module = importlib.import_module(module_name)
    origin = getattr(module, "__file__", None)
    if (
        not isinstance(origin, str)
        or origin.endswith((".pyc", ".pyo"))
        or Path(origin).resolve(strict=True) != expected
        or getattr(module, "__cached__", None) is not None
    ):
        raise RuntimeError("reviewed bootstrap entry origin drift")
    return module


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Provider-free inspect or enter one exact Oracle semantic v11 gate"
    )
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--task-binding-check", type=int)
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument("--execute-live", action="store_true")
    operation.add_argument("--verify-retained", action="store_true")
    parser.add_argument("--state-root", type=Path)
    parser.add_argument("--owner-source-root", type=Path)
    parser.add_argument("--live-task-id", type=int)
    parser.add_argument("--remediation-validation-evidence-id", type=int)
    parser.add_argument("--review-evidence-id", type=int)
    parser.add_argument("--operator-evidence-id", type=int)
    parser.add_argument("--live-gate-evidence-id", type=int)
    parser.add_argument("--gate5-task-id", type=int)
    parser.add_argument("--gate5-evidence-id", type=int)
    args = parser.parse_args()

    if args.execute_live:
        module = _load_target_entry(
            args.repo, "dspx.services.program_oracle_semantic_gate4_v11"
        )
        payload = module.execute_live_once(
            repo_root=args.repo,
            state_root=_required_path(parser, args.state_root, "--state-root"),
            owner_source_root=_required_path(
                parser, args.owner_source_root, "--owner-source-root"
            ),
            live_task_id=_required_int(parser, args.live_task_id, "--live-task-id"),
            remediation_validation_evidence_id=_required_int(
                parser,
                args.remediation_validation_evidence_id,
                "--remediation-validation-evidence-id",
            ),
            review_evidence_id=_required_int(
                parser, args.review_evidence_id, "--review-evidence-id"
            ),
            operator_evidence_id=_required_int(
                parser, args.operator_evidence_id, "--operator-evidence-id"
            ),
            live_gate_evidence_id=_required_int(
                parser, args.live_gate_evidence_id, "--live-gate-evidence-id"
            ),
        )
    elif args.verify_retained:
        module = _load_target_entry(
            args.repo, "dspx.services.program_oracle_semantic_gate5_v11"
        )
        payload = module.verify_retained_once(
            repo_root=args.repo,
            state_root=_required_path(parser, args.state_root, "--state-root"),
            live_task_id=_required_int(parser, args.live_task_id, "--live-task-id"),
            gate5_task_id=_required_int(parser, args.gate5_task_id, "--gate5-task-id"),
            gate5_evidence_id=_required_int(
                parser, args.gate5_evidence_id, "--gate5-evidence-id"
            ),
            owner_source_root=_required_path(
                parser, args.owner_source_root, "--owner-source-root"
            ),
        )
    else:
        module = _load_target_entry(
            args.repo, "dspx.services.program_oracle_semantic_verification_v11"
        )
        payload = module.candidate_manifest(args.repo)
        if args.task_binding_check is not None:
            state_root = _required_path(parser, args.state_root, "--state-root")
            artifacts = importlib.import_module(
                "dspx.services.program_oracle_semantic_artifacts_v11"
            )
            contract = importlib.import_module(
                "dspx.services.program_oracle_semantic_gate4_contract_v11"
            )
            payload["task_binding"] = artifacts.TaskBinding.create(
                args.task_binding_check,
                contract.REQUIRED_LIVE_COMPLETION_KIND,
                state_root,
            ).payload()
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
