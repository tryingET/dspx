# ---
# summary: "Tests public Core evidence custody, receipts, retention, and provider effects."
# read_when:
#   - "Changing Core CI custody or GitHub artifact observation semantics."
# ---

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tarfile
from types import ModuleType
import zipfile

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts/ci/core_release_custody.py"
SCRIPTS = SCRIPT.parent


def _load() -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    try:
        spec = importlib.util.spec_from_file_location("core_release_custody", SCRIPT)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(SCRIPTS))


@pytest.fixture
def module() -> ModuleType:
    return _load()


def _metadata(*, retention_class: str = "trusted_run_14d") -> dict[str, object]:
    days = 14 if retention_class == "trusted_run_14d" else 90
    return {
        "artifact_id": 123,
        "artifact_url": "https://github.com/tryingET/dspx/actions/runs/456/artifacts/123",
        "artifact_digest": f"sha256:{'a' * 64}",
        "artifact_name": "dspx-core-evidence-456-1",
        "evidence_bundle_sha256": "b" * 64,
        "bundle_manifest_sha256": "c" * 64,
        "signed_statement_sha256": "d" * 64,
        "sigstore_bundle_sha256": "e" * 64,
        "workflow_file_sha256": "f" * 64,
        "source_commit_sha": "1" * 40,
        "run_id": 456,
        "run_attempt": 1,
        "policy_version": 1,
        "policy_selector": (
            "dspx-core-policy-selector-v1:git:"
            f"{'1' * 40}:governance/release-signing/policy-selector-v001.json:"
            f"{'2' * 40}:{'3' * 64}"
        ),
        "retention_class": retention_class,
        "provider_retention_cap_days": 90,
        "observed_at": "2026-07-31T00:00:00Z",
        "expires_at": f"2026-{10 if days == 90 else 8:02d}-{29 if days == 90 else 14:02d}T00:00:00Z",
    }


def _observation(
    *, artifacts: list[dict[str, object]], complete: bool = True
) -> dict[str, object]:
    return {
        "schema_version": "dspx-github-artifact-observation-v1",
        "query_status": "success",
        "run_id": 456,
        "complete": complete,
        "artifacts": artifacts,
    }


def _artifact() -> dict[str, object]:
    return {
        "id": 123,
        "name": "dspx-core-evidence-456-1",
        "expired": False,
        "digest": f"sha256:{'a' * 64}",
    }


def _receipt_artifact() -> dict[str, object]:
    return {
        "id": 999,
        "name": "dspx-core-custody-receipt-123",
        "expired": False,
        "digest": f"sha256:{'b' * 64}",
    }


def test_receipt_binds_public_custody_without_release_authority(
    module: ModuleType,
) -> None:
    receipt = module.build_receipt(_metadata())

    assert receipt["schema_version"] == "dspx-core-ci-custody-receipt-v1"
    assert receipt["repository"] == {
        "name": "tryingET/dspx",
        "id": 1_318_473_695,
        "owner_id": 260_287_438,
    }
    assert receipt["workflow"]["environment"] == "core-release-evidence"
    assert receipt["retention"] == {
        "class": "trusted_run_14d",
        "requested_days": 14,
        "provider_cap_days": 90,
    }
    assert receipt["claims"] == {
        "evidence_publication_only": True,
        "package_release_authority": False,
        "package_publication": False,
        "current_availability_requires_fresh_observation": True,
    }
    assert module.validate_receipt(receipt) == receipt


def test_receipt_accepts_90_day_class_and_rejects_short_cap_or_expiry(
    module: ModuleType,
) -> None:
    metadata = _metadata(retention_class="release_candidate_90d")
    receipt = module.build_receipt(metadata)
    assert receipt["retention"]["requested_days"] == 90

    short_cap = dict(metadata, provider_retention_cap_days=14)
    with pytest.raises(module.CoreReleaseEvidenceError, match="provider retention cap"):
        module.build_receipt(short_cap)

    early = dict(metadata, expires_at="2026-08-01T00:00:00Z")
    with pytest.raises(module.CoreReleaseEvidenceError, match="expiry"):
        module.build_receipt(early)


