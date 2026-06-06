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
    assert payload["coverage"]["status"] == "complete"
    assert payload["coverage"]["expected_module_ids"] == ["generated_module"]
    assert payload["coverage"]["captured_module_ids"] == ["generated_module"]
    assert payload["coverage"]["missing_module_ids"] == []
    assert payload["coverage"]["captured_final_output_fields"] == ["answer"]
    assert payload["source_record_coverage"] == [
        {
            "schema_version": "program-runtime-trace-source-coverage-v1",
            "status": "complete",
            "path": "behavior_results.json",
            "split": None,
            "record_count": 1,
            "expected_module_ids": ["generated_module"],
            "program_outputs": ["answer"],
            "module_call_count": 1,
            "final_output_trace_count": 1,
            "records_with_module_calls": [0],
            "records_with_final_outputs": [0],
            "records_with_complete_module_calls": [0],
            "records_with_complete_final_outputs": [0],
            "missing_module_call_record_indexes": [],
            "missing_final_output_record_indexes": [],
            "module_coverage_gaps": [],
            "final_output_coverage_gaps": [],
            "non_authority": payload["non_authority"],
        }
    ]
    assert validate_program_runtime_traces(payload) is True


def test_runtime_traces_preserve_react_v2_declared_tool_refs_without_execution() -> (
    None
):
    module_surfaces = _module_surfaces()
    surface = dict(module_surfaces["module_surfaces"][0])
    surface["primitive"] = "ReActV2"
    surface["react"] = {
        "declared_tool_refs": ["lookup_policy"],
        "tool_binding_status": "declared_refs_only_not_bound",
        "tool_binding_allowed": False,
    }
    module_surfaces["module_surfaces"] = [surface]

    payload = build_program_runtime_traces(
        SimpleNamespace(
            name="TraceProgram",
            objective="Capture ReActV2 runtime traces.",
            outputs=["answer"],
        ),
        module_surfaces=module_surfaces,
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

    call = payload["module_calls"][0]
    assert call["trajectory_slots"]["tool_refs"] == {
        "declared_tool_refs": ["lookup_policy"],
        "tool_binding_status": "declared_refs_only_not_bound",
        "tool_binding_allowed": False,
        "executable_tools": [],
    }
    assert call["trajectory_slots"]["tool_call_intents"] == [
        {
            "schema_version": "program-runtime-tool-call-intent-v1",
            "tool_id": "lookup_policy",
            "status": "declared_intent_shape_not_executed",
            "adapter_dry_run_required": True,
            "tool_call_executed": False,
            "dspy_tool_bound": False,
            "result_recorded": False,
            "effects": {
                "tool_called": False,
                "network": False,
                "filesystem": False,
                "subprocess": False,
                "external_authority_mutated": False,
            },
        }
    ]
    assert call["trajectory_slots"]["tool_calls_executed"] is False
    assert call["effects"]["tool_called"] is False
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

    react_v2_payload = build_program_runtime_traces(
        SimpleNamespace(
            name="TraceProgram",
            objective="Capture ReActV2 runtime traces.",
            outputs=["answer"],
        ),
        module_surfaces={
            "module_surfaces": [
                {
                    **_module_surfaces()["module_surfaces"][0],
                    "primitive": "ReActV2",
                    "react": {
                        "declared_tool_refs": ["lookup_policy"],
                        "tool_binding_status": "declared_refs_only_not_bound",
                        "tool_binding_allowed": False,
                    },
                }
            ]
        },
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
    bad_tool_intent = json.loads(json.dumps(react_v2_payload))
    bad_tool_intent["module_calls"][0]["trajectory_slots"]["tool_call_intents"][0][
        "tool_call_executed"
    ] = True
    assert validate_program_runtime_traces(bad_tool_intent) is False

    bad_tool_result = json.loads(json.dumps(react_v2_payload))
    bad_tool_result["module_calls"][0]["trajectory_slots"]["tool_call_results"] = [
        {"tool_id": "lookup_policy"}
    ]
    assert validate_program_runtime_traces(bad_tool_result) is False

    bad_scheduler_event = json.loads(json.dumps(payload))
    bad_scheduler_event["module_calls"][0]["scheduler_events"] = [
        {"status": "called_external_tool", "missing_outputs": [], "pending": []}
    ]
    assert validate_program_runtime_traces(bad_scheduler_event) is False

    bad_scheduler_shape = json.loads(json.dumps(payload))
    bad_scheduler_shape["module_calls"][0]["scheduler_events"] = [
        {
            "status": "scheduler_stalled",
            "missing_outputs": ["answer"],
            "pending": "answer",
        }
    ]
    assert validate_program_runtime_traces(bad_scheduler_shape) is False

    bad_authority = json.loads(json.dumps(payload))
    bad_authority["non_authority"]["promotion_authority"] = True
    assert validate_program_runtime_traces(bad_authority) is False

    bad_authority_type = json.loads(json.dumps(payload))
    bad_authority_type["non_authority"]["runtime_evidence_only"] = "yes"
    assert validate_program_runtime_traces(bad_authority_type) is False

    bad_status = json.loads(json.dumps(payload))
    bad_status["status"] = "no_runtime_traces_captured"
    assert validate_program_runtime_traces(bad_status) is False

    legacy_without_source_coverage = json.loads(json.dumps(payload))
    legacy_without_source_coverage.pop("source_record_coverage")
    assert validate_program_runtime_traces(legacy_without_source_coverage) is True

    bad_coverage = json.loads(json.dumps(payload))
    bad_coverage["coverage"]["missing_module_ids"] = ["generated_module"]
    assert validate_program_runtime_traces(bad_coverage) is False

    bad_source_coverage = json.loads(json.dumps(payload))
    bad_source_coverage["source_record_coverage"][0][
        "missing_final_output_record_indexes"
    ] = [0]
    assert validate_program_runtime_traces(bad_source_coverage) is False


def test_runtime_trace_coverage_reports_missing_modules_and_outputs() -> None:
    payload = build_program_runtime_traces(
        SimpleNamespace(
            name="PartialTraceProgram",
            objective="Capture partial pipeline traces.",
            outputs=["answer", "confidence"],
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
                        "outputs": ["answer", "confidence"],
                    },
                },
            ],
        },
        behavior_results={
            "schema_version": "program-behavior-results-v1",
            "examples": [
                {
                    "index": 0,
                    "status": "executed",
                    "inputs": {"question": "q"},
                    "observed_outputs": {"answer": "a"},
                    "runtime_trace": {
                        "module_calls": [
                            {
                                "module_id": "extract",
                                "inputs": {"question": "q"},
                                "outputs": {"facts": "f"},
                            }
                        ]
                    },
                }
            ],
        },
    )

    assert payload["coverage"] == {
        "schema_version": "program-runtime-trace-coverage-v1",
        "status": "partial",
        "source_count": 1,
        "expected_module_ids": ["answer", "extract"],
        "captured_module_ids": ["extract"],
        "missing_module_ids": ["answer"],
        "program_outputs": ["answer", "confidence"],
        "captured_final_output_fields": ["answer"],
        "missing_final_output_fields": ["confidence"],
        "source_record_coverage_status": "partial",
        "module_call_count": 1,
        "final_output_trace_count": 1,
        "non_authority": payload["non_authority"],
    }
    assert payload["source_record_coverage"][0]["status"] == "partial"
    assert payload["source_record_coverage"][0]["records_with_module_calls"] == [0]
    assert payload["source_record_coverage"][0]["records_with_final_outputs"] == [0]
    assert payload["source_record_coverage"][0]["module_coverage_gaps"] == [
        {"record_index": 0, "missing_module_ids": ["answer"]}
    ]
    assert payload["source_record_coverage"][0]["final_output_coverage_gaps"] == [
        {"record_index": 0, "missing_final_output_fields": ["confidence"]}
    ]
    assert validate_program_runtime_traces(payload) is True


