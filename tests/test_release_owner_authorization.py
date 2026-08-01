# ---
# summary: "Tests exact hardware-backed Core owner approval authentication."
# ---

from __future__ import annotations

import base64
import copy
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import struct
import sys
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/ci/core_release_owner_authorization.py"
POLICY = ROOT / "governance/release-signing/release-owner-policy-v002.json"
NOW = datetime(2026, 8, 1, 5, 5, tzinfo=timezone.utc)
TRUST_REF = (
    "dspx-core-policy-selector-v1:git:"
    + "1" * 40
    + ":governance/release-signing/policy-selector-v002.json:"
    + "2" * 40
    + ":"
    + "3" * 64
)
OWNER_REF = (
    "dspx-core-owner-policy-selector-v1:git:"
    + "4" * 40
    + ":governance/release-signing/release-owner-policy-selector-v002.json:"
    + "5" * 40
    + ":"
    + "6" * 64
)


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
    return {
        "schema_version": "dspx-core-single-owner-approval-payload-v2",
        "repository": {"name": "tryingET/dspx", "id": 1_318_473_695},
        "policy_version": 2,
        "policy_selector_ref": TRUST_REF,
        "owner_policy_version": 2,
        "owner_policy_selector_ref": OWNER_REF,
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
        "authority_ref": "ak-decision:96",
    }


def _enabled(policy: dict[str, object]) -> dict[str, object]:
    changed = copy.deepcopy(policy)
    changed["revocation"]["authorization_enabled"] = True
    changed["revocation"]["disabled_reason"] = None
    return changed


def _string(raw: bytes) -> bytes:
    return struct.pack(">I", len(raw)) + raw


def _sshsig(
    policy: dict[str, object],
    *,
    flags: int = 5,
    counter: int = 7,
    algorithm: bytes = b"sk-ssh-ed25519@openssh.com",
    namespace: bytes = b"dspx-core-release-authorization-v1",
) -> bytes:
    public = base64.b64decode(policy["authentication"]["public_key"].split()[1])
    signature = (
        _string(algorithm)
        + _string(b"x" * 64)
        + bytes([flags])
        + struct.pack(">I", counter)
    )
    envelope = (
        b"SSHSIG"
        + struct.pack(">I", 1)
        + _string(public)
        + _string(namespace)
        + _string(b"")
        + _string(b"sha512")
        + _string(signature)
    )
    body = base64.b64encode(envelope).decode()
    return (
        "-----BEGIN SSH SIGNATURE-----\n" + body + "\n-----END SSH SIGNATURE-----\n"
    ).encode()


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
    assert valid["claims"]["human_principal_count"] == 1
    assert valid["claims"]["independent_quorum"] is False


def test_ordinary_or_alternate_key_type_is_rejected(
    module: ModuleType, policy: dict[str, object]
) -> None:
    for kind in ("ssh-ed25519", "sk-ecdsa-sha2-nistp256@openssh.com"):
        changed = copy.deepcopy(policy)
        changed["authentication"]["key_type"] = kind
        changed["authentication"]["public_key"] = f"{kind} AAAA fake"
        with pytest.raises(module.CoreReleaseEvidenceError, match="hardware-backed"):
            module.validate_policy(changed, now=NOW)


def test_revocation_invariants_and_current_key_rejection(
    module: ModuleType, policy: dict[str, object]
) -> None:
    enabled = _enabled(policy)
    assert module.validate_policy(enabled, now=NOW)
    stale_reason = copy.deepcopy(enabled)
    stale_reason["revocation"]["disabled_reason"] = "still disabled"
    with pytest.raises(module.CoreReleaseEvidenceError, match="revocation"):
        module.validate_policy(stale_reason, now=NOW)
    revoked = copy.deepcopy(policy)
    revoked["revocation"]["revoked_fingerprints"] = [
        policy["authentication"]["fingerprint_sha256"]
    ]
    with pytest.raises(
        module.CoreReleaseEvidenceError, match="current owner key is revoked"
    ):
        module.validate_policy(revoked, now=NOW)


