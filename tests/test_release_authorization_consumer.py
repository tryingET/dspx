# ---
# summary: "Tests durable replay and fail-closed shadow Core authorization consumption."
# ---

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import sqlite3
import sys
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/ci/core_release_authorization_consumer.py"
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
FINGERPRINT = "SHA256:OYAnSnMFl+jvWmFJ6TFcHdikBdL7N2MG3k+FIlSqVis"


def _load() -> ModuleType:
    sys.path.insert(0, str(SCRIPT.parent))
    try:
        spec = importlib.util.spec_from_file_location(
            "core_release_authorization_consumer", SCRIPT
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(SCRIPT.parent))


@pytest.fixture
def module() -> ModuleType:
    return _load()


def _snapshot() -> dict[str, object]:
    return {
        "trust_policy_version": 2,
        "trust_selector_ref": TRUST_REF,
        "owner_policy_version": 2,
        "owner_selector_ref": OWNER_REF,
        "owner_key_fingerprint": FINGERPRINT,
        "owner_decision_id": 96,
        "wheel_sha256": "a" * 64,
        "bundle_manifest_sha256": "b" * 64,
        "signed_statement_sha256": "c" * 64,
        "source_commit_sha": "d" * 40,
        "package_version": "0.1.0",
        "workflow_run_id": 30660312181,
        "workflow_run_attempt": 1,
        "evidence_artifact_id": 101,
        "evidence_provider_digest": "sha256:" + "e" * 64,
        "receipt_artifact_id": 102,
        "receipt_provider_digest": "sha256:" + "f" * 64,
        "evidence_expires_at": "2026-10-29T00:00:00Z",
        "receipt_expires_at": "2026-10-29T00:00:00Z",
        "owner_policy": {
            "owner_policy_version": 2,
            "authentication": {"fingerprint_sha256": FINGERPRINT},
        },
    }


def _payload(
    module: ModuleType, snapshot: dict[str, object] | None = None
) -> dict[str, object]:
    return module.payload_from_snapshot(
        snapshot or _snapshot(),
        nonce="9" * 64,
        issued_at=datetime(2026, 8, 1, 5, 0, tzinfo=timezone.utc),
        expires_at=datetime(2026, 8, 1, 5, 10, tzinfo=timezone.utc),
    )


def _mock_auth(monkeypatch: pytest.MonkeyPatch, module: ModuleType) -> None:
    monkeypatch.setattr(
        module,
        "authenticate_owner_approval",
        lambda **_kwargs: {"security_key_counter": 11, "release_authority": False},
    )


def _inputs(module: ModuleType, tmp_path: Path) -> object:
    unused = tmp_path / "unused"
    return module.SnapshotInputs(
        repo_root=ROOT,
        trust_checkpoint=unused,
        owner_checkpoint=unused,
        evidence_bundle=unused,
        statement_path=unused,
        sigstore_bundle=unused,
        subject_path=unused,
        receipt_path=unused,
        receipt_statement_path=unused,
        receipt_sigstore_bundle=unused,
        trusted_root_path=unused,
    )


def _mock_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    module: ModuleType,
    provider: Callable[[], dict[str, object]],
) -> None:
    monkeypatch.setattr(
        module,
        "_derive_snapshot",
        lambda _inputs, now: provider(),
    )
    monkeypatch.setattr(module, "_utc_now", lambda: NOW)


def test_precreated_incompatible_ledger_schema_is_rejected(
    module: ModuleType, tmp_path: Path
) -> None:
    path = tmp_path / "ledger.sqlite3"
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE authorizations (owner_selector_ref TEXT, fingerprint TEXT, "
        "nonce TEXT, payload_sha256 TEXT, status TEXT, reserved_at TEXT, "
        "receipt_json TEXT)"
    )
    connection.commit()
    connection.close()
    with pytest.raises(module.CoreReleaseEvidenceError, match="schema drift"):
        module.NonceLedger(path)


def test_unexpected_replay_enabling_trigger_is_rejected(
    module: ModuleType, tmp_path: Path
) -> None:
    path = tmp_path / "ledger.sqlite3"
    module.NonceLedger(path)
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TRIGGER replay_before_insert BEFORE INSERT ON authorizations "
        "BEGIN DELETE FROM authorizations WHERE nonce=NEW.nonce; END"
    )
    connection.commit()
    connection.close()
    with pytest.raises(module.CoreReleaseEvidenceError, match="schema drift"):
        module.NonceLedger(path)