def test_runtime_trace_source_coverage_reports_record_level_gaps() -> None:
    payload = build_program_runtime_traces(
        SimpleNamespace(
            name="RecordGapTraceProgram",
            objective="Capture record-level trace gaps.",
            outputs=["answer"],
        ),
        module_surfaces={
            "schema_version": "program-module-surfaces-v1",
            "module_surfaces": [
                {
                    "module_id": "answer",
                    "primitive": "Predict",
                    "signature": {
                        "name": "AnswerSignature",
                        "inputs": ["question"],
                        "outputs": ["answer"],
                    },
                },
                {
                    "module_id": "critique",
                    "primitive": "Predict",
                    "signature": {
                        "name": "CritiqueSignature",
                        "inputs": ["answer"],
                        "outputs": ["critique"],
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
                    "inputs": {"question": "q0"},
                    "observed_outputs": {"answer": "a0"},
                    "runtime_trace": {"module_calls": []},
                },
                {
                    "index": 1,
                    "status": "error",
                    "inputs": {"question": "q1"},
                    "observed_outputs": {},
                    "runtime_trace": {"module_calls": []},
                },
            ],
        },
    )

    assert payload["source_record_coverage"] == [
        {
            "schema_version": "program-runtime-trace-source-coverage-v1",
            "status": "partial",
            "path": "behavior_results.json",
            "split": None,
            "record_count": 2,
            "expected_module_ids": ["answer", "critique"],
            "program_outputs": ["answer"],
            "module_call_count": 0,
            "final_output_trace_count": 2,
            "records_with_module_calls": [],
            "records_with_final_outputs": [0, 1],
            "records_with_complete_module_calls": [],
            "records_with_complete_final_outputs": [0],
            "missing_module_call_record_indexes": [0, 1],
            "missing_final_output_record_indexes": [1],
            "module_coverage_gaps": [
                {"record_index": 0, "missing_module_ids": ["answer", "critique"]},
                {"record_index": 1, "missing_module_ids": ["answer", "critique"]},
            ],
            "final_output_coverage_gaps": [
                {"record_index": 1, "missing_final_output_fields": ["answer"]}
            ],
            "non_authority": payload["non_authority"],
        }
    ]
    assert validate_program_runtime_traces(payload) is True


def test_runtime_trace_explicit_empty_single_module_trace_is_not_synthesized() -> None:
    payload = build_program_runtime_traces(
        SimpleNamespace(
            name="ExplicitEmptyTraceProgram",
            objective="Respect an explicit empty runtime trace.",
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
                    "runtime_trace": {"module_calls": []},
                }
            ],
        },
    )

    assert payload["module_call_count"] == 0
    assert payload["coverage"]["status"] == "partial"
    assert payload["source_record_coverage"][0]["status"] == "partial"
    assert payload["source_record_coverage"][0][
        "missing_module_call_record_indexes"
    ] == [0]
    assert validate_program_runtime_traces(payload) is True