def test_fingerprint_requires_exact_ssh_keygen_token(
    module: ModuleType, policy: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    _mock_ssh(monkeypatch, module)
    shortened = copy.deepcopy(policy)
    shortened["authentication"]["fingerprint_sha256"] = "SHA256:"
    with pytest.raises(module.CoreReleaseEvidenceError, match="fingerprint drift"):
        module.validate_policy(shortened, now=NOW)
    malformed_revocation = copy.deepcopy(policy)
    malformed_revocation["revocation"]["revoked_fingerprints"] = ["SHA256:"]
    with pytest.raises(module.CoreReleaseEvidenceError, match="revocation"):
        module.validate_policy(malformed_revocation, now=NOW)


def test_exact_up_uv_signature_authenticates_but_never_grants_authority(
    module: ModuleType,
    policy: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _mock_ssh(monkeypatch, module)
    signature = tmp_path / "approval.sig"
    signature.write_bytes(_sshsig(policy))
    result = module.authenticate_owner_approval(
        policy=_enabled(policy),
        payload=_payload(),
        signature_path=signature,
        consumed_nonces=set(),
        now=NOW,
    )
    assert result["security_key_counter"] == 7
    assert result["release_authority"] is False
    assert result["package_publication"] is False


@pytest.mark.parametrize(
    ("flags", "message"),
    [(0, "presence"), (1, "verification"), (4, "presence"), (7, "flags")],
)
def test_security_key_flags_fail_closed(
    module: ModuleType, policy: dict[str, object], flags: int, message: str
) -> None:
    with pytest.raises(module.CoreReleaseEvidenceError, match=message):
        module.parse_sk_signature_details(_sshsig(policy, flags=flags), policy=policy)


def test_wrong_sk_algorithm_and_key_fail_closed(
    module: ModuleType, policy: dict[str, object]
) -> None:
    with pytest.raises(module.CoreReleaseEvidenceError, match="algorithm"):
        module.parse_sk_signature_details(
            _sshsig(policy, algorithm=b"ssh-ed25519"), policy=policy
        )
    changed = copy.deepcopy(policy)
    changed["authentication"]["public_key"] = changed["authentication"][
        "public_key"
    ].replace("IBCk", "IBCl")
    with pytest.raises(module.CoreReleaseEvidenceError):
        module.parse_sk_signature_details(_sshsig(policy), policy=changed)


def test_wrong_sshsig_namespace_and_truncation_fail_closed(
    module: ModuleType, policy: dict[str, object]
) -> None:
    with pytest.raises(module.CoreReleaseEvidenceError, match="envelope"):
        module.parse_sk_signature_details(
            _sshsig(policy, namespace=b"file"), policy=policy
        )
    with pytest.raises(
        module.CoreReleaseEvidenceError, match="framing|truncated|invalid"
    ):
        module.parse_sk_signature_details(_sshsig(policy)[:40], policy=policy)


def test_selector_and_authority_refs_are_exact(
    module: ModuleType, policy: dict[str, object]
) -> None:
    for field, value in (
        ("policy_selector_ref", "dspx-core-policy-selector-v1:git:" + "1" * 40),
        (
            "owner_policy_selector_ref",
            "dspx-core-owner-policy-selector-v1:git:" + "1" * 40,
        ),
        ("authority_ref", "anything"),
    ):
        changed = _payload()
        changed[field] = value
        with pytest.raises(module.CoreReleaseEvidenceError, match="binding|authority"):
            module.canonical_payload(changed, policy=policy, now=NOW)


def test_duplicate_json_is_rejected(module: ModuleType) -> None:
    with pytest.raises(module.CoreReleaseEvidenceError, match="duplicate"):
        module.loads_json(b'{"nonce":"a","nonce":"b"}', "approval payload")


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


def test_replay_expiry_and_disabled_switch_fail_closed(
    module: ModuleType,
    policy: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _mock_ssh(monkeypatch, module)
    signature = tmp_path / "approval.sig"
    signature.write_bytes(_sshsig(policy))
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
