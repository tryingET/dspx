from __future__ import annotations

import hashlib
import json
import os
import signal
import stat
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from typer.testing import CliRunner

from dspx.cli.dspx import app

from dspx.services import soomfon_evaluation_child as child
from dspx.services import soomfon_evaluation_custody as custody
from dspx.services import soomfon_evaluation_executor as executor
from dspx.services import soomfon_evaluation_filesystem as filesystem
from dspx.services import soomfon_evaluation_ledger as soomfon_ledger
from dspx.services import soomfon_evaluation_runtime as soomfon_runtime
from dspx.services.soomfon_evaluation_contract import (
    REQUIRED_ENVIRONMENT,
    classify_provider_disposition,
    load_hash_bound_soomfon_contract,
    validate_case_artifact_bindings,
)
from test_soomfon_evaluation_executor import (
    _effect_behavior,
    _write_mock_runtime_evidence,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_SHA256 = "6c3f913c2fe05eb5edfc39ee0cbea1a4ca43036bdd0e77c9ad3f37d35c0eadae"


@pytest.fixture(autouse=True)
def _provider_free_execution_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    from dspx.services import soomfon_evaluation_authorization as auth
    from dspx.services import soomfon_evaluation_provider as provider
    from dspx.services import soomfon_evaluation_dspx_identity as dspx_identity

    monkeypatch.setattr(
        auth,
        "validate_execution_authorization",
        lambda **_: SimpleNamespace(
            execution_task_id=6000,
            authorization_sha256="f" * 64,
            ak_reconciliation_sha256="e" * 64,
            authorization_path=Path("fixture-authorization.json"),
            dspx_artifact={"kind": "reviewed_source_commit_tree"},
            maximum_provider_transports=12,
        ),
    )
    monkeypatch.setattr(
        dspx_identity, "preload_security_critical_dspx_modules", lambda: None
    )
    monkeypatch.setattr(
        dspx_identity, "verify_executing_dspx_artifact", lambda **_: None
    )
    monkeypatch.setattr(
        provider, "verify_soomfon_owner_source", lambda *_: {"commit": "7" * 40}
    )
    monkeypatch.setattr(
        executor,
        "validate_exact_runtime_identity",
        lambda: {
            "python": "3.13.12",
            "dspx-core": "0.2.1",
            "dspy": "3.3.1",
            "dspy-ai": "3.3.1",
            "gepa": "0.1.4",
            "litellm": "1.82.1",
            "httpx": "0.28.1",
            "httpcore": "1.0.9",
        },
    )


def _execute_suite(**kwargs: Any) -> dict[str, object]:
    return executor.execute_soomfon_evaluation_suite(
        execution_authorization_path=Path("fixture-authorization.json"),
        expected_authorization_sha256="f" * 64,
        owner_source_root=REPO_ROOT,
        **kwargs,
    )


def _patch_roots(monkeypatch: pytest.MonkeyPatch, state_root: Path) -> None:
    monkeypatch.setattr(executor, "_repo_root", lambda: REPO_ROOT)
    monkeypatch.setattr(executor, "default_state_root", lambda: state_root)


def _ledger_with_evidence(
    tmp_path: Path, *, mode: str = "simple"
) -> tuple[Path, int, dict[str, str]]:
    suite, suite_fd = custody.ensure_private_tree(tmp_path / "suite")
    os.close(suite_fd)
    ledger, ledger_fd = custody.ensure_private_tree(suite / "ledger")
    raw, raw_fd = custody.ensure_private_tree(suite / "raw" / mode)
    os.close(raw_fd)
    runtime_sha256, tree_sha256, behavior_sha256, receipt_sha256 = (
        _write_mock_runtime_evidence(raw)
    )
    evidence = {
        "runtime_episode_sha256": runtime_sha256,
        "runtime_tree_sha256": tree_sha256,
        "runtime_receipt_sha256": receipt_sha256,
        "behavior_results_sha256": behavior_sha256,
    }
    return ledger, ledger_fd, evidence


def test_private_tree_rejects_wrong_mode_and_intermediate_symlink(
    tmp_path: Path,
) -> None:
    wrong = tmp_path / "wrong"
    wrong.mkdir(mode=0o755)
    wrong.chmod(0o755)
    with pytest.raises(custody.SoomfonCustodyError, match="unsafe"):
        custody.ensure_private_tree(wrong)

    target = tmp_path / "target"
    target.mkdir(mode=0o700)
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(custody.SoomfonCustodyError, match="unavailable"):
        custody.ensure_private_tree(link / "child")


def test_existing_ledger_directory_rejects_wrong_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger = tmp_path / "ledger"
    ledger.mkdir(mode=0o700)
    ledger.chmod(0o700)
    real_fstat = filesystem.os.fstat

    def wrong_ledger_owner(fd: int):
        info = real_fstat(fd)
        try:
            opened = Path(os.readlink(f"/proc/self/fd/{fd}")).resolve()
        except OSError:
            return info
        if opened == ledger.resolve():
            return SimpleNamespace(st_mode=info.st_mode, st_uid=info.st_uid + 1)
        return info

    monkeypatch.setattr(filesystem.os, "fstat", wrong_ledger_owner)
    with pytest.raises(filesystem.SoomfonCustodyError, match="unsafe"):
        filesystem.ensure_private_tree(ledger)


def test_suite_lock_rejects_wrong_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, root_fd = custody.ensure_private_tree(tmp_path / "suite")
    del root
    real_fstat = custody.os.fstat

    def wrong_owner(fd: int):
        info = real_fstat(fd)
        return SimpleNamespace(st_mode=info.st_mode, st_uid=info.st_uid + 1)

    monkeypatch.setattr(custody.os, "fstat", wrong_owner)
    try:
        with pytest.raises(custody.SoomfonCustodyError, match="identity"):
            custody.acquire_suite_lock(root_fd)
    finally:
        os.close(root_fd)


def test_attempt_marker_directory_fsync_failure_blocks_effect_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger, ledger_fd = custody.ensure_private_tree(tmp_path / "ledger")
    del ledger
    real_fsync = custody.os.fsync

    def fail_ledger_fsync(fd: int) -> None:
        if fd == ledger_fd:
            raise OSError("injected containing-directory fsync failure")
        real_fsync(fd)

    monkeypatch.setattr(custody.os, "fsync", fail_ledger_fsync)
    try:
        with pytest.raises(OSError, match="containing-directory"):
            executor._persist_attempt_before_effect(
                ledger_fd=ledger_fd,
                contract_sha256=CONTRACT_SHA256,
                mode="simple",
                execution_task_id=6000,
                authorization_sha256="f" * 64,
                ak_reconciliation_sha256="e" * 64,
            )
    finally:
        os.close(ledger_fd)


def test_private_tree_creation_fsyncs_each_new_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[int] = []
    monkeypatch.setattr(custody.os, "fsync", lambda fd: calls.append(fd))
    path, fd = custody.ensure_private_tree(tmp_path / "one/two/three")
    os.close(fd)
    assert path == tmp_path / "one/two/three"
    assert len(calls) >= 3
    for part in (tmp_path / "one", tmp_path / "one/two", path):
        assert stat.S_IMODE(part.stat().st_mode) == 0o700


def test_attempt_marker_is_no_replace_and_reconciles_lone_state(
    tmp_path: Path,
) -> None:
    ledger, ledger_fd = custody.ensure_private_tree(tmp_path / "ledger")
    try:
        marker_fd, name = custody.create_attempt_marker(
            ledger_fd=ledger_fd,
            contract_sha256=CONTRACT_SHA256,
            mode="simple",
            execution_task_id=6000,
            authorization_sha256="f" * 64,
            ak_reconciliation_sha256="e" * 64,
        )
        os.close(marker_fd)
        with pytest.raises(custody.SoomfonCustodyError, match="already consumed"):
            custody.create_attempt_marker(
                ledger_fd=ledger_fd,
                contract_sha256=CONTRACT_SHA256,
                mode="simple",
                execution_task_id=6000,
                authorization_sha256="f" * 64,
                ak_reconciliation_sha256="e" * 64,
            )
        records = [
            json.loads(line) for line in (ledger / name).read_text().splitlines()
        ]
        assert [record["state"] for record in records] == ["attempted_outcome_unknown"]
        sidecar = ledger / f"{name}.reconciled-indeterminate.json"
        reconciliation = json.loads(sidecar.read_text())
        assert reconciliation["state"] == "effect_indeterminate"
        assert reconciliation["reason"] == "reconciled_existing_consumed_marker"
    finally:
        os.close(ledger_fd)


def test_corrupt_reconciliation_sidecar_uses_valid_repair(tmp_path: Path) -> None:
    ledger, ledger_fd = custody.ensure_private_tree(tmp_path / "ledger")
    marker_fd, name = custody.create_attempt_marker(
        ledger_fd=ledger_fd,
        contract_sha256=CONTRACT_SHA256,
        mode="simple",
        execution_task_id=6000,
        authorization_sha256="f" * 64,
        ak_reconciliation_sha256="e" * 64,
    )
    os.close(marker_fd)
    canonical = ledger / f"{name}.reconciled-indeterminate.json"
    canonical.write_text("{corrupt\n", encoding="utf-8")
    canonical.chmod(0o600)
    try:
        with pytest.raises(custody.SoomfonCustodyError, match="already consumed"):
            custody.create_attempt_marker(
                ledger_fd=ledger_fd,
                contract_sha256=CONTRACT_SHA256,
                mode="simple",
                execution_task_id=6000,
                authorization_sha256="f" * 64,
                ak_reconciliation_sha256="e" * 64,
            )
        repair = ledger / f"{canonical.name}.repair.json"
        assert json.loads(repair.read_text())["state"] == "effect_indeterminate"
    finally:
        os.close(ledger_fd)


def test_two_corrupt_reconciliation_sidecars_fail_closed(tmp_path: Path) -> None:
    ledger, ledger_fd = custody.ensure_private_tree(tmp_path / "ledger")
    marker_fd, name = custody.create_attempt_marker(
        ledger_fd=ledger_fd,
        contract_sha256=CONTRACT_SHA256,
        mode="simple",
        execution_task_id=6000,
        authorization_sha256="f" * 64,
        ak_reconciliation_sha256="e" * 64,
    )
    os.close(marker_fd)
    canonical = ledger / f"{name}.reconciled-indeterminate.json"
    for path in (canonical, ledger / f"{canonical.name}.repair.json"):
        path.write_text("{}\n", encoding="utf-8")
        path.chmod(0o600)
    try:
        with pytest.raises(
            custody.SoomfonCustodyError,
            match="indeterminate reconciliation sidecars are invalid",
        ):
            custody.reconcile_marker_indeterminate(
                ledger_fd=ledger_fd,
                marker_name=name,
                reason="reconciled_existing_consumed_marker",
            )
    finally:
        os.close(ledger_fd)


def test_attempt_marker_terminal_append_is_durable(tmp_path: Path) -> None:
    ledger, ledger_fd = custody.ensure_private_tree(tmp_path / "ledger")
    try:
        marker_fd, name = custody.create_attempt_marker(
            ledger_fd=ledger_fd,
            contract_sha256=CONTRACT_SHA256,
            mode="simple",
            execution_task_id=6000,
            authorization_sha256="f" * 64,
            ak_reconciliation_sha256="e" * 64,
        )
        try:
            custody.append_terminal(
                marker_fd=marker_fd,
                ledger_fd=ledger_fd,
                contract_sha256=CONTRACT_SHA256,
                mode="simple",
                state="effect_indeterminate",
                details={"reason": "durability_test", "latency_ms": 1},
            )
        finally:
            os.close(marker_fd)
        records = [
            json.loads(line) for line in (ledger / name).read_text().splitlines()
        ]
        assert [record["sequence"] for record in records] == [0, 1]
        assert {record["execution_task_id"] for record in records} == {6000}
        assert {record["authorization_sha256"] for record in records} == {"f" * 64}
        assert {record["ak_reconciliation_sha256"] for record in records} == {"e" * 64}
        assert [record["state"] for record in records] == [
            "attempted_outcome_unknown",
            "effect_indeterminate",
        ]
        assert stat.S_IMODE((ledger / name).stat().st_mode) == 0o600
    finally:
        os.close(ledger_fd)


def test_completed_marker_is_not_reconciled_indeterminate(tmp_path: Path) -> None:
    ledger, ledger_fd, evidence = _ledger_with_evidence(tmp_path)
    try:
        marker_fd, name = custody.create_attempt_marker(
            ledger_fd=ledger_fd,
            contract_sha256=CONTRACT_SHA256,
            mode="simple",
            execution_task_id=6000,
            authorization_sha256="f" * 64,
            ak_reconciliation_sha256="e" * 64,
        )
        custody.append_terminal(
            marker_fd=marker_fd,
            ledger_fd=ledger_fd,
            contract_sha256=CONTRACT_SHA256,
            mode="simple",
            state="succeeded",
            details={
                "latency_ms": 1,
                "response_sha256": hashlib.sha256(b"bounded mock response").hexdigest(),
                "response_length": len("bounded mock response"),
                "runtime_episode_sha256": evidence["runtime_episode_sha256"],
                "runtime_tree_sha256": evidence["runtime_tree_sha256"],
                "runtime_receipt_sha256": evidence["runtime_receipt_sha256"],
                "behavior_results_sha256": evidence["behavior_results_sha256"],
                "provider": classify_provider_disposition(
                    _effect_behavior("completed_success", dispatch_count=1)
                )[1],
            },
        )
        os.close(marker_fd)
        with pytest.raises(custody.SoomfonCustodyError, match="already consumed"):
            custody.create_attempt_marker(
                ledger_fd=ledger_fd,
                contract_sha256=CONTRACT_SHA256,
                mode="simple",
                execution_task_id=6000,
                authorization_sha256="f" * 64,
                ak_reconciliation_sha256="e" * 64,
            )
        assert not (ledger / f"{name}.reconciled-indeterminate.json").exists()
    finally:
        os.close(ledger_fd)


def test_forged_success_without_exact_provider_evidence_is_reconciled(
    tmp_path: Path,
) -> None:
    ledger, ledger_fd = custody.ensure_private_tree(tmp_path / "ledger")
    marker_fd, name = custody.create_attempt_marker(
        ledger_fd=ledger_fd,
        contract_sha256=CONTRACT_SHA256,
        mode="simple",
        execution_task_id=6000,
        authorization_sha256="f" * 64,
        ak_reconciliation_sha256="e" * 64,
    )
    with pytest.raises(custody.SoomfonCustodyError, match="terminal evidence"):
        custody.append_terminal(
            marker_fd=marker_fd,
            ledger_fd=ledger_fd,
            contract_sha256=CONTRACT_SHA256,
            mode="simple",
            state="succeeded",
            details={
                "latency_ms": 1,
                "response_sha256": "a" * 64,
                "response_length": True,
                "runtime_episode_sha256": "b" * 64,
                "behavior_results_sha256": "c" * 64,
                "provider": {
                    "terminal_effect": "completed_success",
                    "attempt_total": 1,
                    "dispositions": ["completed_success"],
                    "dispatch_counts": [True],
                },
            },
        )
    os.close(marker_fd)
    try:
        with pytest.raises(custody.SoomfonCustodyError, match="already consumed"):
            custody.create_attempt_marker(
                ledger_fd=ledger_fd,
                contract_sha256=CONTRACT_SHA256,
                mode="simple",
                execution_task_id=6000,
                authorization_sha256="f" * 64,
                ak_reconciliation_sha256="e" * 64,
            )
        assert (ledger / f"{name}.reconciled-indeterminate.json").is_file()
    finally:
        os.close(ledger_fd)


@pytest.mark.parametrize(
    ("state", "effect", "dispatch_count"),
    [
        ("succeeded", "completed_success", 1),
        ("failed_no_effect_proved", "preflight_rejected", 0),
    ],
)
def test_exact_terminal_shape_without_bound_evidence_is_incomplete(
    state: str, effect: str, dispatch_count: int
) -> None:
    name = f"{CONTRACT_SHA256}.simple.jsonl"
    details: dict[str, object] = {
        "latency_ms": 1,
        "runtime_episode_sha256": "a" * 64,
        "runtime_tree_sha256": "d" * 64,
        "runtime_receipt_sha256": "c" * 64,
        "behavior_results_sha256": "b" * 64,
        "provider": {
            "terminal_effect": effect,
            "attempt_total": 1,
            "dispositions": [effect],
            "dispatch_counts": [dispatch_count],
        },
    }
    if state == "succeeded":
        details.update(response_sha256="c" * 64, response_length=1)
    records = [
        {
            "schema_version": soomfon_ledger.LEDGER_SCHEMA,
            "contract_sha256": CONTRACT_SHA256,
            "mode": "simple",
            "state": "attempted_outcome_unknown",
            "sequence": 0,
        },
        {
            "schema_version": soomfon_ledger.LEDGER_SCHEMA,
            "contract_sha256": CONTRACT_SHA256,
            "mode": "simple",
            "state": state,
            "sequence": 1,
            "details": details,
        },
    ]
    assert not soomfon_ledger.is_complete_terminal_marker(records, name)


def test_terminal_fsync_failure_forces_indeterminate_sidecar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger, ledger_fd = custody.ensure_private_tree(tmp_path / "ledger")
    marker_fd, name = custody.create_attempt_marker(
        ledger_fd=ledger_fd,
        contract_sha256=CONTRACT_SHA256,
        mode="simple",
        execution_task_id=6000,
        authorization_sha256="f" * 64,
        ak_reconciliation_sha256="e" * 64,
    )
    real_fsync = custody.os.fsync
    monkeypatch.setattr(
        custody.os,
        "fsync",
        lambda _: (_ for _ in ()).throw(OSError("simulated terminal fsync failure")),
    )
    with pytest.raises(OSError, match="terminal fsync"):
        custody.append_terminal(
            marker_fd=marker_fd,
            ledger_fd=ledger_fd,
            contract_sha256=CONTRACT_SHA256,
            mode="simple",
            state="effect_indeterminate",
            details={"latency_ms": 1, "reason": "fsync_failure_test"},
        )
    monkeypatch.setattr(custody.os, "fsync", real_fsync)
    custody.reconcile_marker_indeterminate(
        ledger_fd=ledger_fd,
        marker_name=name,
        reason="terminal_persistence_failed",
    )
    assert (ledger / f"{name}.reconciled-indeterminate.json").is_file()
    os.close(marker_fd)
    os.close(ledger_fd)


def test_identity_corrupt_two_record_marker_is_reconciled(tmp_path: Path) -> None:
    ledger, ledger_fd = custody.ensure_private_tree(tmp_path / "ledger")
    marker_fd, name = custody.create_attempt_marker(
        ledger_fd=ledger_fd,
        contract_sha256=CONTRACT_SHA256,
        mode="simple",
        execution_task_id=6000,
        authorization_sha256="f" * 64,
        ak_reconciliation_sha256="e" * 64,
    )
    forged = {
        "schema_version": "soomfon-dspy33-attempt-ledger-v1",
        "contract_sha256": "d" * 64,
        "mode": "bloom",
        "state": "effect_indeterminate",
        "sequence": 1,
        "details": {"latency_ms": 1, "reason": "forged_identity"},
    }
    os.write(marker_fd, (json.dumps(forged) + "\n").encode())
    os.fsync(marker_fd)
    os.fsync(ledger_fd)
    os.close(marker_fd)
    with pytest.raises(custody.SoomfonCustodyError, match="already consumed"):
        custody.create_attempt_marker(
            ledger_fd=ledger_fd,
            contract_sha256=CONTRACT_SHA256,
            mode="simple",
            execution_task_id=6000,
            authorization_sha256="f" * 64,
            ak_reconciliation_sha256="e" * 64,
        )
    assert (ledger / f"{name}.reconciled-indeterminate.json").is_file()
    os.close(ledger_fd)


def test_partial_terminal_append_is_reconciled_and_never_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger, ledger_fd = custody.ensure_private_tree(tmp_path / "ledger")
    marker_fd, name = custody.create_attempt_marker(
        ledger_fd=ledger_fd,
        contract_sha256=CONTRACT_SHA256,
        mode="simple",
        execution_task_id=6000,
        authorization_sha256="f" * 64,
        ak_reconciliation_sha256="e" * 64,
    )
    real_write = custody.os.write

    def partial_write(fd: int, raw: bytes) -> int:
        return real_write(fd, raw[: max(1, len(raw) // 2)])

    monkeypatch.setattr(custody.os, "write", partial_write)
    with pytest.raises(custody.SoomfonCustodyError, match="incomplete"):
        custody.append_terminal(
            marker_fd=marker_fd,
            ledger_fd=ledger_fd,
            contract_sha256=CONTRACT_SHA256,
            mode="simple",
            state="effect_indeterminate",
            details={"latency_ms": 1, "reason": "partial_write_test"},
        )
    os.close(marker_fd)
    monkeypatch.setattr(custody.os, "write", real_write)
    with pytest.raises(custody.SoomfonCustodyError, match="already consumed"):
        custody.create_attempt_marker(
            ledger_fd=ledger_fd,
            contract_sha256=CONTRACT_SHA256,
            mode="simple",
            execution_task_id=6000,
            authorization_sha256="f" * 64,
            ak_reconciliation_sha256="e" * 64,
        )
    assert (ledger / f"{name}.reconciled-indeterminate.json").is_file()
    os.close(ledger_fd)


def test_child_dispatch_claim_is_exclusive(tmp_path: Path) -> None:
    _, ledger_fd = custody.ensure_private_tree(tmp_path / "ledger")
    try:
        custody._claim_child_dispatch(
            ledger_fd=ledger_fd,
            contract_sha256=CONTRACT_SHA256,
            mode="simple",
            execution_task_id=6000,
            authorization_sha256="f" * 64,
            ak_reconciliation_sha256="e" * 64,
        )
        with pytest.raises(custody.SoomfonCustodyError, match="claim is consumed"):
            custody._claim_child_dispatch(
                ledger_fd=ledger_fd,
                contract_sha256=CONTRACT_SHA256,
                mode="simple",
                execution_task_id=6000,
                authorization_sha256="f" * 64,
                ak_reconciliation_sha256="e" * 64,
            )
    finally:
        os.close(ledger_fd)


def test_suite_lock_rejects_concurrent_owner(tmp_path: Path) -> None:
    _, root_fd = custody.ensure_private_tree(tmp_path / "suite")
    first_lock_fd = custody.acquire_suite_lock(root_fd)
    try:
        with pytest.raises(custody.SoomfonCustodyError, match="already running"):
            custody.acquire_suite_lock(root_fd)
    finally:
        custody.fcntl.flock(first_lock_fd, custody.fcntl.LOCK_UN)
        os.close(first_lock_fd)
        os.close(root_fd)


def test_suite_lock_rejects_another_process(tmp_path: Path) -> None:
    suite, root_fd = custody.ensure_private_tree(tmp_path / "suite")
    lock_fd = custody.acquire_suite_lock(root_fd)
    code = """
import os, sys
from pathlib import Path
from dspx.services.soomfon_evaluation_custody import (
    SoomfonCustodyError, acquire_suite_lock, ensure_private_tree,
)
_, fd = ensure_private_tree(Path(sys.argv[1]))
try:
    acquire_suite_lock(fd)
except SoomfonCustodyError:
    raise SystemExit(0)
raise SystemExit(3)
"""
    try:
        result = subprocess.run(
            [sys.executable, "-c", code, str(suite)],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
    finally:
        custody.fcntl.flock(lock_fd, custody.fcntl.LOCK_UN)
        os.close(lock_fd)
        os.close(root_fd)


def test_staged_protected_candidate_requires_and_accepts_fixed_custody(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dspx.services import soomfon_evaluation_contract as contract_service
    from dspx.services import soomfon_evaluation_provider as provider_service

    state_root = tmp_path / "state"
    monkeypatch.setattr(custody, "default_state_root", lambda: state_root)
    monkeypatch.setattr(provider_service, "verify_soomfon_owner_source", lambda *_: {})
    monkeypatch.setattr(executor, "marker_sha256", lambda *_: "b" * 64)
    monkeypatch.setattr(contract_service, "validate_exact_runtime_identity", lambda: {})
    for key in contract_service.FORBIDDEN_ENVIRONMENT:
        monkeypatch.delenv(key, raising=False)
    contract, _, _ = load_hash_bound_soomfon_contract(
        repo_root=REPO_ROOT, expected_sha256=CONTRACT_SHA256
    )
    case = validate_case_artifact_bindings(repo_root=REPO_ROOT, contract=contract)[0]
    _, state_fd = custody.ensure_private_tree(state_root)
    suite, suite_fd = custody.ensure_private_tree(state_root / CONTRACT_SHA256)
    _, ledger_fd = custody.ensure_private_tree(suite / "ledger")
    _, stage_fd = custody.ensure_private_tree(suite / "stage")
    os.close(stage_fd)
    raw, raw_fd = custody.ensure_private_tree(suite / "raw/simple")
    _, provider_fd = custody.ensure_private_tree(suite / "provider-outcomes/simple")
    lock_fd = custody.acquire_suite_lock(suite_fd)
    marker_fd, _ = custody.create_attempt_marker(
        ledger_fd=ledger_fd,
        contract_sha256=CONTRACT_SHA256,
        mode="simple",
        execution_task_id=6000,
        authorization_sha256="f" * 64,
        ak_reconciliation_sha256="e" * 64,
    )
    runtime_fd = -1
    child_cwd_fd = -1
    try:
        staged_manifest = custody.stage_candidate(case, suite / "stage/simple")
        inputs = raw / "inputs.json"
        inputs_sha256 = executor._write_private_json(
            inputs,
            {
                "inputs": {
                    "transcription": case["transcription"],
                    "persona_intent": case["persona_intent"],
                }
            },
        )
        _, child_cwd_fd = custody.ensure_private_tree(raw / "empty-cwd")
        runtime_path, runtime_fd = child.create_child_runtime_directory(
            raw_root_fd=raw_fd, inputs_path=inputs, outdir=raw / "runtime"
        )
        fixed = custody.SoomfonRuntimeCustody(
            contract_sha256=CONTRACT_SHA256,
            mode="simple",
            expected_manifest_sha256=str(case["manifest_sha256"]),
            expected_receipt_sha256=str(case["manifest_receipt_sha256"]),
            staged_manifest_path=staged_manifest.resolve(),
            inputs_path=inputs.resolve(),
            expected_inputs_sha256=inputs_sha256,
            outdir=(raw / "runtime").resolve(),
            raw_root_fd=raw_fd,
            runtime_fd=runtime_fd,
            marker_fd=marker_fd,
            ledger_fd=ledger_fd,
            lock_fd=lock_fd,
            provider_journal_fd=provider_fd,
            execution_task_id=6000,
            authorization_sha256="f" * 64,
            ak_reconciliation_sha256="e" * 64,
            authorization_path=Path("fixture-authorization.json"),
            repo_root=REPO_ROOT,
            owner_source_root=REPO_ROOT,
        )
        snapshot = custody.validate_runtime_custody(
            manifest_path=staged_manifest,
            manifest_sha256=str(case["manifest_sha256"]),
            inputs_path=inputs,
            outdir=raw / "runtime",
            custody=fixed,
        )
        assert snapshot is not None
        with pytest.raises(custody.SoomfonCustodyError, match="child claim"):
            custody.validate_runtime_custody(
                manifest_path=staged_manifest,
                manifest_sha256=str(case["manifest_sha256"]),
                inputs_path=inputs,
                outdir=raw / "runtime",
                custody=fixed,
            )
        assert str(runtime_path).startswith("/proc/self/fd/")
    finally:
        for fd in (
            runtime_fd,
            child_cwd_fd,
            marker_fd,
            provider_fd,
            ledger_fd,
            raw_fd,
            state_fd,
        ):
            if fd >= 0:
                os.close(fd)
        custody.fcntl.flock(lock_fd, custody.fcntl.LOCK_UN)
        os.close(lock_fd)
        os.close(suite_fd)


def test_executor_interruption_is_durably_indeterminate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def crash(**_: Any) -> tuple[str, dict[str, object]]:
        raise KeyboardInterrupt

    state_root = tmp_path / "state"
    _patch_roots(monkeypatch, state_root)
    monkeypatch.setattr(executor, "_evaluate_case", crash)
    payload = _execute_suite(
        expected_contract_sha256=CONTRACT_SHA256,
        environment=REQUIRED_ENVIRONMENT,
    )
    assert payload["state"] == "stopped_non_success"
    results = payload["case_results"]
    assert isinstance(results, list)
    assert isinstance(results[0], dict)
    first = cast(dict[str, object], results[0])
    assert first["state"] == "effect_indeterminate"
    marker = next((state_root / CONTRACT_SHA256 / "ledger").glob("*.jsonl"))
    records = [json.loads(line) for line in marker.read_text().splitlines()]
    assert [record["state"] for record in records] == [
        "attempted_outcome_unknown",
        "effect_indeterminate",
    ]


@pytest.mark.parametrize("interruption", ["keyboard", "timeout"])
def test_run_child_kills_group_on_supervision_interruption(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    interruption: str,
) -> None:
    class FakeProcess:
        pid = 424242
        waits = 0

        def wait(self, timeout: int | None = None) -> int:
            del timeout
            self.waits += 1
            if self.waits == 1:
                if interruption == "keyboard":
                    raise KeyboardInterrupt
                raise subprocess.TimeoutExpired(cmd=("python",), timeout=1)
            return -signal.SIGKILL

    process = FakeProcess()
    kills: list[tuple[int, int]] = []
    popen_calls: list[tuple[tuple[str, ...], dict[str, object]]] = []

    def fake_popen(argv: tuple[str, ...], **kwargs: object) -> FakeProcess:
        popen_calls.append((argv, kwargs))
        return process

    monkeypatch.setattr(child.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(child.os, "killpg", lambda pid, sig: kills.append((pid, sig)))
    raw, raw_fd = custody.ensure_private_tree(tmp_path / "raw")
    os.close(raw_fd)
    expected = (
        KeyboardInterrupt if interruption == "keyboard" else subprocess.TimeoutExpired
    )
    with pytest.raises(expected):
        executor._run_child(
            case={
                "transcription": "fixed",
                "persona_intent": "fixed",
                "mode": "simple",
                "manifest_sha256": "a" * 64,
                "manifest_receipt_sha256": "b" * 64,
            },
            staged_manifest=tmp_path / "manifest.json",
            raw_root=raw,
            child_environment={},
            contract_sha256=CONTRACT_SHA256,
            marker_fd=10,
            ledger_fd=11,
            lock_fd=12,
            provider_journal_fd=13,
            execution_task_id=6000,
            authorization_sha256="f" * 64,
            ak_reconciliation_sha256="e" * 64,
            owner_source_root=REPO_ROOT,
            authorization_path=Path("fixture-authorization.json"),
            repo_root=REPO_ROOT,
        )
    assert kills == [(process.pid, signal.SIGKILL)]
    assert process.waits == 2
    argv, kwargs = popen_calls[0]
    assert argv[1:4] == ("-B", "-I", "-P")
    assert cast(dict[str, str], kwargs["env"])["PYTHONDONTWRITEBYTECODE"] == "1"


def test_run_child_kills_group_when_quiescence_probe_is_interrupted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeProcess:
        pid = 434343
        waits = 0

        def wait(self, timeout: int | None = None) -> int:
            del timeout
            self.waits += 1
            return 0 if self.waits == 1 else -signal.SIGKILL

    process = FakeProcess()
    kills: list[tuple[int, int]] = []
    monkeypatch.setattr(child.subprocess, "Popen", lambda *_, **__: process)
    monkeypatch.setattr(
        child,
        "_assert_child_group_quiescent",
        lambda _: (_ for _ in ()).throw(KeyboardInterrupt),
    )
    monkeypatch.setattr(child.os, "killpg", lambda pid, sig: kills.append((pid, sig)))
    raw, raw_fd = custody.ensure_private_tree(tmp_path / "raw")
    os.close(raw_fd)
    with pytest.raises(KeyboardInterrupt):
        executor._run_child(
            case={
                "transcription": "fixed",
                "persona_intent": "fixed",
                "mode": "simple",
                "manifest_sha256": "a" * 64,
                "manifest_receipt_sha256": "b" * 64,
            },
            staged_manifest=tmp_path / "manifest.json",
            raw_root=raw,
            child_environment={},
            contract_sha256=CONTRACT_SHA256,
            marker_fd=10,
            ledger_fd=11,
            lock_fd=12,
            provider_journal_fd=13,
            execution_task_id=6000,
            authorization_sha256="f" * 64,
            ak_reconciliation_sha256="e" * 64,
            owner_source_root=REPO_ROOT,
            authorization_path=Path("fixture-authorization.json"),
            repo_root=REPO_ROOT,
        )
    assert kills == [(process.pid, signal.SIGKILL)]
    assert process.waits == 2


def test_run_child_rejects_nonempty_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw, raw_fd = custody.ensure_private_tree(tmp_path / "raw")
    os.close(raw_fd)
    child_cwd, child_cwd_fd = custody.ensure_private_tree(raw / "empty-cwd")
    os.close(child_cwd_fd)
    (child_cwd / "unexpected").write_text("unsafe", encoding="utf-8")
    monkeypatch.setattr(
        executor.subprocess,
        "Popen",
        lambda *_, **__: pytest.fail("child must not start"),
    )
    with pytest.raises(executor.SoomfonEvaluationExecutorError, match="not empty"):
        executor._run_child(
            case={
                "transcription": "fixed",
                "persona_intent": "fixed",
                "mode": "simple",
                "manifest_sha256": "a" * 64,
                "manifest_receipt_sha256": "b" * 64,
            },
            staged_manifest=tmp_path / "manifest.json",
            raw_root=raw,
            child_environment={},
            contract_sha256=CONTRACT_SHA256,
            marker_fd=10,
            ledger_fd=11,
            lock_fd=12,
            provider_journal_fd=13,
            execution_task_id=6000,
            authorization_sha256="f" * 64,
            ak_reconciliation_sha256="e" * 64,
            owner_source_root=REPO_ROOT,
            authorization_path=Path("fixture-authorization.json"),
            repo_root=REPO_ROOT,
        )


def test_child_rejects_replaced_working_directory_binding(tmp_path: Path) -> None:
    raw, raw_fd = custody.ensure_private_tree(tmp_path / "raw")
    child_cwd, child_cwd_fd = custody.ensure_private_tree(raw / "empty-cwd")
    original_cwd_fd = os.open(".", os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fchdir(child_cwd_fd)
        child_cwd.rename(raw / "displaced-cwd")
        child_cwd.mkdir(mode=0o700)
        with pytest.raises(ValueError, match="working directory custody drifts"):
            soomfon_runtime.validate_child_working_directory(
                cwd_fd=child_cwd_fd,
                raw_root_fd=raw_fd,
            )
    finally:
        os.fchdir(original_cwd_fd)
        os.close(original_cwd_fd)
        os.close(child_cwd_fd)
        os.close(raw_fd)


def test_parent_death_custody_rejects_wrong_parent() -> None:
    with pytest.raises(RuntimeError, match="parent identity"):
        child._arm_parent_death(os.getppid() + 1)


def test_child_timeout_is_terminal_indeterminate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        executor,
        "_run_child",
        lambda **_: (_ for _ in ()).throw(
            subprocess.TimeoutExpired(cmd=("python",), timeout=1)
        ),
    )
    raw, raw_fd = custody.ensure_private_tree(tmp_path / "raw")
    os.close(raw_fd)
    state, details = executor._evaluate_case(
        case={},
        staged_manifest=tmp_path / "manifest.json",
        raw_root=raw,
        child_environment={},
        contract_sha256=CONTRACT_SHA256,
        marker_fd=-1,
        ledger_fd=-1,
        lock_fd=-1,
        provider_journal_fd=-1,
        execution_task_id=6000,
        authorization_sha256="f" * 64,
        ak_reconciliation_sha256="e" * 64,
        owner_source_root=REPO_ROOT,
        authorization_path=Path("fixture-authorization.json"),
        repo_root=REPO_ROOT,
    )
    assert state == "effect_indeterminate"
    assert details["reason"] == "child_timeout"
    assert isinstance(details["latency_ms"], int)


def test_post_marker_staging_failure_is_terminal_indeterminate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_root = tmp_path / "state"
    _patch_roots(monkeypatch, state_root)
    monkeypatch.setattr(
        executor,
        "stage_candidate",
        lambda *_: (_ for _ in ()).throw(OSError("simulated staging failure")),
    )
    payload = _execute_suite(
        expected_contract_sha256=CONTRACT_SHA256,
        environment=REQUIRED_ENVIRONMENT,
    )
    result = cast(list[dict[str, object]], payload["case_results"])[0]
    assert result["state"] == "effect_indeterminate"
    assert result["reason"] == "post_marker_staging_failed"
    assert isinstance(result["latency_ms"], int)


def test_raw_persistence_failure_retains_latency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw, raw_fd = custody.ensure_private_tree(tmp_path / "raw")
    os.close(raw_fd)
    monkeypatch.setattr(executor, "_run_child", lambda **_: (0, 7))
    monkeypatch.setattr(
        executor,
        "fsync_private_tree",
        lambda *_: (_ for _ in ()).throw(OSError("simulated raw fsync failure")),
    )
    state, details = executor._evaluate_case(
        case={},
        staged_manifest=tmp_path / "manifest.json",
        raw_root=raw,
        child_environment={},
        contract_sha256=CONTRACT_SHA256,
        marker_fd=-1,
        ledger_fd=-1,
        lock_fd=-1,
        provider_journal_fd=-1,
        execution_task_id=6000,
        authorization_sha256="f" * 64,
        ak_reconciliation_sha256="e" * 64,
        owner_source_root=REPO_ROOT,
        authorization_path=Path("fixture-authorization.json"),
        repo_root=REPO_ROOT,
    )
    assert state == "effect_indeterminate"
    assert details == {
        "reason": "raw_evidence_persistence_failed",
        "error_type": "OSError",
        "latency_ms": 7,
    }


def test_degraded_runtime_cannot_be_classified_succeeded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dspx.services import soomfon_evaluation_provider as provider_service

    monkeypatch.setattr(provider_service, "verify_soomfon_owner_source", lambda *_: {})
    monkeypatch.setattr(executor, "marker_sha256", lambda *_: "b" * 64)
    monkeypatch.setattr(
        provider_service,
        "verify_retained_soomfon_journals",
        lambda *_args, **_kwargs: None,
    )
    raw, raw_fd = custody.ensure_private_tree(tmp_path / "raw")
    os.close(raw_fd)
    monkeypatch.setattr(executor, "_run_child", lambda **_: (0, 4))
    _, journal_fd = custody.ensure_private_tree(tmp_path / "journals")
    (raw / "runtime").mkdir(mode=0o700)
    monkeypatch.setattr(
        executor, "private_runtime_tree_sha256_path", lambda _: "d" * 64
    )
    monkeypatch.setattr(executor, "fsync_private_tree", lambda *_: None)
    completed = _effect_behavior("completed_success", dispatch_count=1)
    completed["examples"] = [{"observed_outputs": {"response": "bounded"}}]
    monkeypatch.setattr(
        executor,
        "load_validated_program_runtime_episode_bundle",
        lambda **_: SimpleNamespace(
            runtime_episode={"execution_status": "degraded_missing_outputs"},
            behavior_results=completed,
            runtime_episode_sha256="a" * 64,
            runtime_receipt_sha256="c" * 64,
            behavior_results_sha256="b" * 64,
        ),
    )
    monkeypatch.setattr(
        executor,
        "runtime_evidence_hashes",
        lambda *_: {"runtime_tree_sha256": "d" * 64},
    )
    state, details = executor._evaluate_case(
        case={"manifest_payload": {}, "manifest_sha256": "c" * 64, "mode": "simple"},
        staged_manifest=tmp_path / "manifest.json",
        raw_root=raw,
        child_environment={},
        contract_sha256=CONTRACT_SHA256,
        marker_fd=-1,
        ledger_fd=-1,
        lock_fd=-1,
        provider_journal_fd=journal_fd,
        execution_task_id=6000,
        authorization_sha256="f" * 64,
        ak_reconciliation_sha256="e" * 64,
        owner_source_root=REPO_ROOT,
        authorization_path=Path("fixture-authorization.json"),
        repo_root=REPO_ROOT,
    )
    os.close(journal_fd)
    assert state == "effect_indeterminate"
    assert cast(dict[str, object], details["provider"])["reason"] == (
        "runtime_execution_not_successful"
    )


def test_terminal_keyboard_interrupt_reconciles_indeterminate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_root = tmp_path / "state"
    _patch_roots(monkeypatch, state_root)
    monkeypatch.setattr(
        executor,
        "_evaluate_case",
        lambda **_: (
            "effect_indeterminate",
            {"latency_ms": 1, "reason": "mock_indeterminate"},
        ),
    )
    monkeypatch.setattr(
        executor,
        "append_terminal",
        lambda **_: (_ for _ in ()).throw(KeyboardInterrupt),
    )
    payload = _execute_suite(
        expected_contract_sha256=CONTRACT_SHA256,
        environment=REQUIRED_ENVIRONMENT,
    )
    assert payload["state"] == "stopped_non_success"
    marker = next((state_root / CONTRACT_SHA256 / "ledger").glob("*.jsonl"))
    sidecar = marker.with_name(f"{marker.name}.reconciled-indeterminate.json")
    assert json.loads(sidecar.read_text())["state"] == "effect_indeterminate"


def test_cli_requires_out_of_band_hash() -> None:
    result = CliRunner().invoke(app, ["soomfon", "evaluate-originals"])
    assert result.exit_code != 0
    assert "expected-contract-sha256" in result.stderr
