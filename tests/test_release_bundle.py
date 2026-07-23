# summary: "Tests retained unsigned Core release bundle closure and atomic publication."

from __future__ import annotations

import hashlib
import importlib.util
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
from types import ModuleType
from typing import Any
import zipfile

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "scripts/ci"


def _load(name: str) -> ModuleType:
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPTS))
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.pop(spec.name, None)
        sys.path.remove(str(SCRIPTS))


def _wheel(path: Path, *, marker: str = "original") -> str:
    metadata = (
        "Metadata-Version: 2.4\n"
        "Name: dspx-core\n"
        "Version: 0.1.0\n"
        "Requires-Python: >=3.13\n\n"
    ).encode()
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("dspx_core-0.1.0.dist-info/METADATA", metadata)
        archive.writestr("dspx/__init__.py", f"MARKER = {marker!r}\n")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sdist(path: Path) -> None:
    files = {
        "dspx_core-0.1.0/PKG-INFO": (
            b"Metadata-Version: 2.4\nName: dspx-core\nVersion: 0.1.0\n\n"
        ),
        "dspx_core-0.1.0/pyproject.toml": (
            b"[project]\nname='dspx-core'\nversion='0.1.0'\n"
        ),
        "dspx_core-0.1.0/src/dspx/__init__.py": b"__version__ = '0.1.0'\n",
    }
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


def _inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[ModuleType, Path, Path, Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    release_module = _load("core_release_evidence")
    wheel = tmp_path / "dspx_core-0.1.0-py3-none-any.whl"
    sdist = tmp_path / "dspx_core-0.1.0.tar.gz"
    proof = tmp_path / "installed-proof.json"
    release_path = tmp_path / "release-evidence.json"
    wheel_hash = _wheel(wheel)
    _sdist(sdist)
    _proof(proof, wheel_path=wheel, wheel_sha256=wheel_hash)

    def fake_git(_repo: Path, *args: str) -> str:
        if args == ("rev-parse", "HEAD"):
            return "a" * 40
        if args == ("status", "--porcelain=v1", "--untracked-files=all"):
            return " M local-change"
        raise AssertionError(args)

    monkeypatch.setattr(release_module, "_git", fake_git)
    evidence = release_module.build_evidence(
        repo_root=REPO_ROOT,
        wheel_path=wheel,
        sdist_path=sdist,
        installed_proof_path=proof,
    )
    release_path.write_text(json.dumps(evidence), encoding="utf-8")
    bundle_module = _load("core_release_bundle")
    monkeypatch.setattr(bundle_module, "_git", fake_git)
    return bundle_module, wheel, sdist, proof, release_path


def _build(
    module: ModuleType,
    *,
    wheel: Path,
    sdist: Path,
    proof: Path,
    release: Path,
    out: Path,
) -> dict[str, Any]:
    return module.build_bundle(
        repo_root=REPO_ROOT,
        wheel_path=wheel,
        sdist_path=sdist,
        installed_proof_path=proof,
        release_evidence_path=release,
        out_path=out,
    )


def _rewrite_bundle(
    source: Path,
    destination: Path,
    mutation: Any,
) -> None:
    with zipfile.ZipFile(source) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    mutation(members)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_STORED) as archive:
        for name in sorted(members):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = 0o100600 << 16
            archive.writestr(info, members[name])


def test_bundle_retains_complete_unsigned_closure_deterministically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module, wheel, sdist, proof, release = _inputs(tmp_path, monkeypatch)
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"

    manifest = _build(
        module,
        wheel=wheel,
        sdist=sdist,
        proof=proof,
        release=release,
        out=first,
    )
    _build(
        module,
        wheel=wheel,
        sdist=sdist,
        proof=proof,
        release=release,
        out=second,
    )

    assert first.read_bytes() == second.read_bytes()
    assert stat_mode(first) == 0o600
    assert module.validate_bundle(first) == manifest
    assert module.BUNDLE_SCHEMA == "dspx-core-release-bundle-v1"
    assert module.PROVENANCE_SCHEMA == "dspx-core-local-build-provenance-v1"
    assert {row["role"] for row in manifest["files"]} == module._FILE_ROLES
    assert manifest["claims"] == module._BUNDLE_CLAIMS
    assert manifest["claims"]["local_provenance_retained"] is True
    assert manifest["claims"]["build_provenance_attested"] is False
    assert manifest["claims"]["sbom_generated"] is False
    assert manifest["claims"]["artifact_signature_verified"] is False
    assert manifest["claims"]["release_readiness"] is False
    assert manifest["claims"]["release_authority"] is False
    assert manifest["claims"]["publication_performed"] is False


