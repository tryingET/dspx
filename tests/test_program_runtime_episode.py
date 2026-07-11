# summary: "Tests isolated runtime episodes for generated programs and their evidence contracts."
# read_when:
#   - "Changing program-run execution, runtime validation, input handling, or generated-code safety."

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.coordinates import CoordinateIndex, reset_embedding_engine
import dspx.services.program_runtime_episode as runtime_episode_service
from dspx.services.program_intent import ProgramIntent
from dspx.services.program_oracle_index import index_program_oracle_evidence_path
from dspx.services.program_oracle_report import build_program_oracle_evidence_report
from dspx.services.program_runtime_episode import (
    _generated_program_module,
    _materialize_runtime_inputs,
    load_validated_program_runtime_episode_bundle,
    run_program_runtime_episode,
    validate_program_runtime_episode_contract,
)
from dspx.services.program_service import (
    materialize_program_from_intent,
    run_generate_from_intent_path,
)

runner = CliRunner()


def _write_intent(path: Path) -> None:
    path.write_text(
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
                "  - use only the supplied ticket text",
                "examples:",
                "  - inputs:",
                "      ticket_text: Server is down for all users",
                "    outputs:",
                "      urgency: high",
            ]
        ),
        encoding="utf-8",
    )


def _env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "mock")
    reset_embedding_engine()


def _generated_candidate(tmp_path: Path) -> Path:
    intent = tmp_path / "intent.yaml"
    outdir = tmp_path / "candidate"
    _write_intent(intent)
    run_generate_from_intent_path(intent, outdir=outdir)
    return outdir


def _explicit_pipeline_candidate(tmp_path: Path) -> Path:
    artifact = materialize_program_from_intent(
        ProgramIntent(
            name="SupportRouterProgram",
            objective="Route support tickets and draft a response.",
            inputs=["ticket_text"],
            outputs=["response"],
            metric="exact_match",
            constraints=["preserve the original ticket facts"],
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
            examples=[
                {
                    "inputs": {"ticket_text": "Billing invoice is wrong"},
                    "outputs": {"response": "We will help review the billing invoice."},
                }
            ],
        ),
        outdir=tmp_path / "pipeline-candidate",
    )
    return Path(artifact.root_path)


def test_program_runtime_episode_runs_existing_candidate_without_mutating_manifest(
    tmp_path: Path, monkeypatch
) -> None:
    _env(tmp_path, monkeypatch)
    candidate = _generated_candidate(tmp_path)
    source_manifest_hash = (candidate / "manifest.json").read_bytes()
    inputs = tmp_path / "runtime-inputs.json"
    inputs.write_text(
        json.dumps({"inputs": {"ticket_text": "Server is down for all users"}}),
        encoding="utf-8",
    )
    outdir = tmp_path / "runtime-episode"

    payload = run_program_runtime_episode(
        manifest_path=candidate / "manifest.json",
        inputs_path=inputs,
        outdir=outdir,
    )

    assert payload["schema_version"] == "program-runtime-episode-workflow-v1"
    assert payload["status"] == "ok"
    assert payload["effect"]["candidate_manifest_mutated"] is False
    assert payload["effect"]["shared_oracle_mutated"] is False
    assert payload["steps"]["runtime_execution"]["status"] == "executed"
    assert (candidate / "manifest.json").read_bytes() == source_manifest_hash

    behavior = json.loads((outdir / "behavior_results.json").read_text())
    assert behavior["schema_version"] == "program-behavior-results-v1"
    assert behavior["summary"]["status"] == "executed"
    assert behavior["examples"][0]["observed_outputs"]["urgency"]

    oracle_evidence = json.loads((outdir / "oracle_evidence.json").read_text())
    runtime_manifest = json.loads((outdir / "manifest.json").read_text())
    assert oracle_evidence["schema_version"] == "program-oracle-evidence-v1"
    assert (
        oracle_evidence["identity"]["candidate_id"]
        == runtime_manifest["candidate_assembly"]["candidate_id"]
    )
    assert (
        oracle_evidence["identity"]["episode_id"]
        == runtime_manifest["receipt_bundle"]["episode_id"]
    )
    assert (
        oracle_evidence["identity"]["runtime_episode_id"]
        == payload["runtime_episode_id"]
    )
    assert runtime_manifest["oracle_readability"]["path"] == "oracle_evidence.json"

    report = json.loads((outdir / "program_oracle_report.json").read_text())
    assert report["schema_version"] == "program-oracle-evidence-report-v1"
    assert report["status"] == "ok"
    assert report["total_records"] == 1
    index = CoordinateIndex(db_path=outdir / "oracle" / "coordinates.db")
    stats = index.stats()
    assert stats["total"] == 1
    assert stats["by_run_kind"]["program-oracle-evidence"] == 1
    with sqlite3.connect(outdir / "oracle" / "coordinates.db") as conn:
        run_id = conn.execute("SELECT run_id FROM coordinates").fetchone()[0]
    assert run_id == f"program-oracle-evidence:{payload['runtime_episode_id']}"