def test_receipt_allows_bounded_provider_timestamp_rounding(
    module: ModuleType,
) -> None:
    rounded = _metadata()
    rounded["expires_at"] = "2026-08-13T23:55:01Z"
    receipt = module.build_receipt(rounded)
    assert module.validate_receipt(receipt) == receipt

    too_short = dict(rounded, expires_at="2026-08-13T23:54:59Z")
    with pytest.raises(module.CoreReleaseEvidenceError, match="expiry"):
        module.build_receipt(too_short)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda value: value["claims"].update({"package_release_authority": True}),
            "authority claims",
        ),
        (lambda value: value["repository"].update({"id": 1}), "repository drift"),
        (lambda value: value["workflow"].update({"event": "push"}), "workflow context"),
        (
            lambda value: value["evidence_artifact"].update({"visibility": "private"}),
            "public visibility",
        ),
        (lambda value: value.update({"source_commit_sha": "bad"}), "source commit"),
        (
            lambda value: value["policy"].update({"selector": "saved-output.json"}),
            "policy selector",
        ),
    ],
)
def test_receipt_validator_rejects_identity_and_authority_drift(
    module: ModuleType, mutation: object, message: str
) -> None:
    receipt = module.build_receipt(_metadata())
    mutation(receipt)
    with pytest.raises(module.CoreReleaseEvidenceError, match=message):
        module.validate_receipt(receipt)


def test_upload_observation_requires_complete_provider_truth(
    module: ModuleType,
) -> None:
    observed = module.classify_upload_observation(
        operation_outcome="failure",
        observation=_observation(artifacts=[_artifact()]),
        expected_name="dspx-core-evidence-456-1",
        run_id=456,
    )
    assert observed["status"] == "observed_success"
    assert observed["retry_allowed"] is False

    absent = module.classify_upload_observation(
        operation_outcome="failure",
        observation=_observation(artifacts=[]),
        expected_name="dspx-core-evidence-456-1",
        run_id=456,
    )
    assert absent == {"status": "confirmed_absent", "retry_allowed": True}

    for observation in (
        _observation(artifacts=[], complete=False),
        {
            "schema_version": "dspx-github-artifact-observation-v1",
            "query_status": "error",
        },
        _observation(artifacts=[_artifact(), _artifact()]),
    ):
        result = module.classify_upload_observation(
            operation_outcome="failure",
            observation=observation,
            expected_name="dspx-core-evidence-456-1",
            run_id=456,
        )
        assert result == {"status": "effect_indeterminate", "retry_allowed": False}

    success_but_absent = module.classify_upload_observation(
        operation_outcome="success",
        observation=_observation(artifacts=[]),
        expected_name="dspx-core-evidence-456-1",
        run_id=456,
    )
    assert success_but_absent["status"] == "effect_indeterminate"


def test_observe_upload_cli_never_reports_confirmed_absence_as_success(
    module: ModuleType, tmp_path: Path
) -> None:
    observation = tmp_path / "observation.json"
    observation.write_text(json.dumps(_observation(artifacts=[])), encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "observe-upload",
            "--observation",
            str(observation),
            "--operation-outcome",
            "failure",
            "--name",
            "dspx-core-evidence-456-1",
            "--run-id",
            "456",
        ],
        capture_output=True,
        text=True,
        check=False,
        env={"PYTHONPATH": str(SCRIPTS)},
    )
    assert result.returncode == 4
    assert '"status": "confirmed_absent"' in result.stdout


