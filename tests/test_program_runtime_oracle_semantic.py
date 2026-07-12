# summary: "Tests receipt-bound, resumable runtime Oracle semantic analysis and CLI wiring."

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dspx.cli.commands.oracle import app as oracle_app
from dspx.cli.dspx import app
from dspx.coordinates import reset_embedding_engine
from dspx.services.program_oracle_semantic_contract import (
    OracleSemanticAnalysis,
    OracleSemanticResult,
)
from dspx.services.program_runtime_episode import (
    ProgramRuntimeEpisodeBundle,
    run_program_runtime_episode,
)
from dspx.services.program_service import run_generate_from_intent_path
import dspx.services.program_runtime_oracle_semantic as runtime_semantic


class _Backend:
    def __init__(self, *, succeed: bool = True) -> None:
        self.calls = 0
        self.requests = []
        self.succeed = succeed

    def analyze(self, request):
        self.calls += 1
        self.requests.append(request)
        if not self.succeed:
            return OracleSemanticResult(
                request_sha256=request.request_sha256,
                backend_kind="live",
                preferred_model="codex/gpt-5.6-luna",
                configured_provider="test-provider",
                configured_model="openai/gpt-5.4",
                executed_provider=None,
                executed_model=None,
                execution_status="failed_before_live_success",
                live_call_succeeded=False,
                error="routing unavailable",
            )
        return OracleSemanticResult(
            request_sha256=request.request_sha256,
            backend_kind="live",
            preferred_model="codex/gpt-5.6-luna",
            configured_provider="test-provider",
            configured_model="openai/gpt-5.4",
            executed_provider=None,
            executed_model="openai/gpt-5.4-2026-06-01",
            execution_status="succeeded",
            live_call_succeeded=True,
            analysis=OracleSemanticAnalysis(
                observations=("the runtime output met its declared criterion",),
                failure_attractors=(),
                quality_contract_violations=(),
                hypotheses=("the explicit constraint improved reliability",),
                recommended_experiments=("replay on a second bounded input",),
                evidence_refs=("runtime:episode-1",),
                confidence=0.82,
            ),
        )


def _write_runtime_bundle(tmp_path: Path, monkeypatch) -> tuple[Path, _Backend]:
    episode_path = tmp_path / "runtime_episode.json"
    behavior_path = tmp_path / "behavior_results.json"
    oracle_path = tmp_path / "oracle_evidence.json"
    receipt_path = tmp_path / "runtime_episode.json.meta.json"
    candidate_manifest_path = tmp_path / "candidate_manifest.json"
    candidate_manifest_path.write_text(
        json.dumps({"schema_version": "program-candidate-assembly-v1"}),
        encoding="utf-8",
    )
    behavior = {
        "intent": {
            "objective": "Classify ticket urgency",
            "quality_criteria": [{"name": "accuracy", "threshold": 0.9}],
        },
        "provider": {"status": "configured", "provider": "stub/echo"},
        "summary": {"status": "executed_quality_passed"},
        "execution_status": "executed",
        "quality_evaluation": {"status": "passed"},
        "examples": [
            {
                "index": 0,
                "status": "executed_quality_passed",
                "execution_status": "executed",
                "inputs": {"ticket": "INPUT_SECRET_CANARY"},
                "observed_outputs": {"urgency": "OUTPUT_SECRET_CANARY"},
                "quality_evaluation": {"status": "passed"},
                "notes": ["NOTE_SECRET_CANARY"],
                "error": {"type": "SyntheticError", "message": "ERROR_SECRET_CANARY"},
            }
        ],
        "authority": "behavior_evidence_only_non_authoritative",
    }
    oracle = {
        "schema_version": "program-oracle-evidence-v1",
        "runtime_episode_id": "episode-1",
        "coordinates": {
            "quality_status": "passed",
            "raw_material": "ORACLE_SECRET_CANARY",
        },
        "authority": "empirical_only",
    }
    behavior_path.write_text(json.dumps(behavior), encoding="utf-8")
    oracle_path.write_text(json.dumps(oracle), encoding="utf-8")
    oracle_hash = runtime_semantic._sha256_file(oracle_path)
    episode = {
        "schema_version": "program-runtime-episode-v1",
        "runtime_episode_id": "episode-1",
        "status": "executed_quality_passed",
        "execution_status": "executed",
        "contract_mode": "none",
        "candidate_manifest_path": str(candidate_manifest_path),
        "artifact_hashes": {"oracle_evidence_sha256": oracle_hash},
        "non_authority": {"promotion_authority": False},
    }
    episode_path.write_text(json.dumps(episode), encoding="utf-8")
    receipt_path.write_text(
        json.dumps({"receipt_version": "v2", "run_kind": "program-runtime"}),
        encoding="utf-8",
    )
    bundle = ProgramRuntimeEpisodeBundle(
        runtime_episode=episode,
        behavior_results=behavior,
        runtime_episode_path=episode_path,
        runtime_episode_sha256=runtime_semantic._sha256_file(episode_path),
        behavior_results_path=behavior_path,
        behavior_results_sha256=runtime_semantic._sha256_file(behavior_path),
    )
    monkeypatch.setattr(
        runtime_semantic,
        "load_validated_program_runtime_episode_bundle",
        lambda **kwargs: bundle,
    )
    monkeypatch.setattr(
        runtime_semantic,
        "check_run_receipt",
        lambda path: {"status": "ok", "checks": {"output_hash": True}},
    )
    backend = _Backend()
    monkeypatch.setattr(
        runtime_semantic,
        "resolve_program_oracle_semantic_backend",
        lambda: backend,
    )
    return episode_path, backend


