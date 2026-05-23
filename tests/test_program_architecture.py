from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from dspx.cache import sha256_text
from dspx.cli.dspx import app
from dspx.services.program_architecture import build_program_architecture_candidates
from dspx.services.program_intent import ProgramIntent
from dspx.services.program_service import materialize_program_from_intent
from dspx.services.run_replay_service import check_run_receipt

runner = CliRunner()


def _write_intent(path: Path, objective: str, *, examples: bool = False) -> None:
    lines = [
        "schema_version: program-intent-v2",
        "name: ArchitectDogfoodProgram",
        f"objective: {objective}",
        "inputs:",
        "  - ticket_text",
        "outputs:",
        "  - response",
        "metric: exact_match",
    ]
    if examples:
        lines.extend(
            [
                "examples:",
                "  - inputs:",
                "      ticket_text: I was charged twice for my subscription.",
                "    outputs:",
                "      response: This is a billing issue.",
            ]
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def test_architecture_planner_emits_non_authoritative_prompt_inferred_candidates() -> (
    None
):
    intent = ProgramIntent(
        name="ArchitectDogfoodProgram",
        objective=(
            "Route support tickets by classifying billing versus technical issues, "
            "then draft a helpful response with rationale."
        ),
        inputs=["ticket_text"],
        outputs=["response"],
    )

    plan = build_program_architecture_candidates(intent)

    assert plan["schema_version"] == "program-architecture-candidates-v1"
    assert plan["status"] == "planned_not_materialized"
    assert plan["recommended_candidate_id"] == "prompt_inferred_pipeline"
    assert plan["effect"] == {
        "candidate_materialized": False,
        "portfolio_materialized": False,
        "provider_called": False,
        "oracle_index_mutated": False,
        "ak_called": False,
        "governance_mutated": False,
        "external_authority_mutated": False,
    }
    assert plan["non_authority"]["planning_only"] is True
    assert plan["non_authority"]["winner_selection"] is False
    assert [candidate["candidate_id"] for candidate in plan["candidates"]] == [
        "baseline_single_predict",
        "prompt_inferred_pipeline",
    ]
    baseline, inferred = plan["candidates"]
    assert baseline["module_surface_preview"]["module_surface_count"] == 1
    assert baseline["module_surface_preview"]["module_surfaces"][0]["primitive"] == (
        "Predict"
    )
    assert inferred["module_surface_preview"]["module_surface_count"] == 2
    assert [
        surface["primitive"]
        for surface in inferred["module_surface_preview"]["module_surfaces"]
    ] == ["Predict", "ChainOfThought"]
    assert [
        surface["source_kind"]
        for surface in inferred["module_surface_preview"]["module_surfaces"]
    ] == ["generated_topology_module", "generated_topology_module"]


def test_architecture_planner_preserves_unsupported_declared_pipeline_as_declared_only() -> (
    None
):
    intent = ProgramIntent(
        name="UnsupportedDeclaredProgram",
        objective="Use a tool-like reasoning architecture.",
        inputs=["question"],
        outputs=["answer"],
        topology={
            "kind": "pipeline",
            "execution_status": "declared_not_materialized",
            "modules": [
                {
                    "id": "react_answer",
                    "primitive": "ReAct",
                    "signature": {
                        "name": "ReactAnswer",
                        "inputs": ["question"],
                        "outputs": ["answer"],
                    },
                }
            ],
            "edges": [
                {"from": "input", "to": "react_answer"},
                {"from": "react_answer", "to": "output"},
            ],
        },
    )

    plan = build_program_architecture_candidates(intent)

    assert plan["recommended_candidate_id"] == "baseline_single_predict"
    declared = next(
        candidate
        for candidate in plan["candidates"]
        if candidate["candidate_id"] == "declared_only_topology"
    )
    assert declared["status"] == "declared_only_not_materializable"
    assert declared["module_surface_preview"] is None
    assert any("unsupported primitives" in item for item in declared["limitations"])
    assert declared["effect"]["candidate_materialized"] is False


def test_architecture_planner_cli_writes_plan_and_intent_portfolio(
    tmp_path: Path,
) -> None:
    intent_path = tmp_path / "intent.yaml"
    plan_path = tmp_path / "architecture_plan.json"
    portfolio_dir = tmp_path / "portfolio"
    _write_intent(
        intent_path,
        "Route support tickets by classifying billing versus technical issues, then draft a helpful response with rationale.",
    )

    result = runner.invoke(
        app,
        [
            "program-architect",
            "plan",
            "--intent",
            str(intent_path),
            "--out",
            str(plan_path),
            "--portfolio-outdir",
            str(portfolio_dir),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    stdout_plan = json.loads(result.output)
    assert stdout_plan["schema_version"] == "program-architecture-candidates-v1"
    stdout_without_artifact = dict(stdout_plan)
    stdout_artifact = dict(stdout_without_artifact.pop("artifact"))
    assert stdout_artifact["payload_hash_excluding_artifact"] == sha256_text(
        json.dumps(
            stdout_without_artifact, ensure_ascii=False, indent=2, sort_keys=True
        )
        + "\n"
    )
    assert plan["portfolio"]["schema_version"] == (
        "program-architecture-intent-portfolio-v1"
    )
    assert "content_hash" not in plan["artifact"]
    assert "payload_hash_excluding_artifact" in plan["artifact"]
    assert plan["effect"]["candidate_materialized"] is False
    assert plan["effect"]["portfolio_materialized"] is True
    assert not (portfolio_dir / "manifest.json").exists()
    assert not (portfolio_dir / "program.py").exists()
    index = json.loads((portfolio_dir / "portfolio_index.json").read_text())
    assert index["candidate_intent_count"] == 2
    assert sorted(
        path.name for path in (portfolio_dir / "candidate_intents").glob("*.json")
    ) == [
        "baseline_single_predict.json",
        "prompt_inferred_pipeline.json",
    ]


def test_architecture_planner_refuses_candidate_artifact_output(tmp_path: Path) -> None:
    intent_path = tmp_path / "intent.yaml"
    _write_intent(intent_path, "Answer a question from context.")

    result = runner.invoke(
        app,
        [
            "program-architect",
            "plan",
            "--intent",
            str(intent_path),
            "--out",
            str(tmp_path / "manifest.json"),
        ],
    )

    assert result.exit_code == 2
    assert "refusing to write architecture plan" in result.output


def test_program_architect_loop_runs_guided_local_architecture_flow(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    outdir = tmp_path / "architect_loop"

    result = runner.invoke(
        app,
        [
            "program-architect",
            "loop",
            "--prompt",
            "Route support tickets by classifying billing versus technical issues, then draft a helpful response with rationale.",
            "--outdir",
            str(outdir),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema_version"] == "program-architect-loop-v1"
    assert (outdir / "normalization.json").exists()
    assert (outdir / "normalized_intent.json").exists()
    assert (outdir / "architecture_plan.json").exists()
    assert (outdir / "tournament.json").exists()
    assert (outdir / "architecture_recommendation.json").exists()
    assert (outdir / "program_architect_loop.json").exists()
    assert payload == json.loads((outdir / "program_architect_loop.json").read_text())
    assert payload["steps"]["normalization"]["status"] == "normalized"
    assert payload["steps"]["architecture_plan"]["candidate_count"] == 2
    assert payload["steps"]["tournament"]["materialized_candidate_count"] == 2
    assert payload["steps"]["recommendation"]["next_move_count"] >= 1
    assert payload["effect"]["candidate_programs_materialized"] is True
    assert payload["effect"]["receipts_replay_checked"] is True
    assert payload["effect"]["oracle_index_mutated"] is False
    assert payload["effect"]["shared_oracle_mutated"] is False
    assert payload["effect"]["winner_selected"] is False
    assert payload["effect"]["promotion_applied"] is False
    assert payload["effect"]["ak_called"] is False
    assert payload["effect"]["governance_mutated"] is False
    assert payload["non_authority"]["guided_architecture_loop_only"] is True
    assert payload["non_authority"]["winner_selection"] is False
    assert not (outdir / "manifest.json").exists()
    assert not (outdir / "program.py").exists()


def test_program_architect_loop_with_oracle_reports_is_candidate_local(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "mock")
    outdir = tmp_path / "architect_loop"

    result = runner.invoke(
        app,
        [
            "program-architect",
            "loop",
            "--prompt",
            "Route support tickets by classifying billing versus technical issues, then draft a helpful response with rationale.",
            "--outdir",
            str(outdir),
            "--candidate",
            "prompt_inferred_pipeline",
            "--with-oracle-reports",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["effect"]["oracle_index_mutated"] is True
    assert payload["effect"]["oracle_index_scope"] == "candidate_local_explicit_paths"
    assert payload["effect"]["shared_oracle_mutated"] is False
    candidate_root = outdir / "tournament" / "candidates" / "prompt_inferred_pipeline"
    assert (candidate_root / "oracle" / "coordinates.db").exists()
    assert (candidate_root / "program_oracle_report.json").exists()
    recommendation = json.loads(
        (outdir / "architecture_recommendation.json").read_text()
    )
    assert recommendation["effect"]["winner_selected"] is False
    assert recommendation["effect"]["promotion_applied"] is False


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


def test_program_architect_recommend_emits_next_moves_without_winner_selection(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    intent_path = tmp_path / "intent.yaml"
    plan_path = tmp_path / "architecture_plan.json"
    tournament_out = tmp_path / "tournament.json"
    recommendation_out = tmp_path / "architecture_recommendation.json"
    _write_intent(
        intent_path,
        "Route support tickets by classifying billing versus technical issues, then draft a helpful response with rationale.",
        examples=True,
    )
    assert (
        runner.invoke(
            app,
            [
                "program-architect",
                "plan",
                "--intent",
                str(intent_path),
                "--out",
                str(plan_path),
            ],
        ).exit_code
        == 0
    )
    tournament_result = runner.invoke(
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
        ],
    )
    assert tournament_result.exit_code == 0, tournament_result.output
    before_hash = sha256_text(tournament_out.read_text(encoding="utf-8"))

    result = runner.invoke(
        app,
        [
            "program-architect",
            "recommend",
            "--tournament",
            str(tournament_out),
            "--out",
            str(recommendation_out),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(recommendation_out.read_text(encoding="utf-8"))
    assert json.loads(result.output) == payload
    assert sha256_text(tournament_out.read_text(encoding="utf-8")) == before_hash
    assert payload["schema_version"] == "program-architecture-recommendation-v1"
    assert payload["created_from"]["tournament_schema_version"] == (
        "program-architecture-tournament-v1"
    )
    assert payload["status"] in {"advisory_ready", "needs_attention"}
    assert payload["next_moves"]
    assert [item["candidate_id"] for item in payload["candidate_advisories"]] == [
        "baseline_single_predict",
        "prompt_inferred_pipeline",
    ]
    assert all("winner" not in item for item in payload)
    assert "selected_candidate_id" not in payload
    assert "winner_candidate_id" not in payload
    assert payload["effect"]["recommendation_sidecar_written"] is True
    assert payload["effect"]["candidate_programs_materialized"] is False
    assert payload["effect"]["oracle_index_mutated"] is False
    assert payload["effect"]["winner_selected"] is False
    assert payload["effect"]["promotion_applied"] is False
    assert payload["effect"]["ak_called"] is False
    assert payload["effect"]["governance_mutated"] is False
    assert payload["non_authority"]["advisory_only"] is True
    assert payload["non_authority"]["winner_selection"] is False
    assert payload["non_authority"]["promotion_authority"] is False


def test_program_architect_recommend_rejects_authority_widened_tournament(
    tmp_path: Path,
) -> None:
    tournament_path = tmp_path / "tournament.json"
    recommendation_out = tmp_path / "recommendation.json"
    tournament_path.write_text(
        json.dumps(
            {
                "schema_version": "program-architecture-tournament-v1",
                "status": "materialized_and_replay_checked",
                "evidence_matrix": {
                    "schema_version": "program-architecture-tournament-evidence-matrix-v1",
                    "rows": [],
                },
                "effect": {
                    "winner_selected": True,
                    "promotion_applied": False,
                    "ak_called": False,
                    "governance_mutated": False,
                    "external_authority_mutated": False,
                    "shared_oracle_mutated": False,
                },
                "non_authority": {"winner_selection": False},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "program-architect",
            "recommend",
            "--tournament",
            str(tournament_path),
            "--out",
            str(recommendation_out),
        ],
    )

    assert result.exit_code == 2
    assert "widens authority" in result.output
    assert not recommendation_out.exists()


def test_program_architect_recommend_rejects_shared_oracle_mutation(
    tmp_path: Path,
) -> None:
    tournament_path = tmp_path / "tournament.json"
    recommendation_out = tmp_path / "recommendation.json"
    tournament_path.write_text(
        json.dumps(
            {
                "schema_version": "program-architecture-tournament-v1",
                "status": "materialized_and_replay_checked",
                "evidence_matrix": {
                    "schema_version": "program-architecture-tournament-evidence-matrix-v1",
                    "rows": [],
                },
                "effect": {
                    "winner_selected": False,
                    "promotion_applied": False,
                    "ak_called": False,
                    "governance_mutated": False,
                    "external_authority_mutated": False,
                    "shared_oracle_mutated": True,
                },
                "non_authority": {"winner_selection": False},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "program-architect",
            "recommend",
            "--tournament",
            str(tournament_path),
            "--out",
            str(recommendation_out),
        ],
    )

    assert result.exit_code == 2
    assert "shared_oracle_mutated" in result.output
    assert not recommendation_out.exists()


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
            objective="Use a tool-like reasoning architecture.",
            inputs=["question"],
            outputs=["answer"],
            topology={
                "kind": "pipeline",
                "execution_status": "declared_not_materialized",
                "modules": [
                    {
                        "id": "react_answer",
                        "primitive": "ReAct",
                        "signature": {
                            "name": "ReactAnswer",
                            "inputs": ["question"],
                            "outputs": ["answer"],
                        },
                    }
                ],
                "edges": [
                    {"from": "input", "to": "react_answer"},
                    {"from": "react_answer", "to": "output"},
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


def test_program_architect_tournament_rejects_wrong_schema_without_partial_dirs(
    tmp_path: Path,
) -> None:
    plan_path = tmp_path / "not_architecture_plan.json"
    outdir = tmp_path / "tournament"
    plan_path.write_text(json.dumps({"schema_version": "wrong", "candidates": []}))

    result = runner.invoke(
        app,
        [
            "program-architect",
            "tournament",
            "--architecture-plan",
            str(plan_path),
            "--outdir",
            str(outdir),
            "--out",
            str(tmp_path / "tournament.json"),
        ],
    )

    assert result.exit_code == 2
    assert "schema_version" in result.output
    assert not outdir.exists()


def test_architecture_plan_portfolio_dogfoods_program_gen_and_replay(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    intent_path = tmp_path / "intent.yaml"
    plan_path = tmp_path / "architecture_plan.json"
    portfolio_dir = tmp_path / "portfolio"
    _write_intent(
        intent_path,
        "Route support tickets by classifying billing versus technical issues, then draft a helpful response with rationale.",
    )
    result = runner.invoke(
        app,
        [
            "program-architect",
            "plan",
            "--intent",
            str(intent_path),
            "--out",
            str(plan_path),
            "--portfolio-outdir",
            str(portfolio_dir),
        ],
    )
    assert result.exit_code == 0, result.output

    candidate_intent = (
        portfolio_dir / "candidate_intents" / "prompt_inferred_pipeline.json"
    )
    artifact = materialize_program_from_intent(
        ProgramIntent.model_validate(json.loads(candidate_intent.read_text())),
        outdir=tmp_path / "generated" / "prompt_inferred_pipeline",
    )
    root = Path(artifact.root_path)
    generated_surfaces = json.loads((root / "module_surfaces.json").read_text())
    planned = json.loads(plan_path.read_text())
    planned_inferred = next(
        candidate
        for candidate in planned["candidates"]
        if candidate["candidate_id"] == "prompt_inferred_pipeline"
    )

    assert generated_surfaces == planned_inferred["module_surface_preview"]
    assert check_run_receipt(root / "manifest.json.meta.json")["status"] == "ok"
