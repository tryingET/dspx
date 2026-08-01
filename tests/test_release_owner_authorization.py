# ---
# summary: "Tests hardware-backed exact single-owner Core approval authentication."
# ---

from __future__ import annotations

import copy
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/ci/core_release_owner_authorization.py"
POLICY = ROOT / "governance/release-signing/release-owner-policy-v002.json"
NOW = datetime(2026, 8, 1, 5, 5, tzinfo=timezone.utc)


def _load() -> ModuleType:
    sys.path.insert(0, str(SCRIPT.parent))
    try:
        spec = importlib.util.spec_from_file_location(
            "core_release_owner_authorization", SCRIPT
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(SCRIPT.parent))


@pytest.fixture
def module() -> ModuleType:
    return _load()


@pytest.fixture
def policy() -> dict[str, object]:
    return json.loads(POLICY.read_text(encoding="utf-8"))


def _payload() -> dict[str, object]:
    # Exact production-shaped payload; cryptographic dogfood remains disabled
    # until the real FIDO PIN/user-verification ceremony succeeds.
    return {
        "schema_version": "dspx-core-single-owner-approval-payload-v1",
        "repository": {"name": "tryingET/dspx", "id": 1_318_473_695},
        "policy_version": 2,
        "policy_selector_ref": "dspx-core-policy-selector-v1:git:" + "1" * 40,
        "owner_policy_version": 2,
        "owner_key_fingerprint": "SHA256:OYAnSnMFl+jvWmFJ6TFcHdikBdL7N2MG3k+FIlSqVis",
        "wheel_sha256": "a" * 64,
        "bundle_manifest_sha256": "b" * 64,
        "signed_statement_sha256": "c" * 64,
        "source_commit_sha": "d" * 40,
        "package_version": "0.1.0",
        "workflow_run_id": 30660312181,
        "workflow_run_attempt": 1,
        "purpose": "authorize-dspx-core-wheel-release",
        "nonce": "e" * 64,
        "issued_at": "2026-08-01T05:00:00Z",
        "expires_at": "2026-08-01T05:10:00Z",
        "authority_ref": "AK-4405",
    }


def _enabled(policy: dict[str, object]) -> dict[str, object]:
    changed = copy.deepcopy(policy)
    changed["revocation"]["authorization_enabled"] = True
    changed["revocation"]["disabled_reason"] = ""
    return changed


def _mock_ssh(monkeypatch: pytest.MonkeyPatch, module: ModuleType) -> None:
    def run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        if "-lf" in command:
            return SimpleNamespace(
                returncode=0,
                stdout="256 SHA256:OYAnSnMFl+jvWmFJ6TFcHdikBdL7N2MG3k+FIlSqVis owner (ED25519-SK)\n",
                stderr="",
            )
        return SimpleNamespace(returncode=0, stdout=b"Good signature", stderr=b"")

    monkeypatch.setattr(module.subprocess, "run", run)


def test_policy_pins_one_real_hardware_principal(
    module: ModuleType, policy: dict[str, object]
) -> None:
    valid = module.validate_policy(policy, now=NOW)
    assert valid["claims"] == {
        "human_principal_count": 1,
        "independent_quorum": False,
        "concentrated_risk_accepted": True,
        "technical_controls_are_conjunction_not_principals": True,
        "package_publication": False,
        "sdist_supported": False,
    }


def test_ordinary_software_key_is_rejected(
    module: ModuleType, policy: dict[str, object]
) -> None:
    changed = copy.deepcopy(policy)
    changed["authentication"]["key_type"] = "ssh-ed25519"
    changed["authentication"]["public_key"] = "ssh-ed25519 AAAA fake"
    with pytest.raises(module.CoreReleaseEvidenceError, match="hardware-backed"):
        module.validate_policy(changed, now=NOW)


def test_exact_hardware_approval_authenticates_but_does_not_grant_authority(
    module: ModuleType,
    policy: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _mock_ssh(monkeypatch, module)
    signature = tmp_path / "approval.sig"
    signature.write_bytes(b"sshsig")
    result = module.authenticate_owner_approval(
        policy=_enabled(policy),
        payload=_payload(),
        signature_path=signature,
        consumed_nonces=set(),
        now=NOW,
    )
    assert result["status"] == "owner_authenticated_technical_consumer_required"
    assert result["release_authority"] is False
    assert result["package_publication"] is False


def test_signature_failure_is_closed(
    module: ModuleType,
    policy: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *_a, **_k: SimpleNamespace(returncode=1, stdout=b"", stderr=b"bad"),
    )
    signature = tmp_path / "approval.sig"
    signature.write_bytes(b"bad")
    with pytest.raises(module.CoreReleaseEvidenceError):
        module.authenticate_owner_approval(
            policy=_enabled(policy),
            payload=_payload(),
            signature_path=signature,
            consumed_nonces=set(),
            now=NOW,
        )


@pytest.mark.parametrize(
    "field",
    [
        "wheel_sha256",
        "bundle_manifest_sha256",
        "signed_statement_sha256",
        "source_commit_sha",
        "nonce",
    ],
)
def test_identity_digest_drift_is_rejected(
    module: ModuleType, policy: dict[str, object], field: str
) -> None:
    changed = _payload()
    changed[field] = "bad"
    with pytest.raises(module.CoreReleaseEvidenceError, match="drift"):
        module.canonical_payload(changed, policy=policy, now=NOW)


def test_replay_and_expiry_are_rejected(
    module: ModuleType,
    policy: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _mock_ssh(monkeypatch, module)
    signature = tmp_path / "approval.sig"
    signature.write_bytes(b"sshsig")
    with pytest.raises(module.CoreReleaseEvidenceError, match="already consumed"):
        module.authenticate_owner_approval(
            policy=_enabled(policy),
            payload=_payload(),
            signature_path=signature,
            consumed_nonces={"e" * 64},
            now=NOW,
        )
    with pytest.raises(module.CoreReleaseEvidenceError, match="time window"):
        module.canonical_payload(
            _payload(),
            policy=policy,
            now=datetime(2026, 8, 1, 5, 11, tzinfo=timezone.utc),
        )


def test_revocation_kill_switch_is_closed(
    module: ModuleType, policy: dict[str, object], tmp_path: Path
) -> None:
    signature = tmp_path / "approval.sig"
    signature.write_bytes(b"not reached")
    with pytest.raises(
        module.CoreReleaseEvidenceError, match="authorization is disabled"
    ):
        module.authenticate_owner_approval(
            policy=policy,
            payload=_payload(),
            signature_path=signature,
            consumed_nonces=set(),
            now=NOW,
        )