def test_runtime_semantics_binds_receipt_evidence_and_writes_private_sidecar(
    tmp_path: Path, monkeypatch
) -> None:
    episode_path, backend = _write_runtime_bundle(tmp_path, monkeypatch)

    payload = runtime_semantic.run_program_runtime_oracle_semantics(
        runtime_episode_path=episode_path
    )

    sidecar = tmp_path / "program_oracle_semantic.json"
    assert payload["status"] == "ok"
    assert payload["semantic_result"]["preferred_model"] == "codex/gpt-5.6-luna"
    assert payload["semantic_result"]["executed_model"] == "openai/gpt-5.4-2026-06-01"
    assert payload["source_binding"]["runtime_receipt"]["sha256"]
    assert payload["non_authority"]["promotion_authority"] is False
    assert backend.calls == 1
    request_payload = backend.requests[0].payload()
    example = request_payload["evidence"]["behavior"]["examples"][0]
    assert example["output_fields"] == ["urgency"]
    assert example["observed_outputs_sha256"]
    assert example["notes_count"] == 1
    assert example["error_type"] == "SyntheticError"
    serialized_request = json.dumps(request_payload, sort_keys=True)
    for canary in (
        "INPUT_SECRET_CANARY",
        "OUTPUT_SECRET_CANARY",
        "NOTE_SECRET_CANARY",
        "ERROR_SECRET_CANARY",
        "ORACLE_SECRET_CANARY",
    ):
        assert canary not in serialized_request
    assert sidecar.exists()
    assert stat.S_IMODE(sidecar.stat().st_mode) == 0o600


def test_runtime_semantics_resume_reuses_bound_success_without_new_call(
    tmp_path: Path, monkeypatch
) -> None:
    episode_path, backend = _write_runtime_bundle(tmp_path, monkeypatch)
    first = runtime_semantic.run_program_runtime_oracle_semantics(
        runtime_episode_path=episode_path
    )
    monkeypatch.setattr(
        runtime_semantic,
        "resolve_program_oracle_semantic_backend",
        lambda: pytest.fail("resume must not invoke the semantic backend"),
    )

    second = runtime_semantic.run_program_runtime_oracle_semantics(
        runtime_episode_path=episode_path
    )

    assert second == first
    assert backend.calls == 1