def test_program_runtime_episode_round_trips_explicit_pipeline_candidate(
    tmp_path: Path, monkeypatch
) -> None:
    _env(tmp_path, monkeypatch)
    candidate = _explicit_pipeline_candidate(tmp_path)
    inputs = tmp_path / "pipeline-runtime-inputs.json"
    inputs.write_text(
        json.dumps({"inputs": {"ticket_text": "Billing invoice is wrong"}}),
        encoding="utf-8",
    )

    payload = run_program_runtime_episode(
        manifest_path=candidate / "manifest.json",
        inputs_path=inputs,
        outdir=tmp_path / "pipeline-runtime-episode",
        skip_oracle_index=True,
    )

    assert payload["status"] == "ok"
    assert payload["steps"]["runtime_execution"]["status"] == "executed"
    behavior = json.loads(
        (tmp_path / "pipeline-runtime-episode" / "behavior_results.json").read_text(
            encoding="utf-8"
        )
    )
    assert behavior["summary"]["status"] == "executed"
    assert behavior["examples"][0]["observed_outputs"]["response"]


def test_pdf_review_runtime_cannot_hide_declared_quality_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _env(tmp_path, monkeypatch)
    outputs = [
        "section_units_json",
        "distillation_frames_json",
        "evidence_cards_json",
        "merge_create_proposals_json",
        "review_packet_json",
        "artifact_contract_manifest_json",
    ]
    stub_response = {
        "section_units_json": "[]",
        "distillation_frames_json": "[]",
        "evidence_cards_json": "[]",
        "merge_create_proposals_json": "[]",
        "review_packet_json": json.dumps({"canonical_mutation_performed": False}),
        "artifact_contract_manifest_json": json.dumps(
            {"canonical_mutation_performed": False}
        ),
    }
    monkeypatch.setenv("DSPX_STUB_RESPONSE_JSON", json.dumps(stub_response))
    artifact = materialize_program_from_intent(
        ProgramIntent(
            name="PdfReviewQualityProgram",
            objective="Produce review-only PDF transition evidence.",
            inputs=["document"],
            outputs=outputs,
            examples=[
                {
                    "inputs": {"document": "bounded source"},
                    "outputs": stub_response,
                }
            ],
            quality_criteria=[
                {
                    "id": "review_quality",
                    "output_field": "review_packet_json",
                    "evaluator": "concept_coverage",
                    "required_concept_groups": [["quality-pass-token"]],
                    "forbidden_concepts": [],
                    "min_score": 1.0,
                }
            ],
        ),
        outdir=tmp_path / "pdf-quality-candidate",
    )
    inputs = tmp_path / "pdf-inputs.json"
    inputs.write_text(json.dumps({"inputs": {"document": "bounded source"}}))

    result = run_program_runtime_episode(
        manifest_path=Path(artifact.root_path) / "manifest.json",
        inputs_path=inputs,
        outdir=tmp_path / "pdf-quality-runtime",
        contract_mode="pdf_transition_review",
        skip_oracle_index=True,
    )
    behavior = json.loads(
        (tmp_path / "pdf-quality-runtime/behavior_results.json").read_text()
    )

    assert behavior["execution_status"] == "executed_valid_review_only"
    assert behavior["quality_evaluation"]["status"] == "failed"
    assert behavior["summary"]["status"] == "failed_quality"
    assert result["steps"]["runtime_execution"]["status"] == "failed_quality"
    assert result["status"] == "degraded"

    candidate_manifest_path = Path(artifact.root_path) / "manifest.json"
    candidate_manifest = json.loads(candidate_manifest_path.read_text())
    bundle = load_validated_program_runtime_episode_bundle(
        runtime_episode_path=tmp_path / "pdf-quality-runtime/runtime_episode.json",
        expected_manifest_path=candidate_manifest_path,
        expected_manifest=candidate_manifest,
        expected_manifest_sha256=hashlib.sha256(
            candidate_manifest_path.read_bytes()
        ).hexdigest(),
    )
    assert bundle.runtime_episode["status"] == "failed_quality"
    assert bundle.behavior_results["execution_status"] == "executed_valid_review_only"

    index_path = tmp_path / "pdf-quality-oracle/coordinates.db"
    indexed = index_program_oracle_evidence_path(
        tmp_path / "pdf-quality-runtime/oracle_evidence.json",
        index_path=index_path,
    )
    assert indexed["indexed"] == 1
    report = build_program_oracle_evidence_report(index_path=index_path)
    assert report["behavior_status_counts"]["failed"] == 1
    assert report["records"][0]["behavior_status"] == "failed"

    drift_root = tmp_path / "drifted-oracle"
    drift_root.mkdir()
    drifted_oracle = json.loads(
        (tmp_path / "pdf-quality-runtime/oracle_evidence.json").read_text()
    )
    drifted_oracle["oracle_facets"]["behavior_status"] = "executed_valid_review_only"
    (drift_root / "oracle_evidence.json").write_text(json.dumps(drifted_oracle))
    drifted = index_program_oracle_evidence_path(
        drift_root, index_path=tmp_path / "drifted-oracle.db"
    )
    assert drifted["indexed"] == 0
    assert drifted["errors"] == 1
    assert "behavior status drifts" in drifted["error_details"][0]["error"]


