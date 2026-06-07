from __future__ import annotations

import json
from pathlib import Path


from dspx.cli.dspx import app
from dspx.services.program_jury_execution import (
    build_program_jury_execution_result,
    write_program_jury_execution_result,
)
from dspx.services.program_meta_adjudication import (
    build_program_adjudication_behavior_trace,
    build_program_adjudication_gepa_example,
    build_program_adjudicator_delegation,
    build_program_adjudicator_formation,
    build_program_adjudicator_verification,
    build_program_evidence_adjudication,
    build_program_jury_requirements,
    build_program_jury_verification,
    build_program_meta_adjudication_plan,
    build_program_meta_jury_selection,
    write_program_adjudication_behavior_trace,
    write_program_adjudication_gepa_example,
    write_program_adjudicator_delegation,
    write_program_adjudicator_formation,
    write_program_adjudicator_verification,
    write_program_evidence_adjudication,
    write_program_jury_requirements,
    write_program_jury_verification,
    write_program_meta_adjudication_plan,
    write_program_meta_jury_selection,
)
from program_meta_adjudication_helpers import (
    _materialize_obsidian_like_candidate,
    _write_minimal_activation_packet,
    runner,
)


def test_program_adjudication_gepa_example_sidecar(tmp_path: Path, monkeypatch) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    requirements_path = tmp_path / "jury_requirements.json"
    selection_path = tmp_path / "meta_jury_selection.json"
    jury_verification_path = tmp_path / "jury_verification.json"
    formation_path = tmp_path / "program_adjudicator_formation.json"
    adjudicator_verification_path = tmp_path / "program_adjudicator_verification.json"
    activation_packet_path = candidate_root / "activation_packet.json"
    evidence_adjudication_path = tmp_path / "program_evidence_adjudication.json"
    trace_path = tmp_path / "adjudication_behavior_trace.json"
    gepa_example_path = tmp_path / "adjudication_gepa_example.json"

    requirements = build_program_jury_requirements(
        manifest_path=candidate_root / "manifest.json"
    )
    write_program_jury_requirements(requirements, requirements_path)
    selection = build_program_meta_jury_selection(
        jury_requirements_path=requirements_path
    )
    write_program_meta_jury_selection(selection, selection_path)
    jury_verification = build_program_jury_verification(
        jury_selection_path=selection_path
    )
    write_program_jury_verification(jury_verification, jury_verification_path)
    formation = build_program_adjudicator_formation(
        jury_verification_path=jury_verification_path
    )
    write_program_adjudicator_formation(formation, formation_path)
    adjudicator_verification = build_program_adjudicator_verification(
        adjudicator_formation_path=formation_path
    )
    write_program_adjudicator_verification(
        adjudicator_verification, adjudicator_verification_path
    )
    _write_minimal_activation_packet(activation_packet_path)
    adjudication = build_program_evidence_adjudication(
        adjudicator_verification_path=adjudicator_verification_path,
        manifest_path=candidate_root / "manifest.json",
        activation_packet_path=activation_packet_path,
    )
    write_program_evidence_adjudication(adjudication, evidence_adjudication_path)
    trace = build_program_adjudication_behavior_trace(
        evidence_adjudication_path=evidence_adjudication_path
    )
    write_program_adjudication_behavior_trace(trace, trace_path)

    example = build_program_adjudication_gepa_example(trace_path=trace_path)
    write_program_adjudication_gepa_example(example, gepa_example_path)

    assert example["schema_version"] == "program-adjudication-gepa-example-v1"
    assert example["status"] == "curated_pending_outcome_label"
    assert example["label"]["usable_for_gepa_training"] is False
    assert example["expected_output"]["activation_authority"] is False
    assert example["gepa_improvement_lane"]["activation_authority"] is False
    assert gepa_example_path.exists()


