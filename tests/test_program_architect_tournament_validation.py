from __future__ import annotations

import json
from pathlib import Path


from dspx.cache import sha256_text
from dspx.cli.dspx import app
from dspx.services.program_architecture import (
    build_program_architecture_candidates,
)
from dspx.services.program_intent import ProgramIntent
from program_architecture_shared import (
    runner,
)


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


def test_program_architect_tournament_rejects_invalid_plan_before_out_parent_creation(
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
            str(outdir / "tournament.json"),
        ],
    )

    assert result.exit_code == 2
    assert "schema_version" in result.output
    assert not outdir.exists()


def test_program_architect_tournament_rejects_authority_widened_architecture_plan(
    tmp_path: Path,
) -> None:
    plan_path = tmp_path / "architecture_plan.json"
    outdir = tmp_path / "tournament"
    tournament_out = tmp_path / "tournament.json"
    plan_path.write_text(
        json.dumps(
            {
                "schema_version": "program-architecture-candidates-v1",
                "status": "planned_not_materialized",
                "intent_identity": {
                    "schema_version": "program-intent-v2",
                    "objective": "Answer a question from context.",
                    "inputs": ["question"],
                    "outputs": ["answer"],
                    "intent_hash": "8dac0bb5fea0c081c235e1d0afa69598259199efab3e2a6945eeaadbc12b5cda",
                },
                "source_intent_payload": {
                    "schema_version": "program-intent-v2",
                    "name": "ManualPlanProgram",
                    "objective": "Answer a question from context.",
                    "inputs": ["question"],
                    "outputs": ["answer"],
                },
                "candidates": [
                    {
                        "candidate_id": "baseline_single_predict",
                        "status": "materializable",
                        "effect": {"candidate_materialized": False},
                        "non_authority": {"winner_selection": False},
                    }
                ],
                "effect": {
                    "candidate_materialized": False,
                    "provider_called": False,
                    "oracle_index_mutated": False,
                    "ak_called": False,
                    "governance_mutated": False,
                    "external_authority_mutated": True,
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
            "tournament",
            "--architecture-plan",
            str(plan_path),
            "--outdir",
            str(outdir),
            "--out",
            str(tournament_out),
        ],
    )

    assert result.exit_code == 2
    assert "architecture plan effect widens authority" in result.output
    assert "external_authority_mutated" in result.output
    assert not tournament_out.exists()
    assert not outdir.exists()


def test_program_architect_tournament_rejects_missing_plan_authority_flags(
    tmp_path: Path,
) -> None:
    plan_path = tmp_path / "architecture_plan.json"
    outdir = tmp_path / "tournament"
    tournament_out = tmp_path / "tournament.json"
    plan_path.write_text(
        json.dumps(
            {
                "schema_version": "program-architecture-candidates-v1",
                "status": "planned_not_materialized",
                "intent_identity": {
                    "schema_version": "program-intent-v2",
                    "objective": "Answer a question from context.",
                    "inputs": ["question"],
                    "outputs": ["answer"],
                    "intent_hash": "8dac0bb5fea0c081c235e1d0afa69598259199efab3e2a6945eeaadbc12b5cda",
                },
                "source_intent_payload": {
                    "schema_version": "program-intent-v2",
                    "name": "ManualPlanProgram",
                    "objective": "Answer a question from context.",
                    "inputs": ["question"],
                    "outputs": ["answer"],
                },
                "candidates": [],
                "non_authority": {
                    "winner_selection": False,
                    "ranking_authority": False,
                    "promotion_authority": False,
                    "activation_authority": False,
                    "oracle_authority": False,
                    "governance_authority": False,
                    "external_mutation": False,
                    "canonical_mutation": False,
                },
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
            "tournament",
            "--architecture-plan",
            str(plan_path),
            "--outdir",
            str(outdir),
            "--out",
            str(tournament_out),
        ],
    )

    assert result.exit_code == 2
    assert "architecture plan effect missing authority flags" in result.output
    assert "candidate_materialized" in result.output
    assert not tournament_out.exists()
    assert not outdir.exists()


def test_program_architect_tournament_rejects_authority_widened_plan_candidate(
    tmp_path: Path,
) -> None:
    plan_path = tmp_path / "architecture_plan.json"
    outdir = tmp_path / "tournament"
    tournament_out = tmp_path / "tournament.json"
    plan_path.write_text(
        json.dumps(
            {
                "schema_version": "program-architecture-candidates-v1",
                "status": "planned_not_materialized",
                "intent_identity": {
                    "schema_version": "program-intent-v2",
                    "objective": "Answer a question from context.",
                    "inputs": ["question"],
                    "outputs": ["answer"],
                    "intent_hash": "8dac0bb5fea0c081c235e1d0afa69598259199efab3e2a6945eeaadbc12b5cda",
                },
                "source_intent_payload": {
                    "schema_version": "program-intent-v2",
                    "name": "ManualPlanProgram",
                    "objective": "Answer a question from context.",
                    "inputs": ["question"],
                    "outputs": ["answer"],
                },
                "candidates": [
                    {
                        "candidate_id": "baseline_single_predict",
                        "status": "materializable",
                        "effect": {
                            "candidate_materialized": False,
                            "provider_called": False,
                            "oracle_index_mutated": False,
                            "ak_called": False,
                            "governance_mutated": False,
                            "external_authority_mutated": False,
                        },
                        "non_authority": {
                            "winner_selection": False,
                            "ranking_authority": False,
                            "promotion_authority": True,
                            "activation_authority": False,
                            "oracle_authority": False,
                            "governance_authority": False,
                            "external_mutation": False,
                            "canonical_mutation": False,
                        },
                    }
                ],
                "effect": {
                    "candidate_materialized": False,
                    "provider_called": False,
                    "oracle_index_mutated": False,
                    "ak_called": False,
                    "governance_mutated": False,
                    "external_authority_mutated": False,
                },
                "non_authority": {
                    "winner_selection": False,
                    "ranking_authority": False,
                    "promotion_authority": False,
                    "activation_authority": False,
                    "oracle_authority": False,
                    "governance_authority": False,
                    "external_mutation": False,
                    "canonical_mutation": False,
                },
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
            "tournament",
            "--architecture-plan",
            str(plan_path),
            "--outdir",
            str(outdir),
            "--out",
            str(tournament_out),
        ],
    )

    assert result.exit_code == 2
    assert (
        "architecture plan candidate 0 non_authority widens authority" in result.output
    )
    assert "promotion_authority" in result.output
    assert not tournament_out.exists()
    assert not outdir.exists()


def test_program_architect_tournament_rejects_candidate_intent_source_identity_drift_without_partial_dirs(
    tmp_path: Path,
) -> None:
    plan = build_program_architecture_candidates(
        ProgramIntent(
            name="SourceBindingProgram",
            objective="Answer support questions from context.",
            inputs=["question"],
            outputs=["answer"],
        )
    )
    candidate = next(
        item
        for item in plan["candidates"]
        if item["candidate_id"] == "baseline_single_predict"
    )
    candidate["intent_payload"]["objective"] = "Unrelated changed objective."
    candidate["intent_payload"]["inputs"] = ["unrelated_input"]
    candidate["intent_hash"] = sha256_text(
        json.dumps(
            candidate["intent_payload"], ensure_ascii=False, indent=2, sort_keys=True
        )
        + "\n"
    )
    plan_path = tmp_path / "architecture_plan.json"
    outdir = tmp_path / "tournament"
    tournament_out = tmp_path / "tournament.json"
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")

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
            str(tournament_out),
        ],
    )

    assert result.exit_code == 2
    assert "intent_payload does not match intent_identity.objective" in result.output
    assert not tournament_out.exists()
    assert not outdir.exists()


def test_program_architect_tournament_rejects_source_payload_hash_drift_without_partial_dirs(
    tmp_path: Path,
) -> None:
    plan = build_program_architecture_candidates(
        ProgramIntent(
            name="SourceHashBindingProgram",
            objective="Classify support tickets.",
            inputs=["ticket_text"],
            outputs=["label"],
            metric="exact_match",
        )
    )
    plan["source_intent_payload"]["metric"] = "f1"
    candidate = next(
        item
        for item in plan["candidates"]
        if item["candidate_id"] == "baseline_single_predict"
    )
    candidate["intent_payload"]["metric"] = "f1"
    candidate["intent_hash"] = sha256_text(
        json.dumps(
            candidate["intent_payload"], ensure_ascii=False, indent=2, sort_keys=True
        )
        + "\n"
    )
    plan_path = tmp_path / "architecture_plan.json"
    outdir = tmp_path / "tournament"
    tournament_out = tmp_path / "tournament.json"
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")

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
            str(tournament_out),
        ],
    )

    assert result.exit_code == 2
    assert "source_intent_payload hash does not match" in result.output
    assert not tournament_out.exists()
    assert not outdir.exists()


