from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from dspx.services.program_runtime_traces import (
    build_program_runtime_traces,
    validate_program_runtime_traces,
)
from dspx.services.program_service import ProgramIntent, materialize_program_from_intent
from dspx.services.run_replay_service import check_run_receipt


def _module_surfaces() -> dict[str, object]:
    return {
        "schema_version": "program-module-surfaces-v1",
        "module_surfaces": [
            {
                "module_id": "generated_module",
                "primitive": "Predict",
                "signature": {
                    "name": "AnswerSignature",
                    "inputs": ["question"],
                    "outputs": ["answer"],
                },
                "effects": {
                    "provider_called": False,
                    "tool_called": False,
                    "custom_import_loaded": False,
                    "network": False,
                    "filesystem_read": False,
                    "filesystem_write": False,
                    "subprocess": False,
                    "external_authority": False,
                },
            }
        ],
    }


def test_runtime_traces_reconstruct_single_module_behavior_call() -> None:
    payload = build_program_runtime_traces(
        SimpleNamespace(
            name="TraceProgram",
            objective="Capture runtime traces.",
            outputs=["answer"],
        ),
        module_surfaces=_module_surfaces(),
        behavior_results={
            "schema_version": "program-behavior-results-v1",
            "examples": [
                {
                    "index": 0,
                    "status": "passed",
                    "inputs": {"question": "q"},
                    "observed_outputs": {"answer": "a"},
                }
            ],
            "summary": {"total": 1, "status": "passed"},
        },
        behavior_results_hash="abc",
    )

    assert payload["schema_version"] == "program-runtime-traces-v1"
    assert payload["status"] == "runtime_traces_captured"
    assert payload["module_call_count"] == 1
    assert payload["final_output_trace_count"] == 1
    call = payload["module_calls"][0]
    assert call["schema_version"] == "program-runtime-module-call-v1"
    assert call["capture_status"] == (
        "actual_single_module_call_reconstructed_from_behavior_result"
    )
    assert call["inputs"] == {"question": "q"}
    assert call["outputs"] == {"answer": "a"}
    assert call["trajectory_slots"]["tool_calls_executed"] is False
    assert call["effects"]["tool_called"] is False
    assert call["non_authority"]["promotion_authority"] is False
    assert payload["runtime_policy"]["tool_execution_allowed"] is False
    assert payload["trace_hashes"]["module_calls"] == [call["trace_hash"]]
    assert validate_program_runtime_traces(payload) is True


def test_runtime_trace_semantic_validator_rejects_hash_and_tool_drift() -> None:
    payload = build_program_runtime_traces(
        SimpleNamespace(
            name="TraceProgram",
            objective="Capture runtime traces.",
            outputs=["answer"],
        ),
        module_surfaces=_module_surfaces(),
        behavior_results={
            "schema_version": "program-behavior-results-v1",
            "examples": [
                {
                    "index": 0,
                    "status": "passed",
                    "inputs": {"question": "q"},
                    "observed_outputs": {"answer": "a"},
                }
            ],
            "summary": {"total": 1, "status": "passed"},
        },
    )
    assert validate_program_runtime_traces(payload) is True

    bad_hash = json.loads(json.dumps(payload))
    bad_hash["module_calls"][0]["outputs"] = {"answer": "tampered"}
    assert validate_program_runtime_traces(bad_hash) is False

    bad_tool_policy = json.loads(json.dumps(payload))
    bad_tool_policy["module_calls"][0]["trajectory_slots"]["tool_calls_executed"] = True
    assert validate_program_runtime_traces(bad_tool_policy) is False

    bad_authority = json.loads(json.dumps(payload))
    bad_authority["non_authority"]["promotion_authority"] = True
    assert validate_program_runtime_traces(bad_authority) is False


def test_runtime_trace_missing_upstream_input_is_not_reported_as_present_source() -> (
    None
):
    payload = build_program_runtime_traces(
        SimpleNamespace(
            name="PipelineTraceProgram",
            objective="Capture partial pipeline traces.",
            outputs=["answer"],
        ),
        module_surfaces={
            "schema_version": "program-module-surfaces-v1",
            "module_surfaces": [
                {
                    "module_id": "extract",
                    "primitive": "Predict",
                    "signature": {
                        "name": "ExtractSignature",
                        "inputs": ["question"],
                        "outputs": ["facts"],
                    },
                },
                {
                    "module_id": "answer",
                    "primitive": "Predict",
                    "signature": {
                        "name": "AnswerSignature",
                        "inputs": ["facts"],
                        "outputs": ["answer"],
                    },
                },
            ],
        },
        behavior_results={
            "schema_version": "program-behavior-results-v1",
            "examples": [
                {
                    "index": 0,
                    "status": "passed",
                    "inputs": {"question": "q"},
                    "observed_outputs": {"answer": "a"},
                    "runtime_trace": {
                        "module_calls": [
                            {
                                "module_id": "extract",
                                "inputs": {"question": "q"},
                                "outputs": {"facts": "f"},
                            },
                            {
                                "module_id": "answer",
                                "inputs": {},
                                "outputs": {"answer": "a"},
                            },
                        ]
                    },
                }
            ],
        },
    )

    answer_call = payload["module_calls"][1]
    assert answer_call["input_field_linkage"] == [
        {
            "field": "facts",
            "source": "missing",
            "present": False,
            "declared_available_from_prior_output": True,
        }
    ]


def test_program_gen_writes_hash_bound_runtime_traces_and_replay_checks(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    intent = ProgramIntent(
        name="RuntimeTraceProgram",
        objective="Answer a question.",
        inputs=["question"],
        outputs=["answer"],
        examples=[{"inputs": {"question": "hello"}, "outputs": {"answer": "hello"}}],
    )

    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "program")
    root = Path(artifact.root_path)
    traces_path = root / "program_runtime_traces.json"
    traces = json.loads(traces_path.read_text(encoding="utf-8"))

    assert traces["schema_version"] == "program-runtime-traces-v1"
    assert traces["status"] == "runtime_traces_captured"
    assert traces["module_call_count"] >= 1
    assert traces["runtime_policy"]["tool_execution_allowed"] is False
    assert traces["non_authority"]["governance_authority"] is False
    assert artifact.manifest["runtime_traces_artifact"]["path"] == (
        "program_runtime_traces.json"
    )
    assert (
        artifact.manifest["request"]["runtime_traces_hash"]
        == artifact.metadata["runtime_traces_hash"]
    )

    replay = check_run_receipt(root / "manifest.json.meta.json")
    assert replay["status"] == "ok"
    assert replay["checks"]["program_runtime_traces_exists"] is True
    assert replay["checks"]["program_runtime_traces_hash_match"] is True
    assert replay["checks"]["program_runtime_traces_semantic_valid"] is True

    traces["status"] = "drifted"
    traces_path.write_text(
        json.dumps(traces, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    drift = check_run_receipt(root / "manifest.json.meta.json")

    assert drift["status"] == "failed"
    assert drift["checks"]["program_runtime_traces_hash_match"] is False
    assert drift["checks"]["program_runtime_traces_semantic_valid"] is False
    assert "program_evidence_hash_mismatch" in drift["error_codes"]
    assert "program_evidence_declaration_mismatch" in drift["error_codes"]
