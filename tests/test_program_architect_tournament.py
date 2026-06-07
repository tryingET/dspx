from __future__ import annotations

import json
from pathlib import Path

import pytest

from dspx.cli.dspx import app
from dspx.services.program_architecture import (
    build_program_architecture_candidates,
)
from dspx.services.program_architecture_tournament import (
    run_program_architecture_tournament,
)
from dspx.services.program_intent import ProgramIntent
from dspx.services.run_replay_service import check_run_receipt
from program_architecture_shared import (
    _write_intent,
    runner,
)


@pytest.mark.slow
def test_program_architect_tournament_materializes_plan_candidates_locally(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    intent_path = tmp_path / "intent.yaml"
    plan_path = tmp_path / "architecture_plan.json"
    tournament_outdir = tmp_path / "tournament"
    tournament_out = tmp_path / "tournament.json"
    _write_intent(
        intent_path,
        "Route support tickets by classifying billing versus technical issues, then draft a helpful response with rationale.",
        examples=True,
    )
    plan_result = runner.invoke(
        app,
        [
            "program-architect",
            "plan",
            "--intent",
            str(intent_path),
            "--out",
            str(plan_path),
        ],
    )
    assert plan_result.exit_code == 0, plan_result.output

    result = runner.invoke(
        app,
        [
            "program-architect",
            "tournament",
            "--architecture-plan",
            str(plan_path),
            "--outdir",
            str(tournament_outdir),
            "--out",
            str(tournament_out),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    stdout_payload = json.loads(result.output)
    sidecar = json.loads(tournament_out.read_text(encoding="utf-8"))
    assert stdout_payload == sidecar
    assert sidecar["schema_version"] == "program-architecture-tournament-v1"
    assert sidecar["status"] == "materialized_and_replay_checked"
    assert sidecar["materialized_candidate_count"] == 2
    assert sidecar["interpretation"]["replay_ok_count"] == 2
    assert sidecar["effect"]["candidate_programs_materialized"] is True
    assert sidecar["effect"]["receipts_replay_checked"] is True
    assert sidecar["effect"]["winner_selected"] is False
    assert sidecar["effect"]["promotion_applied"] is False
    assert sidecar["effect"]["oracle_index_mutated"] is False
    assert sidecar["effect"]["ak_called"] is False
    assert sidecar["non_authority"]["winner_selection"] is False
    matrix = sidecar["evidence_matrix"]
    assert matrix["schema_version"] == (
        "program-architecture-tournament-evidence-matrix-v1"
    )
    assert matrix["source_kind_counts"] == {"inline_examples": 2}
    assert matrix["non_authority"]["raw_examples_included"] is False
    assert matrix["non_authority"]["winner_selection"] is False
    assert [row["candidate_id"] for row in matrix["rows"]] == [
        "baseline_single_predict",
        "prompt_inferred_pipeline",
    ]
    for row in matrix["rows"]:
        assert row["replay_status"] == "ok"
        assert row["behavior_summary"]["total"] == 1
        assert row["behavior_sources"]["source_kinds"] == ["inline_examples"]
        assert row["artifacts"]["behavior_results"]["exists"] is True
        assert row["artifacts"]["behavior_episode"]["exists"] is True
        assert row["artifacts"]["oracle_evidence"]["exists"] is True
        assert row["artifacts"]["module_surfaces"]["exists"] is True
        assert row["artifacts"]["capability_registry"]["exists"] is True
        assert row["artifacts"]["generated_module_policy"]["exists"] is True
        assert row["non_authority"]["winner_selection"] is False
    assert [candidate["candidate_id"] for candidate in sidecar["candidates"]] == [
        "baseline_single_predict",
        "prompt_inferred_pipeline",
    ]
    for candidate in sidecar["candidates"]:
        root = Path(candidate["root_path"])
        assert (root / "manifest.json").exists()
        assert (root / "manifest.json.meta.json").exists()
        assert (root / "program.py").exists()
        assert (root / "module_surfaces.json").exists()
        assert (root / "program_capability_registry.json").exists()
        assert (root / "generated_module_policy.json").exists()
        assert candidate["capability_registry_hash"]
        assert candidate["generated_module_policy_hash"]
        assert not (root / "oracle" / "coordinates.db").exists()
        assert not (root / "program_oracle_report.json").exists()
        assert candidate["replay_check"]["status"] == "ok"
        assert check_run_receipt(root / "manifest.json.meta.json")["status"] == "ok"


@pytest.mark.slow
def test_program_architect_tournament_with_oracle_reports_writes_candidate_local_reports(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "mock")
    intent_path = tmp_path / "intent.yaml"
    plan_path = tmp_path / "architecture_plan.json"
    tournament_outdir = tmp_path / "tournament"
    tournament_out = tmp_path / "tournament.json"
    _write_intent(
        intent_path,
        "Route support tickets by classifying billing versus technical issues, then draft a helpful response with rationale.",
        examples=True,
    )
    plan_result = runner.invoke(
        app,
        [
            "program-architect",
            "plan",
            "--intent",
            str(intent_path),
            "--out",
            str(plan_path),
        ],
    )
    assert plan_result.exit_code == 0, plan_result.output

    result = runner.invoke(
        app,
        [
            "program-architect",
            "tournament",
            "--architecture-plan",
            str(plan_path),
            "--outdir",
            str(tournament_outdir),
            "--out",
            str(tournament_out),
            "--candidate",
            "prompt_inferred_pipeline",
            "--with-oracle-reports",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(tournament_out.read_text())
    assert payload["effect"]["oracle_index_mutated"] is True
    assert payload["effect"]["oracle_index_scope"] == "candidate_local_explicit_paths"
    assert payload["effect"]["shared_oracle_mutated"] is False
    assert payload["effect"]["winner_selected"] is False
    materialized = next(
        candidate
        for candidate in payload["candidates"]
        if candidate["candidate_id"] == "prompt_inferred_pipeline"
    )
    root = Path(materialized["root_path"])
    assert (root / "oracle" / "coordinates.db").exists()
    report_path = root / "program_oracle_report.json"
    assert report_path.exists()
    report = json.loads(report_path.read_text())
    assert report["schema_version"] == "program-oracle-evidence-report-v1"
    assert report["total_records"] == 1
    assert report["non_authority"]["oracle_promotion"] is False
    assert (
        materialized["candidate_local_oracle"]["report_summary"]["total_records"] == 1
    )
    row = next(
        item
        for item in payload["evidence_matrix"]["rows"]
        if item["candidate_id"] == "prompt_inferred_pipeline"
    )
    assert row["artifacts"]["oracle_report"]["exists"] is True
    assert row["artifacts"]["oracle_index"]["exists"] is True
    assert row["oracle_readability"]["candidate_local_report_status"] == "ok"
    assert row["oracle_readability"]["candidate_local_report_records"] == 1
    skipped = next(
        candidate
        for candidate in payload["candidates"]
        if candidate["candidate_id"] == "baseline_single_predict"
    )
    assert skipped["status"] == "skipped"
    assert not (tournament_outdir / "candidates" / "baseline_single_predict").exists()


@pytest.mark.slow
def test_program_architect_tournament_materializes_declared_inline_retriever_candidate(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    plan = build_program_architecture_candidates(
        ProgramIntent(
            name="InlineRetrieverDeclaredProgram",
            objective="Retrieve local context for a question from an inline corpus.",
            inputs=["question"],
            outputs=["context"],
            topology={
                "kind": "pipeline",
                "execution_status": "declared_not_materialized",
                "modules": [
                    {
                        "id": "retrieve_context",
                        "primitive": "Retriever",
                        "signature": {
                            "name": "RetrieveContext",
                            "inputs": ["question"],
                            "outputs": ["context"],
                        },
                        "retriever": {
                            "mode": "inline_corpus",
                            "k": 1,
                            "documents": [
                                {
                                    "id": "refund_policy",
                                    "text": "Refunds are available for duplicate billing within 30 days.",
                                }
                            ],
                        },
                    }
                ],
                "edges": [
                    {"from": "input", "to": "retrieve_context"},
                    {"from": "retrieve_context", "to": "output"},
                ],
            },
        )
    )

    payload = run_program_architecture_tournament(
        architecture_plan=plan,
        outdir=tmp_path / "tournament",
        candidate_ids=["declared_pipeline"],
    )

    assert payload["materialized_candidate_count"] == 1
    assert payload["interpretation"]["replay_ok_count"] == 1
    assert payload["effect"]["candidate_programs_materialized"] is True
    assert payload["effect"]["oracle_index_mutated"] is False
    assert payload["effect"]["winner_selected"] is False
    assert payload["effect"]["promotion_applied"] is False
    materialized = next(
        candidate
        for candidate in payload["candidates"]
        if candidate["candidate_id"] == "declared_pipeline"
    )
    root = Path(materialized["root_path"])
    manifest = json.loads((root / "manifest.json").read_text())
    assert materialized["status"] == "replay_ok"
    assert materialized["replay_check"]["status"] == "ok"
    assert manifest["topology_execution"]["status"] == "pipeline_materialized"
    assert manifest["topology_execution"]["materialized"] is True
    scheduler_plan = manifest["program_plan"]["materialized_topology"]["scheduler_plan"]
    assert scheduler_plan["schema_version"] == "program-topology-scheduler-plan-v1"
    assert scheduler_plan["status"] == "deterministic_local_dag_schedule"
    assert scheduler_plan["module_order"] == ["retrieve_context"]
    assert scheduler_plan["output_producers"] == ["retrieve_context"]
    assert scheduler_plan["effect"]["retriever_called"] is False
    assert (root / "program_capability_registry.json").exists()
    capability_registry = json.loads(
        (root / "program_capability_registry.json").read_text()
    )
    retriever_ref = next(
        ref
        for ref in capability_registry["used_capability_refs"]
        if ref["primitive"] == "Retriever"
    )
    assert retriever_ref["runtime_binding"] == (
        "generated_bounded_inline_retriever_adapter"
    )
    row = next(
        item
        for item in payload["evidence_matrix"]["rows"]
        if item["candidate_id"] == "declared_pipeline"
    )
    assert row["replay_status"] == "ok"
    assert row["topology"]["status"] == "pipeline_materialized"
    assert row["artifacts"]["capability_registry"]["exists"] is True
    skipped = next(
        candidate
        for candidate in payload["candidates"]
        if candidate["candidate_id"] == "baseline_single_predict"
    )
    assert skipped["status"] == "skipped"


@pytest.mark.slow
def test_program_architect_tournament_skips_declared_only_candidates(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    plan = build_program_architecture_candidates(
        ProgramIntent(
            name="UnsupportedDeclaredProgram",
            objective="Use an unsupported custom reasoning architecture.",
            inputs=["question"],
            outputs=["answer"],
            topology={
                "kind": "pipeline",
                "execution_status": "declared_not_materialized",
                "modules": [
                    {
                        "id": "custom_answer",
                        "primitive": "Custom",
                        "signature": {
                            "name": "CustomAnswer",
                            "inputs": ["question"],
                            "outputs": ["answer"],
                        },
                    }
                ],
                "edges": [
                    {"from": "input", "to": "custom_answer"},
                    {"from": "custom_answer", "to": "output"},
                ],
            },
        )
    )
    plan_path = tmp_path / "architecture_plan.json"
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")
    tournament_out = tmp_path / "tournament.json"

    result = runner.invoke(
        app,
        [
            "program-architect",
            "tournament",
            "--architecture-plan",
            str(plan_path),
            "--outdir",
            str(tmp_path / "tournament"),
            "--out",
            str(tournament_out),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(tournament_out.read_text())
    assert payload["materialized_candidate_count"] == 1
    skipped = next(
        candidate
        for candidate in payload["candidates"]
        if candidate["candidate_id"] == "declared_only_topology"
    )
    assert skipped["status"] == "skipped"
    assert not (
        tmp_path / "tournament" / "candidates" / "declared_only_topology"
    ).exists()