def test_program_architect_tournament_rejects_candidate_source_payload_field_drift_without_partial_dirs(
    tmp_path: Path,
) -> None:
    plan = build_program_architecture_candidates(
        ProgramIntent(
            name="SourcePayloadBindingProgram",
            objective="Classify support tickets.",
            inputs=["ticket_text"],
            outputs=["label"],
            metric="exact_match",
            examples=[
                {
                    "inputs": {"ticket_text": "I was charged twice."},
                    "outputs": {"label": "billing"},
                }
            ],
        )
    )
    candidate = next(
        item
        for item in plan["candidates"]
        if item["candidate_id"] == "baseline_single_predict"
    )
    candidate["intent_payload"]["examples"] = [
        {
            "inputs": {"ticket_text": "The app crashes on launch."},
            "outputs": {"label": "technical"},
        }
    ]
    candidate["intent_hash"] = sha256_text(
        json.dumps(
            candidate["intent_payload"], ensure_ascii=False, indent=2, sort_keys=True
        )
        + "\n"
    )
    plan_path = tmp_path / "architecture_plan.json"
    outdir = tmp_path / "tournament"
    tournament_out = tmp_path / "tournament.json"
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")

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
            str(tournament_out),
        ],
    )

    assert result.exit_code == 2
    assert "source fields drift from source_intent_payload" in result.output
    assert not tournament_out.exists()
    assert not outdir.exists()