def test_verify_availability_cli_requires_exact_current_pair(
    module: ModuleType, tmp_path: Path
) -> None:
    receipt = tmp_path / "custody-receipt.json"
    observation = tmp_path / "observation.json"
    receipt.write_text(json.dumps(module.build_receipt(_metadata())), encoding="utf-8")

    command = [
        sys.executable,
        str(SCRIPT),
        "verify-availability",
        "--receipt",
        str(receipt),
        "--receipt-artifact-id",
        "999",
        "--receipt-provider-digest",
        f"sha256:{'b' * 64}",
        "--observation",
        str(observation),
        "--now",
        "2026-08-01T00:00:00Z",
    ]
    observation.write_text(
        json.dumps(_observation(artifacts=[_artifact(), _receipt_artifact()])),
        encoding="utf-8",
    )
    current = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        env={"PYTHONPATH": str(SCRIPTS)},
    )
    assert current.returncode == 0
    assert '"release_use_custody": true' in current.stdout
    assert '"status": "current"' in current.stdout

    observation.write_text(
        json.dumps(_observation(artifacts=[_receipt_artifact()])), encoding="utf-8"
    )
    absent = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        env={"PYTHONPATH": str(SCRIPTS)},
    )
    assert absent.returncode == 5
    assert '"release_use_custody": false' in absent.stdout
    assert '"status": "confirmed_absent"' in absent.stdout

    observation.write_text(
        json.dumps(_observation(artifacts=[_artifact(), _receipt_artifact()])),
        encoding="utf-8",
    )
    drifted = subprocess.run(
        [
            *command[:8],
            f"sha256:{'0' * 64}",
            *command[9:],
        ],
        capture_output=True,
        text=True,
        check=False,
        env={"PYTHONPATH": str(SCRIPTS)},
    )
    assert drifted.returncode == 5
    assert '"status": "digest_or_expiry_drift"' in drifted.stdout


def test_current_availability_fails_closed_on_absence_expiry_and_drift(
    module: ModuleType,
) -> None:
    receipt = module.build_receipt(_metadata())
    current = module.verify_current_availability(
        receipt=receipt,
        receipt_artifact_id=999,
        receipt_provider_digest=f"sha256:{'b' * 64}",
        observation=_observation(artifacts=[_artifact(), _receipt_artifact()]),
        now=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )
    assert current == {"status": "current", "release_use_custody": True}

    absent = module.verify_current_availability(
        receipt=receipt,
        receipt_artifact_id=999,
        receipt_provider_digest=f"sha256:{'b' * 64}",
        observation=_observation(artifacts=[_artifact()]),
        now=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )
    assert absent == {"status": "confirmed_absent", "release_use_custody": False}

    drifted = _artifact()
    drifted["digest"] = f"sha256:{'0' * 64}"
    drift = module.verify_current_availability(
        receipt=receipt,
        receipt_artifact_id=999,
        receipt_provider_digest=f"sha256:{'b' * 64}",
        observation=_observation(artifacts=[drifted, _receipt_artifact()]),
        now=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )
    assert drift == {"status": "digest_or_expiry_drift", "release_use_custody": False}

    expired = module.verify_current_availability(
        receipt=receipt,
        receipt_artifact_id=999,
        receipt_provider_digest=f"sha256:{'b' * 64}",
        observation=_observation(artifacts=[_artifact(), _receipt_artifact()]),
        now=datetime(2026, 8, 15, tzinfo=timezone.utc),
    )
    assert expired == {"status": "expired", "release_use_custody": False}


def _wheel_bytes(*, secret: bool = False) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        payload = b"public wheel payload\n"
        if secret:
            payload = b"access_token=github_pat_abcdefghijklmnopqrstuvwxyz1234567890ABCDEFGH\n"
        archive.writestr("dspx/__init__.py", payload)
    return buffer.getvalue()


def _sdist_bytes(*, secret: bool = False) -> bytes:
    payload = b"public sdist payload\n"
    if secret:
        payload = (
            b"access_token=github_pat_abcdefghijklmnopqrstuvwxyz1234567890ABCDEFGH\n"
        )
    info = tarfile.TarInfo("dspx_core-1.0.0/src/dspx/__init__.py")
    info.size = len(payload)
    buffer = BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        archive.addfile(info, BytesIO(payload))
    return buffer.getvalue()