def test_shadow_commit_is_durable_and_never_authoritative(
    module: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _mock_auth(monkeypatch, module)
    _mock_snapshot(monkeypatch, module, _snapshot)
    ledger = module.NonceLedger(tmp_path / "ledger.sqlite3")
    payload = _payload(module)
    signature = tmp_path / "approval.sig"
    signature.write_bytes(b"fixture")
    receipt = module.consume_shadow(
        payload=payload,
        signature_path=signature,
        ledger=ledger,
        inputs=_inputs(module, tmp_path),
    )
    assert receipt["status"] == "shadow_verified_not_authorized"
    assert receipt["release_authority"] is False
    assert receipt["package_publication"] is False
    assert (
        ledger.status(
            owner_selector_ref=OWNER_REF, fingerprint=FINGERPRINT, nonce="9" * 64
        )
        == "committed"
    )
    with pytest.raises(module.CoreReleaseEvidenceError, match="already reserved"):
        module.consume_shadow(
            payload=payload,
            signature_path=signature,
            ledger=ledger,
            inputs=_inputs(module, tmp_path),
        )


def test_failure_after_reservation_leaves_pending_tombstone(
    module: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _mock_snapshot(
        monkeypatch,
        module,
        lambda: (_ for _ in ()).throw(RuntimeError("provider failed")),
    )
    ledger = module.NonceLedger(tmp_path / "ledger.sqlite3")
    payload = _payload(module)
    signature = tmp_path / "approval.sig"
    signature.write_bytes(b"fixture")
    with pytest.raises(RuntimeError, match="provider failed"):
        module.consume_shadow(
            payload=payload,
            signature_path=signature,
            ledger=ledger,
            inputs=_inputs(module, tmp_path),
        )
    assert (
        ledger.status(
            owner_selector_ref=OWNER_REF, fingerprint=FINGERPRINT, nonce="9" * 64
        )
        == "pending"
    )


def test_currentness_change_after_signature_never_commits(
    module: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _mock_auth(monkeypatch, module)
    ledger = module.NonceLedger(tmp_path / "ledger.sqlite3")
    payload = _payload(module)
    signature = tmp_path / "approval.sig"
    signature.write_bytes(b"fixture")
    calls = 0

    def provider() -> dict[str, object]:
        nonlocal calls
        calls += 1
        value = _snapshot()
        if calls == 2:
            value["receipt_provider_digest"] = "sha256:" + "0" * 64
        return value

    _mock_snapshot(monkeypatch, module, provider)

    with pytest.raises(module.CoreReleaseEvidenceError, match="currentness changed"):
        module.consume_shadow(
            payload=payload,
            signature_path=signature,
            ledger=ledger,
            inputs=_inputs(module, tmp_path),
        )
    assert (
        ledger.status(
            owner_selector_ref=OWNER_REF, fingerprint=FINGERPRINT, nonce="9" * 64
        )
        == "pending"
    )


def test_expiry_is_rechecked_immediately_before_commit(
    module: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _mock_auth(monkeypatch, module)
    _mock_snapshot(monkeypatch, module, _snapshot)
    ledger = module.NonceLedger(tmp_path / "ledger.sqlite3")
    payload = _payload(module)
    signature = tmp_path / "approval.sig"
    signature.write_bytes(b"fixture")
    times = iter(
        [
            NOW,
            NOW,
            NOW,
            NOW,
            datetime(2026, 8, 1, 5, 11, tzinfo=timezone.utc),
        ]
    )
    monkeypatch.setattr(module, "_utc_now", lambda: next(times))
    with pytest.raises(module.CoreReleaseEvidenceError, match="time window"):
        module.consume_shadow(
            payload=payload,
            signature_path=signature,
            ledger=ledger,
            inputs=_inputs(module, tmp_path),
        )
    assert (
        ledger.status(
            owner_selector_ref=OWNER_REF, fingerprint=FINGERPRINT, nonce="9" * 64
        )
        == "pending"
    )


def test_custody_expiry_is_rechecked_at_finalization(
    module: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _mock_auth(monkeypatch, module)
    expiring = _snapshot()
    expiring["evidence_expires_at"] = "2026-08-01T05:10:00Z"
    expiring["receipt_expires_at"] = "2026-08-01T05:10:00Z"
    _mock_snapshot(monkeypatch, module, lambda: expiring)
    ledger = module.NonceLedger(tmp_path / "ledger.sqlite3")
    payload = _payload(module, expiring)
    payload["expires_at"] = "2026-08-01T05:15:00Z"
    signature = tmp_path / "approval.sig"
    signature.write_bytes(b"fixture")
    times = iter([NOW, NOW, NOW, NOW, datetime(2026, 8, 1, 5, 11, tzinfo=timezone.utc)])
    monkeypatch.setattr(module, "_utc_now", lambda: next(times))
    with pytest.raises(module.CoreReleaseEvidenceError, match="custody expired"):
        module.consume_shadow(
            payload=payload,
            signature_path=signature,
            ledger=ledger,
            inputs=_inputs(module, tmp_path),
        )
    assert (
        ledger.status(
            owner_selector_ref=OWNER_REF, fingerprint=FINGERPRINT, nonce="9" * 64
        )
        == "pending"
    )


def test_concurrent_consumers_have_one_linearization_winner(
    module: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _mock_auth(monkeypatch, module)
    _mock_snapshot(monkeypatch, module, _snapshot)
    ledger_path = tmp_path / "ledger.sqlite3"
    module.NonceLedger(ledger_path)
    payload = _payload(module)
    signature = tmp_path / "approval.sig"
    signature.write_bytes(b"fixture")

    def consume() -> str:
        try:
            module.consume_shadow(
                payload=payload,
                signature_path=signature,
                ledger=module.NonceLedger(ledger_path),
                inputs=_inputs(module, tmp_path),
            )
            return "committed"
        except module.CoreReleaseEvidenceError:
            return "rejected"

    with ThreadPoolExecutor(max_workers=8) as executor:
        outcomes = list(executor.map(lambda _index: consume(), range(8)))
    assert outcomes.count("committed") == 1
    assert outcomes.count("rejected") == 7


def test_payload_is_not_accepted_from_caller_drift(
    module: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _mock_auth(monkeypatch, module)
    _mock_snapshot(monkeypatch, module, _snapshot)
    ledger = module.NonceLedger(tmp_path / "ledger.sqlite3")
    payload = _payload(module)
    payload["wheel_sha256"] = "0" * 64
    signature = tmp_path / "approval.sig"
    signature.write_bytes(b"fixture")
    with pytest.raises(module.CoreReleaseEvidenceError, match="independently derived"):
        module.consume_shadow(
            payload=payload,
            signature_path=signature,
            ledger=ledger,
            inputs=_inputs(module, tmp_path),
        )