def test_runtime_trace_coverage_requires_outputs_on_each_record() -> None:
    payload = build_program_runtime_traces(
        SimpleNamespace(
            name="SplitOutputTraceProgram",
            objective="Catch aggregate-only output coverage.",
            outputs=["answer", "confidence"],
        ),
        module_surfaces={
            "schema_version": "program-module-surfaces-v1",
            "module_surfaces": [
                {
                    "module_id": "generated_module",
                    "primitive": "Predict",
                    "signature": {
                        "name": "SplitOutputSignature",
                        "inputs": ["question"],
                        "outputs": ["answer", "confidence"],
                    },
                }
            ],
        },
        behavior_results={
            "schema_version": "program-behavior-results-v1",
            "examples": [
                {
                    "index": 0,
                    "status": "passed",
                    "inputs": {"question": "q0"},
                    "observed_outputs": {"answer": "a0"},
                },
                {
                    "index": 1,
                    "status": "passed",
                    "inputs": {"question": "q1"},
                    "observed_outputs": {"confidence": 0.9},
                },
            ],
        },
    )

    assert payload["coverage"]["captured_final_output_fields"] == [
        "answer",
        "confidence",
    ]
    assert payload["coverage"]["missing_final_output_fields"] == []
    assert payload["coverage"]["source_record_coverage_status"] == "partial"
    assert payload["coverage"]["status"] == "partial"
    assert payload["source_record_coverage"][0][
        "missing_final_output_record_indexes"
    ] == [0, 1]
    assert payload["source_record_coverage"][0]["final_output_coverage_gaps"] == [
        {"record_index": 0, "missing_final_output_fields": ["confidence"]},
        {"record_index": 1, "missing_final_output_fields": ["answer"]},
    ]
    assert validate_program_runtime_traces(payload) is True


