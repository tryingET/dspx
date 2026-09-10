"""Independent identity/custody and byte-integrity negative tests, synthetic only."""

from dataclasses import replace

import pytest

from dspx.services.program_reading_contracts import (
    CEILING,
    canonical_bytes,
    strict_json,
)
from dspx.services.program_reading_receipts import capture, exclusive_write
import test_program_reading_runtime as runtime_tests

reading_test_environment = runtime_tests.reading_test_environment
candidates = runtime_tests.candidates
run_factory = runtime_tests.run_factory
executed = runtime_tests.executed
consume = runtime_tests.consume


def test_receipt_ceiling_and_independent_expected_identities(executed):
    root = executed["result"]["root"]
    receipt = strict_json(capture(root, "reading_receipt.json"))
    assert receipt["schema_version"] == "dspx-program-reading-receipt-v1"
    assert all(receipt[k] == v for k, v in CEILING.items())
    assert receipt["expected"] == executed["expected"].payload()
    assert "reading_proposal_json" not in receipt["output_parsed_sha256"]
    assert (
        receipt["raw_file_sha256"]["review_packet_json"]
        != receipt["output_parsed_sha256"]["review_packet_json"]
    )
    assert receipt["native_index"] == 0
    assert consume(executed)
    for field in (
        "request_id",
        "source_ref",
        "source_sha256",
        "puzzle_snapshot_sha256",
        "candidate_manifest_sha256",
        "input_raw_sha256",
        "reading_intent_binding",
    ):
        expected = replace(
            executed["expected"],
            **{field: {} if field == "reading_intent_binding" else "wrong"},
        )
        with pytest.raises(ValueError):
            consume(executed, expected=expected)
    for kwargs in (
        {"expected_native_episode_id": "wrong"},
        {"expected_native_index": 1},
        {"expected_native_index": False},
        {"trusted_receipt_sha256": "wrong"},
    ):
        with pytest.raises(ValueError):
            consume(executed, **kwargs)


def test_tampered_outputs_receipt_readback_and_native_evidence(executed):
    root = executed["result"]["root"]
    for name in (
        "review_packet_json",
        "reading_receipt.json",
        "reading_readback.json",
        "runtime_episode.json",
        "runtime_episode.json.meta.json",
        "behavior_results.json",
    ):
        path = root / name
        raw = path.read_bytes()
        try:
            path.write_bytes(raw + b" ")
            with pytest.raises(ValueError):
                consume(executed)
        finally:
            path.write_bytes(raw)
    assert consume(executed)


def test_stale_consumer_never_rebinds(executed):
    receipt_before = capture(executed["result"]["root"], "reading_receipt.json")
    with pytest.raises(ValueError, match="stale"):
        consume(executed, current_intent=lambda: {**executed["intent"], "revision": 2})
    assert capture(executed["result"]["root"], "reading_receipt.json") == receipt_before


def test_consumer_checks_current_at_end(executed):
    calls = 0

    def current():
        nonlocal calls
        calls += 1
        return (
            executed["intent"] if calls == 1 else {**executed["intent"], "revision": 2}
        )

    with pytest.raises(ValueError, match="stale"):
        consume(executed, current_intent=current)
    assert calls == 2


def test_confined_references_regular_files_and_symlinks(tmp_path):
    safe = tmp_path / "safe"
    safe.mkdir()
    (safe / "data.json").write_bytes(b"{}")
    (tmp_path / "external.json").write_bytes(b"{}")
    (safe / "link.json").symlink_to(tmp_path / "external.json")
    (tmp_path / "linked-root").symlink_to(safe, target_is_directory=True)
    for reference in (
        "../external.json",
        "/external.json",
        "./data.json",
        "x/../data.json",
    ):
        with pytest.raises(ValueError):
            capture(safe, reference)
    with pytest.raises(OSError):
        capture(safe, "link.json")
    with pytest.raises(OSError):
        capture(tmp_path / "linked-root", "data.json")
    with pytest.raises(ValueError):
        capture(tmp_path, "safe")
    with pytest.raises(FileExistsError):
        exclusive_write(safe / "data.json", canonical_bytes({"overwritten": True}))
    assert (safe / "data.json").read_bytes() == b"{}"


def test_native_output_symlink_rejected(executed, tmp_path):
    root = executed["result"]["root"]
    path = root / "review_packet_json"
    original = path.read_bytes()
    outside = tmp_path / "external-output"
    outside.write_bytes(original)
    path.unlink()
    path.symlink_to(outside)
    with pytest.raises(OSError):
        consume(executed)