def test_program_runtime_episode_applies_declared_quality_without_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _env(tmp_path, monkeypatch)
    artifact = materialize_program_from_intent(
        ProgramIntent(
            name="CalibratedRuntimeProgram",
            objective="Produce a calibrated failure statement.",
            inputs=["observation"],
            outputs=["response"],
            quality_criteria=[
                {
                    "id": "calibrated_response",
                    "output_field": "response",
                    "evaluator": "concept_coverage",
                    "required_concept_groups": [
                        ["failure", "failed"],
                        ["unknown", "undetermined"],
                        ["investigate", "investigation"],
                    ],
                    "forbidden_concepts": ["definitely caused"],
                    "min_score": 1.0,
                }
            ],
        ),
        outdir=tmp_path / "quality-candidate",
    )
    candidate = Path(artifact.root_path)
    inputs = tmp_path / "quality-inputs.json"
    inputs.write_text(
        json.dumps({"inputs": {"observation": "one test failed"}}),
        encoding="utf-8",
    )

    monkeypatch.setenv(
        "DSPX_STUB_RESPONSE_JSON",
        json.dumps(
            {
                "reasoning": "bounded evidence",
                "response": "One test failed; the cause is undetermined and needs investigation.",
            }
        ),
    )
    passed = run_program_runtime_episode(
        manifest_path=candidate / "manifest.json",
        inputs_path=inputs,
        outdir=tmp_path / "quality-pass",
        skip_oracle_index=True,
    )
    passed_behavior = json.loads(
        (tmp_path / "quality-pass/behavior_results.json").read_text()
    )
    assert passed["steps"]["runtime_execution"]["status"] == "executed_quality_passed"
    assert passed["status"] == "ok"
    assert passed_behavior["quality_evaluation"]["status"] == "passed"
    assert passed_behavior["quality_evaluation"]["quality_approved"] is False
    passed_oracle = json.loads(
        (tmp_path / "quality-pass/oracle_evidence.json").read_text()
    )
    assert passed_oracle["behavior"]["failure_modes"] == []

    monkeypatch.setenv(
        "DSPX_STUB_RESPONSE_JSON",
        json.dumps(
            {
                "reasoning": "overclaim",
                "response": "One failure has an unknown cause and needs investigation, but it was definitely caused by deployment.",
            }
        ),
    )
    failed = run_program_runtime_episode(
        manifest_path=candidate / "manifest.json",
        inputs_path=inputs,
        outdir=tmp_path / "quality-fail",
        skip_oracle_index=True,
    )
    failed_behavior = json.loads(
        (tmp_path / "quality-fail/behavior_results.json").read_text()
    )
    assert failed["steps"]["runtime_execution"]["status"] == "failed_quality"
    assert failed["status"] == "degraded"
    assert failed_behavior["quality_evaluation"]["status"] == "failed"
    assert failed_behavior["quality_evaluation"]["criteria"][0]["forbidden_hits"] == [
        "definitely caused"
    ]

    monkeypatch.setenv(
        "DSPX_STUB_RESPONSE_JSON",
        json.dumps({"reasoning": "missing declared response"}),
    )
    errored = run_program_runtime_episode(
        manifest_path=candidate / "manifest.json",
        inputs_path=inputs,
        outdir=tmp_path / "quality-error",
        skip_oracle_index=True,
    )
    error_episode_path = tmp_path / "quality-error/runtime_episode.json"
    error_episode = json.loads(error_episode_path.read_text())
    source_manifest = json.loads((candidate / "manifest.json").read_text())
    assert errored["steps"]["runtime_execution"]["status"] == "error"
    assert error_episode["execution_status"] == "error"
    validate_program_runtime_episode_contract(
        error_episode,
        runtime_episode_path=error_episode_path,
        expected_manifest_path=candidate / "manifest.json",
        expected_manifest=source_manifest,
        expected_manifest_sha256=hashlib.sha256(
            (candidate / "manifest.json").read_bytes()
        ).hexdigest(),
    )

    pass_root = tmp_path / "quality-pass"
    behavior_path = pass_root / "behavior_results.json"
    behavior_payload = json.loads(behavior_path.read_text())
    behavior_payload["intent"]["quality_criteria"] = []
    not_declared = {
        "schema_version": "program-quality-evaluation-v1",
        "status": "not_declared",
        "criteria_total": 0,
        "criteria_passed": 0,
        "criteria_failed": 0,
        "criteria": [],
        "quality_approved": False,
    }
    behavior_payload["quality_evaluation"] = not_declared
    behavior_payload["examples"][0]["quality_evaluation"] = not_declared
    behavior_payload["examples"][0]["status"] = "executed"
    behavior_payload["summary"] = {
        "total": 1,
        "passed": 0,
        "failed": 0,
        "error": 0,
        "degraded": 0,
        "executed": 1,
        "status_counts": {"executed": 1},
        "status": "executed",
    }
    behavior_path.write_text(
        json.dumps(behavior_payload, indent=2, sort_keys=True) + "\n"
    )
    behavior_hash = hashlib.sha256(behavior_path.read_bytes()).hexdigest()
    traces_path = pass_root / "program_runtime_traces.json"
    traces = json.loads(traces_path.read_text())
    for source in traces["sources"]:
        if source["path"] == "behavior_results.json":
            source["content_hash"] = behavior_hash
    traces_path.write_text(json.dumps(traces, indent=2, sort_keys=True) + "\n")
    traces_hash = hashlib.sha256(traces_path.read_bytes()).hexdigest()
    oracle_path = pass_root / "oracle_evidence.json"
    oracle = json.loads(oracle_path.read_text())
    oracle["behavior"]["result_hash"] = behavior_hash
    for source in oracle["source_artifacts"]:
        if source["path"] == "behavior_results.json":
            source["content_hash"] = behavior_hash
        if source["path"] == "program_runtime_traces.json":
            source["content_hash"] = traces_hash
    oracle_path.write_text(json.dumps(oracle, indent=2, sort_keys=True) + "\n")
    oracle_hash = hashlib.sha256(oracle_path.read_bytes()).hexdigest()
    runtime_manifest_path = pass_root / "manifest.json"
    runtime_manifest = json.loads(runtime_manifest_path.read_text())
    runtime_manifest["runtime_episode"]["behavior_results_sha256"] = behavior_hash
    runtime_manifest_path.write_text(
        json.dumps(runtime_manifest, indent=2, sort_keys=True) + "\n"
    )
    episode_path = pass_root / "runtime_episode.json"
    episode = json.loads(episode_path.read_text())
    episode["status"] = "executed"
    episode["artifact_hashes"]["behavior_results_sha256"] = behavior_hash
    episode["artifact_hashes"]["program_runtime_traces_sha256"] = traces_hash
    episode["artifact_hashes"]["oracle_evidence_sha256"] = oracle_hash
    episode_path.write_text(json.dumps(episode, indent=2, sort_keys=True) + "\n")
    source_manifest = json.loads((candidate / "manifest.json").read_text())
    with pytest.raises(ValueError, match="quality criteria drift"):
        validate_program_runtime_episode_contract(
            episode,
            runtime_episode_path=episode_path,
            expected_manifest_path=candidate / "manifest.json",
            expected_manifest=source_manifest,
            expected_manifest_sha256=hashlib.sha256(
                (candidate / "manifest.json").read_bytes()
            ).hexdigest(),
        )