def test_runtime_traces_record_stage_and_intermediate_lineage() -> None:
    payload = build_program_runtime_traces(
        SimpleNamespace(
            name="GraphTraceProgram",
            objective="Draft, critique, and revise.",
            outputs=["answer"],
        ),
        module_surfaces={
            "schema_version": "program-module-surfaces-v1",
            "module_surfaces": [
                {
                    "module_id": "generate_draft",
                    "primitive": "ChainOfThought",
                    "stage": {
                        "role": "generate_draft",
                        "metadata_source": "program_intent_topology_module.role",
                    },
                    "signature": {
                        "name": "GenerateDraft",
                        "inputs": ["question"],
                        "outputs": ["draft"],
                    },
                },
                {
                    "module_id": "critique_draft",
                    "primitive": "ChainOfThought",
                    "stage": {
                        "role": "critique_draft",
                        "metadata_source": "program_intent_topology_module.role",
                    },
                    "signature": {
                        "name": "CritiqueDraft",
                        "inputs": ["question", "draft"],
                        "outputs": ["critique"],
                    },
                },
                {
                    "module_id": "revise_final",
                    "primitive": "ChainOfThought",
                    "stage": {
                        "role": "revise_final",
                        "metadata_source": "program_intent_topology_module.role",
                    },
                    "signature": {
                        "name": "ReviseFinal",
                        "inputs": ["question", "draft", "critique"],
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
                        "scheduler_events": [
                            {
                                "status": "completed",
                                "missing_outputs": [],
                                "pending": [],
                            }
                        ],
                        "module_calls": [
                            {
                                "module_id": "generate_draft",
                                "inputs": {"question": "q"},
                                "outputs": {"draft": "d"},
                            },
                            {
                                "module_id": "critique_draft",
                                "inputs": {"question": "q", "draft": "d"},
                                "outputs": {"critique": "c"},
                            },
                            {
                                "module_id": "revise_final",
                                "inputs": {
                                    "question": "q",
                                    "draft": "d",
                                    "critique": "c",
                                },
                                "outputs": {"answer": "a"},
                            },
                        ],
                    },
                }
            ],
        },
    )

    calls = payload["module_calls"]
    assert [call["stage"]["role"] for call in calls] == [
        "generate_draft",
        "critique_draft",
        "revise_final",
    ]
    assert calls[1]["intermediate_field_lineage"]["inputs"] == [
        {
            "field": "draft",
            "source": "upstream_module_output",
            "source_module_id": "generate_draft",
        },
        {"field": "question", "source": "program_input", "source_module_id": None},
    ]
    assert calls[2]["final_output_linkage"] == [
        {"field": "answer", "source_module_id": "revise_final", "present": True}
    ]
    assert calls[0]["scheduler_events"] == [
        {"status": "completed", "missing_outputs": [], "pending": []}
    ]
    assert validate_program_runtime_traces(payload) is True


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