def test_attempt_marker_directory_is_fsynced_before_backend_invocation(
    tmp_path: Path, monkeypatch
) -> None:
    episode_path, _ = _write_runtime_bundle(tmp_path, monkeypatch)
    events: list[str] = []
    original_fsync = runtime_semantic.os.fsync

    def tracked_fsync(descriptor: int) -> None:
        if stat.S_ISDIR(runtime_semantic.os.fstat(descriptor).st_mode):
            events.append("directory_fsync")
        original_fsync(descriptor)

    class OrderingBackend(_Backend):
        def analyze(self, request):
            events.append("backend_analyze")
            return super().analyze(request)

    monkeypatch.setattr(runtime_semantic.os, "fsync", tracked_fsync)
    monkeypatch.setattr(
        runtime_semantic,
        "resolve_program_oracle_semantic_backend",
        lambda: OrderingBackend(),
    )

    runtime_semantic.run_program_runtime_oracle_semantics(
        runtime_episode_path=episode_path
    )

    assert "directory_fsync" in events
    assert events.index("directory_fsync") < events.index("backend_analyze")


def test_runtime_semantics_backend_exception_is_durable_and_never_replayed(
    tmp_path: Path, monkeypatch
) -> None:
    episode_path, _ = _write_runtime_bundle(tmp_path, monkeypatch)

    class RaisingBackend:
        calls = 0

        def analyze(self, request):
            self.calls += 1
            raise RuntimeError("connection ended after dispatch")

    backend = RaisingBackend()
    monkeypatch.setattr(
        runtime_semantic,
        "resolve_program_oracle_semantic_backend",
        lambda: backend,
    )

    first = runtime_semantic.run_program_runtime_oracle_semantics(
        runtime_episode_path=episode_path
    )
    second = runtime_semantic.run_program_runtime_oracle_semantics(
        runtime_episode_path=episode_path
    )

    assert first == second
    assert first["status"] == "degraded"
    assert first["semantic_result"]["execution_status"] == "effect_indeterminate"
    assert first["effect"]["effect_disposition"] == "indeterminate"
    assert backend.calls == 1


def test_runtime_semantics_interruption_before_finalization_leaves_no_replay_marker(
    tmp_path: Path, monkeypatch
) -> None:
    episode_path, backend = _write_runtime_bundle(tmp_path, monkeypatch)
    replace = runtime_semantic._replace_private_json_atomic
    monkeypatch.setattr(
        runtime_semantic,
        "_replace_private_json_atomic",
        lambda path, payload: (_ for _ in ()).throw(RuntimeError("simulated crash")),
    )

    with pytest.raises(RuntimeError, match="simulated crash"):
        runtime_semantic.run_program_runtime_oracle_semantics(
            runtime_episode_path=episode_path
        )
    monkeypatch.setattr(runtime_semantic, "_replace_private_json_atomic", replace)

    resumed = runtime_semantic.run_program_runtime_oracle_semantics(
        runtime_episode_path=episode_path
    )

    assert resumed["semantic_result"]["execution_status"] == "effect_indeterminate"
    assert resumed["effect"]["effect_disposition"] == "indeterminate"
    assert backend.calls == 1


def test_runtime_semantics_resume_fails_closed_on_source_drift(
    tmp_path: Path, monkeypatch
) -> None:
    episode_path, _ = _write_runtime_bundle(tmp_path, monkeypatch)
    runtime_semantic.run_program_runtime_oracle_semantics(
        runtime_episode_path=episode_path
    )
    behavior_path = tmp_path / "behavior_results.json"
    behavior_path.write_text('{"drifted":true}', encoding="utf-8")

    with pytest.raises(
        runtime_semantic.ProgramRuntimeOracleSemanticError,
        match="source binding drifted",
    ):
        runtime_semantic.run_program_runtime_oracle_semantics(
            runtime_episode_path=episode_path
        )