def test_program_architect_tournament_rejects_candidate_topology_payload_mismatch_without_partial_dirs(
    tmp_path: Path,
) -> None:
    plan = build_program_architecture_candidates(
        ProgramIntent(
            name="TopologyCongruenceProgram",
            objective=(
                "Route support tickets by classifying billing versus technical issues, "
                "then draft a helpful response with rationale."
            ),
            inputs=["ticket_text"],
            outputs=["response"],
        )
    )
    baseline = next(
        item
        for item in plan["candidates"]
        if item["candidate_id"] == "baseline_single_predict"
    )
    inferred = next(
        item
        for item in plan["candidates"]
        if item["candidate_id"] == "prompt_inferred_pipeline"
    )
    inferred["intent_payload"] = json.loads(json.dumps(baseline["intent_payload"]))
    inferred["intent_hash"] = sha256_text(
        json.dumps(
            inferred["intent_payload"], ensure_ascii=False, indent=2, sort_keys=True
        )
        + "\n"
    )
    plan_path = tmp_path / "architecture_plan.json"
    outdir = tmp_path / "tournament"
    tournament_out = tmp_path / "tournament.json"
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")

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
            str(tournament_out),
        ],
    )

    assert result.exit_code == 2
    assert "prompt_inferred_pipeline" in result.output
    assert "topology" in result.output
    assert not tournament_out.exists()
    assert not outdir.exists()


def test_program_architect_tournament_rejects_duplicate_candidate_ids_without_partial_dirs(
    tmp_path: Path,
) -> None:
    plan = build_program_architecture_candidates(
        ProgramIntent(
            name="CandidateIdentityProgram",
            objective=(
                "Route support tickets by classifying billing versus technical issues, "
                "then draft a helpful response with rationale."
            ),
            inputs=["ticket_text"],
            outputs=["response"],
        )
    )
    plan["candidates"].append(json.loads(json.dumps(plan["candidates"][0])))
    plan["candidate_count"] = len(plan["candidates"])
    plan_path = tmp_path / "architecture_plan.json"
    outdir = tmp_path / "tournament"
    tournament_out = tmp_path / "tournament.json"
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")

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
            str(tournament_out),
        ],
    )

    assert result.exit_code == 2
    assert "duplicate architecture candidate_id" in result.output
    assert "baseline_single_predict" in result.output
    assert not tournament_out.exists()
    assert not outdir.exists()