def test_program_adjudication_gepa_example_cli_write_json(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    requirements_out = tmp_path / "jury-requirements.json"
    selection_out = tmp_path / "meta-jury-selection.json"
    jury_verification_out = tmp_path / "jury-verification.json"
    formation_out = tmp_path / "adjudicator-formation.json"
    adjudicator_verification_out = tmp_path / "adjudicator-verification.json"
    activation_packet_path = candidate_root / "activation_packet.json"
    evidence_out = tmp_path / "evidence-adjudication.json"
    trace_out = tmp_path / "adjudication-trace.json"
    gepa_example_out = tmp_path / "adjudication-gepa-example.json"
    _write_minimal_activation_packet(activation_packet_path)

    for args in (
        [
            "program-promote",
            "jury-requirements",
            "--manifest",
            str(candidate_root / "manifest.json"),
            "--out",
            str(requirements_out),
            "--json",
        ],
        [
            "program-promote",
            "jury-panel",
            "--jury-requirements",
            str(requirements_out),
            "--out",
            str(selection_out),
            "--json",
        ],
        [
            "program-promote",
            "verify-jury-panel",
            "--jury-selection",
            str(selection_out),
            "--out",
            str(jury_verification_out),
            "--json",
        ],
        [
            "program-promote",
            "adjudicator-formation",
            "--jury-verification",
            str(jury_verification_out),
            "--out",
            str(formation_out),
            "--json",
        ],
        [
            "program-promote",
            "verify-program-adjudicator",
            "--adjudicator-formation",
            str(formation_out),
            "--out",
            str(adjudicator_verification_out),
            "--json",
        ],
        [
            "program-promote",
            "evidence-adjudication",
            "--manifest",
            str(candidate_root / "manifest.json"),
            "--adjudicator-verification",
            str(adjudicator_verification_out),
            "--activation-packet",
            str(activation_packet_path),
            "--out",
            str(evidence_out),
            "--json",
        ],
        [
            "program-promote",
            "adjudication-behavior-trace",
            "--evidence-adjudication",
            str(evidence_out),
            "--out",
            str(trace_out),
            "--json",
        ],
    ):
        result = runner.invoke(app, args)
        assert result.exit_code == 0, result.output

    result = runner.invoke(
        app,
        [
            "program-promote",
            "adjudication-gepa-example",
            "--trace",
            str(trace_out),
            "--out",
            str(gepa_example_out),
            "--outcome-label",
            "domain_accepted_for_review",
            "--feedback",
            "Good authority boundary preservation.",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema_version"] == "program-adjudication-gepa-example-v1"
    assert payload["status"] == "curated_with_outcome_label"
    assert payload["label"]["usable_for_gepa_training"] is True
    assert gepa_example_out.exists()


def test_meta_adjudication_plan_tracks_present_sidecars(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    jury = build_program_jury_execution_result(
        manifest_path=candidate_root / "manifest.json"
    )
    jury_path = candidate_root / "jury_results.json"
    write_program_jury_execution_result(jury, jury_path)
    requirements_path = tmp_path / "jury_requirements.json"
    selection_path = tmp_path / "meta_jury_selection.json"
    jury_verification_path = tmp_path / "jury_verification.json"
    formation_path = tmp_path / "program_adjudicator_formation.json"
    adjudicator_verification_path = tmp_path / "program_adjudicator_verification.json"
    delegation_path = tmp_path / "program_adjudicator_delegation.json"
    requirements = build_program_jury_requirements(
        manifest_path=candidate_root / "manifest.json"
    )
    write_program_jury_requirements(requirements, requirements_path)
    selection = build_program_meta_jury_selection(
        jury_requirements_path=requirements_path
    )
    write_program_meta_jury_selection(selection, selection_path)
    jury_verification = build_program_jury_verification(
        jury_selection_path=selection_path
    )
    write_program_jury_verification(jury_verification, jury_verification_path)
    formation = build_program_adjudicator_formation(
        jury_verification_path=jury_verification_path
    )
    write_program_adjudicator_formation(formation, formation_path)
    adjudicator_verification = build_program_adjudicator_verification(
        adjudicator_formation_path=formation_path
    )
    write_program_adjudicator_verification(
        adjudicator_verification, adjudicator_verification_path
    )
    delegation = build_program_adjudicator_delegation(
        manifest_path=candidate_root / "manifest.json",
        adjudicator_verification_path=adjudicator_verification_path,
    )
    write_program_adjudicator_delegation(delegation, delegation_path)

    plan = build_program_meta_adjudication_plan(
        manifest_path=candidate_root / "manifest.json",
        jury_results_path=jury_path,
        program_adjudicator_delegation_path=delegation_path,
    )

    assert plan["sidecars"]["jury_results"]["status"] == "present"
    assert (
        plan["sidecars"]["jury_results"]["schema_version"] == "program-jury-results-v1"
    )
    assert plan["sidecars"]["program_adjudicator_delegation"]["status"] == "present"
    assert (
        plan["sidecars"]["program_adjudicator_delegation"]["schema_version"]
        == "program-adjudicator-delegation-v1"
    )
    assert "program_jury_results" not in plan["missing_evidence"]
    assert "program_adjudicator_delegation" not in plan["missing_evidence"]


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
