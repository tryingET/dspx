# summary: "Tests fail-closed Core package release-evidence claim distinctions."

from __future__ import annotations

import copy
import hashlib
import importlib.util
from io import BytesIO
import json
from pathlib import Path
import sys
import tarfile
from types import ModuleType
from typing import Any
import zipfile

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts/ci/core_release_evidence.py"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("core_release_evidence", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    script_dir = str(SCRIPT_PATH.parent)
    sys.path.insert(0, script_dir)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.pop(spec.name, None)
        sys.path.remove(script_dir)


def _wheel(path: Path, *, marker: str = "original") -> str:
    metadata = (
        "Metadata-Version: 2.4\n"
        "Name: dspx-core\n"
        "Version: 0.1.0\n"
        "Requires-Python: >=3.13\n"
        "\n"
    ).encode()
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("dspx_core-0.1.0.dist-info/METADATA", metadata)
        archive.writestr("dspx/__init__.py", f"MARKER = {marker!r}\n")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sdist(
    path: Path, *, package_name: str = "dspx-core", add_pkg_info_alias: bool = False
) -> None:
    files = {
        "dspx_core-0.1.0/PKG-INFO": (
            f"Metadata-Version: 2.4\nName: {package_name}\nVersion: 0.1.0\n\n".encode()
        ),
        "dspx_core-0.1.0/pyproject.toml": (
            b"[project]\nname='dspx-core'\nversion='0.1.0'\n"
        ),
        "dspx_core-0.1.0/src/dspx/__init__.py": b"__version__ = '0.1.0'\n",
    }
    if add_pkg_info_alias:
        files["dspx_core-0.1.0/./PKG-INFO"] = files["dspx_core-0.1.0/PKG-INFO"]
    with tarfile.open(path, "w:gz") as archive:
        for name, raw in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(raw)
            archive.addfile(info, BytesIO(raw))


def _proof(path: Path, *, wheel_path: Path, wheel_sha256: str) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "dspx-installed-core-golden-path-proof-v2",
                "status": "passed",
                "provider": "stub",
                "oracle_embedding_backend": "mock",
                "oracle_semantic_claim": "plumbing_only_not_production_semantics",
                "behavior_status": "passed",
                "receipt_check_status": "ok",
                "replay_claim_matrix_schema": "dspx-replay-claim-matrix-v1",
                "candidate_identity": {
                    "assembly_id": "assembly-1",
                    "candidate_id": "candidate-1",
                    "episode_id": "episode-1",
                    "receipt_bundle_id": "bundle-1",
                    "request_id": "request-1",
                },
                "evidence_hashes": {
                    "manifest_sha256": "1" * 64,
                    "intent_sha256": "2" * 64,
                    "behavior_episode_sha256": "3" * 64,
                    "behavior_results_sha256": "4" * 64,
                    "oracle_evidence_sha256": "5" * 64,
                    "oracle_report_sha256": "6" * 64,
                },
                "oracle_record_count": 1,
                "workflow_declared_effects": {
                    "shared_oracle_mutated": False,
                    "ak_called": False,
                    "governance_mutated": False,
                    "external_authority_mutated": False,
                    "promotion_applied": False,
                    "winner_selected": False,
                },
                "non_authority": {
                    "release_readiness": False,
                    "live_provider_proof": False,
                    "semantic_quality_approval": False,
                    "network_isolation_proven": False,
                    "absolute_path_external_effects_excluded": False,
                    "promotion_authority": False,
                    "activation_authority": False,
                },
                "artifact_under_test": {
                    "filename": wheel_path.name,
                    "sha256": wheel_sha256,
                    "distribution_name": "dspx-core",
                    "distribution_version": "0.1.0",
                    "direct_url_bound": True,
                    "installed_payload_record_verified": True,
                    "installed_payload_file_count": 2,
                },
                "install": {
                    "module_path": "/venv/site-packages/dspx/__init__.py",
                    "distribution_version": "0.1.0",
                },
                "independent_effect_observations": {
                    "path_resolved_ak_canary_invoked": False
                },
            }
        ),
        encoding="utf-8",
    )


def _inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    wheel = tmp_path / "dspx_core-0.1.0-py3-none-any.whl"
    sdist = tmp_path / "dspx_core-0.1.0.tar.gz"
    proof = tmp_path / "installed-proof.json"
    wheel_hash = _wheel(wheel)
    _sdist(sdist)
    _proof(proof, wheel_path=wheel, wheel_sha256=wheel_hash)
    return wheel, sdist, proof


def _build(
    module: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, Any]:
    wheel, sdist, proof = _inputs(tmp_path)

    def fake_git(_repo: Path, *args: str) -> str:
        if args == ("rev-parse", "HEAD"):
            return "a" * 40
        if args == ("status", "--porcelain=v1", "--untracked-files=all"):
            return " M scripts/ci/package-check.sh"
        raise AssertionError(args)

    monkeypatch.setattr(module, "_git", fake_git)
    return module.build_evidence(
        repo_root=REPO_ROOT,
        wheel_path=wheel,
        sdist_path=sdist,
        installed_proof_path=proof,
    )