def stat_mode(path: Path) -> int:
    return path.stat().st_mode & 0o777


def test_bundle_forces_mode_0600_under_restrictive_umask(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module, wheel, sdist, proof, release = _inputs(tmp_path, monkeypatch)
    out = tmp_path / "bundle.zip"
    prior_umask = os.umask(0o777)
    try:
        _build(
            module,
            wheel=wheel,
            sdist=sdist,
            proof=proof,
            release=release,
            out=out,
        )
    finally:
        os.umask(prior_umask)

    assert stat_mode(out) == 0o600


def test_descriptor_close_failure_is_non_authoritative_after_durability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load("core_release_bundle")
    monkeypatch.setattr(
        module.os,
        "close",
        lambda _descriptor: (_ for _ in ()).throw(OSError("injected close failure")),
    )

    module._close_quietly(123)


def test_bundle_rejects_preexisting_output_and_symlinked_subject(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module, wheel, sdist, proof, release = _inputs(tmp_path, monkeypatch)
    out = tmp_path / "bundle.zip"
    out.write_bytes(b"existing")
    with pytest.raises(module.CoreReleaseEvidenceError, match="already exists"):
        _build(
            module,
            wheel=wheel,
            sdist=sdist,
            proof=proof,
            release=release,
            out=out,
        )
    out.unlink()
    linked = tmp_path / "linked.whl"
    linked.symlink_to(wheel)
    with pytest.raises(
        module.CoreReleaseEvidenceError, match="non-symlink regular file"
    ):
        _build(
            module,
            wheel=linked,
            sdist=sdist,
            proof=proof,
            release=release,
            out=out,
        )
    assert not out.exists()


def test_bundle_rejects_source_observation_and_subject_substitution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module, wheel, sdist, proof, release = _inputs(tmp_path, monkeypatch)
    payload = json.loads(release.read_text(encoding="utf-8"))
    payload["source"]["git_commit"] = "b" * 40
    release.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(
        module.CoreReleaseEvidenceError, match="source observation drift"
    ):
        _build(
            module,
            wheel=wheel,
            sdist=sdist,
            proof=proof,
            release=release,
            out=tmp_path / "source-drift.zip",
        )

    module, wheel, sdist, proof, release = _inputs(tmp_path / "again", monkeypatch)
    _wheel(wheel, marker="substituted")
    with pytest.raises(
        module.CoreReleaseEvidenceError, match="core-wheel subject drift"
    ):
        _build(
            module,
            wheel=wheel,
            sdist=sdist,
            proof=proof,
            release=release,
            out=tmp_path / "subject-drift.zip",
        )


def test_bundle_validator_rejects_member_hash_and_unknown_member(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module, wheel, sdist, proof, release = _inputs(tmp_path, monkeypatch)
    valid = tmp_path / "valid.zip"
    _build(
        module,
        wheel=wheel,
        sdist=sdist,
        proof=proof,
        release=release,
        out=valid,
    )
    drift = tmp_path / "drift.zip"
    _rewrite_bundle(
        valid,
        drift,
        lambda members: members.__setitem__(wheel.name, b"substituted"),
    )
    with pytest.raises(module.CoreReleaseEvidenceError, match="member hash drift"):
        module.validate_bundle(drift)

    unknown = tmp_path / "unknown.zip"
    _rewrite_bundle(
        valid,
        unknown,
        lambda members: members.__setitem__("unexpected.txt", b"unexpected"),
    )
    with pytest.raises(module.CoreReleaseEvidenceError, match="closure drift"):
        module.validate_bundle(unknown)


def test_bundle_validator_rejects_provenance_claim_widening(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module, wheel, sdist, proof, release = _inputs(tmp_path, monkeypatch)
    valid = tmp_path / "valid.zip"
    _build(
        module,
        wheel=wheel,
        sdist=sdist,
        proof=proof,
        release=release,
        out=valid,
    )

    def widen(members: dict[str, bytes]) -> None:
        provenance = json.loads(members[module._PROVENANCE_NAME])
        provenance["claims"]["attestation_verified"] = True
        raw = module._json_bytes(provenance)
        members[module._PROVENANCE_NAME] = raw
        manifest = json.loads(members[module._MANIFEST_NAME])
        entry = next(
            item
            for item in manifest["files"]
            if item["role"] == "local-build-provenance"
        )
        entry["size"] = len(raw)
        entry["sha256"] = hashlib.sha256(raw).hexdigest()
        members[module._MANIFEST_NAME] = module._json_bytes(manifest)

    widened = tmp_path / "widened.zip"
    _rewrite_bundle(valid, widened, widen)
    with pytest.raises(module.CoreReleaseEvidenceError, match="provenance claim drift"):
        module.validate_bundle(widened)


def test_bundle_link_failure_leaves_no_success_shaped_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module, wheel, sdist, proof, release = _inputs(tmp_path, monkeypatch)
    out = tmp_path / "bundle.zip"

    def fail_link(*_args: Any, **_kwargs: Any) -> None:
        raise OSError("injected link failure")

    monkeypatch.setattr(module.os, "link", fail_link)
    with pytest.raises(OSError, match="injected link failure"):
        _build(
            module,
            wheel=wheel,
            sdist=sdist,
            proof=proof,
            release=release,
            out=out,
        )
    assert not out.exists()
    assert list(tmp_path.glob(".bundle.zip.*.tmp")) == []


def test_bundle_rejects_symlinked_ancestor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module, wheel, sdist, proof, release = _inputs(tmp_path, monkeypatch)
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(real_parent, target_is_directory=True)

    with pytest.raises(
        module.CoreReleaseEvidenceError, match="unavailable or symlinked"
    ):
        _build(
            module,
            wheel=wheel,
            sdist=sdist,
            proof=proof,
            release=release,
            out=linked_parent / "bundle.zip",
        )
    assert not (real_parent / "bundle.zip").exists()


def test_bundle_parent_swap_before_publish_leaves_no_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module, wheel, sdist, proof, release = _inputs(tmp_path, monkeypatch)
    out = tmp_path / "bundle.zip"
    monkeypatch.setattr(
        module,
        "_assert_directory_identity",
        lambda *_args: (_ for _ in ()).throw(
            module.CoreReleaseEvidenceError("parent identity changed")
        ),
    )

    with pytest.raises(
        module.CoreReleaseEvidenceError, match="parent identity changed"
    ):
        _build(
            module,
            wheel=wheel,
            sdist=sdist,
            proof=proof,
            release=release,
            out=out,
        )
    assert not out.exists()


def test_post_publish_failure_is_effect_indeterminate_and_preserves_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module, wheel, sdist, proof, release = _inputs(tmp_path, monkeypatch)
    out = tmp_path / "bundle.zip"
    original = module._assert_directory_identity
    calls = 0

    def fail_after_publish(*args: Any) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected post-link identity failure")
        original(*args)

    monkeypatch.setattr(module, "_assert_directory_identity", fail_after_publish)
    with pytest.raises(
        module.CoreReleaseEvidenceError, match="effect is indeterminate"
    ):
        _build(
            module,
            wheel=wheel,
            sdist=sdist,
            proof=proof,
            release=release,
            out=out,
        )
    assert out.is_file()
    module.validate_bundle(out)


def test_bundle_rejects_noncanonical_trailing_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module, wheel, sdist, proof, release = _inputs(tmp_path, monkeypatch)
    valid = tmp_path / "valid.zip"
    _build(
        module,
        wheel=wheel,
        sdist=sdist,
        proof=proof,
        release=release,
        out=valid,
    )
    trailing = tmp_path / "trailing.zip"
    trailing.write_bytes(valid.read_bytes() + b"unmanifested")

    with pytest.raises(
        module.CoreReleaseEvidenceError, match="canonical or has trailing"
    ):
        module.validate_bundle(trailing)


def test_bundle_rejects_source_race(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module, wheel, sdist, proof, release = _inputs(tmp_path, monkeypatch)
    responses = iter(
        [
            "a" * 40,
            " M local-change",
            "a" * 40,
            " M local-change",
            "b" * 40,
            " M local-change",
            "b" * 40,
            " M local-change",
        ]
    )
    monkeypatch.setattr(module, "_git", lambda *_args: next(responses))
    out = tmp_path / "bundle.zip"

    with pytest.raises(
        module.CoreReleaseEvidenceError, match="changed during bundle construction"
    ):
        _build(
            module,
            wheel=wheel,
            sdist=sdist,
            proof=proof,
            release=release,
            out=out,
        )
    assert not out.exists()


def test_package_check_rejects_invalid_retention_arguments() -> None:
    result = subprocess.run(
        ["bash", "scripts/ci/package-check.sh", "--retain-core-evidence"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "usage:" in result.stderr
