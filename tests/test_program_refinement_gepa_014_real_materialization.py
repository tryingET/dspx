# summary: "Proves one real credential-free GEPA 0.1.4 output-to-candidate runtime and replay journey."
# read_when:
#   - "Changing real GEPA output materialization, fresh-process behavior refresh, receipts, replay, or comparison."

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.services.program_intent import ProgramIntent
from dspx.services.program_refinement_workflow import (
    materialize_and_compare_gepa_refinement_candidate,
)
from dspx.services.program_runtime_episode import run_program_runtime_episode
from dspx.services.program_service import materialize_program_from_intent
from dspx.services.run_replay_service import check_run_receipt, execute_run_receipt
from dspx.run_receipts import load_run_receipt

runner = CliRunner()


def _tree_hash(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_real_gepa_014_output_materializes_runs_replays_and_compares(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "mock")
    monkeypatch.setenv("DSPX_REPLAY_FIXTURE_JSON", json.dumps({"urgency": "high"}))

    source_artifact = materialize_program_from_intent(
        ProgramIntent(
            name="RealGepaTicketProgram",
            objective="Classify support ticket urgency.",
            inputs=["ticket_text"],
            outputs=["urgency"],
            metric="exact_match",
            examples=[
                {
                    "inputs": {"ticket_text": "Server is down for all users"},
                    "outputs": {"urgency": "high"},
                }
            ],
        ),
        outdir=tmp_path / "source",
    )
    source_root = Path(source_artifact.root_path)
    source_manifest = source_root / "manifest.json"
    source_before = _tree_hash(source_root)
    monkeypatch.setattr(sys, "dont_write_bytecode", False)

    optimizer_root = tmp_path / "optimizer"
    gepa_result_path = tmp_path / "sidecars" / "gepa-result.json"
    optimize = runner.invoke(
        app,
        [
            "program-refine",
            "optimize-gepa",
            "--manifest",
            str(source_manifest),
            "--outdir",
            str(optimizer_root),
            "--result-out",
            str(gepa_result_path),
            "--max-metric-calls",
            "2",
            "--json",
        ],
    )

    assert optimize.exit_code == 0, optimize.output
    assert optimize.stderr.strip()
    optimize_payload = json.loads(optimize.stdout)
    assert optimize_payload == json.loads(gepa_result_path.read_text(encoding="utf-8"))
    assert optimize_payload["gepa"]["status"] == "completed"
    assert (
        optimize_payload["gepa_output"]["readiness"][
            "ready_for_future_candidate_materializer"
        ]
        is True
    )
    assert _tree_hash(source_root) == source_before
    assert not any(path.name == "__pycache__" for path in source_root.rglob("*"))

    optimizer_manifest = json.loads(
        (optimizer_root / "manifest.json").read_text(encoding="utf-8")
    )
    assert optimizer_manifest["dspy_version"] == "3.3.1"
    assert optimizer_manifest["gepa_version"] == "0.1.4"
    assert optimizer_manifest["providers"]["student"]["provider"] == "stub"
    assert optimizer_manifest["providers"]["reflection"]["provider"] == "stub"
    assert (optimizer_root / "program.pkl").is_file()
    assert not (optimizer_root / "compiled.bin").exists()
    optimizer_before = _tree_hash(optimizer_root)
    optimizer_manifest_sha256 = hashlib.sha256(
        (optimizer_root / "manifest.json").read_bytes()
    ).hexdigest()
    monkeypatch.setenv(
        "DSPX_ALLOW_UNSAFE_GEPA_PICKLE_SHA256", optimizer_manifest_sha256
    )

    candidate_root = tmp_path / "gepa-candidate"
    comparison_path = tmp_path / "sidecars" / "comparison.json"
    candidate_result_path = tmp_path / "sidecars" / "candidate-result.json"
    workflow = materialize_and_compare_gepa_refinement_candidate(
        manifest_path=source_manifest,
        gepa_result_path=gepa_result_path,
        outdir=candidate_root,
        comparison_out_path=comparison_path,
        gepa_candidate_result_out=candidate_result_path,
    )

    assert workflow["status"] == "materialized_and_compared_gepa_candidate"
    assert workflow["generation"]["status"] == "materialized"
    refresh = workflow["generation"]["behavior_refresh"]
    assert refresh["status"] == "refreshed"
    assert refresh["behavior_results_sha256"]
    behavior = json.loads(
        (candidate_root / "behavior_results.json").read_text(encoding="utf-8")
    )
    assert behavior["summary"]["status"] == "passed"
    candidate_receipt = candidate_root / "manifest.json.meta.json"
    candidate_check = check_run_receipt(candidate_receipt)
    assert candidate_check["status"] == "ok", candidate_check
    assert candidate_check["replay_claims"]["mode"] == "check_only"
    candidate_receipt_payload = load_run_receipt(candidate_receipt)
    assert candidate_receipt_payload is not None
    assert candidate_receipt_payload["run_kind"] == "program-gen"
    assert candidate_receipt_payload["execution_replay"]["supported"] is False
    comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
    assert comparison["status"] == "compared"
    assert comparison["non_authority"]["winner_selection"] is False
    assert _tree_hash(source_root) == source_before
    assert _tree_hash(optimizer_root) == optimizer_before

    runtime_inputs = tmp_path / "runtime-inputs.json"
    runtime_inputs.write_text(
        json.dumps(
            {"inputs": {"ticket_text": "Server is down for all users"}},
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    candidate_before_runtime = _tree_hash(candidate_root)
    monkeypatch.delenv("DSPX_ALLOW_UNSAFE_GEPA_PICKLE_SHA256")
    blocked_runtime = run_program_runtime_episode(
        manifest_path=candidate_root / "manifest.json",
        inputs_path=runtime_inputs,
        outdir=tmp_path / "runtime-without-pickle-opt-in",
        skip_oracle_index=True,
    )
    assert blocked_runtime["status"] != "ok"
    assert blocked_runtime["steps"]["runtime_execution"]["status"] == "error"
    assert _tree_hash(candidate_root) == candidate_before_runtime
    monkeypatch.setenv(
        "DSPX_ALLOW_UNSAFE_GEPA_PICKLE_SHA256", optimizer_manifest_sha256
    )
    runtime_root = tmp_path / "runtime"
    runtime = run_program_runtime_episode(
        manifest_path=candidate_root / "manifest.json",
        inputs_path=runtime_inputs,
        outdir=runtime_root,
        skip_oracle_index=True,
        capture_replay_fixture=True,
    )

    assert runtime["status"] == "ok"
    assert runtime["steps"]["runtime_execution"]["status"] == "executed"
    assert _tree_hash(candidate_root) == candidate_before_runtime
    runtime_receipt = runtime_root / "runtime_episode.json.meta.json"
    runtime_check = check_run_receipt(runtime_receipt)
    assert runtime_check["status"] == "ok", runtime_check
    runtime_receipt_payload = load_run_receipt(runtime_receipt)
    assert runtime_receipt_payload is not None
    assert runtime_receipt_payload["run_kind"] == "program-runtime"
    assert runtime_receipt_payload["execution_replay"]["supported"] is True
    monkeypatch.chdir(runtime_root)
    replay = execute_run_receipt(runtime_receipt, Path("replay-evidence.json"))
    assert replay["status"] == "executed", replay
    assert replay["execution"]["evidence"]["status"] == "execution_reproduced"
    claims = replay["replay_claims"]
    assert claims["mode"] == "runtime_execution_reproduction"
    assert claims["dimensions"]["runtime_execution_reproduction"]["status"] == (
        "passed"
    )
    assert claims["dimensions"]["semantic_reproduction"]["status"] == ("not_evaluated")
    assert claims["release_claim_allowed"] is False
    assert _tree_hash(candidate_root) == candidate_before_runtime
    assert _tree_hash(source_root) == source_before
    assert _tree_hash(optimizer_root) == optimizer_before


def test_bytecode_suppression_is_shared_serialized_and_exception_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor

    from dspx.services.python_import_guard import suppress_bytecode_writes

    monkeypatch.setattr(sys, "dont_write_bytecode", False)
    start = threading.Barrier(2)
    state_lock = threading.Lock()
    active = 0
    max_active = 0

    def worker() -> None:
        nonlocal active, max_active
        start.wait()
        with suppress_bytecode_writes():
            assert sys.dont_write_bytecode is True
            with state_lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.02)
            with state_lock:
                active -= 1

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(worker) for _ in range(2)]
        for future in futures:
            future.result()

    assert max_active == 1
    assert sys.dont_write_bytecode is False
    with pytest.raises(RuntimeError, match="forced import failure"):
        with suppress_bytecode_writes():
            assert sys.dont_write_bytecode is True
            raise RuntimeError("forced import failure")
    assert sys.dont_write_bytecode is False