def test_program_architect_tournament_rejects_candidates_file_without_partial_writes(
    tmp_path: Path,
) -> None:
    plan = build_program_architecture_candidates(
        ProgramIntent(
            name="CandidateParentCollisionProgram",
            objective="Answer a question from context.",
            inputs=["question"],
            outputs=["answer"],
        )
    )
    plan_path = tmp_path / "architecture_plan.json"
    outdir = tmp_path / "tournament"
    candidates_path = outdir / "candidates"
    outdir.mkdir()
    candidates_path.write_text("SENTINEL\n")
    tournament_out = tmp_path / "tournament.json"
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")

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
            str(tournament_out),
        ],
    )

    assert result.exit_code == 2
    assert "candidate outputs path is not a directory" in result.output
    assert candidates_path.read_text() == "SENTINEL\n"
    assert not (outdir / "candidate_intents").exists()
    assert not tournament_out.exists()


def test_program_architect_tournament_rejects_existing_later_candidate_without_partial_writes(
    tmp_path: Path,
) -> None:
    plan = build_program_architecture_candidates(
        ProgramIntent(
            name="CollisionPreflightProgram",
            objective=(
                "Route support tickets by classifying billing versus technical issues, "
                "then draft a helpful response with rationale."
            ),
            inputs=["ticket_text"],
            outputs=["response"],
        )
    )
    plan_path = tmp_path / "architecture_plan.json"
    outdir = tmp_path / "tournament"
    tournament_out = tmp_path / "tournament.json"
    existing_candidate = outdir / "candidates" / "prompt_inferred_pipeline"
    existing_candidate.mkdir(parents=True)
    (existing_candidate / "manifest.json").write_text("{}\n")
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")

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
            str(tournament_out),
        ],
    )

    assert result.exit_code == 2
    assert "candidate output already exists" in result.output
    assert not tournament_out.exists()
    assert not (outdir / "candidates" / "baseline_single_predict").exists()
    assert not (outdir / "candidate_intents").exists()


def test_program_architect_tournament_rejects_internal_output_path_before_materialization(
    tmp_path: Path,
) -> None:
    plan = build_program_architecture_candidates(
        ProgramIntent(
            name="InternalTournamentOutProgram",
            objective="Answer a question from context.",
            inputs=["question"],
            outputs=["answer"],
        )
    )
    plan_path = tmp_path / "architecture_plan.json"
    outdir = tmp_path / "tournament"
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")

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
            str(outdir / "candidate_intents" / "baseline_single_predict.json"),
        ],
    )

    assert result.exit_code == 2
    assert "collides with internal tournament artifacts" in result.output
    assert not outdir.exists()


def test_program_architect_tournament_rejects_out_equal_to_outdir_before_materialization(
    tmp_path: Path,
) -> None:
    plan = build_program_architecture_candidates(
        ProgramIntent(
            name="TournamentOutdirCollisionProgram",
            objective="Answer a question from context.",
            inputs=["question"],
            outputs=["answer"],
        )
    )
    plan_path = tmp_path / "architecture_plan.json"
    outdir = tmp_path / "tournament"
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")

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
            str(outdir),
        ],
    )

    assert result.exit_code == 2
    assert "collides with tournament outdir" in result.output
    assert not outdir.exists()


def test_program_architect_tournament_rejects_forbidden_output_before_materialization(
    tmp_path: Path,
) -> None:
    plan = build_program_architecture_candidates(
        ProgramIntent(
            name="ForbiddenTournamentOutProgram",
            objective="Answer a question from context.",
            inputs=["question"],
            outputs=["answer"],
        )
    )
    plan_path = tmp_path / "architecture_plan.json"
    outdir = tmp_path / "tournament"
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")

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
            str(tmp_path / "manifest.json"),
        ],
    )

    assert result.exit_code == 2
    assert "refusing to write architecture tournament" in result.output
    assert not outdir.exists()


