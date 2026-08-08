from __future__ import annotations

import hashlib
import json
import multiprocessing as mp
import os
import socket
import sqlite3
import threading
import time
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from jsonschema import ValidationError, validate

import dspx.services.semantic_evaluation_execution_custody as custody_module

from dspx.services.semantic_evaluation_execution_custody import (
    AllocationMaterial,
    AttemptRequest,
    CustodyError,
    ExecutionCustodyStore,
    SnapshotView,
    canonical_json_bytes,
)


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sources(root: Path) -> tuple[AttemptRequest, AllocationMaterial, bytes]:
    root.mkdir(parents=True, exist_ok=True)
    candidate = root / "candidate"
    candidate.mkdir()
    manifest = candidate / "manifest.json"
    receipt = candidate / "manifest.json.meta.json"
    inputs = root / "inputs.json"
    manifest_bytes = canonical_json_bytes({"candidate": "synthetic"})
    receipt_bytes = canonical_json_bytes({"receipt": "synthetic"})
    input_bytes = canonical_json_bytes({"prompt": "synthetic-only"})
    manifest.write_bytes(manifest_bytes)
    receipt.write_bytes(receipt_bytes)
    inputs.write_bytes(input_bytes)
    request = AttemptRequest(
        episode_id="synthetic-episode-1",
        attempt_kind="original",
        source_receipt_digest=None,
        source_manifest_digest=_sha(manifest_bytes),
        candidate_receipt_digest=_sha(receipt_bytes),
        normalized_input_digest=_sha(input_bytes),
        evaluation_request_digest=_sha(b"synthetic-request"),
        configured_runtime_digest=_sha(b"synthetic-runtime"),
        configured_provider=None,
        configured_model=None,
    )
    return request, AllocationMaterial(manifest, receipt, inputs), input_bytes


def _store(root: Path, *, barrier=None) -> ExecutionCustodyStore:
    parent = root / "store-parent"
    parent.mkdir(mode=0o700)
    return ExecutionCustodyStore.create(parent, fault_barrier=barrier)


def _tamper_with_trigger_restored(
    store: ExecutionCustodyStore,
    trigger_name: str,
    statement: str,
    parameters: tuple[object, ...],
) -> None:
    trigger = store._connection.execute(
        "SELECT sql FROM sqlite_schema WHERE type='trigger' AND name=?", (trigger_name,)
    ).fetchone()
    assert trigger is not None
    trigger_sql = trigger["sql"]
    store._connection.execute(f'DROP TRIGGER "{trigger_name}"')
    store._connection.execute(statement, parameters)
    store._connection.execute(trigger_sql)


def _material_from_strings(
    manifest: str, receipt: str, inputs: str
) -> AllocationMaterial:
    return AllocationMaterial(Path(manifest), Path(receipt), Path(inputs))


def _crash_during_callable(
    root: str, attempt_id: str, manifest: str, receipt: str, inputs: str
) -> None:
    def crash(_snapshot: SnapshotView) -> object:
        os._exit(23)

    with ExecutionCustodyStore.open(Path(root)) as store:
        store.run_attempt(
            "crash-run",
            attempt_id,
            _material_from_strings(manifest, receipt, inputs),
            crash,
        )


def _crash_allocation_before_commit(
    root: str,
    request: AttemptRequest,
    manifest: str,
    receipt: str,
    inputs: str,
) -> None:
    def barrier(operation: str, phase: str) -> None:
        if operation == "allocate_episode" and phase == "before_commit":
            os._exit(29)

    with ExecutionCustodyStore.open(Path(root), fault_barrier=barrier) as store:
        store._connection.execute("PRAGMA cache_size=1")
        store.allocate_attempt(
            "crash-allocation",
            request,
            _material_from_strings(manifest, receipt, inputs),
        )


