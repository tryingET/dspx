from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.coordinates import reset_embedding_engine
from dspx.services.program_intent import ProgramIntent
from dspx.services.program_jury_execution import (
    build_program_jury_execution_result,
    write_program_jury_execution_result,
)
from dspx.services.program_meta_adjudication import (
    build_program_jury_requirements,
    build_program_meta_adjudication_plan,
    build_program_target_profile,
    write_program_jury_requirements,
    write_program_meta_adjudication_plan,
    write_program_target_profile,
)
from dspx.services.program_service import materialize_program_from_intent

runner = CliRunner()


def _setup_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "mock")
    reset_embedding_engine()


def _materialize_obsidian_like_candidate(tmp_path: Path, monkeypatch) -> Path:
    _setup_env(tmp_path, monkeypatch)
    intent = ProgramIntent(
        name="ObsidianPdfTransitionReviewer",
        objective=(
            "Transform PDF source package evidence into review-only Obsidian Wiki "
            "transition proposals without canonical Atlas or Wiki mutation."
        ),
        inputs=["marker_markdown", "source_package_json", "existing_wiki_index_json"],
        outputs=["review_packet_json", "merge_create_proposals_json"],
        metric="exact_match",
        constraints=[
            "Preserve Zotero/source identity and source refs.",
            "All Wiki or Atlas targets require review_required=true.",
            "Canonical mutation is forbidden during generation.",
        ],
        examples=[
            {
                "inputs": {
                    "marker_markdown": "# Close Reading\nUse source-grounded evidence.",
                    "source_package_json": '{"source_id":"zotero:user:demo/DEMO2026"}',
                    "existing_wiki_index_json": "{}",
                },
                "outputs": {
                    "review_packet_json": '{"canonical_mutation_performed":false}',
                    "merge_create_proposals_json": "[]",
                },
            }
        ],
    )
    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "program")
    return Path(artifact.root_path)


def test_meta_adjudication_plan_derives_target_sensitive_jury_requirements(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)

    plan = build_program_meta_adjudication_plan(
        manifest_path=candidate_root / "manifest.json"
    )

    assert plan["schema_version"] == "program-meta-adjudication-plan-v1"
    assert plan["status"] == "planned_not_executed"
    assert plan["effect"]["provider_called"] is False
    assert plan["non_authority"]["activation_authority"] is False
    assert (
        plan["oracle_postgres_behavior_memory"]["publication_allowed_by_this_plan"]
        is False
    )
    assert plan["gepa_improvement_lane"]["activation_authority"] is False

    risk_ids = {risk["risk_id"] for risk in plan["target_profile"]["risks"]}
    assert "source_grounding" in risk_ids
    assert "canonical_mutation_boundary" in risk_ids
    assert "review_queue_boundary" in risk_ids

    perspectives = {
        item["perspective"]
        for item in plan["jury_requirements"]["required_perspectives"]
    }
    assert "source_grounding" in perspectives
    assert "canonical_mutation_safety" in perspectives
    assert "review_surface" in perspectives
    assert "authority_boundary" in perspectives
    assert "program_jury_results" in plan["missing_evidence"]
    assert "jury_panel_verification" in plan["missing_evidence"]
    assert any(
        cmd["step"] == "run_deterministic_jury_baseline"
        for cmd in plan["next_commands"]
    )


def test_target_profile_and_jury_requirements_write_first_class_sidecars(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    profile_path = tmp_path / "target_profile.json"
    requirements_path = tmp_path / "jury_requirements.json"

    profile = build_program_target_profile(
        manifest_path=candidate_root / "manifest.json"
    )
    write_program_target_profile(profile, profile_path)
    requirements = build_program_jury_requirements(target_profile_path=profile_path)
    write_program_jury_requirements(requirements, requirements_path)

    assert profile["schema_version"] == "program-target-profile-v1"
    assert profile["identity"]["candidate_id"]
    assert profile["manifest"]["path"] == str(candidate_root / "manifest.json")
    assert profile["effect"]["provider_called"] is False
    assert profile["non_authority"]["activation_authority"] is False
    risk_ids = {risk["risk_id"] for risk in profile["risks"]}
    assert "canonical_mutation_boundary" in risk_ids

    assert requirements["schema_version"] == "program-jury-requirements-v1"
    assert requirements["target_profile"]["path"] == str(profile_path.resolve())
    assert requirements["effect"]["provider_called"] is False
    perspectives = {
        item["perspective"] for item in requirements["required_perspectives"]
    }
    assert "canonical_mutation_safety" in perspectives
    assert "review_surface" in perspectives

    written_profile = json.loads(profile_path.read_text(encoding="utf-8"))
    written_requirements = json.loads(requirements_path.read_text(encoding="utf-8"))
    assert written_profile["schema_version"] == "program-target-profile-v1"
    assert written_requirements["schema_version"] == "program-jury-requirements-v1"


def test_target_profile_and_jury_requirements_cli_write_json(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    profile_out = tmp_path / "target-profile.json"
    requirements_out = tmp_path / "jury-requirements.json"

    profile_result = runner.invoke(
        app,
        [
            "program-promote",
            "target-profile",
            "--manifest",
            str(candidate_root / "manifest.json"),
            "--out",
            str(profile_out),
            "--json",
        ],
    )
    assert profile_result.exit_code == 0, profile_result.output
    profile_payload = json.loads(profile_result.output)
    assert profile_payload["schema_version"] == "program-target-profile-v1"

    requirements_result = runner.invoke(
        app,
        [
            "program-promote",
            "jury-requirements",
            "--target-profile",
            str(profile_out),
            "--out",
            str(requirements_out),
            "--json",
        ],
    )
    assert requirements_result.exit_code == 0, requirements_result.output
    requirements_payload = json.loads(requirements_result.output)
    assert requirements_payload["schema_version"] == "program-jury-requirements-v1"
    assert requirements_payload["target_profile"]["path"] == str(profile_out.resolve())
    assert requirements_out.exists()


def test_meta_adjudication_plan_tracks_present_sidecars(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    jury = build_program_jury_execution_result(
        manifest_path=candidate_root / "manifest.json"
    )
    jury_path = candidate_root / "jury_results.json"
    write_program_jury_execution_result(jury, jury_path)

    plan = build_program_meta_adjudication_plan(
        manifest_path=candidate_root / "manifest.json",
        jury_results_path=jury_path,
    )

    assert plan["sidecars"]["jury_results"]["status"] == "present"
    assert (
        plan["sidecars"]["jury_results"]["schema_version"] == "program-jury-results-v1"
    )
    assert "program_jury_results" not in plan["missing_evidence"]


def test_meta_adjudication_plan_cli_writes_json(tmp_path: Path, monkeypatch) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    out = tmp_path / "meta-adjudication-plan.json"

    result = runner.invoke(
        app,
        [
            "program-promote",
            "meta-adjudication-plan",
            "--manifest",
            str(candidate_root / "manifest.json"),
            "--out",
            str(out),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema_version"] == "program-meta-adjudication-plan-v1"
    assert out.exists()
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["manifest"]["path"] == str(candidate_root / "manifest.json")
    assert written["effect"]["candidate_files_mutated"] is False


def test_write_meta_adjudication_plan_rejects_wrong_schema(tmp_path: Path) -> None:
    try:
        write_program_meta_adjudication_plan(
            {"schema_version": "wrong-schema"}, tmp_path / "plan.json"
        )
    except ValueError as exc:
        assert "program-meta-adjudication-plan-v1" in str(exc)
    else:  # pragma: no cover - defensive clarity
        raise AssertionError("expected wrong schema to be rejected")