def test_runtime_semantics_preserves_failed_attempt_without_claiming_execution(
    tmp_path: Path, monkeypatch
) -> None:
    episode_path, _ = _write_runtime_bundle(tmp_path, monkeypatch)
    failing = _Backend(succeed=False)
    monkeypatch.setattr(
        runtime_semantic,
        "resolve_program_oracle_semantic_backend",
        lambda: failing,
    )

    payload = runtime_semantic.run_program_runtime_oracle_semantics(
        runtime_episode_path=episode_path
    )

    assert payload["status"] == "degraded"
    assert (
        payload["semantic_result"]["execution_status"] == "failed_before_live_success"
    )
    assert payload["semantic_result"]["executed_model"] is None
    assert payload["effect"]["live_call_succeeded"] is False


def test_oracle_semantic_analyze_cli_is_registered(monkeypatch, tmp_path: Path) -> None:
    import dspx.config_loader as config_loader

    episode = tmp_path / "runtime_episode.json"
    episode.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(config_loader, "load_config_env", lambda path=None: {})
    monkeypatch.setattr(
        runtime_semantic,
        "run_program_runtime_oracle_semantics",
        lambda **kwargs: {
            "status": "ok",
            "semantic_result": {
                "preferred_model": "codex/gpt-5.6-luna",
                "executed_model": "openai/gpt-5.4",
            },
        },
    )

    result = CliRunner().invoke(
        oracle_app,
        ["program-semantic-analyze", "--runtime-episode", str(episode), "--json"],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["status"] == "ok"


def test_program_run_cli_forwards_oracle_semantic_opt_in(
    monkeypatch, tmp_path: Path
) -> None:
    import dspx.services.program_runtime_episode as runtime_episode

    manifest = tmp_path / "manifest.json"
    inputs = tmp_path / "inputs.json"
    manifest.write_text("{}", encoding="utf-8")
    inputs.write_text("{}", encoding="utf-8")
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "status": "ok",
            "runtime_root": str(tmp_path / "runtime"),
            "steps": {
                "runtime_execution": {"status": "executed"},
                "oracle_report": {"status": "skipped"},
                "oracle_semantic": {"status": "ok"},
            },
        }

    monkeypatch.setattr(runtime_episode, "run_program_runtime_episode", fake_run)
    result = CliRunner().invoke(
        app,
        [
            "program-run",
            "--manifest",
            str(manifest),
            "--inputs",
            str(inputs),
            "--outdir",
            str(tmp_path / "runtime"),
            "--oracle-semantic",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured["run_oracle_semantic"] is True


def test_real_runtime_bundle_and_receipt_gate_semantic_execution(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "mock")
    reset_embedding_engine()
    intent = tmp_path / "intent.yaml"
    intent.write_text(
        "\n".join(
            [
                "name: TicketProgram",
                "objective: Classify support ticket urgency.",
                "inputs:",
                "  - ticket_text",
                "outputs:",
                "  - urgency",
                "metric: exact_match",
                "constraints:",
                "  - use only supplied text",
            ]
        ),
        encoding="utf-8",
    )
    candidate = tmp_path / "candidate"
    run_generate_from_intent_path(intent, outdir=candidate)
    inputs = tmp_path / "inputs.json"
    inputs.write_text(
        json.dumps({"inputs": {"ticket_text": "Server unavailable"}}),
        encoding="utf-8",
    )
    runtime_root = tmp_path / "runtime"
    run_program_runtime_episode(
        manifest_path=candidate / "manifest.json",
        inputs_path=inputs,
        outdir=runtime_root,
        skip_oracle_index=True,
    )
    backend = _Backend()
    monkeypatch.setattr(
        runtime_semantic,
        "resolve_program_oracle_semantic_backend",
        lambda: backend,
    )
    episode_path = runtime_root / "runtime_episode.json"

    payload = runtime_semantic.run_program_runtime_oracle_semantics(
        runtime_episode_path=episode_path
    )

    assert payload["status"] == "ok"
    assert backend.calls == 1

    receipt_path = runtime_root / "runtime_episode.json.meta.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["hash"] = "0" * 64
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(
        runtime_semantic.ProgramRuntimeOracleSemanticError,
        match="receipt must pass replay validation",
    ):
        runtime_semantic.run_program_runtime_oracle_semantics(
            runtime_episode_path=episode_path,
            out_path=runtime_root / "second-attempt.json",
        )
    assert backend.calls == 1