def _concurrent_process_run(
    root: str,
    attempt_id: str,
    operation_id: str,
    manifest: str,
    receipt: str,
    inputs: str,
    marker: str,
    start_event: Any,
) -> None:
    start_event.wait()

    def invoke(_snapshot: SnapshotView) -> dict[str, bool]:
        descriptor = os.open(marker, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
        try:
            os.write(descriptor, b"entered\n")
        finally:
            os.close(descriptor)
        time.sleep(0.2)
        return {"ok": True}

    with ExecutionCustodyStore.open(Path(root)) as store:
        store.run_attempt(
            operation_id,
            attempt_id,
            _material_from_strings(manifest, receipt, inputs),
            invoke,
        )


def test_return_path_seals_exact_projection_after_mediated_snapshot(
    tmp_path: Path,
) -> None:
    request, material, input_bytes = _sources(tmp_path)
    with _store(tmp_path) as store:
        allocated = store.allocate_attempt("allocate-1", request, material)
        observed: list[SnapshotView] = []

        def invoke(snapshot: SnapshotView) -> dict[str, str]:
            observed.append(snapshot)
            assert snapshot.bytes == input_bytes
            assert snapshot.sha256 == request.normalized_input_digest
            return {"answer": "synthetic"}

        closed = store.run_attempt("run-1", allocated.attempt_id, material, invoke)
        assert closed.state == "closed"
        assert closed.terminal_reason == "observed_return"
        assert closed.invoked is True
        assert len(observed) == 1

        projection_bytes = store.read_projection(allocated.attempt_id)
        assert not projection_bytes.endswith(b"\n")
        projection = json.loads(projection_bytes)
        schema = json.loads(
            Path(
                "docs/project/semantic-evaluation-execution-custody-v1-projection.schema.json"
            ).read_text(encoding="utf-8")
        )
        validate(projection, schema)
        schema_path = Path(
            "docs/project/semantic-evaluation-execution-custody-v1-projection.schema.json"
        )
        assert _sha(schema_path.read_bytes()) == (
            "d42569781d23c625627d92a9f37ea9c26211c92c403b0dcdb45b0360c386c532"
        )
        trailing_newline_variants: list[dict[str, Any]] = []
        for field in ("episode_id", "attempt_id", "evaluation_request_digest"):
            variant = json.loads(json.dumps(projection))
            variant[field] += "\n"
            trailing_newline_variants.append(variant)
        configured_variant = json.loads(json.dumps(projection))
        configured_variant["runtime_observation"]["configured_provider"] = "provider\n"
        trailing_newline_variants.append(configured_variant)
        for variant in trailing_newline_variants:
            with pytest.raises(ValidationError):
                validate(variant, schema)
            with pytest.raises(CustodyError):
                custody_module._validate_projection(variant)
        assert set(projection) == {
            "schema_version",
            "episode_id",
            "attempt_id",
            "attempt_kind",
            "source_receipt_digest",
            "candidate_coordinate",
            "input_coordinate",
            "evaluation_request_digest",
            "effect_inventory_version",
            "runtime_observation",
            "outcome_evidence",
            "episode_evidence_manifest_digest",
            "receipt_digest",
            "state_trace_digest",
            "non_authority",
        }
        assert projection["runtime_observation"]["outcome_kind"] == "return"
        assert projection["outcome_evidence"]["observation_kind"] == "return"
        assert projection["runtime_observation"]["executed_provider_identity"] is None
        assert projection["runtime_observation"]["executed_model_identity"] is None
        assert all(value is False for value in projection["non_authority"].values())
        invalid_non_authority = dict(projection)
        invalid_non_authority["non_authority"] = list(
            projection["non_authority"].items()
        )
        with pytest.raises(CustodyError, match="non-authority"):
            custody_module._validate_projection(invalid_non_authority)
        for numeric_false in (0, 0.0):
            invalid_numeric_non_authority = dict(projection)
            invalid_numeric_non_authority["non_authority"] = dict(
                projection["non_authority"]
            )
            invalid_numeric_non_authority["non_authority"]["governance"] = numeric_false
            with pytest.raises(CustodyError, match="non-authority"):
                custody_module._validate_projection(invalid_numeric_non_authority)
        assert input_bytes not in projection_bytes

        terminal = store.read_terminal(allocated.attempt_id)
        assert terminal["projection_digest"] == _sha(projection_bytes)
        assert terminal["terminal_marker"] == {
            "state": "closed",
            "terminal_reason": "observed_return",
        }
        assert (
            _sha(canonical_json_bytes(terminal["state_trace"]))
            == projection["state_trace_digest"]
        )
        assert (
            _sha(canonical_json_bytes(terminal["evidence_manifest"]))
            == projection["episode_evidence_manifest_digest"]
        )
        assert (
            _sha(canonical_json_bytes(terminal["receipt"]))
            == projection["receipt_digest"]
        )
        sealed_row = store._connection.execute(
            "SELECT seal, seal_digest FROM terminal_seals WHERE attempt_id=?",
            (allocated.attempt_id,),
        ).fetchone()
        assert _sha(bytes(sealed_row["seal"])) == sealed_row["seal_digest"]


def test_failure_path_is_digest_only_and_eligible(tmp_path: Path) -> None:
    request, material, _ = _sources(tmp_path)
    with _store(tmp_path) as store:
        attempt = store.allocate_attempt("allocate", request, material)

        def fail(_snapshot: SnapshotView) -> object:
            raise RuntimeError("synthetic failure")

        result = store.run_attempt("run", attempt.attempt_id, material, fail)
        projection = json.loads(store.read_projection(attempt.attempt_id))
        assert result.terminal_reason == "observed_failure"
        assert projection["outcome_evidence"]["observation_kind"] == "failure"
        assert projection["outcome_evidence"]["normalized_return_digest"] is None
        assert len(projection["outcome_evidence"]["sanitized_failure_digest"]) == 64
        assert b"synthetic failure" not in store.read_projection(attempt.attempt_id)


def test_replay_requires_distinct_attempt_and_source_receipt(tmp_path: Path) -> None:
    request, material, _ = _sources(tmp_path)
    with _store(tmp_path) as store:
        original = store.allocate_attempt("original", request, material)
        store.run_attempt("run-original", original.attempt_id, material, lambda _s: {})
        source_receipt = _sha(
            canonical_json_bytes(store.read_terminal(original.attempt_id)["receipt"])
        )
        replay = replace(
            request,
            episode_id="synthetic-replay-1",
            attempt_kind="replay",
            source_receipt_digest=source_receipt,
        )
        replayed = store.allocate_attempt("replay", replay, material)
        assert original.attempt_id != replayed.attempt_id
        store.run_attempt("run-replay", replayed.attempt_id, material, lambda _s: {})
        projection = json.loads(store.read_projection(replayed.attempt_id))
        assert projection["attempt_kind"] == "replay"
        assert projection["source_receipt_digest"] == source_receipt


def test_original_rejects_source_receipt_and_rejection_allocates_no_attempt(
    tmp_path: Path,
) -> None:
    request, material, _ = _sources(tmp_path)
    invalid = replace(request, source_receipt_digest=_sha(b"x"))
    with _store(tmp_path) as store:
        with pytest.raises(CustodyError, match="null source receipt"):
            store.allocate_attempt("invalid", invalid, material)
        rejection = store.reject_request("reject", invalid, material)
        assert rejection.state == "rejected"
        assert store.list_incomplete() == ()
        count = store._connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
        assert count == 0
        with pytest.raises(CustodyError, match="requires a DSPx-observed"):
            store.reject_request("reject-valid", request, material)
        invalid_number = replace(request, episode_id=1)
        invalid_list = replace(request, episode_id=[])
        first_rejection = store.reject_request("typed-rejection", invalid_number)
        assert (
            store.reject_request("typed-rejection", invalid_number) == first_rejection
        )
        with pytest.raises(CustodyError, match="operation ID reuse differs"):
            store.reject_request("typed-rejection", invalid_list)
        rejection_row = store._connection.execute(
            "SELECT terminal_json, terminal_digest FROM terminal_nonseals WHERE terminal_id=? AND attempt_id IS NULL",
            (first_rejection.rejection_id,),
        ).fetchone()
        assert rejection_row is not None
        assert (
            _sha(rejection_row["terminal_json"].encode())
            == rejection_row["terminal_digest"]
        )
        missing_one = replace(
            material, candidate_manifest_path=tmp_path / "missing-one.json"
        )
        missing_two = replace(
            material, candidate_manifest_path=tmp_path / "missing-two.json"
        )
        material_rejection = store.reject_request(
            "material-rejection", request, missing_one
        )
        assert (
            store.reject_request("material-rejection", request, missing_one)
            == material_rejection
        )
        with pytest.raises(CustodyError, match="operation ID reuse differs"):
            store.reject_request("material-rejection", request, missing_two)


def test_allocation_is_idempotent_and_snapshot_is_immutable(tmp_path: Path) -> None:
    request, material, input_bytes = _sources(tmp_path)
    with _store(tmp_path) as store:
        first = store.allocate_attempt("allocate", request, material)
        second = store.allocate_attempt("allocate", request, material)
        assert second == first
        row = store._connection.execute(
            "SELECT snapshot, snapshot_digest FROM input_snapshots WHERE attempt_id=?",
            (first.attempt_id,),
        ).fetchone()
        assert bytes(row["snapshot"]) == input_bytes
        assert row["snapshot_digest"] == _sha(input_bytes)
        with pytest.raises(sqlite3.IntegrityError, match="immutable input snapshot"):
            store._connection.execute(
                "UPDATE input_snapshots SET snapshot=? WHERE attempt_id=?",
                (b"different", first.attempt_id),
            )
        with pytest.raises(CustodyError, match="operation ID reuse differs"):
            changed = replace(request, episode_id="different-episode")
            store.allocate_attempt("allocate", changed, material)


def test_coordinate_and_path_guards_fail_before_allocation(tmp_path: Path) -> None:
    request, material, _ = _sources(tmp_path)
    with _store(tmp_path) as store:
        material.candidate_manifest_path.write_bytes(
            canonical_json_bytes({"changed": True})
        )
        with pytest.raises(CustodyError, match="manifest coordinate mismatch"):
            store.allocate_attempt("bad-hash", request, material)
        assert store.list_incomplete() == ()

    request2, material2, _ = _sources(tmp_path / "second")
    unsafe_parent = material2.candidate_manifest_path.parent
    os.chmod(unsafe_parent, 0o700)
    with ExecutionCustodyStore.create(unsafe_parent) as unsafe_store:
        with pytest.raises(CustodyError, match="disjoint from candidate root"):
            unsafe_store.allocate_attempt("unsafe-path", request2, material2)
    assert request2.episode_id == "synthetic-episode-1"


def test_schema_ascii_and_store_ancestor_guards(tmp_path: Path) -> None:
    request, material, _ = _sources(tmp_path)
    with _store(tmp_path) as store:
        with pytest.raises(CustodyError, match="episode_id is invalid"):
            store.allocate_attempt(
                "unicode-episode", replace(request, episode_id="épisode"), material
            )
        with pytest.raises(CustodyError, match="configured_provider is invalid"):
            store.allocate_attempt(
                "unicode-provider",
                replace(request, configured_provider="prøvider"),
                material,
            )
    owner_parent = tmp_path / "owner-parent"
    owner_parent.mkdir(mode=0o700)
    symlink_parent = tmp_path / "symlink-parent"
    symlink_parent.symlink_to(owner_parent, target_is_directory=True)
    with pytest.raises(CustodyError, match="contains a symlink"):
        ExecutionCustodyStore.create(symlink_parent)
    writable_parent = tmp_path / "writable-parent"
    writable_parent.mkdir(mode=0o720)
    os.chmod(writable_parent, 0o720)
    with pytest.raises(CustodyError, match="group/world writable"):
        ExecutionCustodyStore.create(writable_parent)


def test_source_drift_before_start_prevents_callable(tmp_path: Path) -> None:
    request, material, _ = _sources(tmp_path)
    with _store(tmp_path) as store:
        attempt = store.allocate_attempt("allocate", request, material)
        material.input_source_path.write_bytes(
            canonical_json_bytes({"prompt": "drift"})
        )
        calls = 0

        def invoke(_snapshot: SnapshotView) -> object:
            nonlocal calls
            calls += 1
            return {}

        with pytest.raises(CustodyError, match="content binding changed"):
            store.run_attempt("run", attempt.attempt_id, material, invoke)
        assert calls == 0
        recovered = store.recover_unstarted_allocation("recover", attempt.attempt_id)
        assert recovered.terminal_reason == "recovered_unstarted"


def test_start_commit_precedes_callable_and_ambiguous_start_is_not_retried(
    tmp_path: Path,
) -> None:
    request, material, _ = _sources(tmp_path)
    raised = False

    def barrier(operation: str, phase: str) -> None:
        nonlocal raised
        if operation == "start_attempt" and phase == "before_callable" and not raised:
            raised = True
            raise RuntimeError("synthetic crash boundary")

    with _store(tmp_path, barrier=barrier) as store:
        attempt = store.allocate_attempt("allocate", request, material)
        calls = 0

        def invoke(_snapshot: SnapshotView) -> object:
            nonlocal calls
            calls += 1
            return {}

        with pytest.raises(RuntimeError, match="crash boundary"):
            store.run_attempt("run", attempt.attempt_id, material, invoke)
        assert calls == 0
        assert store.list_incomplete() == (attempt.attempt_id,)
        second = store.run_attempt("run", attempt.attempt_id, material, invoke)
        assert second.state == "attempting"
        assert second.invoked is False
        assert calls == 0
        terminal = store.recover_unknown_attempt("recover", attempt.attempt_id)
        assert terminal.state == "indeterminate"
        with pytest.raises(CustodyError, match="ineligible"):
            store.read_projection(attempt.attempt_id)


def test_subprocess_crash_after_start_recovers_indeterminate(tmp_path: Path) -> None:
    request, material, _ = _sources(tmp_path)
    store = _store(tmp_path)
    attempt = store.allocate_attempt("allocate", request, material)
    root = store.root
    store.close()
    process = mp.Process(
        target=_crash_during_callable,
        args=(
            str(root),
            attempt.attempt_id,
            str(material.candidate_manifest_path),
            str(material.candidate_receipt_path),
            str(material.input_source_path),
        ),
    )
    process.start()
    process.join(10)
    assert process.exitcode == 23
    with ExecutionCustodyStore.open(root) as reopened:
        assert reopened.list_incomplete() == (attempt.attempt_id,)
        terminal = reopened.recover_unknown_attempt("recover", attempt.attempt_id)
        assert terminal.state == "indeterminate"


def test_hot_rollback_journal_is_validated_read_only_then_recovered(
    tmp_path: Path,
) -> None:
    request, material, _ = _sources(tmp_path)
    large_input = canonical_json_bytes({"payload": "x" * (2 * 1024 * 1024)})
    material.input_source_path.write_bytes(large_input)
    request = replace(request, normalized_input_digest=_sha(large_input))
    store = _store(tmp_path)
    root = store.root
    store.close()
    process = mp.Process(
        target=_crash_allocation_before_commit,
        args=(
            str(root),
            request,
            str(material.candidate_manifest_path),
            str(material.candidate_receipt_path),
            str(material.input_source_path),
        ),
    )
    process.start()
    process.join(10)
    assert process.exitcode == 29
    journal = root / "custody.sqlite3-journal"
    assert journal.exists()
    assert journal.read_bytes()[:8] == b"\xd9\xd5\x05\xf9\x20\xa1\x63\xd7"
    with ExecutionCustodyStore.open(root) as recovered:
        assert recovered.list_incomplete() == ()
    assert not journal.exists()


def test_before_commit_fault_rolls_back_allocation(tmp_path: Path) -> None:
    request, material, _ = _sources(tmp_path)

    def barrier(operation: str, phase: str) -> None:
        if operation == "allocate_episode" and phase == "before_commit":
            raise RuntimeError("rollback")

    with _store(tmp_path, barrier=barrier) as store:
        with pytest.raises(RuntimeError, match="rollback"):
            store.allocate_attempt("allocate", request, material)
        assert (
            store._connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
            == 0
        )
        assert (
            store._connection.execute(
                "SELECT COUNT(*) FROM input_snapshots"
            ).fetchone()[0]
            == 0
        )


def test_failed_seal_transaction_exposes_no_partial_terminal(tmp_path: Path) -> None:
    request, material, _ = _sources(tmp_path)
    fail_once = True

    def barrier(operation: str, phase: str) -> None:
        nonlocal fail_once
        if operation == "seal_and_close" and phase == "before_commit" and fail_once:
            fail_once = False
            raise RuntimeError("seal rollback")

    with _store(tmp_path, barrier=barrier) as store:
        attempt = store.allocate_attempt("allocate", request, material)
        with pytest.raises(RuntimeError, match="seal rollback"):
            store.run_attempt("run", attempt.attempt_id, material, lambda _s: {})
        row = store._connection.execute(
            "SELECT state FROM attempts WHERE attempt_id=?", (attempt.attempt_id,)
        ).fetchone()
        assert row["state"] == "outcome_observed"
        assert (
            store._connection.execute(
                "SELECT COUNT(*) FROM terminal_seals WHERE attempt_id=?",
                (attempt.attempt_id,),
            ).fetchone()[0]
            == 0
        )
        with pytest.raises(CustodyError, match="valid seal remains constructible"):
            store.recover_unsealed_outcome("invalid-recovery", attempt.attempt_id)
        with pytest.raises(sqlite3.IntegrityError, match="immutable observed outcome"):
            store._connection.execute(
                "UPDATE attempts SET outcome_digest=? WHERE attempt_id=?",
                ("f" * 64, attempt.attempt_id),
            )
        closed = store.seal_and_close("recovery-seal", attempt.attempt_id)
        assert closed.terminal_reason == "observed_return"


def test_callable_cannot_recover_its_own_active_attempt(tmp_path: Path) -> None:
    request, material, _ = _sources(tmp_path)
    with _store(tmp_path) as store:
        attempt = store.allocate_attempt("allocate", request, material)
        nested_attempt = store.allocate_attempt("allocate-nested", request, material)

        def invoke(_snapshot: SnapshotView) -> dict[str, bool]:
            with pytest.raises(CustodyError, match="active callable"):
                store.recover_unknown_attempt("self-recovery", attempt.attempt_id)
            with pytest.raises(CustodyError, match="active callable"):
                store.allocate_attempt("nested-allocation", request, material)
            with pytest.raises(CustodyError, match="active callable"):
                store.run_attempt(
                    "nested-run",
                    nested_attempt.attempt_id,
                    material,
                    lambda _nested_snapshot: {},
                )
            with pytest.raises(CustodyError, match="execution is active"):
                store.close()
            return {"ok": True}

        result = store.run_attempt("run", attempt.attempt_id, material, invoke)
        assert result.terminal_reason == "observed_return"


def test_concurrent_run_has_exactly_one_callable_entry(tmp_path: Path) -> None:
    request, material, _ = _sources(tmp_path)
    store = _store(tmp_path)
    attempt = store.allocate_attempt("allocate", request, material)
    root = store.root
    entered = threading.Event()
    release = threading.Event()
    calls: list[str] = []
    results: list[object] = []

    def invoke(_snapshot: SnapshotView) -> dict[str, bool]:
        calls.append("entered")
        entered.set()
        assert release.wait(5)
        return {"ok": True}

    def first() -> None:
        with ExecutionCustodyStore.open(root) as first_store:
            results.append(
                first_store.run_attempt("run-a", attempt.attempt_id, material, invoke)
            )

    thread = threading.Thread(target=first)
    thread.start()
    assert entered.wait(5)
    with pytest.raises(CustodyError, match="execution is still active"):
        store.recover_unknown_attempt("premature-recovery", attempt.attempt_id)
    loser = store.run_attempt("run-b", attempt.attempt_id, material, invoke)
    assert loser.invoked is False
    assert loser.state == "attempting"
    release.set()
    thread.join(5)
    assert not thread.is_alive()
    assert calls == ["entered"]
    assert len(results) == 1
    store.close()


def test_process_concurrency_enters_callable_once(tmp_path: Path) -> None:
    request, material, _ = _sources(tmp_path)
    store = _store(tmp_path)
    attempt = store.allocate_attempt("allocate", request, material)
    root = store.root
    store.close()
    marker = tmp_path / "callable-entries.log"
    context = mp.get_context("fork")
    start_event = context.Event()
    args = (
        str(root),
        attempt.attempt_id,
        str(material.candidate_manifest_path),
        str(material.candidate_receipt_path),
        str(material.input_source_path),
        str(marker),
        start_event,
    )
    first = context.Process(
        target=_concurrent_process_run, args=(args[0], args[1], "process-a", *args[2:])
    )
    second = context.Process(
        target=_concurrent_process_run, args=(args[0], args[1], "process-b", *args[2:])
    )
    first.start()
    second.start()
    start_event.set()
    first.join(10)
    second.join(10)
    assert first.exitcode == 0
    assert second.exitcode == 0
    assert marker.read_text(encoding="utf-8").splitlines() == ["entered"]


def test_terminal_cannot_reopen_or_accept_new_event(tmp_path: Path) -> None:
    request, material, _ = _sources(tmp_path)
    with _store(tmp_path) as store:
        attempt = store.allocate_attempt("allocate", request, material)
        store.run_attempt("run", attempt.attempt_id, material, lambda _s: {})
        with pytest.raises(CustodyError, match="requires state attempting"):
            store.recover_unknown_attempt("recover", attempt.attempt_id)
        with pytest.raises(sqlite3.IntegrityError, match="no outgoing transition"):
            store._connection.execute(
                "INSERT INTO events(attempt_id, sequence, operation, from_state, to_state, operation_digest, event_digest, event_json) VALUES(?,?,?,?,?,?,?,?)",
                (
                    attempt.attempt_id,
                    99,
                    "retry",
                    "closed",
                    "attempting",
                    "a" * 64,
                    "b" * 64,
                    "{}",
                ),
            )


def test_projection_bytes_stable_after_reopen(tmp_path: Path) -> None:
    request, material, _ = _sources(tmp_path)
    store = _store(tmp_path)
    attempt = store.allocate_attempt("allocate", request, material)
    store.run_attempt(
        "run", attempt.attempt_id, material, lambda snapshot: {"n": len(snapshot.bytes)}
    )
    before = store.read_projection(attempt.attempt_id)
    root = store.root
    store.close()
    with ExecutionCustodyStore.open(root) as reopened:
        after = reopened.read_projection(attempt.attempt_id)
        assert after == before
        assert _sha(after) == _sha(before)
        integrity = reopened._connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = reopened._connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()
        assert integrity == "ok"
        assert foreign_keys == []


def test_uuid4_attempt_identity(tmp_path: Path) -> None:
    request, material, _ = _sources(tmp_path)
    with _store(tmp_path) as store:
        attempt = store.allocate_attempt("allocate", request, material)
        parsed = UUID(attempt.attempt_id)
        assert parsed.version == 4
        with pytest.raises(CustodyError, match="attempt ID"):
            store.allocate_attempt(
                "bad-uuid",
                request,
                material,
                attempt_id_factory=lambda: "00000000-0000-1000-8000-000000000000",
            )


def test_partial_or_foreign_key_invalid_schema_fails_closed(tmp_path: Path) -> None:
    partial_parent = tmp_path / "partial-parent"
    partial_parent.mkdir(mode=0o700)
    partial_root = partial_parent / "semantic-evaluation-custody-v1"
    partial_root.mkdir(mode=0o700)
    partial_db = partial_root / "custody.sqlite3"
    connection = sqlite3.connect(partial_db)
    connection.executescript(
        "CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);"
        f"INSERT INTO meta VALUES('schema_version', '{custody_module.SCHEMA_VERSION}');"
    )
    connection.close()
    os.chmod(partial_db, 0o600)
    unexpected_wal = partial_root / "custody.sqlite3-wal"
    unexpected_wal.write_bytes(b"must-not-be-recovered-or-removed")
    with pytest.raises(CustodyError, match="unexpected SQLite sidecar"):
        ExecutionCustodyStore.open(partial_root)
    assert unexpected_wal.read_bytes() == b"must-not-be-recovered-or-removed"
    unexpected_wal.unlink()
    with pytest.raises(CustodyError, match="schema objects differ"):
        ExecutionCustodyStore.open(partial_root)

    request, material, _ = _sources(tmp_path / "foreign-key")
    store = _store(tmp_path / "foreign-key")
    attempt = store.allocate_attempt("allocate", request, material)
    root = store.root
    store.close()
    raw = sqlite3.connect(root / "custody.sqlite3")
    raw.execute("PRAGMA foreign_keys=OFF")
    event = {
        "sequence": 0,
        "operation": "allocate_episode",
        "from_state": "requested",
        "to_state": "allocated",
        "operation_digest": "a" * 64,
    }
    event["event_digest"] = _sha(canonical_json_bytes(event))
    raw.execute(
        "INSERT INTO events VALUES(?,?,?,?,?,?,?,?)",
        (
            "00000000-0000-4000-8000-000000000000",
            0,
            "allocate_episode",
            "requested",
            "allocated",
            "a" * 64,
            event["event_digest"],
            canonical_json_bytes(event).decode(),
        ),
    )
    raw.commit()
    raw.close()
    with pytest.raises(CustodyError, match="foreign-key check failed"):
        ExecutionCustodyStore.open(root)
    assert attempt.state == "allocated"


def test_operation_and_terminal_digests_are_reverified(tmp_path: Path) -> None:
    request, material, _ = _sources(tmp_path)
    with _store(tmp_path) as store:
        store.allocate_attempt("allocate", request, material)
        _tamper_with_trigger_restored(
            store,
            "immutable_operations_update",
            "UPDATE operations SET result_digest=? WHERE operation_id='allocate'",
            ("0" * 64,),
        )
        with pytest.raises(CustodyError, match="operation result binding"):
            store.allocate_attempt("allocate", request, material)

    request2, material2, _ = _sources(tmp_path / "sealed")
    with _store(tmp_path / "sealed") as store:
        attempt2 = store.allocate_attempt("allocate", request2, material2)
        store.run_attempt("run", attempt2.attempt_id, material2, lambda _snapshot: {})
        _tamper_with_trigger_restored(
            store,
            "immutable_seals_update",
            "UPDATE terminal_seals SET seal_digest=? WHERE attempt_id=?",
            ("0" * 64, attempt2.attempt_id),
        )
        with pytest.raises(CustodyError, match="seal or projection digest mismatch"):
            store.read_terminal(attempt2.attempt_id)
        with pytest.raises(CustodyError, match="seal or projection digest mismatch"):
            store.seal_and_close("run:seal_and_close", attempt2.attempt_id)

    request3, material3, _ = _sources(tmp_path / "path-binding")
    with _store(tmp_path / "path-binding") as store:
        attempt3 = store.allocate_attempt("allocate", request3, material3)
        store.run_attempt("run", attempt3.attempt_id, material3, lambda _snapshot: {})
        changed_paths = canonical_json_bytes(
            {
                "candidate_manifest_path_digest": "0" * 64,
                "candidate_receipt_path_digest": "1" * 64,
                "input_source_path_digest": "2" * 64,
            }
        ).decode()
        trigger_rows = store._connection.execute(
            "SELECT name, sql FROM sqlite_schema WHERE type='trigger' AND name IN ('immutable_attempt_bindings','terminal_attempt_immutable') ORDER BY name"
        ).fetchall()
        assert len(trigger_rows) == 2
        for trigger_row in trigger_rows:
            store._connection.execute(f'DROP TRIGGER "{trigger_row["name"]}"')
        store._connection.execute(
            "UPDATE attempts SET path_digests_json=? WHERE attempt_id=?",
            (changed_paths, attempt3.attempt_id),
        )
        for trigger_row in trigger_rows:
            store._connection.execute(trigger_row["sql"])
        with pytest.raises(CustodyError, match="allocation request and source-path"):
            store.read_terminal(attempt3.attempt_id)


def test_observation_infrastructure_failure_is_not_callable_failure(
    tmp_path: Path,
) -> None:
    request, material, _ = _sources(tmp_path)
    with _store(tmp_path) as store:
        attempt = store.allocate_attempt("allocate", request, material)
        with pytest.raises(CustodyError, match="canonical JSON"):
            store.run_attempt(
                "run", attempt.attempt_id, material, lambda _snapshot: {"not-json"}
            )
        row = store._connection.execute(
            "SELECT state, outcome_kind, outcome_digest FROM attempts WHERE attempt_id=?",
            (attempt.attempt_id,),
        ).fetchone()
        assert tuple(row) == ("attempting", None, None)
        operations = [
            value[0]
            for value in store._connection.execute(
                "SELECT operation FROM events WHERE attempt_id=? ORDER BY sequence",
                (attempt.attempt_id,),
            ).fetchall()
        ]
        assert operations == ["allocate_episode", "start_attempt"]
        terminal = store.recover_unknown_attempt("recover", attempt.attempt_id)
        assert terminal.state == "indeterminate"


def test_observation_commit_failure_remains_unknown_and_recovery_is_idempotent(
    tmp_path: Path,
) -> None:
    failed = False

    def barrier(operation: str, phase: str) -> None:
        nonlocal failed
        if operation == "observe_return" and phase == "before_commit" and not failed:
            failed = True
            raise RuntimeError("observation persistence failed")

    request, material, _ = _sources(tmp_path)
    with _store(tmp_path, barrier=barrier) as store:
        attempt = store.allocate_attempt("allocate", request, material)
        with pytest.raises(RuntimeError, match="observation persistence"):
            store.run_attempt("run", attempt.attempt_id, material, lambda _snapshot: {})
        row = store._connection.execute(
            "SELECT state, outcome_kind FROM attempts WHERE attempt_id=?",
            (attempt.attempt_id,),
        ).fetchone()
        assert tuple(row) == ("attempting", None)
        first = store.recover_unknown_attempt("recover", attempt.attempt_id)
        second = store.recover_unknown_attempt("recover", attempt.attempt_id)
        assert second == first
        with pytest.raises(CustodyError, match="requires state attempting"):
            store.recover_unknown_attempt("different-recovery", attempt.attempt_id)


def test_unsealed_recovery_requires_unconstructible_evidence_and_replays(
    tmp_path: Path,
) -> None:
    fail_seal = True

    def barrier(operation: str, phase: str) -> None:
        nonlocal fail_seal
        if operation == "seal_and_close" and phase == "before_commit" and fail_seal:
            fail_seal = False
            raise RuntimeError("stop before seal")

    request, material, _ = _sources(tmp_path)
    with _store(tmp_path, barrier=barrier) as store:
        attempt = store.allocate_attempt("allocate", request, material)
        with pytest.raises(RuntimeError, match="stop before seal"):
            store.run_attempt("run", attempt.attempt_id, material, lambda _snapshot: {})
        with pytest.raises(CustodyError, match="valid seal remains constructible"):
            store.recover_unsealed_outcome("recover-valid", attempt.attempt_id)
        _tamper_with_trigger_restored(
            store,
            "immutable_operations_update",
            "UPDATE operations SET result_digest=? WHERE operation_kind='observe_return'",
            ("0" * 64,),
        )
        first = store.recover_unsealed_outcome("recover-invalid", attempt.attempt_id)
        second = store.recover_unsealed_outcome("recover-invalid", attempt.attempt_id)
        assert first == second
        assert first.state == "indeterminate"
        with pytest.raises(CustodyError, match="ineligible"):
            store.read_projection(attempt.attempt_id)
        future_attempt = store.allocate_attempt(
            "future-equal-allocation", request, material
        )
        assert future_attempt.attempt_id != attempt.attempt_id
        with pytest.raises(CustodyError, match="ineligible"):
            store.read_projection(attempt.attempt_id)
        original_start_digest = store._connection.execute(
            "SELECT event_digest FROM events WHERE attempt_id=? AND operation='start_attempt'",
            (attempt.attempt_id,),
        ).fetchone()[0]
        _tamper_with_trigger_restored(
            store,
            "immutable_events_update",
            "UPDATE events SET event_digest=? WHERE attempt_id=? AND operation='start_attempt'",
            ("1" * 64, attempt.attempt_id),
        )
        with pytest.raises(CustodyError, match="failure binding"):
            store.read_terminal(attempt.attempt_id)
        _tamper_with_trigger_restored(
            store,
            "immutable_events_update",
            "UPDATE events SET event_digest=? WHERE attempt_id=? AND operation='start_attempt'",
            (original_start_digest, attempt.attempt_id),
        )
        _tamper_with_trigger_restored(
            store,
            "immutable_events_update",
            "UPDATE events SET event_digest=? WHERE attempt_id=? AND operation='recover_unsealed_outcome'",
            ("0" * 64, attempt.attempt_id),
        )
        with pytest.raises(CustodyError, match="unsealed recovery terminal event"):
            store.read_terminal(attempt.attempt_id)


def test_create_detects_store_substitution_before_reopen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    replacement_parent = tmp_path / "replacement-parent"
    replacement_parent.mkdir(mode=0o700)
    replacement_store = ExecutionCustodyStore.create(replacement_parent)
    replacement_root = replacement_store.root
    replacement_store.close()

    target_parent = tmp_path / "target-parent"
    target_parent.mkdir(mode=0o700)
    original_init = ExecutionCustodyStore.__init__
    substituted = False

    def substituting_init(
        self: ExecutionCustodyStore, root: Path, *args: Any, **kwargs: Any
    ) -> None:
        nonlocal substituted
        if kwargs.get("_expected_binding") is not None and not substituted:
            substituted = True
            root.rename(root.with_name(f"{root.name}-displaced"))
            replacement_root.rename(root)
        original_init(self, root, *args, **kwargs)

    monkeypatch.setattr(ExecutionCustodyStore, "__init__", substituting_init)
    with pytest.raises(CustodyError, match="binding changed before reopen"):
        ExecutionCustodyStore.create(target_parent)
    assert substituted is True


def test_store_descriptor_binding_hardlink_sidecar_and_network_guards(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, material, _ = _sources(tmp_path / "binding")
    store = _store(tmp_path / "binding")
    attempt = store.allocate_attempt("allocate", request, material)
    original_parent = store.root.parent
    displaced_parent = original_parent.with_name("displaced-parent")
    original_parent.rename(displaced_parent)
    original_parent.mkdir(mode=0o700)
    with pytest.raises(CustodyError, match="parent descriptor/path binding changed"):
        store.recover_unstarted_allocation("recover", attempt.attempt_id)
    store.close()

    request2, material2, _ = _sources(tmp_path / "hardlink")
    store2 = _store(tmp_path / "hardlink")
    root2 = store2.root
    store2.close()
    os.link(root2 / "custody.sqlite3", root2.parent / "custody-hardlink.sqlite3")
    with pytest.raises(CustodyError, match="owner/link count"):
        ExecutionCustodyStore.open(root2)
    assert request2.source_manifest_digest == _sha(
        material2.candidate_manifest_path.read_bytes()
    )

    request3, material3, _ = _sources(tmp_path / "sidecar")
    store3 = _store(tmp_path / "sidecar")
    sidecar = store3.root / "custody.sqlite3-wal"
    sidecar.write_bytes(b"unexpected")
    with pytest.raises(CustodyError, match="unexpected SQLite sidecar"):
        store3.list_incomplete()
    sidecar.unlink()
    store3.close()
    assert request3.normalized_input_digest == _sha(
        material3.input_source_path.read_bytes()
    )

    descriptor_root_parent = tmp_path / "descriptor-connect"
    descriptor_root_parent.mkdir(mode=0o700)
    descriptor_store = ExecutionCustodyStore.create(descriptor_root_parent)
    descriptor_root = descriptor_store.root
    descriptor_store.close()
    connect_calls: list[str] = []
    real_connect = sqlite3.connect

    def tracked_connect(database, *args, **kwargs):
        connect_calls.append(str(database))
        return real_connect(database, *args, **kwargs)

    monkeypatch.setattr(custody_module.sqlite3, "connect", tracked_connect)
    with ExecutionCustodyStore.open(descriptor_root) as reopened:
        database = reopened._connection.execute("PRAGMA database_list").fetchone()[2]
        database_info = os.stat(database, follow_symlinks=False)
        descriptor_info = os.fstat(reopened._db_fd)
        assert (database_info.st_dev, database_info.st_ino) == (
            descriptor_info.st_dev,
            descriptor_info.st_ino,
        )
    assert "mode=ro" in connect_calls[0]
    assert "immutable=1" in connect_calls[0]
    assert "/fd/" in connect_calls[0]
    assert "/fd/" in connect_calls[1]
    monkeypatch.setattr(custody_module.sqlite3, "connect", real_connect)

    source_request, source_material, _ = _sources(tmp_path / "remote-source")
    source_store = _store(tmp_path / "remote-source")
    real_filesystem_type = custody_module._filesystem_type
    remote_source = source_material.candidate_manifest_path

    def source_filesystem_type(path: Path) -> str | None:
        if path == remote_source:
            return "nfs"
        return real_filesystem_type(path)

    monkeypatch.setattr(custody_module, "_filesystem_type", source_filesystem_type)
    with pytest.raises(CustodyError, match="network filesystems"):
        source_store.allocate_attempt("allocate", source_request, source_material)
    assert source_store.list_incomplete() == ()
    source_store.close()
    monkeypatch.setattr(custody_module, "_filesystem_type", real_filesystem_type)

    network_parent = tmp_path / "network-parent"
    network_parent.mkdir(mode=0o700)
    monkeypatch.setattr(custody_module, "_filesystem_type", lambda _path: "nfs")
    with pytest.raises(CustodyError, match="network filesystems"):
        ExecutionCustodyStore.create(network_parent)
    monkeypatch.setattr(custody_module, "_filesystem_type", lambda _path: None)
    with pytest.raises(CustodyError, match="cannot be verified"):
        ExecutionCustodyStore.create(network_parent)


def test_clean_close_rejects_leftover_journal_and_forbidden_effects_are_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    phases: list[tuple[str, str]] = []

    def barrier(operation: str, phase: str) -> None:
        phases.append((operation, phase))

    request, material, _ = _sources(tmp_path / "effects")
    with _store(tmp_path / "effects", barrier=barrier) as store:
        attempt = store.allocate_attempt("allocate", request, material)

        def deny_socket(*_args: object, **_kwargs: object) -> object:
            raise AssertionError("socket creation is forbidden")

        monkeypatch.setattr(socket, "socket", deny_socket)
        result = store.run_attempt(
            "run", attempt.attempt_id, material, lambda _snapshot: {"ok": True}
        )
        assert result.state == "closed"
        assert ("start_attempt", "during_callable") in phases

    source = Path(custody_module.__file__).read_text(encoding="utf-8")
    for forbidden_import in (
        "import socket",
        "import subprocess",
        "import httpx",
        "import requests",
        "import dspx.oracle",
        "import ak",
    ):
        assert forbidden_import not in source

    dirty_root = tmp_path / "dirty-close"
    dirty_root.mkdir()
    dirty_store = _store(dirty_root)
    journal = dirty_store.root / "custody.sqlite3-journal"
    journal.write_bytes(b"not-a-live-sqlite-journal")
    os.chmod(journal, 0o600)
    with pytest.raises(CustodyError, match="sidecar remains after clean close"):
        dirty_store.close()