def test_program_runtime_episode_can_write_shared_publication_preflight(
    tmp_path: Path, monkeypatch
) -> None:
    _env(tmp_path, monkeypatch)
    candidate = _generated_candidate(tmp_path)
    inputs = tmp_path / "runtime-inputs.json"
    inputs.write_text(
        json.dumps({"ticket_text": "Server is down for all users"}), encoding="utf-8"
    )
    preflight = tmp_path / "runtime-episode" / "publication-preflight.json"

    payload = run_program_runtime_episode(
        manifest_path=candidate / "manifest.json",
        inputs_path=inputs,
        outdir=tmp_path / "runtime-episode",
        publication_preflight_out=preflight,
        publication_target="shared-postgres",
        publication_label="retained",
        publisher_id="pi-test",
        publisher_role="operator",
        publisher_assertion="share checked runtime behavior evidence for future Oracle retrieval",
        redaction_status="checked",
        retention_class="retained_behavior_memory",
    )

    assert payload["effect"]["oracle_publication_preflight_written"] is True
    packet = json.loads(preflight.read_text())
    assert packet["schema_version"] == "program-oracle-shared-publication-preflight-v1"
    assert packet["status"] == "ready_not_published"
    assert packet["preflight"]["identity_matches_manifest"] is True
    assert packet["effect"]["shared_oracle_mutated"] is False


def test_program_runtime_episode_preflight_args_fail_before_writing_artifacts(
    tmp_path: Path, monkeypatch
) -> None:
    _env(tmp_path, monkeypatch)
    candidate = _generated_candidate(tmp_path)
    inputs = tmp_path / "runtime-inputs.json"
    inputs.write_text(
        json.dumps({"ticket_text": "Server is down for all users"}), encoding="utf-8"
    )
    runtime_dir = tmp_path / "runtime-episode"

    with pytest.raises(ValueError, match="publication preflight requires"):
        run_program_runtime_episode(
            manifest_path=candidate / "manifest.json",
            inputs_path=inputs,
            outdir=runtime_dir,
            publication_preflight_out=runtime_dir / "publication-preflight.json",
        )

    assert not runtime_dir.exists()


