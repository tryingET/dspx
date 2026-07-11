from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterator

import pytest

from dspx.run_receipts import load_run_receipt
import dspx.services.program_execution_replay_executor as replay_executor
from dspx.services.program_intent import ProgramIntent
from dspx.services.program_runtime_episode import run_program_runtime_episode
from dspx.services.program_service import (
    materialize_program_from_intent,
    run_generate_from_intent_path,
)
from dspx.services.run_replay_service import check_run_receipt, execute_run_receipt


def _tree_hash(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


@pytest.fixture
def replay_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    keys = {
        "DSPX_PROVIDER": "stub",
        "DSPX_STUB_RESPONSE_JSON": json.dumps(
            {
                "reasoning": "The supplied ticket describes an outage.",
                "urgency": "high",
                "route": "support",
                "response": "We will help review the billing invoice.",
            }
        ),
        "DSPX_CACHE_ENABLE": "0",
        "DSPX_CACHE_DIR": str(tmp_path / "cache"),
        "MLFLOW_ENABLE": "0",
        "DSPX_ORACLE_EMBEDDING_BACKEND": "mock",
    }
    for key, value in keys.items():
        monkeypatch.setenv(key, value)
    yield


def _single_runtime(
    tmp_path: Path, *, capture_replay_fixture: bool = True
) -> tuple[Path, Path, Path]:
    intent = tmp_path / "intent.yaml"
    intent.write_text(
        "\n".join(
            [
                "name: TicketProgram",
                "objective: Classify support ticket urgency.",
                "inputs: [ticket_text]",
                "outputs: [urgency]",
                "metric: exact_match",
            ]
        ),
        encoding="utf-8",
    )
    candidate = tmp_path / "candidate"
    run_generate_from_intent_path(intent, outdir=candidate)
    inputs = tmp_path / "inputs.json"
    inputs.write_text(
        json.dumps({"inputs": {"ticket_text": "Server is down"}}),
        encoding="utf-8",
    )
    runtime = tmp_path / "runtime"
    run_program_runtime_episode(
        manifest_path=candidate / "manifest.json",
        inputs_path=inputs,
        outdir=runtime,
        skip_oracle_index=True,
        capture_replay_fixture=capture_replay_fixture,
    )
    return candidate, runtime, runtime / "runtime_episode.json.meta.json"


def _pipeline_runtime(tmp_path: Path) -> tuple[Path, Path, Path]:
    artifact = materialize_program_from_intent(
        ProgramIntent(
            name="SupportRouterProgram",
            objective="Route support tickets and draft a response.",
            inputs=["ticket_text"],
            outputs=["response"],
            metric="exact_match",
            topology={
                "kind": "pipeline",
                "execution_status": "declared_not_materialized",
                "modules": [
                    {
                        "id": "classify_ticket",
                        "primitive": "Predict",
                        "signature": {
                            "name": "ClassifyTicket",
                            "inputs": ["ticket_text"],
                            "outputs": ["route"],
                        },
                    },
                    {
                        "id": "draft_response",
                        "primitive": "chain_of_thought",
                        "signature": {
                            "name": "DraftResponse",
                            "inputs": ["ticket_text", "route"],
                            "outputs": ["response"],
                        },
                    },
                ],
                "edges": [
                    {"from": "input", "to": "classify_ticket"},
                    {"from": "classify_ticket", "to": "draft_response"},
                    {"from": "draft_response", "to": "output"},
                ],
            },
        ),
        outdir=tmp_path / "candidate",
    )
    candidate = Path(artifact.root_path)
    inputs = tmp_path / "inputs.json"
    inputs.write_text(
        json.dumps({"inputs": {"ticket_text": "Billing invoice is wrong"}}),
        encoding="utf-8",
    )
    runtime = tmp_path / "runtime"
    run_program_runtime_episode(
        manifest_path=candidate / "manifest.json",
        inputs_path=inputs,
        outdir=runtime,
        skip_oracle_index=True,
        capture_replay_fixture=True,
    )
    return candidate, runtime, runtime / "runtime_episode.json.meta.json"


def _assert_replay(
    *, candidate: Path, runtime: Path, receipt_path: Path, output_name: str
) -> dict[str, Any]:
    receipt = load_run_receipt(receipt_path)
    assert receipt is not None
    assert receipt["run_kind"] == "program-runtime"
    assert receipt["execution_replay"]["supported"] is True
    assert "runtime_inputs" not in receipt["replay_inputs"]
    assert "stub_response" not in receipt["replay_inputs"]
    fixture = Path(receipt["replay_inputs"]["replay_fixture_path"])
    assert fixture.stat().st_mode & 0o777 == 0o600
    assert check_run_receipt(receipt_path)["status"] == "ok"
    candidate_before = _tree_hash(candidate)
    runtime_before = _tree_hash(runtime)

    report = execute_run_receipt(receipt_path, Path(output_name))

    assert report["status"] == "executed", report
    execution = report["execution"]
    assert execution["strategy"] == "program-runtime-local-reexecution"
    evidence = execution["evidence"]
    assert evidence["schema_version"] == "program-execution-replay-evidence-v1"
    assert evidence["status"] == "execution_reproduced"
    assert evidence["behavior_quality_approved"] is False
    assert all(evidence["checks"].values())
    output = runtime / output_name
    assert json.loads(output.read_text(encoding="utf-8")) == evidence
    assert _tree_hash(candidate) == candidate_before
    assert {
        key: value for key, value in _tree_hash(runtime).items() if key != output_name
    } == runtime_before
    return report


def test_program_runtime_receipt_replays_single_module_and_confines_output(
    tmp_path: Path,
    replay_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate, runtime, receipt = _single_runtime(tmp_path)
    monkeypatch.setenv("PYTHONPATH", "/tmp/ambient-injection")
    monkeypatch.setenv("LD_PRELOAD", "/tmp/ambient-loader.so")
    monkeypatch.setenv("API_KEY", "ambient-secret")
    original_run = replay_executor.subprocess.run

    def guarded_run(*args: Any, **kwargs: Any) -> Any:
        child_env = kwargs["env"]
        assert "PYTHONPATH" not in child_env
        assert "LD_PRELOAD" not in child_env
        assert "API_KEY" not in child_env
        assert child_env["PYTHONDONTWRITEBYTECODE"] == "1"
        return original_run(*args, **kwargs)

    monkeypatch.setattr(replay_executor.subprocess, "run", guarded_run)
    _assert_replay(
        candidate=candidate,
        runtime=runtime,
        receipt_path=receipt,
        output_name="replay-evidence.json",
    )

    existing = runtime / "existing.json"
    existing.write_text("unchanged", encoding="utf-8")
    conflict = execute_run_receipt(receipt, existing)
    assert conflict["status"] == "failed"
    assert "execution_replay_output_exists" in conflict["error_codes"]
    assert existing.read_text(encoding="utf-8") == "unchanged"

    escaped = execute_run_receipt(receipt, tmp_path / "escaped.json")
    assert escaped["status"] == "invalid"
    assert not (tmp_path / "escaped.json").exists()

    outside = tmp_path / "outside"
    outside.mkdir()
    linked_parent = runtime / "linked-parent"
    linked_parent.symlink_to(outside, target_is_directory=True)
    symlinked = execute_run_receipt(receipt, Path("linked-parent/evidence.json"))
    assert symlinked["status"] == "invalid"
    assert not (outside / "evidence.json").exists()

    fixture = runtime / "runtime_replay_fixture.json"
    fixture.chmod(0o644)
    exposed = execute_run_receipt(receipt, Path("exposed-fixture-replay.json"))
    assert exposed["status"] == "invalid"
    assert exposed["execution"]["attempted"] is False
    assert not (runtime / "exposed-fixture-replay.json").exists()
    fixture.chmod(0o600)


def test_program_runtime_receipt_replays_bounded_pipeline(
    tmp_path: Path, replay_env: None
) -> None:
    candidate, runtime, receipt = _pipeline_runtime(tmp_path)
    report = _assert_replay(
        candidate=candidate,
        runtime=runtime,
        receipt_path=receipt,
        output_name="pipeline-replay-evidence.json",
    )
    assert report["execution"]["evidence"]["behavior_status"] == "executed"


def test_program_runtime_episode_rejects_candidate_root_overlap_before_writes(
    tmp_path: Path, replay_env: None
) -> None:
    intent = tmp_path / "intent.yaml"
    intent.write_text(
        "name: OverlapProgram\nobjective: Test overlap.\ninputs: [question]\noutputs: [answer]\n",
        encoding="utf-8",
    )
    candidate = tmp_path / "candidate"
    run_generate_from_intent_path(intent, outdir=candidate)
    inputs = tmp_path / "inputs.json"
    inputs.write_text('{"inputs":{"question":"hello"}}', encoding="utf-8")
    nested_runtime = candidate / "runtime"

    with pytest.raises(ValueError, match="disjoint from the candidate root"):
        run_program_runtime_episode(
            manifest_path=candidate / "manifest.json",
            inputs_path=inputs,
            outdir=nested_runtime,
            skip_oracle_index=True,
            capture_replay_fixture=True,
        )
    assert not nested_runtime.exists()


def test_program_runtime_replay_rejects_stale_evidence_before_subprocess(
    tmp_path: Path, replay_env: None
) -> None:
    _candidate, runtime, receipt = _single_runtime(tmp_path)
    behavior = runtime / "behavior_results.json"
    behavior.write_text(behavior.read_text(encoding="utf-8") + " ", encoding="utf-8")

    report = execute_run_receipt(receipt, Path("replay-evidence.json"))

    assert report["status"] in {"failed", "invalid"}
    assert report["execution"]["attempted"] is False
    assert not (runtime / "replay-evidence.json").exists()


def test_program_runtime_replay_timeout_is_bounded_and_writes_nothing(
    tmp_path: Path, replay_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _candidate, runtime, receipt = _single_runtime(tmp_path)

    def timeout(*args: Any, **kwargs: Any) -> Any:
        raise replay_executor.subprocess.TimeoutExpired(
            cmd="program-run", timeout=60, stderr="api_key=secret"
        )

    monkeypatch.setattr(replay_executor.subprocess, "run", timeout)
    report = execute_run_receipt(receipt, Path("timeout-replay.json"))

    assert report["status"] == "failed"
    assert report["execution"]["attempted"] is True
    assert "execution_replay_process_failed" in report["error_codes"]
    assert "secret" not in json.dumps(report)
    assert not (runtime / "timeout-replay.json").exists()


def test_program_runtime_replay_preserves_failed_behavior_as_nonapproval(
    tmp_path: Path, replay_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(
        "DSPX_STUB_RESPONSE_JSON",
        json.dumps({"reasoning": "No declared output was supplied."}),
    )
    _candidate, runtime, receipt = _single_runtime(tmp_path)

    report = execute_run_receipt(receipt, Path("degraded-replay.json"))

    assert report["status"] == "executed", report
    evidence = report["execution"]["evidence"]
    assert evidence["behavior_status"] == "error"
    assert evidence["behavior_quality_approved"] is False
    assert (runtime / "degraded-replay.json").is_file()


def test_program_runtime_replay_policy_is_unsupported_without_safe_stub_fixture(
    tmp_path: Path, replay_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_STUB_RESPONSE_JSON", "api_key=secret")
    _candidate, runtime, receipt_path = _single_runtime(
        tmp_path, capture_replay_fixture=False
    )
    receipt = load_run_receipt(receipt_path)
    assert receipt is not None
    assert receipt["execution_replay"]["supported"] is False
    assert (
        "missing_replay_fixture" in receipt["execution_replay"]["unsupported_reasons"]
    )

    report = execute_run_receipt(receipt_path, Path("replay-evidence.json"))
    assert report["status"] == "invalid"
    assert report["execution"]["attempted"] is False
    assert not (runtime / "replay-evidence.json").exists()