def test_build_evidence_binds_exact_wheel_and_denies_release_claims(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_module()
    evidence = _build(module, tmp_path, monkeypatch)

    wheel_subject = next(
        subject for subject in evidence["subjects"] if subject["role"] == "core-wheel"
    )
    assert evidence["installed_wheel_proof"]["wheel_sha256"] == wheel_subject["sha256"]
    assert evidence["source"] == {
        "git_commit": "a" * 40,
        "tree_state": "dirty",
        "commit_binding_status": "working_tree_not_commit_bound",
    }
    assert evidence["sbom"]["status"] == "not_generated"
    assert evidence["signature_verification"]["status"] == "not_present_not_verified"
    assert evidence["claims"] == {
        "artifact_hashes_verified": True,
        "installed_wheel_bytes_bound": True,
        "source_commit_clean": False,
        "build_provenance_attested": False,
        "sbom_verified": False,
        "artifact_signature_verified": False,
        "technical_release_evidence_complete": False,
        "release_readiness": False,
        "release_authority": False,
        "publication_performed": False,
    }


def test_build_evidence_rejects_same_version_substituted_wheel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_module()
    wheel, sdist, proof = _inputs(tmp_path)
    _wheel(wheel, marker="substituted")
    monkeypatch.setattr(module, "_git", lambda *_args: "")

    with pytest.raises(
        module.CoreReleaseEvidenceError, match="installed proof artifact sha256 drift"
    ):
        module.build_evidence(
            repo_root=REPO_ROOT,
            wheel_path=wheel,
            sdist_path=sdist,
            installed_proof_path=proof,
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda proof: proof.pop("provider"), "installed Core proof fields drift"),
        (
            lambda proof: proof["workflow_declared_effects"].update(
                {"external_authority_mutated": True}
            ),
            "installed proof effects drift",
        ),
        (
            lambda proof: proof["artifact_under_test"].update(
                {"installed_payload_record_verified": False}
            ),
            "installed proof artifact installed_payload_record_verified drift",
        ),
        (
            lambda proof: proof["artifact_under_test"].update({"direct_url_bound": 1}),
            "installed proof artifact direct_url_bound drift",
        ),
        (
            lambda proof: proof.update({"oracle_record_count": True}),
            "installed proof oracle_record_count drift",
        ),
    ],
)
def test_build_evidence_rejects_truncated_or_widened_installed_proof(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: Any,
    message: str,
) -> None:
    module = _load_module()
    wheel, sdist, proof_path = _inputs(tmp_path)
    proof = json.loads(proof_path.read_text(encoding="utf-8"))
    mutation(proof)
    proof_path.write_text(json.dumps(proof), encoding="utf-8")
    monkeypatch.setattr(module, "_git", lambda *_args: "")

    with pytest.raises(module.CoreReleaseEvidenceError, match=message):
        module.build_evidence(
            repo_root=REPO_ROOT,
            wheel_path=wheel,
            sdist_path=sdist,
            installed_proof_path=proof_path,
        )


def test_build_evidence_rejects_sdist_metadata_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_module()
    wheel, sdist, proof = _inputs(tmp_path)
    _sdist(sdist, package_name="substituted-core")
    monkeypatch.setattr(module, "_git", lambda *_args: "")

    with pytest.raises(
        module.CoreReleaseEvidenceError, match="sdist package name drift"
    ):
        module.build_evidence(
            repo_root=REPO_ROOT,
            wheel_path=wheel,
            sdist_path=sdist,
            installed_proof_path=proof,
        )


def test_build_evidence_rejects_sdist_canonical_path_alias(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_module()
    wheel, sdist, proof = _inputs(tmp_path)
    _sdist(sdist, add_pkg_info_alias=True)
    monkeypatch.setattr(module, "_git", lambda *_args: "")

    with pytest.raises(
        module.CoreReleaseEvidenceError, match="sdist contains an unsafe path"
    ):
        module.build_evidence(
            repo_root=REPO_ROOT,
            wheel_path=wheel,
            sdist_path=sdist,
            installed_proof_path=proof,
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda value: value.update({"release_approved": True}),
            "Core release evidence fields drift",
        ),
        (
            lambda value: value["claims"].update({"release_readiness": True}),
            "release evidence claim matrix drift",
        ),
        (
            lambda value: value["claims"].update({"release_readiness": 0}),
            "release evidence claim matrix drift",
        ),
        (
            lambda value: value["subjects"][0].update({"sha256": "x" * 64}),
            "release subject 0 hash is invalid",
        ),
        (
            lambda value: value["subjects"][0].update({"size": True}),
            "release subject 0 size is invalid",
        ),
        (
            lambda value: value["installed_wheel_proof"].update({"sha256": None}),
            "installed proof hash is invalid",
        ),
        (
            lambda value: value["sbom"].update(
                {"status": "verified", "format": "CycloneDX"}
            ),
            "SBOM status drift",
        ),
        (
            lambda value: value["signature_verification"].update(
                {"status": "verified", "subject_hashes_verified": True}
            ),
            "signature status drift",
        ),
        (
            lambda value: value["source"].update(
                {
                    "tree_state": "clean",
                    "commit_binding_status": "commit_bound_clean_tree",
                }
            ),
            "source tree truth drift",
        ),
    ],
)
def test_validator_rejects_success_shaped_claim_widening(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: Any,
    message: str,
) -> None:
    module = _load_module()
    evidence = _build(module, tmp_path, monkeypatch)
    widened = copy.deepcopy(evidence)
    mutation(widened)

    with pytest.raises(module.CoreReleaseEvidenceError, match=message):
        module.validate_evidence(widened)


def test_build_evidence_rejects_symlinked_release_subject(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_module()
    wheel, sdist, proof = _inputs(tmp_path)
    linked = tmp_path / "linked.whl"
    linked.symlink_to(wheel)
    monkeypatch.setattr(module, "_git", lambda *_args: "")

    with pytest.raises(
        module.CoreReleaseEvidenceError, match="non-symlink regular file"
    ):
        module.build_evidence(
            repo_root=REPO_ROOT,
            wheel_path=linked,
            sdist_path=sdist,
            installed_proof_path=proof,
        )