def test_program_architect_tournament_rejects_candidate_intents_file_without_materialization(
    tmp_path: Path,
) -> None:
    plan = build_program_architecture_candidates(
        ProgramIntent(
            name="CandidateIntentParentCollisionProgram",
            objective="Answer a question from context.",
            inputs=["question"],
            outputs=["answer"],
        )
    )
    plan_path = tmp_path / "architecture_plan.json"
    outdir = tmp_path / "tournament"
    candidate_intents = outdir / "candidate_intents"
    outdir.mkdir()
    candidate_intents.write_text("SENTINEL\n")
    tournament_out = tmp_path / "tournament.json"
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")

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
            str(tournament_out),
            "--candidate",
            "baseline_single_predict",
        ],
    )

    assert result.exit_code == 2
    assert "candidate intents output path is not a directory" in result.output
    assert candidate_intents.read_text() == "SENTINEL\n"
    assert not (outdir / "candidates" / "baseline_single_predict").exists()
    assert not tournament_out.exists()


def test_program_architect_tournament_rejects_existing_candidate_intent_without_materialization(
    tmp_path: Path,
) -> None:
    plan = build_program_architecture_candidates(
        ProgramIntent(
            name="CandidateIntentCollisionProgram",
            objective="Answer a question from context.",
            inputs=["question"],
            outputs=["answer"],
        )
    )
    plan_path = tmp_path / "architecture_plan.json"
    outdir = tmp_path / "tournament"
    candidate_intent = outdir / "candidate_intents" / "baseline_single_predict.json"
    candidate_intent.parent.mkdir(parents=True)
    candidate_intent.write_text("SENTINEL\n")
    tournament_out = tmp_path / "tournament.json"
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")

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
            str(tournament_out),
            "--candidate",
            "baseline_single_predict",
        ],
    )

    assert result.exit_code == 2
    assert "candidate intent output already exists" in result.output
    assert candidate_intent.read_text() == "SENTINEL\n"
    assert not (outdir / "candidates" / "baseline_single_predict").exists()
    assert not tournament_out.exists()


def test_program_architect_tournament_rejects_unknown_candidate_filter_without_partial_dirs(
    tmp_path: Path,
) -> None:
    plan = build_program_architecture_candidates(
        ProgramIntent(
            name="CandidateIdentityProgram",
            objective="Answer a question from context.",
            inputs=["question"],
            outputs=["answer"],
        )
    )
    plan_path = tmp_path / "architecture_plan.json"
    outdir = tmp_path / "tournament"
    tournament_out = tmp_path / "tournament.json"
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")

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
            str(tournament_out),
            "--candidate",
            "typo_candidate",
        ],
    )

    assert result.exit_code == 2
    assert "unknown architecture candidate id" in result.output
    assert "typo_candidate" in result.output
    assert not tournament_out.exists()
    assert not outdir.exists()


def test_program_architect_tournament_rejects_materializable_candidate_missing_intent_payload_without_partial_dirs(
    tmp_path: Path,
) -> None:
    plan = build_program_architecture_candidates(
        ProgramIntent(
            name="IntegrityPreflightProgram",
            objective="Answer a question from context.",
            inputs=["question"],
            outputs=["answer"],
        )
    )
    materializable = next(
        candidate
        for candidate in plan["candidates"]
        if candidate["candidate_id"] == "baseline_single_predict"
    )
    materializable.pop("intent_payload")
    plan_path = tmp_path / "architecture_plan.json"
    outdir = tmp_path / "tournament"
    tournament_out = tmp_path / "tournament.json"
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")

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
            str(tournament_out),
        ],
    )

    assert result.exit_code == 2
    assert "materializable candidate lacks intent_payload" in result.output
    assert not tournament_out.exists()
    assert not outdir.exists()


def test_program_architect_tournament_rejects_candidate_intent_hash_mismatch_without_partial_dirs(
    tmp_path: Path,
) -> None:
    plan = build_program_architecture_candidates(
        ProgramIntent(
            name="IntegrityPreflightProgram",
            objective="Answer a question from context.",
            inputs=["question"],
            outputs=["answer"],
        )
    )
    materializable = next(
        candidate
        for candidate in plan["candidates"]
        if candidate["candidate_id"] == "baseline_single_predict"
    )
    materializable["intent_hash"] = "not-the-real-hash"
    plan_path = tmp_path / "architecture_plan.json"
    outdir = tmp_path / "tournament"
    tournament_out = tmp_path / "tournament.json"
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")

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
            str(tournament_out),
        ],
    )

    assert result.exit_code == 2
    assert "intent_hash mismatch" in result.output
    assert not tournament_out.exists()
    assert not outdir.exists()
