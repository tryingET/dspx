from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.coordinates import reset_embedding_engine
from dspx.services.program_candidate_state import (
    ProgramCandidateStateError,
    build_program_candidate_state,
)
from dspx.services.program_external_authority_export import (
    build_program_external_authority_export_preflight,
    write_program_external_authority_export_preflight,
)
from dspx.services.program_intent import ProgramIntent
from dspx.services.program_oracle_index import index_program_oracle_evidence_path
from dspx.services.program_oracle_report import build_program_oracle_evidence_report
from dspx.services.program_promotion_decision import (
    build_program_promotion_decision_record,
    write_program_promotion_decision_record,
)
from dspx.services.program_promotion_plan import build_program_promotion_plan
from dspx.services.program_promotion_refinement import build_program_promotion_refinement
from dspx.services.program_refinement import build_program_refinement_proposal
from dspx.services.program_refinement_workflow import (
    materialize_and_compare_refinement_candidate,
)
from dspx.services.program_service import materialize_program_from_intent

runner = CliRunner()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _file_hashes(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _setup_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "mock")
    reset_embedding_engine()


def _materialize_candidate_state_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path, dict[str, Path]]:
    _setup_env(tmp_path, monkeypatch)
    intent = ProgramIntent(
        name="TicketProgram",
        objective="Classify support ticket urgency.",
        inputs=["ticket_text"],
        outputs=["urgency"],
        metric="exact_match",
        constraints=["use only the supplied ticket text"],
        examples=[
            {
                "inputs": {"ticket_text": "Server is down for all users"},
                "outputs": {"urgency": "high"},
            }
        ],
        promotion={
            "adjudicator": {"kind": "human_operator", "id": "local_operator"},
            "external_authority": {
                "refs": [
                    {
                        "system": "agent_kernel",
                        "ref": "AK-EXAMPLE",
                        "role": "optional_authority_export_target",
                    }
                ]
            },
        },
    )
    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "program")
    source_root = Path(artifact.root_path)

    index_path = tmp_path / "oracle" / "coordinates.db"
    index_result = index_program_oracle_evidence_path(source_root, index_path=index_path)
    assert index_result["indexed"] == 1

    oracle_report = build_program_oracle_evidence_report(index_path=index_path)
    oracle_report_path = tmp_path / "oracle" / "program-evidence-report.json"
    _write_json(oracle_report_path, oracle_report)

    proposal = build_program_refinement_proposal(
        manifest_path=source_root / "manifest.json",
        oracle_report_path=oracle_report_path,
    )
    assert proposal["status"] == "proposed"
    proposal_path = tmp_path / "refinement" / "refinement_proposal.json"
    _write_json(proposal_path, proposal)

    review = build_program_promotion_refinement(
        manifest_path=source_root / "manifest.json",
        oracle_report_path=oracle_report_path,
        refinement_proposal_path=proposal_path,
    )
    review_path = tmp_path / "promotion" / "promotion_review_refined.json"
    _write_json(review_path, review)

    decision = build_program_promotion_decision_record(
        refined_review_path=review_path,
        outcome="request_more_evidence",
        decided_by="local_operator",
        rationale="Generate one bounded second candidate for observed mismatch.",
    )
    decision_path = tmp_path / "promotion" / "promotion_decision_record.json"
    write_program_promotion_decision_record(decision, decision_path)

    comparison_path = tmp_path / "refinement" / "candidate_comparison.json"
    workflow = materialize_and_compare_refinement_candidate(
        manifest_path=source_root / "manifest.json",
        refinement_proposal_path=proposal_path,
        decision_record_path=decision_path,
        outdir=tmp_path / "program-v2",
        comparison_out_path=comparison_path,
    )
    candidate_root = Path(workflow["generation"]["candidate"]["root_path"])
    assert (candidate_root / "manifest.json").exists()
    assert comparison_path.exists()

    promotion_plan = build_program_promotion_plan(
        manifest_path=candidate_root / "manifest.json",
        decision_record_path=decision_path,
        comparison_path=comparison_path,
        target="local_preferred_candidate",
        authority_owner="local_operator",
        review_path=review_path,
        source_manifest_path=source_root / "manifest.json",
    )
    promotion_plan_path = tmp_path / "promotion" / "promotion_plan.json"
    _write_json(promotion_plan_path, promotion_plan)

    export_preflight = build_program_external_authority_export_preflight(
        manifest_path=source_root / "manifest.json",
        external_ref="AK-EXAMPLE",
        decision_record_path=decision_path,
        comparison_path=comparison_path,
    )
    export_preflight_path = tmp_path / "export" / "ak-export-preflight.json"
    write_program_external_authority_export_preflight(
        export_preflight,
        export_preflight_path,
    )

    paths = {
        "oracle_report": oracle_report_path,
        "proposal": proposal_path,
        "review": review_path,
        "decision": decision_path,
        "comparison": comparison_path,
        "promotion_plan": promotion_plan_path,
        "export_preflight": export_preflight_path,
        "index": index_path,
    }
    return source_root, candidate_root, paths