def _public_zip(*, secret_member: str | None = None) -> tuple[bytes, dict[str, object]]:
    names = {
        "dspx_core-1.0.0-py3-none-any.whl",
        "dspx_core-1.0.0.tar.gz",
        "installed-core-golden-path-proof.json",
        "dspx-core-release-evidence.json",
        "local-build-provenance.json",
        "dspx-core-wheel-sbom.cdx.json",
        "dspx-core-installed-environment-sbom.cdx.json",
    }
    files = [{"filename": name} for name in sorted(names)]
    manifest: dict[str, object] = {"files": files}
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for name in names:
            if name.endswith(".whl"):
                payload = _wheel_bytes(secret=name == secret_member)
            elif name.endswith(".tar.gz"):
                payload = _sdist_bytes(secret=name == secret_member)
            else:
                payload = b"public evidence\n"
                if name == secret_member:
                    payload = b"api_key=ghp_abcdefghijklmnopqrstuvwxyz1234567890\n"
            archive.writestr(name, payload)
        archive.writestr("bundle-manifest.json", json.dumps(manifest).encode())
    return buffer.getvalue(), manifest


def test_public_bundle_preflight_enforces_allowlist_and_secret_scan(
    module: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    raw, manifest = _public_zip()
    bundle = tmp_path / "bundle.zip"
    bundle.write_bytes(raw)
    monkeypatch.setattr(module, "validate_bundle", lambda _path: manifest)

    result = module.validate_public_bundle(bundle)
    assert result["status"] == "passed"
    assert result["public_non_secret_evidence"] is True
    assert result["release_authority"] is False

    secret_raw, secret_manifest = _public_zip(
        secret_member="dspx-core-release-evidence.json"
    )
    bundle.write_bytes(secret_raw)
    monkeypatch.setattr(module, "validate_bundle", lambda _path: secret_manifest)
    with pytest.raises(module.CoreReleaseEvidenceError, match="secret-shaped"):
        module.validate_public_bundle(bundle)

    nested_raw, nested_manifest = _public_zip(
        secret_member="dspx_core-1.0.0-py3-none-any.whl"
    )
    bundle.write_bytes(nested_raw)
    monkeypatch.setattr(module, "validate_bundle", lambda _path: nested_manifest)
    with pytest.raises(module.CoreReleaseEvidenceError, match="secret-shaped"):
        module.validate_public_bundle(bundle)

    nested_sdist_raw, nested_sdist_manifest = _public_zip(
        secret_member="dspx_core-1.0.0.tar.gz"
    )
    bundle.write_bytes(nested_sdist_raw)
    monkeypatch.setattr(module, "validate_bundle", lambda _path: nested_sdist_manifest)
    with pytest.raises(module.CoreReleaseEvidenceError, match="secret-shaped"):
        module.validate_public_bundle(bundle)


def test_public_upload_preflight_scans_every_exact_file(
    module: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bundle = tmp_path / "evidence.zip"
    statement = tmp_path / "signed-statement.json"
    sigstore = tmp_path / "statement.sigstore.json"
    bundle.write_bytes(b"bundle")
    statement.write_text('{"public":true}\n', encoding="utf-8")
    sigstore.write_text('{"certificate":"public"}\n', encoding="utf-8")
    monkeypatch.setattr(
        module,
        "validate_public_bundle",
        lambda _path: {"manifest_sha256": "a" * 64},
    )

    result = module.validate_public_upload_files([bundle, statement, sigstore])
    assert result["status"] == "passed"
    assert result["package_publication"] is False

    statement.write_text(
        '{"access_token":"github_pat_abcdefghijklmnopqrstuvwxyz1234567890ABCDEFGH"}\n',
        encoding="utf-8",
    )
    with pytest.raises(module.CoreReleaseEvidenceError, match="secret-shaped"):
        module.validate_public_upload_files([bundle, statement, sigstore])

    with pytest.raises(module.CoreReleaseEvidenceError, match="allowlist"):
        module.validate_public_upload_files([bundle, statement])


def test_public_bundle_preflight_rejects_unknown_member(
    module: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    raw, manifest = _public_zip()
    source = BytesIO(raw)
    target = BytesIO()
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(target, "w") as changed:
        for name in original.namelist():
            changed.writestr(name, original.read(name))
        changed.writestr("debug.log", b"not public evidence")
    bundle = tmp_path / "bundle.zip"
    bundle.write_bytes(target.getvalue())
    monkeypatch.setattr(module, "validate_bundle", lambda _path: manifest)

    with pytest.raises(module.CoreReleaseEvidenceError, match="allowlist"):
        module.validate_public_bundle(bundle)
