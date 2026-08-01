# ---
# summary: "Tests durable replay and fail-closed shadow Core authorization consumption."
# ---

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import importlib.util
import os
from pathlib import Path
import sqlite3
import stat
import sys
import tempfile
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

STAGED_FIELDS = (
    "evidence_bundle",
    "statement_path",
    "sigstore_bundle",
    "subject_path",
    "receipt_path",
    "receipt_statement_path",
    "receipt_sigstore_bundle",
    "trusted_root_path",
)


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
    directory = Path(tempfile.mkdtemp(prefix="inputs-", dir=tmp_path))
    paths: dict[str, Path] = {}
    for field in STAGED_FIELDS:
        path = directory / field
        path.write_bytes(f"original:{field}".encode())
        paths[field] = path
    return module.SnapshotInputs(
        repo_root=ROOT,
        trust_checkpoint=directory / "trust-checkpoint.json",
        owner_checkpoint=directory / "owner-checkpoint.json",
        **paths,
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


def test_retained_ledger_revalidates_schema_inside_reservation_transaction(
    module: ModuleType, tmp_path: Path
) -> None:
    path = tmp_path / "ledger.sqlite3"
    ledger = module.NonceLedger(path)
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TRIGGER replay_before_insert BEFORE INSERT ON authorizations "
        "BEGIN DELETE FROM authorizations WHERE nonce=NEW.nonce; END"
    )
    connection.commit()
    connection.close()
    with pytest.raises(module.CoreReleaseEvidenceError, match="schema drift"):
        ledger.reserve(
            owner_selector_ref=OWNER_REF,
            fingerprint=FINGERPRINT,
            nonce="8" * 64,
            payload_sha256="7" * 64,
            now=NOW,
        )


def test_ledger_rejects_database_symlink(module: ModuleType, tmp_path: Path) -> None:
    target = tmp_path / "target.sqlite3"
    target.write_bytes(b"not-a-ledger")
    target.chmod(0o600)
    link = tmp_path / "ledger.sqlite3"
    link.symlink_to(target)
    with pytest.raises(module.CoreReleaseEvidenceError, match="path is unsafe"):
        module.NonceLedger(link)


def test_ledger_rejects_symlinked_parent_component(
    module: ModuleType, tmp_path: Path
) -> None:
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir(mode=0o700)
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(real_parent, target_is_directory=True)
    with pytest.raises(module.CoreReleaseEvidenceError, match="component is unsafe"):
        module.NonceLedger(linked_parent / "ledger.sqlite3")


def test_ledger_rejects_non_owner_only_immediate_parent(
    module: ModuleType, tmp_path: Path
) -> None:
    parent = tmp_path / "shared-parent"
    parent.mkdir(mode=0o755)
    with pytest.raises(module.CoreReleaseEvidenceError, match="not owner-only"):
        module.NonceLedger(parent / "ledger.sqlite3")


def test_ledger_rejects_database_entry_replacement_before_reserve(
    module: ModuleType, tmp_path: Path
) -> None:
    path = tmp_path / "ledger.sqlite3"
    ledger = module.NonceLedger(path)
    replacement = tmp_path / "replacement.sqlite3"
    replacement.write_bytes(b"replacement")
    replacement.chmod(0o600)
    os.replace(replacement, path)
    with pytest.raises(module.CoreReleaseEvidenceError, match="identity changed"):
        ledger.reserve(
            owner_selector_ref=OWNER_REF,
            fingerprint=FINGERPRINT,
            nonce="8" * 64,
            payload_sha256="7" * 64,
            now=NOW,
        )


def test_ledger_rejects_database_entry_replacement_before_finalize(
    module: ModuleType, tmp_path: Path
) -> None:
    path = tmp_path / "ledger.sqlite3"
    ledger = module.NonceLedger(path)
    ledger.reserve(
        owner_selector_ref=OWNER_REF,
        fingerprint=FINGERPRINT,
        nonce="8" * 64,
        payload_sha256="7" * 64,
        now=NOW,
    )
    replacement = tmp_path / "replacement.sqlite3"
    replacement.write_bytes(b"replacement")
    replacement.chmod(0o600)
    os.replace(replacement, path)
    with pytest.raises(module.CoreReleaseEvidenceError, match="identity changed"):
        ledger.finalize(
            owner_selector_ref=OWNER_REF,
            fingerprint=FINGERPRINT,
            nonce="8" * 64,
            payload_sha256="7" * 64,
            receipt={"release_authority": False},
        )


