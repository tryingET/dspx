# summary: "Immutable no-replace record publication and independent directory descriptions."
import os

import pytest

from dspx.image_admission import ImageContractError, canonical, sha
from dspx.image_records import list_root, publish, read_record


@pytest.fixture
def root(tmp_path):
    tmp_path.chmod(0o700)
    fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        yield fd
    finally:
        os.close(fd)


def test_directory_scans_do_not_share_offsets_across_dup_and_fork(root):
    publish(root, "ready.json", {"schema_version": "fixture"})
    # Deliberately exhaust the original directory description first.
    os.listdir(root)
    duplicate = os.dup(root)
    try:
        assert list_root(duplicate) == ["ready.json"]
        pid = os.fork()
        if pid == 0:
            os._exit(0 if list_root(duplicate) == ["ready.json"] else 1)
        child, status = os.waitpid(pid, 0)
        assert child == pid and os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0
        assert list_root(root) == ["ready.json"]
    finally:
        os.close(duplicate)


def test_no_replace_preserves_published_bytes_and_failure_residue(root):
    original = {"status": "known"}
    assert publish(root, "intent-1.json", original) == sha(canonical(original))
    with pytest.raises(ImageContractError, match="image_durability"):
        publish(root, "intent-1.json", {"status": "different"})
    assert read_record(root, "intent-1.json") == canonical(original)
    assert any(name.startswith(".pending-") for name in list_root(root))


def test_directory_fsync_failure_is_not_publication_success(root, monkeypatch):
    original = os.fsync

    def fail_directory(fd):
        if fd == root:
            raise OSError("private-canary-must-not-escape")
        original(fd)

    monkeypatch.setattr(os, "fsync", fail_directory)
    with pytest.raises(ImageContractError) as error:
        publish(root, "terminal-1.json", {"status": "fixture"})
    assert str(error.value) == "image_durability"
    assert error.value.__cause__ is None
    assert read_record(root, "terminal-1.json") == canonical({"status": "fixture"})


def test_read_denies_symlink_and_changed_file_mode(root, tmp_path):
    publish(root, "ready.json", {"status": "fixture"})
    os.symlink("ready.json", "alias.json", dir_fd=root)
    with pytest.raises(OSError):
        read_record(root, "alias.json")
    (tmp_path / "ready.json").chmod(0o644)
    with pytest.raises(ImageContractError, match="image_custody"):
        read_record(root, "ready.json")


@pytest.mark.parametrize(
    "mutation",
    ["original", "count", "result", "typed", "response", "bytes", "model", "time"],
)
def test_scan_rejects_contradictory_success_cross_fields(root, mutation):
    """Real scanner + immutable records; not a generated-run or transport claim."""
    import time
    import uuid
    from types import SimpleNamespace
    from dspx.image_admission import digest
    from dspx.image_records import scan

    now = time.time_ns() // 1_000_000
    binding = {
        "custody_id": str(uuid.uuid4()),
        "caller_run_id": str(uuid.uuid4()),
        "caller_binding_sha256": "1" * 64,
    }
    plan = {"request_shape_sha256": "2" * 64, "image_occurrence_sequence": ["s000001"]}
    admission_hash, manifest_hash = "3" * 64, "4" * 64
    request_hash = digest(
        "request-v1",
        {
            "admission_sha256": admission_hash,
            "input_manifest_sha256": manifest_hash,
            "plan_ordinal": 1,
            "request_shape_sha256": plan["request_shape_sha256"],
        },
    )
    ready = {"fixture": "scanner-only-bound-ready"}
    publish(root, "ready.json", ready)
    fd = os.open("lock", os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600, dir_fd=root)
    os.close(fd)
    intent = {
        "schema_version": "dspx-image-dispatch-intent-v1",
        **binding,
        "admission_sha256": admission_hash,
        "input_manifest_sha256": manifest_hash,
        "attempt_id": str(uuid.uuid4()),
        "attempt_ordinal": 1,
        "plan_ordinal": 1,
        "request_sha256": request_hash,
        "request_shape_sha256": plan["request_shape_sha256"],
        "image_occurrence_sequence": plan["image_occurrence_sequence"],
        "validated_image_count": 1,
        "validated_image_bytes": 1,
        "reserved_utc_ms": now,
        "deadline_utc_ms": now + 30_000,
    }
    intent_hash = publish(root, "intent-1.json", intent)
    terminal = {
        "schema_version": "dspx-image-dispatch-terminal-v1",
        "custody_id": binding["custody_id"],
        "caller_run_id": binding["caller_run_id"],
        "attempt_id": intent["attempt_id"],
        "attempt_ordinal": 1,
        "intent_sha256": intent_hash,
        "request_sha256": request_hash,
        "dispatch_count": 1,
        "provider_disposition": "completed_success",
        "observed_model": "fixture",
        "response_sha256": "5" * 64,
        "response_byte_count": 1,
        "finalization_kind": "dspy_lm",
        "result_finalization_completed": True,
        "typed_finalization_completed": True,
        "failure_code": None,
        "terminal_utc_ms": now,
    }
    changes = {
        "count": ("dispatch_count", 0),
        "result": ("result_finalization_completed", False),
        "typed": ("typed_finalization_completed", False),
        "response": ("response_sha256", None),
        "bytes": ("response_byte_count", -1),
        "model": ("observed_model", None),
        "time": ("terminal_utc_ms", now - 1),
    }
    if mutation != "original":
        key, value = changes[mutation]
        terminal[key] = value
    publish(root, "terminal-1.json", terminal)
    view = SimpleNamespace(
        root_fd=root,
        ready_raw=canonical(ready),
        record={
            "request_plan": [plan],
            "model": "fixture",
            "deadlines": {"expires_utc_ms": now + 30_000},
            "limits": {"max_response_bytes": 100},
        },
        binding=binding,
        admission=SimpleNamespace(sha256=admission_hash),
        manifest_sha256=manifest_hash,
        context=SimpleNamespace(
            source={
                "source_occurrences": [{"occurrence_id": "s000001", "byte_count": 1}]
            }
        ),
    )
    if mutation == "original":
        assert scan(view)[0][1] == terminal
    else:
        with pytest.raises(ImageContractError, match="image_custody"):
            scan(view)


def test_scan_tolerates_only_own_residue_and_only_for_reconciliation(root):
    """`.pending-<uuid4>` residue never passes a dispatching scan; nothing else passes."""
    import uuid
    from types import SimpleNamespace
    from dspx.image_records import residue, scan

    ready = {"fixture": "scanner-only-bound-ready"}
    publish(root, "ready.json", ready)
    os.close(os.open("lock", os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600, dir_fd=root))
    own = ".pending-" + str(uuid.uuid4())
    os.close(os.open(own, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600, dir_fd=root))
    view = SimpleNamespace(root_fd=root, ready_raw=canonical(ready))
    assert residue(own) and not residue(own.upper()) and not residue(".pending-x")
    with pytest.raises(ImageContractError, match="image_custody"):
        scan(view, allow_open=True, allow_closure=True)
    assert scan(view, allow_open=True, allow_residue=True) == []
    foreign = ".pending-" + str(uuid.uuid4()).upper()
    os.close(os.open(foreign, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600, dir_fd=root))
    with pytest.raises(ImageContractError, match="image_custody"):
        scan(view, allow_open=True, allow_residue=True)
