from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from dspx.cli.dspx import app
from dspx.services.program_promotion_decision import (
    build_generated_program_adjudicator_decision_record,
    write_program_promotion_decision_record,
)
from dspx.services.program_runtime_episode import run_program_runtime_episode
from dspx.services.program_meta_adjudication import (
    ProgramMetaAdjudicationError,
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
    write_program_adjudicator_delegation,
    write_program_adjudicator_formation,
    write_program_adjudicator_verification,
    write_program_evidence_adjudication,
    write_program_jury_requirements,
    write_program_jury_verification,
    write_program_meta_jury_selection,
)
from program_meta_adjudication_helpers import (
    _materialize_obsidian_like_candidate,
    _quarantined_negative_fixture,
    _write_generation_fitness_results,
    _write_generation_traceability,
    _write_minimal_activation_packet,
    runner,
)


def _remove_candidate_behavior_sidecars(candidate_root: Path) -> None:
    for name in ("behavior_results.json", "behavior_episode.json"):
        path = candidate_root / name
        if path.exists():
            path.unlink()


def _write_runtime_inputs(tmp_path: Path) -> Path:
    inputs_path = tmp_path / "runtime_inputs.json"
    inputs_path.write_text(
        json.dumps(
            {
                "marker_markdown": "# Close Reading\nUse source-grounded evidence.",
                "source_package_json": '{"source_id":"zotero:user:demo/DEMO2026"}',
                "existing_wiki_index_json": "{}",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return inputs_path


def _write_runtime_episode(candidate_root: Path, tmp_path: Path) -> Path:
    runtime_out = tmp_path / "runtime-episode"
    run_program_runtime_episode(
        manifest_path=candidate_root / "manifest.json",
        inputs_path=_write_runtime_inputs(tmp_path),
        outdir=runtime_out,
        skip_oracle_index=True,
    )
    return runtime_out / "runtime_episode.json"


def _write_verified_program_adjudicator(candidate_root: Path, tmp_path: Path) -> Path:
    requirements_path = tmp_path / "jury_requirements.json"
    selection_path = tmp_path / "meta_jury_selection.json"
    jury_verification_path = tmp_path / "jury_verification.json"
    formation_path = tmp_path / "program_adjudicator_formation.json"
    adjudicator_verification_path = tmp_path / "program_adjudicator_verification.json"

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
    return adjudicator_verification_path


def test_meta_adjudication_plan_tracks_target_fidelity_sidecars(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    traceability_path = candidate_root / "generation_traceability.json"
    fitness_results_path = candidate_root / "generation_fitness_results.json"
    _write_generation_traceability(traceability_path)
    _write_generation_fitness_results(fitness_results_path)

    plan = build_program_meta_adjudication_plan(
        manifest_path=candidate_root / "manifest.json"
    )

    assert plan["sidecars"]["generation_traceability"]["status"] == "present"
    assert plan["sidecars"]["generation_fitness_results"]["status"] == "present"
    assert (
        plan["target_profile"]["target_fidelity_evidence"]["fitness_results_status"]
        == "fitness_passed"
    )
    risk_ids = {risk["risk_id"] for risk in plan["target_profile"]["risks"]}
    assert "target_protocol_fidelity" in risk_ids
    perspectives = {
        item["perspective"]
        for item in plan["jury_requirements"]["required_perspectives"]
    }
    assert "target_protocol_fidelity" in perspectives
    commands = {item["step"]: item["command"] for item in plan["next_commands"]}
    assert "--generation-traceability" in commands["write_target_profile"]
    assert "--generation-fitness-results" in commands["write_target_profile"]
    assert "--target-profile" in commands["write_jury_requirements"]
    assert "--manifest" not in commands["write_jury_requirements"]
    assert "--generation-traceability" in commands["adjudicate_program_evidence"]
    assert "--generation-fitness-results" in commands["adjudicate_program_evidence"]


def test_quarantined_pdf_outputs_need_more_evidence_in_meta_adjudication(
    tmp_path: Path, monkeypatch
) -> None:
    fixture = _quarantined_negative_fixture()
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    requirements_path = tmp_path / "jury_requirements.json"
    selection_path = tmp_path / "meta_jury_selection.json"
    jury_verification_path = tmp_path / "jury_verification.json"
    formation_path = tmp_path / "program_adjudicator_formation.json"
    adjudicator_verification_path = tmp_path / "program_adjudicator_verification.json"

    requirements = build_program_jury_requirements(
        manifest_path=candidate_root / "manifest.json"
    )
    requirements["required_perspectives"].append(
        {
            "perspective": "target_protocol_fidelity",
            "reason": "quarantined pre-target-fidelity PDF outputs must not pass without generation fitness results",
        }
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

    adjudication = build_program_evidence_adjudication(
        adjudicator_verification_path=adjudicator_verification_path,
        manifest_path=candidate_root / "manifest.json",
    )

    assert adjudication["aggregate"]["ready_for_domain_decision"] is False
    assert (
        "target_protocol_fidelity" in adjudication["aggregate"]["blocking_perspectives"]
    )
    target_judgment = next(
        item
        for item in adjudication["role_judgments"]
        if item["perspective"] == "target_protocol_fidelity"
    )
    assert (
        target_judgment["judgment"]
        == fixture["required_rejection_contract"][
            "missing_generation_fitness_results_judgment"
        ]
    )
    assert target_judgment["missing_evidence"] == ["generation_fitness_results.json"]
    for record in fixture["records"]:
        assert record["expected_adjudication_judgment"] == target_judgment["judgment"]
        assert (
            record["expected_missing_evidence"] == target_judgment["missing_evidence"]
        )


def test_program_evidence_adjudication_withholds_failed_target_fitness(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    requirements_path = tmp_path / "jury_requirements.json"
    selection_path = tmp_path / "meta_jury_selection.json"
    jury_verification_path = tmp_path / "jury_verification.json"
    formation_path = tmp_path / "program_adjudicator_formation.json"
    adjudicator_verification_path = tmp_path / "program_adjudicator_verification.json"
    fitness_results_path = candidate_root / "generation_fitness_results.json"
    _write_generation_fitness_results(fitness_results_path, status="fitness_failed")

    requirements = build_program_jury_requirements(
        manifest_path=candidate_root / "manifest.json"
    )
    requirements["required_perspectives"].append(
        {
            "perspective": "target_protocol_fidelity",
            "reason": "verify target-fidelity fitness before domain review",
        }
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

    adjudication = build_program_evidence_adjudication(
        adjudicator_verification_path=adjudicator_verification_path,
        manifest_path=candidate_root / "manifest.json",
        generation_fitness_results_path=fitness_results_path,
    )

    assert adjudication["aggregate"]["ready_for_domain_decision"] is False
    assert (
        "target_protocol_fidelity" in adjudication["aggregate"]["blocking_perspectives"]
    )
    assert adjudication["evidence_refs"]["generation_fitness_results"] is not None
    target_judgment = next(
        item
        for item in adjudication["role_judgments"]
        if item["perspective"] == "target_protocol_fidelity"
    )
    assert target_judgment["judgment"] == "withhold"


def test_program_evidence_adjudication_consumes_runtime_episode(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    adjudicator_verification_path = _write_verified_program_adjudicator(
        candidate_root, tmp_path
    )
    runtime_episode_path = _write_runtime_episode(candidate_root, tmp_path)
    _remove_candidate_behavior_sidecars(candidate_root)

    adjudication = build_program_evidence_adjudication(
        adjudicator_verification_path=adjudicator_verification_path,
        manifest_path=candidate_root / "manifest.json",
        runtime_episode_path=runtime_episode_path,
    )

    runtime_ref = adjudication["evidence_refs"]["runtime_episode"]
    behavior_ref = adjudication["evidence_refs"]["behavior"]
    assert runtime_ref["schema_version"] == "program-runtime-episode-v1"
    assert behavior_ref["path"] == str(
        runtime_episode_path.parent / "behavior_results.json"
    )
    assert adjudication["behavior_summary"]["present"] is True
    behavior_judgment = next(
        item
        for item in adjudication["role_judgments"]
        if item["perspective"] == "behavior_evidence"
    )
    assert behavior_judgment["missing_evidence"] == []
    assert "behavior evidence" not in adjudication["aggregate"]["missing_evidence"]


def test_program_evidence_adjudication_rejects_behavior_results_hash_drift(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    adjudicator_verification_path = _write_verified_program_adjudicator(
        candidate_root, tmp_path
    )
    behavior_path = candidate_root / "behavior_results.json"
    behavior = json.loads(behavior_path.read_text(encoding="utf-8"))
    behavior["summary"]["status"] = "tampered"
    behavior_path.write_text(json.dumps(behavior, indent=2, sort_keys=True) + "\n")

    with pytest.raises(
        ProgramMetaAdjudicationError,
        match="behavior results sha256 does not match manifest behavior_results_hash",
    ):
        build_program_evidence_adjudication(
            adjudicator_verification_path=adjudicator_verification_path,
            manifest_path=candidate_root / "manifest.json",
            behavior_results_path=behavior_path,
        )


def test_program_evidence_adjudication_rejects_ambiguous_runtime_and_behavior_inputs(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    adjudicator_verification_path = _write_verified_program_adjudicator(
        candidate_root, tmp_path
    )
    runtime_episode_path = _write_runtime_episode(candidate_root, tmp_path)

    with pytest.raises(
        ProgramMetaAdjudicationError,
        match="runtime_episode cannot be combined with explicit behavior_results",
    ):
        build_program_evidence_adjudication(
            adjudicator_verification_path=adjudicator_verification_path,
            manifest_path=candidate_root / "manifest.json",
            runtime_episode_path=runtime_episode_path,
            behavior_results_path=candidate_root / "behavior_results.json",
        )


def test_program_evidence_adjudication_rejects_malformed_behavior_summary_counts(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    adjudicator_verification_path = _write_verified_program_adjudicator(
        candidate_root, tmp_path
    )
    behavior_path = candidate_root / "behavior_results.json"
    behavior = json.loads(behavior_path.read_text(encoding="utf-8"))
    behavior["summary"]["passed"] = "NaN"
    behavior_path.write_text(json.dumps(behavior, indent=2, sort_keys=True) + "\n")
    manifest_path = candidate_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["request"]["behavior_results_hash"] = hashlib.sha256(
        behavior_path.read_bytes()
    ).hexdigest()
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    with pytest.raises(
        ProgramMetaAdjudicationError,
        match="behavior summary passed must be an integer",
    ):
        build_program_evidence_adjudication(
            adjudicator_verification_path=adjudicator_verification_path,
            manifest_path=manifest_path,
            behavior_results_path=behavior_path,
        )


def test_program_evidence_adjudication_rejects_stale_runtime_episode(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    adjudicator_verification_path = _write_verified_program_adjudicator(
        candidate_root, tmp_path
    )
    runtime_episode_path = _write_runtime_episode(candidate_root, tmp_path)
    traces_path = runtime_episode_path.parent / "program_runtime_traces.json"
    traces = json.loads(traces_path.read_text(encoding="utf-8"))
    traces["sources"][0]["content_hash"] = "0" * 64
    traces_path.write_text(json.dumps(traces, indent=2, sort_keys=True) + "\n")

    with pytest.raises(
        ProgramMetaAdjudicationError,
        match="runtime episode program_runtime_traces_sha256 does not match current file",
    ):
        build_program_evidence_adjudication(
            adjudicator_verification_path=adjudicator_verification_path,
            manifest_path=candidate_root / "manifest.json",
            runtime_episode_path=runtime_episode_path,
        )


def test_program_evidence_adjudication_cli_accepts_runtime_episode(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    adjudicator_verification_path = _write_verified_program_adjudicator(
        candidate_root, tmp_path
    )
    runtime_episode_path = _write_runtime_episode(candidate_root, tmp_path)
    out = tmp_path / "program_evidence_adjudication.json"

    result = runner.invoke(
        app,
        [
            "program-promote",
            "evidence-adjudication",
            "--adjudicator-verification",
            str(adjudicator_verification_path),
            "--manifest",
            str(candidate_root / "manifest.json"),
            "--runtime-episode",
            str(runtime_episode_path),
            "--out",
            str(out),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["evidence_refs"]["runtime_episode"]["schema_version"] == (
        "program-runtime-episode-v1"
    )
    assert out.exists()


def test_program_evidence_adjudication_and_behavior_trace_sidecars(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    requirements_path = tmp_path / "jury_requirements.json"
    selection_path = tmp_path / "meta_jury_selection.json"
    jury_verification_path = tmp_path / "jury_verification.json"
    formation_path = tmp_path / "program_adjudicator_formation.json"
    adjudicator_verification_path = tmp_path / "program_adjudicator_verification.json"
    delegation_path = tmp_path / "program_adjudicator_delegation.json"
    activation_packet_path = candidate_root / "activation_packet.json"
    evidence_adjudication_path = tmp_path / "program_evidence_adjudication.json"
    trace_path = tmp_path / "adjudication_behavior_trace.json"

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
    _write_minimal_activation_packet(activation_packet_path)

    adjudication = build_program_evidence_adjudication(
        adjudicator_verification_path=adjudicator_verification_path,
        manifest_path=candidate_root / "manifest.json",
        activation_packet_path=activation_packet_path,
    )
    write_program_evidence_adjudication(adjudication, evidence_adjudication_path)
    decision_path = tmp_path / "promotion_decision_record.json"
    decision = build_generated_program_adjudicator_decision_record(
        evidence_adjudication_path=evidence_adjudication_path,
        adjudicator_delegation_path=delegation_path,
    )
    write_program_promotion_decision_record(decision, decision_path)
    trace = build_program_adjudication_behavior_trace(
        evidence_adjudication_path=evidence_adjudication_path,
        adjudicator_delegation_path=delegation_path,
        decision_record_path=decision_path,
    )
    write_program_adjudication_behavior_trace(trace, trace_path)

    assert adjudication["schema_version"] == "program-evidence-adjudication-v1"
    assert adjudication["status"] == "evidence_adjudicated"
    assert adjudication["non_authority"]["activation_authority"] is False
    assert adjudication["effect"]["provider_called"] is False
    assert adjudication["aggregate"]["activation_approved"] is False
    assert isinstance(adjudication["aggregate"]["ready_for_domain_decision"], bool)
    assert {item["perspective"] for item in adjudication["role_judgments"]} >= {
        "behavior_evidence",
        "authority_boundary",
    }

    assert trace["schema_version"] == "program-adjudication-behavior-trace-v1"
    assert trace["status"] == "trace_ready_for_publication_preflight"
    assert (
        trace["oracle_postgres_publication"]["shared_oracle_write_performed"] is False
    )
    assert trace["gepa_improvement_lane"]["activation_authority"] is False
    assert (
        trace["linked_artifacts"]["program_adjudicator_delegation"]["schema_version"]
        == "program-adjudicator-delegation-v1"
    )
    assert (
        trace["linked_artifacts"]["generated_program_adjudicator_decision"][
            "schema_version"
        ]
        == "program-promotion-decision-record-v1"
    )
    assert any(
        event["event"]
        == "dspx_meta_adjudicator_delegated_generated_program_adjudicator"
        for event in trace["trace_events"]
    )
    assert any(
        event["event"] == "generated_program_adjudicator_decided"
        for event in trace["trace_events"]
    )
    assert trace["judging_behavior"]["generated_program_adjudicator_id"] == (
        "dspx_program_adjudicator_v1"
    )
    assert (
        trace["judging_behavior"]["generated_program_decision_outcome"]
        == (decision["outcome"])
    )
    assert trace_path.exists()
    gepa_example = build_program_adjudication_gepa_example(trace_path=trace_path)
    assert (
        gepa_example["input"]["program_adjudicator_delegation"]["schema_version"]
        == "program-adjudicator-delegation-v1"
    )
    assert (
        gepa_example["input"]["generated_program_adjudicator_decision"][
            "schema_version"
        ]
        == "program-promotion-decision-record-v1"
    )

    assert decision["schema_version"] == "program-promotion-decision-record-v1"
    assert decision["status"] == "recorded"
    assert decision["decided_by"] == "dspx_program_adjudicator_v1"
    assert (
        decision["adjudicator_delegation"]["decided_by"] == "dspx_meta_adjudicator_v1"
    )
    expected_outcome = (
        "withhold"
        if adjudication["aggregate"]["ready_for_domain_decision"] is True
        else "request_more_evidence"
    )
    assert decision["outcome"] == expected_outcome
    assert decision["review_snapshot"]["ready_for_adjudicator_review"] is (
        adjudication["aggregate"]["ready_for_domain_decision"] is True
    )
    assert decision["non_authority"]["dspx_adjudicator_evidence_only"] is True
    assert decision["non_authority"]["promotion_authority"] is False
    assert decision["effect"]["governance_mutated"] is False
    assert decision_path.exists()


def test_generated_program_adjudicator_decision_uses_dspx_meta_delegation(
    tmp_path: Path,
) -> None:
    evidence_path = tmp_path / "program_evidence_adjudication.json"
    delegation_path = tmp_path / "program_adjudicator_delegation.json"
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "program-candidate-assembly-v1",
                "candidate_assembly": {"candidate_id": "prog-cand-ready"},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    evidence_path.write_text(
        json.dumps(
            {
                "schema_version": "program-evidence-adjudication-v1",
                "status": "evidence_adjudicated",
                "identity": {"candidate_id": "prog-cand-ready"},
                "aggregate": {
                    "recommendation": "ready_for_domain_decision_not_activation",
                    "ready_for_domain_decision": True,
                    "activation_approved": False,
                    "missing_evidence": ["canonical binding ref before rollout"],
                    "judgment_counts": {"supports_domain_review": 7},
                },
                "non_authority": {
                    "activation_authority": False,
                    "governance_authority": False,
                    "oracle_authority": False,
                    "promotion_authority": False,
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    delegation_path.write_text(
        json.dumps(
            {
                "schema_version": "program-adjudicator-delegation-v1",
                "status": "delegated",
                "dspx_meta_adjudicator": {"id": "dspx_meta_adjudicator_v1"},
                "generated_program_adjudicator": {
                    "id": "dspx_program_adjudicator_v1",
                    "kind": "ai_agent",
                    "approved_to_decide": True,
                    "decision_scope": "generated_program_local_promotion_decision_only",
                },
                "manifest": {
                    "path": str(manifest_path),
                    "sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                },
                "non_authority": {
                    "activation_authority": False,
                    "governance_authority": False,
                    "oracle_authority": False,
                    "promotion_authority": False,
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    decision = build_generated_program_adjudicator_decision_record(
        evidence_adjudication_path=evidence_path,
        adjudicator_delegation_path=delegation_path,
    )

    assert decision["outcome"] == "withhold"
    assert decision["decided_by"] == "dspx_program_adjudicator_v1"
    assert (
        decision["adjudicator_delegation"]["decided_by"] == "dspx_meta_adjudicator_v1"
    )
    assert decision["review_snapshot"]["ready_for_adjudicator_review"] is True
    assert (
        "canonical binding ref before rollout"
        in decision["review_snapshot"]["missing_required_evidence"]
    )
    assert decision["non_authority"]["promotion_authority"] is False


def test_program_evidence_adjudication_and_behavior_trace_cli_write_json(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    requirements_out = tmp_path / "jury-requirements.json"
    selection_out = tmp_path / "meta-jury-selection.json"
    jury_verification_out = tmp_path / "jury-verification.json"
    formation_out = tmp_path / "adjudicator-formation.json"
    adjudicator_verification_out = tmp_path / "adjudicator-verification.json"
    delegation_out = tmp_path / "adjudicator-delegation.json"
    activation_packet_path = candidate_root / "activation_packet.json"
    evidence_out = tmp_path / "evidence-adjudication.json"
    trace_out = tmp_path / "adjudication-trace.json"
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
    ):
        result = runner.invoke(app, args)
        assert result.exit_code == 0, result.output

    delegation_result = runner.invoke(
        app,
        [
            "program-promote",
            "adjudicator-delegation",
            "--manifest",
            str(candidate_root / "manifest.json"),
            "--adjudicator-verification",
            str(adjudicator_verification_out),
            "--out",
            str(delegation_out),
            "--json",
        ],
    )
    assert delegation_result.exit_code == 0, delegation_result.output

    adjudication_result = runner.invoke(
        app,
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
    )
    assert adjudication_result.exit_code == 0, adjudication_result.output
    adjudication_payload = json.loads(adjudication_result.output)
    assert adjudication_payload["schema_version"] == "program-evidence-adjudication-v1"
    assert adjudication_payload["aggregate"]["activation_approved"] is False

    decision_out = tmp_path / "generated-adjudicator-decision.json"
    decision_result = runner.invoke(
        app,
        [
            "program-promote",
            "generated-adjudicator-decision",
            "--evidence-adjudication",
            str(evidence_out),
            "--adjudicator-delegation",
            str(delegation_out),
            "--out",
            str(decision_out),
            "--json",
        ],
    )
    assert decision_result.exit_code == 0, decision_result.output
    decision_payload = json.loads(decision_result.output)
    assert decision_payload["schema_version"] == "program-promotion-decision-record-v1"
    assert decision_payload["decided_by"] == "dspx_program_adjudicator_v1"
    assert (
        decision_payload["adjudicator_delegation"]["decided_by"]
        == "dspx_meta_adjudicator_v1"
    )
    expected_outcome = (
        "withhold"
        if adjudication_payload["aggregate"]["ready_for_domain_decision"] is True
        else "request_more_evidence"
    )
    assert decision_payload["outcome"] == expected_outcome
    assert decision_payload["review_snapshot"]["ready_for_adjudicator_review"] is (
        adjudication_payload["aggregate"]["ready_for_domain_decision"] is True
    )
    assert decision_payload["non_authority"]["promotion_authority"] is False
    assert decision_out.exists()

    trace_result = runner.invoke(
        app,
        [
            "program-promote",
            "adjudication-behavior-trace",
            "--evidence-adjudication",
            str(evidence_out),
            "--adjudicator-delegation",
            str(delegation_out),
            "--decision-record",
            str(decision_out),
            "--out",
            str(trace_out),
            "--json",
        ],
    )
    assert trace_result.exit_code == 0, trace_result.output
    trace_payload = json.loads(trace_result.output)
    assert trace_payload["schema_version"] == "program-adjudication-behavior-trace-v1"
    assert (
        trace_payload["oracle_postgres_publication"]["shared_oracle_write_performed"]
        is False
    )
    assert (
        trace_payload["linked_artifacts"]["program_adjudicator_delegation"][
            "schema_version"
        ]
        == "program-adjudicator-delegation-v1"
    )
    assert (
        trace_payload["judging_behavior"]["generated_program_decision_outcome"]
        == decision_payload["outcome"]
    )
    assert trace_out.exists()

    manifest_before = (candidate_root / "manifest.json").read_bytes()
    with pytest.raises(
        ProgramMetaAdjudicationError, match="must not overwrite manifest.json"
    ):
        write_program_evidence_adjudication(
            adjudication_payload,
            candidate_root / "manifest.json",
        )
    with pytest.raises(ProgramMetaAdjudicationError, match="protected artifact root"):
        write_program_adjudication_behavior_trace(
            trace_payload,
            candidate_root / "unsafe_trace.json",
        )
    assert (candidate_root / "manifest.json").read_bytes() == manifest_before
    assert not (candidate_root / "unsafe_trace.json").exists()


def test_program_evidence_adjudication_rejects_unverified_adjudicator(
    tmp_path: Path, monkeypatch
) -> None:
    candidate_root = _materialize_obsidian_like_candidate(tmp_path, monkeypatch)
    adjudicator_verification_path = tmp_path / "bad-adjudicator-verification.json"
    adjudicator_verification_path.write_text(
        json.dumps(
            {
                "schema_version": "program-adjudicator-verification-v1",
                "status": "revise_program_adjudicator",
                "approved_for_program_evidence_adjudication": False,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must be verified"):
        build_program_evidence_adjudication(
            adjudicator_verification_path=adjudicator_verification_path,
            manifest_path=candidate_root / "manifest.json",
        )