def test_ledger_rejects_parent_replacement(module: ModuleType, tmp_path: Path) -> None:
    parent = tmp_path / "ledger-parent"
    parent.mkdir(mode=0o700)
    ledger = module.NonceLedger(parent / "ledger.sqlite3")
    moved = tmp_path / "original-parent"
    parent.rename(moved)
    parent.mkdir(mode=0o700)
    with pytest.raises(
        module.CoreReleaseEvidenceError, match="parent identity changed"
    ):
        ledger.reserve(
            owner_selector_ref=OWNER_REF,
            fingerprint=FINGERPRINT,
            nonce="8" * 64,
            payload_sha256="7" * 64,
            now=NOW,
        )


def test_ledger_rejects_post_open_symlink_replacement(
    module: ModuleType, tmp_path: Path
) -> None:
    path = tmp_path / "ledger.sqlite3"
    ledger = module.NonceLedger(path)
    original = tmp_path / "original.sqlite3"
    path.rename(original)
    path.symlink_to(original)
    with pytest.raises(module.CoreReleaseEvidenceError, match="path is unsafe"):
        ledger.reserve(
            owner_selector_ref=OWNER_REF,
            fingerprint=FINGERPRINT,
            nonce="8" * 64,
            payload_sha256="7" * 64,
            now=NOW,
        )


@pytest.mark.parametrize("swapped_field", STAGED_FIELDS)
def test_consumer_uses_one_coherent_staged_generation_when_original_is_swapped(
    module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    swapped_field: str,
) -> None:
    inputs = _inputs(module, tmp_path)
    originals = {field: getattr(inputs, field).read_bytes() for field in STAGED_FIELDS}
    calls = 0

    def derive(staged_inputs: object, *, now: datetime) -> dict[str, object]:
        nonlocal calls
        assert now == NOW
        calls += 1
        if calls == 1:
            getattr(inputs, swapped_field).write_bytes(b"adversarial replacement")
        for field in STAGED_FIELDS:
            staged_path = getattr(staged_inputs, field)
            assert staged_path != getattr(inputs, field)
            assert staged_path.read_bytes() == originals[field]
            assert stat.S_IMODE(staged_path.stat().st_mode) == 0o600
            assert stat.S_IMODE(staged_path.parent.stat().st_mode) == 0o700
            assert staged_path.stat().st_uid == os.geteuid()
        return _snapshot()

    monkeypatch.setattr(module, "_derive_snapshot", derive)
    monkeypatch.setattr(module, "_utc_now", lambda: NOW)
    _mock_auth(monkeypatch, module)
    signature = tmp_path / f"approval-{swapped_field}.sig"
    signature.write_bytes(b"fixture")
    receipt = module.consume_shadow(
        payload=_payload(module),
        signature_path=signature,
        ledger=module.NonceLedger(tmp_path / f"ledger-{swapped_field}.sqlite3"),
        inputs=inputs,
    )
    assert calls == 2
    assert getattr(inputs, swapped_field).read_bytes() == b"adversarial replacement"
    assert receipt["release_authority"] is False


def test_consumer_authenticates_only_the_staged_signature_generation(
    module: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    inputs = _inputs(module, tmp_path)
    _mock_snapshot(monkeypatch, module, _snapshot)
    signature = tmp_path / "approval.sig"
    signature.write_bytes(b"signed generation")

    def authenticate(**kwargs: object) -> dict[str, object]:
        signature.write_bytes(b"adversarial replacement")
        staged_signature = kwargs["signature_path"]
        assert isinstance(staged_signature, Path)
        assert staged_signature != signature
        assert staged_signature.read_bytes() == b"signed generation"
        return {"security_key_counter": 11, "release_authority": False}

    monkeypatch.setattr(module, "authenticate_owner_approval", authenticate)
    receipt = module.consume_shadow(
        payload=_payload(module),
        signature_path=signature,
        ledger=module.NonceLedger(tmp_path / "ledger.sqlite3"),
        inputs=inputs,
    )
    assert signature.read_bytes() == b"adversarial replacement"
    assert receipt["release_authority"] is False


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