def test_program_runtime_episode_rejects_tampered_candidate_surface(
    tmp_path: Path, monkeypatch
) -> None:
    _env(tmp_path, monkeypatch)
    candidate = _generated_candidate(tmp_path)
    program_path = candidate / "program.py"
    program_path.write_text(
        program_path.read_text(encoding="utf-8")
        + "\n# tampered after manifest write\n",
        encoding="utf-8",
    )
    inputs = tmp_path / "runtime-inputs.json"
    inputs.write_text(
        json.dumps({"inputs": {"ticket_text": "Server is down for all users"}}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="program.py"):
        run_program_runtime_episode(
            manifest_path=candidate / "manifest.json",
            inputs_path=inputs,
            outdir=tmp_path / "runtime-episode",
        )


def test_generated_program_module_rejects_program_class_body_side_effects(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "marker.txt"
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "program.py").write_text(
        "from pathlib import Path\n"
        "import dspy\n"
        "class UnsafeProgram(dspy.Module):\n"
        f"    marker = Path({str(marker)!r}).touch()\n"
        "def io_spec():\n"
        "    return {'inputs': [], 'outputs': []}\n"
        "def intent_summary():\n"
        "    return {}\n"
        "def build_program():\n"
        "    return UnsafeProgram()\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="program.py"):
        with _generated_program_module(candidate):
            pass

    assert not marker.exists()


def test_generated_program_module_rejects_program_class_method_side_effects(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "marker.txt"
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "program.py").write_text(
        "from pathlib import Path\n"
        "import dspy\n"
        "class UnsafeProgram(dspy.Module):\n"
        "    def __init__(self):\n"
        f"        Path({str(marker)!r}).touch()\n"
        "def io_spec():\n"
        "    return {'inputs': [], 'outputs': []}\n"
        "def intent_summary():\n"
        "    return {}\n"
        "def build_program():\n"
        "    return UnsafeProgram()\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="touch"):
        with _generated_program_module(candidate):
            pass

    assert not marker.exists()


@pytest.mark.parametrize("method_expr", ["'touch'", "method"])
def test_generated_program_module_rejects_dynamic_lookup_side_effects(
    tmp_path: Path, method_expr: str
) -> None:
    marker = tmp_path / "marker.txt"
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "program.py").write_text(
        "from pathlib import Path\n"
        "import dspy\n"
        "def io_spec():\n"
        "    return {'inputs': [], 'outputs': []}\n"
        "def intent_summary():\n"
        "    return {}\n"
        "def build_program():\n"
        "    method = 'touch'\n"
        f"    f = getattr(Path({str(marker)!r}), {method_expr})\n"
        "    f()\n"
        "    return lambda **kwargs: {}\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="getattr"):
        with _generated_program_module(candidate):
            pass

    assert not marker.exists()


def test_runtime_observed_output_files_reject_path_escape(tmp_path: Path) -> None:
    from dspx.services.program_runtime_episode import _write_observed_output_files

    outdir = tmp_path / "out"
    outdir.mkdir()

    with pytest.raises(ValueError, match="unsafe path component|escapes"):
        _write_observed_output_files(outdir, {"../escape.json": {"ok": True}})

    assert not (tmp_path / "escape.json").exists()


@pytest.mark.parametrize(
    "field_name",
    ["behavior_results.json", "nested/manifest.json", "runtime_episode.json"],
)
def test_runtime_observed_output_files_reject_protected_artifact_names(
    tmp_path: Path, field_name: str
) -> None:
    from dspx.services.program_runtime_episode import _write_observed_output_files

    outdir = tmp_path / "out"
    outdir.mkdir()

    with pytest.raises(ValueError, match="protected artifact"):
        _write_observed_output_files(outdir, {field_name: {"spoofed": True}})

    assert not (outdir / field_name).exists()


def test_generated_program_module_rejects_import_time_side_effects(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "marker.txt"
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "program.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('ran')\n"
        "def io_spec():\n"
        "    return {'inputs': [], 'outputs': []}\n"
        "def intent_summary():\n"
        "    return {}\n"
        "def build_program():\n"
        "    return lambda **kwargs: {}\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError, match="generated program surface safety policy failed"
    ):
        with _generated_program_module(candidate):
            pass

    assert not marker.exists()


def test_generated_program_module_rejects_sibling_import_time_side_effects(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "marker.txt"
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "program.py").write_text(
        "from module import io_spec\n"
        "def intent_summary():\n"
        "    return {}\n"
        "def build_program():\n"
        "    return lambda **kwargs: {}\n",
        encoding="utf-8",
    )
    (candidate / "module.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('ran')\n"
        "def io_spec():\n"
        "    return {'inputs': [], 'outputs': []}\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="module.py"):
        with _generated_program_module(candidate):
            pass

    assert not marker.exists()


def test_generated_program_module_rejects_class_body_side_effects(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "marker.txt"
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "program.py").write_text(
        "from module import io_spec\n"
        "def intent_summary():\n"
        "    return {}\n"
        "def build_program():\n"
        "    return lambda **kwargs: {}\n",
        encoding="utf-8",
    )
    (candidate / "module.py").write_text(
        "from pathlib import Path\n"
        "class Unsafe:\n"
        f"    marker = Path({str(marker)!r}).touch()\n"
        "def io_spec():\n"
        "    return {'inputs': [], 'outputs': []}\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="class body"):
        with _generated_program_module(candidate):
            pass

    assert not marker.exists()


def test_generated_program_module_rejects_import_time_assignment_targets(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "marker.txt"
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "program.py").write_text(
        "from module import io_spec\n"
        "def intent_summary():\n"
        "    return {}\n"
        "def build_program():\n"
        "    return lambda **kwargs: {}\n",
        encoding="utf-8",
    )
    (candidate / "module.py").write_text(
        "from pathlib import Path\n"
        "x = {}\n"
        f"x[Path({str(marker)!r}).touch()] = 1\n"
        "def io_spec():\n"
        "    return {'inputs': [], 'outputs': []}\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="assignment target is not import-safe"):
        with _generated_program_module(candidate):
            pass

    assert not marker.exists()


def test_generated_program_module_rejects_import_time_header_expressions(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "marker.txt"
    cases = {
        "decorator": "@Path({marker!r}).touch()\ndef io_spec():\n    return {{'inputs': [], 'outputs': []}}\n",
        "default": "def io_spec(x=Path({marker!r}).touch()):\n    return {{'inputs': [], 'outputs': []}}\n",
        "annotation": "def io_spec(x: Path({marker!r}).touch()):\n    return {{'inputs': [], 'outputs': []}}\n",
        "string_annotation": "def io_spec(x: \"Path({marker!r}).touch()\"):\n    return {{'inputs': [], 'outputs': []}}\n",
        "base": "class Unsafe(Path({marker!r}).touch()):\n    pass\ndef io_spec():\n    return {{'inputs': [], 'outputs': []}}\n",
    }
    for name, module_template in cases.items():
        candidate = tmp_path / name
        candidate.mkdir()
        (candidate / "program.py").write_text(
            "from module import io_spec\n"
            "def intent_summary():\n"
            "    return {}\n"
            "def build_program():\n"
            "    return lambda **kwargs: {}\n",
            encoding="utf-8",
        )
        (candidate / "module.py").write_text(
            "from pathlib import Path\n" + module_template.format(marker=str(marker)),
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match="import-safe|literal|class bases"):
            with _generated_program_module(candidate):
                pass

    assert not marker.exists()


def test_generated_program_module_rejects_missing_sibling_import(
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "program.py").write_text(
        "from module import io_spec\n"
        "def intent_summary():\n"
        "    return {}\n"
        "def build_program():\n"
        "    return lambda **kwargs: {}\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="module.py is missing"):
        with _generated_program_module(candidate):
            pass


def test_generated_program_module_rejects_sibling_package_shadowing(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "marker.txt"
    candidate = tmp_path / "candidate"
    module_dir = candidate / "module"
    module_dir.mkdir(parents=True)
    (module_dir / "__init__.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n",
        encoding="utf-8",
    )
    (candidate / "program.py").write_text(
        "from module import io_spec\n"
        "def intent_summary():\n"
        "    return {}\n"
        "def build_program():\n"
        "    return lambda **kwargs: {}\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="shadows generated sibling module file"):
        with _generated_program_module(candidate):
            pass

    assert not marker.exists()


def test_generated_program_module_rejects_external_import_shadowing(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "marker.txt"
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "dspy.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n",
        encoding="utf-8",
    )
    (candidate / "program.py").write_text(
        "import dspy\n"
        "def io_spec():\n"
        "    return {'inputs': [], 'outputs': []}\n"
        "def intent_summary():\n"
        "    return {}\n"
        "def build_program():\n"
        "    return lambda **kwargs: {}\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="shadows allowed external import root"):
        with _generated_program_module(candidate):
            pass

    assert not marker.exists()


def test_generated_program_module_allows_signature_sibling_import(
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "signature.py").write_text(
        "import dspy\n"
        "class DemoSignature(dspy.Signature):\n"
        "    text: str = dspy.InputField()\n"
        "    answer: str = dspy.OutputField()\n",
        encoding="utf-8",
    )
    (candidate / "module.py").write_text(
        "from signature import DemoSignature\n"
        "def io_spec():\n"
        "    return {'inputs': ['text'], 'outputs': ['answer']}\n",
        encoding="utf-8",
    )
    (candidate / "program.py").write_text(
        "from module import io_spec\n"
        "def intent_summary():\n"
        "    return {}\n"
        "def build_program():\n"
        "    return lambda **kwargs: {}\n",
        encoding="utf-8",
    )

    with _generated_program_module(candidate) as module:
        assert module.io_spec()["outputs"] == ["answer"]


def test_runtime_input_materialization_converts_image_file_descriptors(
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "ref.png"
    image_path.write_bytes(
        bytes.fromhex(
            "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de0000000c49444154789c63f8cfc00000030101c9fe92ef0000000049454e44ae426082"
        )
    )
    inputs_path = tmp_path / "runtime-inputs.json"
    inputs_path.write_text("{}\n", encoding="utf-8")

    materialized = _materialize_runtime_inputs(
        {
            "visual_image_blocks": [
                {"type": "image_file", "path": "ref.png"},
                {
                    "type": "image_url",
                    "url": "data:image/png;base64,iVBORw0KGgo=",
                },
            ],
            "text": "unchanged",
        },
        inputs_path=inputs_path,
    )

    assert materialized["text"] == "unchanged"
    visual_image_blocks = materialized["visual_image_blocks"]
    assert isinstance(visual_image_blocks, str)
    assert visual_image_blocks.count("CUSTOM-TYPE-START-IDENTIFIER") == 2
    assert "image_url" in visual_image_blocks


def test_runtime_input_materialization_rejects_remote_image_url(
    tmp_path: Path,
) -> None:
    inputs_path = tmp_path / "runtime-inputs.json"
    inputs_path.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="only accepts data:image"):
        _materialize_runtime_inputs(
            {
                "visual_image_blocks": [
                    {
                        "type": "image_url",
                        "url": "http://169.254.169.254/latest/meta-data/",
                    }
                ]
            },
            inputs_path=inputs_path,
        )


def test_runtime_input_materialization_rejects_absolute_image_path_outside_inputs(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    image_path = outside / "ref.png"
    image_path.write_bytes(
        bytes.fromhex(
            "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de0000000c49444154789c63f8cfc00000030101c9fe92ef0000000049454e44ae426082"
        )
    )
    input_dir = tmp_path / "inputs"
    input_dir.mkdir()
    inputs_path = input_dir / "runtime-inputs.json"
    inputs_path.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Path escapes confinement root"):
        _materialize_runtime_inputs(
            {"image": {"type": "image_file", "path": str(image_path)}},
            inputs_path=inputs_path,
        )


def test_program_runtime_episode_redacts_provider_diagnostics(
    tmp_path: Path, monkeypatch
) -> None:
    _env(tmp_path, monkeypatch)
    candidate = _generated_candidate(tmp_path)
    secret_message = (
        "provider failed api_key=supersecret-value Authorization: Bearer bearer-secret "
        "https://user:pass@example.test/run?token=url-secret&ok=1"
    )

    from dspx import provider_registry

    def raise_secret_provider(*args, **kwargs):
        raise RuntimeError(secret_message)

    monkeypatch.setattr(provider_registry, "create_from_env", raise_secret_provider)
    inputs = tmp_path / "runtime-inputs.json"
    inputs.write_text(
        json.dumps({"inputs": {"ticket_text": "Server is down for all users"}}),
        encoding="utf-8",
    )
    outdir = tmp_path / "runtime-redacted"

    payload = run_program_runtime_episode(
        manifest_path=candidate / "manifest.json",
        inputs_path=inputs,
        outdir=outdir,
        skip_oracle_index=True,
    )

    assert payload["status"] in {"ok", "degraded"}
    behavior = json.loads((outdir / "behavior_results.json").read_text())
    combined = json.dumps({"payload": payload, "behavior": behavior}, sort_keys=True)
    assert "supersecret-value" not in combined
    assert "bearer-secret" not in combined
    assert "url-secret" not in combined
    assert "user:pass@" not in combined
    assert "api_key=[REDACTED]" in combined
    assert "Bearer [REDACTED]" in combined
    assert "token=[REDACTED]" in combined
    assert (
        behavior["provider"]["error"]["message"]
        == payload["steps"]["runtime_execution"]["provider"]["error"]["message"]
    )


def test_runtime_episode_validator_accepts_producer_failure_statuses(
    tmp_path: Path, monkeypatch
) -> None:
    _env(tmp_path, monkeypatch)
    candidate = _generated_candidate(tmp_path)
    inputs = tmp_path / "runtime-inputs.json"
    inputs.write_text(
        json.dumps({"inputs": {"ticket_text": "Server is down for all users"}}),
        encoding="utf-8",
    )
    outdir = tmp_path / "runtime-statuses"
    run_program_runtime_episode(
        manifest_path=candidate / "manifest.json",
        inputs_path=inputs,
        outdir=outdir,
        skip_oracle_index=True,
    )
    episode_path = outdir / "runtime_episode.json"
    base_episode = json.loads(episode_path.read_text(encoding="utf-8"))
    manifest = json.loads((candidate / "manifest.json").read_text(encoding="utf-8"))
    manifest_hash = base_episode["artifact_hashes"]["source_manifest_sha256"]

    for status in ("degraded_missing_outputs", "failed_boundary"):
        episode = {**base_episode, "status": status}
        validate_program_runtime_episode_contract(
            episode,
            runtime_episode_path=episode_path,
            expected_manifest_path=candidate / "manifest.json",
            expected_manifest=manifest,
            expected_manifest_sha256=manifest_hash,
        )


def test_runtime_episode_provider_configuration_failure_does_not_import_program(
    tmp_path: Path, monkeypatch
) -> None:
    _env(tmp_path, monkeypatch)
    candidate = _generated_candidate(tmp_path)

    from dspx import provider_registry

    def raise_provider(*args, **kwargs):
        raise RuntimeError("no provider")

    monkeypatch.setattr(provider_registry, "create_from_env", raise_provider)
    imported_program: list[bool] = []

    def fail_if_imported(*args, **kwargs):
        imported_program.append(True)
        raise AssertionError("program module should not load without provider")

    monkeypatch.setattr(
        runtime_episode_service,
        "_generated_program_module",
        fail_if_imported,
    )
    inputs = tmp_path / "runtime-inputs.json"
    inputs.write_text(
        json.dumps({"inputs": {"ticket_text": "Server is down for all users"}}),
        encoding="utf-8",
    )
    outdir = tmp_path / "runtime-provider-failed"

    payload = run_program_runtime_episode(
        manifest_path=candidate / "manifest.json",
        inputs_path=inputs,
        outdir=outdir,
        skip_oracle_index=True,
    )

    behavior = json.loads((outdir / "behavior_results.json").read_text())
    assert imported_program == []
    assert payload["status"] == "degraded"
    assert payload["steps"]["runtime_execution"]["status"] == "error"
    assert behavior["provider"]["status"] == "unavailable"
    assert behavior["examples"][0]["observed_outputs"] == {}


def test_quality_runtime_provider_failure_remains_final_consumer_valid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _env(tmp_path, monkeypatch)
    artifact = materialize_program_from_intent(
        ProgramIntent(
            name="QualityProviderFailureProgram",
            objective="Return calibrated evidence.",
            inputs=["question"],
            outputs=["answer"],
            quality_criteria=[
                {
                    "id": "answer_evidence",
                    "output_field": "answer",
                    "evaluator": "concept_coverage",
                    "required_concept_groups": [["evidence"]],
                    "forbidden_concepts": ["approved"],
                    "min_score": 1.0,
                }
            ],
        ),
        outdir=tmp_path / "quality-provider-candidate",
    )
    candidate = Path(artifact.root_path)
    from dspx import provider_registry

    def raise_provider(*args, **kwargs):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(provider_registry, "create_from_env", raise_provider)
    inputs = tmp_path / "quality-provider-inputs.json"
    inputs.write_text('{"inputs":{"question":"what happened?"}}')
    outdir = tmp_path / "quality-provider-runtime"
    run_program_runtime_episode(
        manifest_path=candidate / "manifest.json",
        inputs_path=inputs,
        outdir=outdir,
        skip_oracle_index=True,
    )
    episode_path = outdir / "runtime_episode.json"
    episode = json.loads(episode_path.read_text())
    manifest = json.loads((candidate / "manifest.json").read_text())

    assert episode["status"] == "error"
    assert episode["execution_status"] == "error"
    validate_program_runtime_episode_contract(
        episode,
        runtime_episode_path=episode_path,
        expected_manifest_path=candidate / "manifest.json",
        expected_manifest=manifest,
        expected_manifest_sha256=hashlib.sha256(
            (candidate / "manifest.json").read_bytes()
        ).hexdigest(),
    )


def test_program_run_cli_help_describes_inputs_as_file_path() -> None:
    result = runner.invoke(app, ["program-run", "--help"])

    assert result.exit_code == 0, result.output
    assert "Path to a JSON file" in result.output
    assert "--capture-replay-fixture" in result.output


def test_program_run_cli(tmp_path: Path, monkeypatch) -> None:
    _env(tmp_path, monkeypatch)
    candidate = _generated_candidate(tmp_path)
    inputs = tmp_path / "runtime-inputs.json"
    inputs.write_text(
        json.dumps({"inputs": {"ticket_text": "Server is down for all users"}}),
        encoding="utf-8",
    )
    outdir = tmp_path / "runtime-cli"

    result = runner.invoke(
        app,
        [
            "program-run",
            "--manifest",
            str(candidate / "manifest.json"),
            "--inputs",
            str(inputs),
            "--outdir",
            str(outdir),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["runtime_root"] == str(outdir)
    assert payload["steps"]["runtime_execution"]["status"] == "executed"
    assert payload["steps"]["runtime_receipt"]["status"] == "written"
    assert payload["steps"]["runtime_receipt"]["execution_replay_supported"] is False
    assert (outdir / "runtime_episode.json.meta.json").is_file()
    assert (outdir / "oracle" / "coordinates.db").exists()