def test_program_promote_status_writes_whole_candidate_truth_state_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root, candidate_root, paths = _materialize_candidate_state_inputs(
        tmp_path,
        monkeypatch,
    )
    before_source = _file_hashes(source_root)
    before_candidate = _file_hashes(candidate_root)
    before_sidecars = {name: _sha256(path) for name, path in paths.items()}
    out_path = tmp_path / "state" / "program_candidate_state.json"

    def forbid_subprocess_run(
        *_args: object, **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        raise AssertionError("candidate state summarization must not invoke subprocesses")

    monkeypatch.setattr(subprocess, "run", forbid_subprocess_run)

    result = runner.invoke(
        app,
        [
            "program-promote",
            "status",
            "--manifest",
            str(candidate_root / "manifest.json"),
            "--source-manifest",
            str(source_root / "manifest.json"),
            "--oracle-report",
            str(paths["oracle_report"]),
            "--refinement-proposal",
            str(paths["proposal"]),
            "--review",
            str(paths["review"]),
            "--decision-record",
            str(paths["decision"]),
            "--comparison",
            str(paths["comparison"]),
            "--promotion-plan",
            str(paths["promotion_plan"]),
            "--export-preflight",
            str(paths["export_preflight"]),
            "--out",
            str(out_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert out_path.exists()
    assert json.loads(out_path.read_text(encoding="utf-8")) == payload
    assert payload["schema_version"] == "program-candidate-state-v1"
    assert payload["status"] == "not_promoted_external_preflighted_not_applied"
    assert payload["state_id"].startswith("prog-cand-state-")
    assert payload["candidate_identity"]["candidate_id"]
    assert payload["source_identity"]["candidate_id"]
    assert payload["candidate_identity"] != payload["source_identity"]
    assert payload["candidate"] == {
        "root_path": str(candidate_root.resolve()),
        "artifact_kind": "program",
        "assembly_status": "materialized",
        "promotion_state": "not_promoted",
        "candidate_status": "exploratory",
        "program_gen_source_command": "program-gen",
    }
    assert payload["artifact_hashes"]["manifest_sha256"] == _sha256(
        candidate_root / "manifest.json"
    )
    assert payload["artifact_hashes"]["source_manifest_sha256"] == _sha256(
        source_root / "manifest.json"
    )
    assert payload["artifact_hashes"]["behavior_results_sha256"] == _sha256(
        candidate_root / "behavior_results.json"
    )
    assert payload["artifact_hashes"]["comparison_sha256"] == before_sidecars[
        "comparison"
    ]
    assert payload["artifact_hashes"]["export_preflight_sha256"] == before_sidecars[
        "export_preflight"
    ]

    evidence = payload["evidence_state"]
    assert evidence["behavior"]["present"] is True
    assert evidence["behavior"]["schema_version"] == "program-behavior-results-v1"
    assert evidence["behavior"]["example_count"] == 1
    assert evidence["execution_episode"]["present"] is True
    assert evidence["oracle_readability"]["present"] is True
    assert evidence["oracle_readability"]["oracle_invoked_by_program_gen"] is False
    assert evidence["oracle_report"] == {
        "present": True,
        "schema_version": "program-oracle-evidence-report-v1",
        "status": "ok",
        "total_records": 1,
        "interpretation_only": True,
    }
    assert evidence["refinement_proposal"]["present"] is True
    assert evidence["refinement_proposal"]["proposal_only"] is True

    promotion = payload["promotion_state"]
    assert promotion["review"]["present"] is True
    assert promotion["review"]["promotion_state"] == "not_promoted"
    assert promotion["review"]["ready_for_adjudicator_review"] is False
    assert promotion["decision"] == {
        "present": True,
        "schema_version": "program-promotion-decision-record-v1",
        "status": "recorded",
        "outcome": "request_more_evidence",
        "promotion_state_after_decision": "not_promoted",
        "external_authority_exported": False,
    }
    assert promotion["comparison"]["present"] is True
    assert promotion["comparison"]["manifest_role"] == "candidate"
    assert promotion["comparison"]["winner_selected"] is False
    assert promotion["promotion_plan"]["present"] is True
    assert promotion["promotion_plan"]["status"] == "planned_not_applied"
    assert promotion["promotion_plan"]["allowed_for_apply"] is False
    assert promotion["external_authority_export_preflight"]["present"] is True
    assert promotion["external_authority_export_preflight"]["status"] == (
        "ready_not_applied"
    )
    assert promotion["external_authority_export_preflight"]["ready_for_future_apply"] is False
    assert promotion["external_authority_export_preflight"]["ak_called"] is False
    assert (
        promotion["external_authority_export_preflight"][
            "external_authority_mutated"
        ]
        is False
    )
    assert "external_apply_not_implemented" in promotion[
        "external_authority_export_preflight"
    ]["blocking_reasons"]

    truth = payload["truth_summary"]
    assert truth["program_materialized"] is True
    assert truth["behavior_evidence_present"] is True
    assert truth["oracle_report_present"] is True
    assert truth["review_present"] is True
    assert truth["decision_record_present"] is True
    assert truth["comparison_present"] is True
    assert truth["promotion_plan_present"] is True
    assert truth["external_authority_preflight_present"] is True
    assert truth["promotion_applied"] is False
    assert truth["external_authority_mutated"] is False
    assert truth["governance_mutated"] is False
    assert truth["ak_called"] is False
    assert truth["winner_selected"] is False
    assert truth["automatic_promotion"] is False
    assert truth["ready_for_future_apply"] is False
    assert "future_apply_requires_exact_ak_target_contract" in truth[
        "required_next_steps"
    ]

    assert payload["effect"] == {
        "local_state_written": True,
        "program_files_mutated": False,
        "sidecar_inputs_mutated": False,
        "oracle_index_mutated": False,
        "ak_called": False,
        "external_authority_mutated": False,
        "governance_mutated": False,
        "promotion_state_changed": False,
    }
    assert payload["non_authority"] == {
        "state_summary_only": True,
        "preflight_only": True,
        "apply_promotion": False,
        "external_apply": False,
        "agent_kernel_mutation": False,
        "governance_authority": False,
        "promotion_authority": False,
        "oracle_authority": False,
        "winner_selection": False,
        "automatic_promotion": False,
    }

    second = tmp_path / "state" / "program_candidate_state_again.json"
    repeated = runner.invoke(
        app,
        [
            "program-promote",
            "status",
            "--manifest",
            str(candidate_root / "manifest.json"),
            "--source-manifest",
            str(source_root / "manifest.json"),
            "--oracle-report",
            str(paths["oracle_report"]),
            "--refinement-proposal",
            str(paths["proposal"]),
            "--review",
            str(paths["review"]),
            "--decision-record",
            str(paths["decision"]),
            "--comparison",
            str(paths["comparison"]),
            "--promotion-plan",
            str(paths["promotion_plan"]),
            "--export-preflight",
            str(paths["export_preflight"]),
            "--out",
            str(second),
            "--json",
        ],
    )
    assert repeated.exit_code == 0, repeated.output
    assert json.loads(repeated.stdout)["state_id"] == payload["state_id"]

    assert _file_hashes(source_root) == before_source
    assert _file_hashes(candidate_root) == before_candidate
    assert {name: _sha256(path) for name, path in paths.items()} == before_sidecars
    assert not (source_root / "program_candidate_state.json").exists()
    assert not (candidate_root / "program_candidate_state.json").exists()
    assert not (source_root / "eval_behavior.py").exists()
    assert not (candidate_root / "eval_behavior.py").exists()
    assert not (tmp_path / "generated" / "oracle" / "coordinates.db").exists()


def test_program_candidate_state_degrades_with_manifest_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    artifact = materialize_program_from_intent(
        ProgramIntent(
            name="StateOnlyProgram",
            objective="Answer a question.",
            inputs=["question"],
            outputs=["answer"],
        ),
        outdir=tmp_path / "program",
    )
    program_root = Path(artifact.root_path)
    before = _file_hashes(program_root)

    payload = build_program_candidate_state(manifest_path=program_root / "manifest.json")

    assert payload["schema_version"] == "program-candidate-state-v1"
    assert payload["status"] == "not_promoted_materialized"
    assert payload["evidence_state"]["behavior"] == {
        "present": False,
        "schema_version": None,
        "status": "insufficient_behavior_evidence",
        "example_count": 0,
        "status_counts": {},
        "sha256": None,
    }
    assert payload["promotion_state"]["decision"] == {
        "present": False,
        "status": "missing",
    }
    assert payload["promotion_state"]["external_authority_export_preflight"] == {
        "present": False,
        "status": "missing",
    }
    assert payload["truth_summary"]["behavior_evidence_present"] is False
    assert payload["truth_summary"]["external_authority_preflight_present"] is False
    assert "capture_behavior_evidence" in payload["truth_summary"]["required_next_steps"]
    assert payload["effect"]["local_state_written"] is False
    assert not (tmp_path / "oracle" / "coordinates.db").exists()
    assert _file_hashes(program_root) == before


def test_program_candidate_state_fails_closed_on_widened_preflight_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root, candidate_root, paths = _materialize_candidate_state_inputs(
        tmp_path,
        monkeypatch,
    )
    bad_preflight = json.loads(paths["export_preflight"].read_text(encoding="utf-8"))
    bad_preflight["effect"]["ak_called"] = True
    bad_preflight_path = tmp_path / "export" / "bad-preflight.json"
    _write_json(bad_preflight_path, bad_preflight)

    with pytest.raises(ProgramCandidateStateError, match="ak_called false"):
        build_program_candidate_state(
            manifest_path=candidate_root / "manifest.json",
            source_manifest_path=source_root / "manifest.json",
            decision_record_path=paths["decision"],
            comparison_path=paths["comparison"],
            export_preflight_path=bad_preflight_path,
        )
