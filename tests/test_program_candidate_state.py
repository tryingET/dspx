from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest
from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.coordinates import CoordinateStore, ExecutionEmbedding, reset_embedding_engine
from dspx.services.program_candidate_state import (
    ProgramCandidateStateError,
    build_program_candidate_state,
)
from dspx.services.program_external_authority_export import (
    build_program_external_authority_export_preflight,
    write_program_external_authority_export_preflight,
)
from dspx.services.program_intent import ProgramIntent
from dspx.services.program_jury_execution import (
    build_program_jury_execution_result,
    write_program_jury_execution_result,
)
from dspx.services.program_oracle_index import index_program_oracle_evidence_path
from dspx.services.program_oracle_publication import (
    publish_program_oracle_preflight,
    write_program_oracle_publication_receipt,
)
from dspx.services.program_oracle_publication_preflight import (
    build_program_oracle_publication_preflight,
    write_program_oracle_publication_preflight,
)
from dspx.services.program_oracle_report import build_program_oracle_evidence_report
from dspx.services.program_promotion_decision import (
    build_program_promotion_decision_record,
    write_program_promotion_decision_record,
)
from dspx.services.program_promotion_plan import build_program_promotion_plan
from dspx.services.program_promotion_refinement import (
    build_program_promotion_refinement,
)
from dspx.services.program_refinement import build_program_refinement_proposal
from dspx.services.program_refinement_workflow import (
    materialize_and_compare_refinement_candidate,
)
from dspx.services.program_service import materialize_program_from_intent

runner = CliRunner()


class FakeSharedOracleStore:
    backend_name = "fake_shared_oracle"
    redacted_database_url = (
        "postgresql://dspx_oracle:<redacted>@example.invalid/dspx_oracle"
    )

    def __init__(self) -> None:
        self.records: dict[str, ExecutionEmbedding] = {}

    def upsert(self, embedding: ExecutionEmbedding) -> bool:
        self.records[embedding.run_id] = embedding
        return True


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")


def _write_generation_gate_preflight(path: Path, *, allowed: bool = True) -> Path:
    _write_json(
        path,
        {
            "schema_version": "gen-generation-gate-preflight-v1",
            "status": "generation_allowed" if allowed else "generation_blocked",
            "generation_allowed": allowed,
            "fail_closed_reasons": [] if allowed else ["insufficient_target_contract"],
        },
    )
    return path


def _write_generation_fitness_results(
    path: Path, *, status: str = "fitness_passed"
) -> Path:
    _write_json(
        path,
        {
            "schema_version": "gen-fitness-results-v1",
            "status": status,
            "rendered_state": "eligible_for_downstream_evidence_review"
            if status == "fitness_passed"
            else "withheld_for_target_protocol_failure",
            "identity": {
                "candidate_manifest_sha256": "candidate-sha",
                "target_contract_sha256": "contract-sha",
                "fitness_suite_sha256": "suite-sha",
            },
            "cases": [
                {
                    "case_id": "target-protocol-fidelity",
                    "status": "passed" if status == "fitness_passed" else "failed",
                    "evidence_refs": ["generation_traceability.json"],
                }
            ],
            "non_authority": {
                "activation_authority": False,
                "promotion_authority": False,
                "oracle_authority": False,
                "governance_authority": False,
                "external_mutation": False,
            },
            "effect": {
                "candidate_files_mutated": False,
                "canonical_target_mutated": False,
                "ak_mutated": False,
                "governance_mutated": False,
            },
        },
    )
    return path


def _write_program_evidence_adjudication(
    path: Path, *, judgment: str = "supports_domain_review"
) -> Path:
    _write_json(
        path,
        {
            "schema_version": "program-evidence-adjudication-v1",
            "status": "evidence_adjudicated",
            "aggregate": {
                "ready_for_domain_decision": False,
                "recommendation": "revise_or_collect_missing_evidence",
                "blocking_perspectives": []
                if judgment == "supports_domain_review"
                else ["target_protocol_fidelity"],
                "missing_evidence": [],
            },
            "role_judgments": [
                {
                    "perspective": "target_protocol_fidelity",
                    "judgment": judgment,
                    "missing_evidence": []
                    if judgment == "supports_domain_review"
                    else ["generation_fitness_results.json"],
                    "rationale": "target-fidelity result permits downstream evidence review only, not approval or activation",
                }
            ],
        },
    )
    return path


def _file_hashes(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_oracle_publication_receipt(root: Path, out: Path) -> Path:
    preflight_path = out.parent / "oracle_publication_preflight.json"
    preflight = build_program_oracle_publication_preflight(
        manifest_path=root / "manifest.json",
        target="shared-postgres",
        publication_label="retained",
        publisher_id="pi-test",
        publisher_role="operator",
        publisher_assertion="share synthetic behavior evidence for future Oracle retrieval",
        redaction_status="checked",
        retention_class="retained_behavior_memory",
    )
    write_program_oracle_publication_preflight(preflight, preflight_path)
    receipt = publish_program_oracle_preflight(
        preflight_path=preflight_path,
        store=cast(CoordinateStore, FakeSharedOracleStore()),
    )
    write_program_oracle_publication_receipt(receipt, out)
    return out


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
    index_result = index_program_oracle_evidence_path(
        source_root, index_path=index_path
    )
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

    jury_results = build_program_jury_execution_result(
        manifest_path=candidate_root / "manifest.json"
    )
    jury_results_path = tmp_path / "promotion" / "jury_results.json"
    write_program_jury_execution_result(jury_results, jury_results_path)

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
        "jury_results": jury_results_path,
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
        raise AssertionError(
            "candidate state summarization must not invoke subprocesses"
        )

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
            "--jury-results",
            str(paths["jury_results"]),
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
    assert payload["artifact_hashes"]["behavior_episode_sha256"] == _sha256(
        candidate_root / "behavior_episode.json"
    )
    assert (
        payload["artifact_hashes"]["jury_results_sha256"]
        == before_sidecars["jury_results"]
    )
    assert (
        payload["artifact_hashes"]["comparison_sha256"] == before_sidecars["comparison"]
    )
    assert (
        payload["artifact_hashes"]["export_preflight_sha256"]
        == before_sidecars["export_preflight"]
    )

    assert payload["created_from"]["behavior_episode_path"] == str(
        (candidate_root / "behavior_episode.json").resolve()
    )

    evidence = payload["evidence_state"]
    assert evidence["behavior"]["present"] is True
    assert evidence["behavior"]["schema_version"] == "program-behavior-results-v1"
    assert evidence["behavior"]["example_count"] == 1
    assert evidence["behavior_episode"]["present"] is True
    assert evidence["behavior_episode"]["schema_version"] == (
        "program-behavior-episode-v1"
    )
    assert evidence["behavior_episode"]["source_count"] == 1
    assert evidence["behavior_episode"]["sha256"] == _sha256(
        candidate_root / "behavior_episode.json"
    )
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
    assert promotion["jury_results"]["present"] is True
    assert promotion["jury_results"]["schema_version"] == "program-jury-results-v1"
    assert promotion["jury_results"]["status"] == "executed"
    assert promotion["jury_results"]["manifest_role"] == "candidate"
    assert promotion["jury_results"]["selected_juror_count"] >= 1
    assert promotion["jury_results"]["provider_backed_model_calls"] is False
    assert promotion["jury_results"]["behavior_evidence_present"] is True
    assert promotion["jury_results"]["promotion_authority"] is False
    assert promotion["jury_results"]["ready_for_promotion_decision"] is False
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
    assert (
        promotion["external_authority_export_preflight"]["ready_for_future_apply"]
        is False
    )
    assert promotion["external_authority_export_preflight"]["ak_called"] is False
    assert (
        promotion["external_authority_export_preflight"]["external_authority_mutated"]
        is False
    )
    assert promotion["external_authority_export_preflight"]["blocking_reasons"] == []
    assert (
        "external_apply_not_implemented"
        in promotion["external_authority_export_preflight"][
            "external_apply_blocking_reasons"
        ]
    )

    truth = payload["truth_summary"]
    assert truth["program_materialized"] is True
    assert truth["behavior_evidence_present"] is True
    assert truth["oracle_report_present"] is True
    assert truth["review_present"] is True
    assert truth["decision_record_present"] is True
    assert truth["jury_results_present"] is True
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
    assert (
        "future_apply_requires_exact_ak_target_contract" in truth["required_next_steps"]
    )

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
            "--jury-results",
            str(paths["jury_results"]),
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
    assert (source_root / "eval_behavior.py").exists()
    assert (candidate_root / "eval_behavior.py").exists()
    assert (source_root / "behavior_episode.json").exists()
    assert (candidate_root / "behavior_episode.json").exists()
    assert not (tmp_path / "generated" / "oracle" / "coordinates.db").exists()


def test_program_promote_status_reports_target_fidelity_admission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _source_root, candidate_root, _paths = _materialize_candidate_state_inputs(
        tmp_path,
        monkeypatch,
    )
    gate_path = _write_generation_gate_preflight(
        tmp_path / "target" / "generation_gate_preflight.json"
    )
    fitness_path = _write_generation_fitness_results(
        tmp_path / "target" / "generation_fitness_results.json"
    )
    adjudication_path = _write_program_evidence_adjudication(
        tmp_path / "target" / "program_evidence_adjudication.json"
    )
    out_path = tmp_path / "state" / "program_candidate_state_target_ready.json"

    result = runner.invoke(
        app,
        [
            "program-promote",
            "status",
            "--manifest",
            str(candidate_root / "manifest.json"),
            "--generation-gate-preflight",
            str(gate_path),
            "--generation-fitness-results",
            str(fitness_path),
            "--program-evidence-adjudication",
            str(adjudication_path),
            "--out",
            str(out_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    target = payload["target_fidelity_state"]
    assert target["generation_gate_preflight"]["generation_allowed"] is True
    assert target["generation_fitness_results"]["status"] == "fitness_passed"
    assert (
        target["generation_fitness_results"]["eligible_for_downstream_evidence_review"]
        is True
    )
    assert (
        target["target_protocol_fidelity_judgment"]["judgment"]
        == "supports_domain_review"
    )
    assert target["downstream_evidence_review_eligible"] is True
    assert target["obsidian_review_adapter_materialization_allowed"] is True
    assert target["production_or_domain_activation_allowed"] is False
    assert target["canonical_mutation_allowed"] is False
    assert payload["truth_summary"]["target_fidelity_evidence_present"] is True
    assert payload["truth_summary"]["target_protocol_adjudication_present"] is True
    assert (
        payload["truth_summary"]["obsidian_review_adapter_materialization_allowed"]
        is True
    )


def test_program_promote_status_blocks_adapter_admission_without_target_adjudication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _source_root, candidate_root, _paths = _materialize_candidate_state_inputs(
        tmp_path,
        monkeypatch,
    )
    fitness_path = _write_generation_fitness_results(
        tmp_path / "target" / "generation_fitness_results.json"
    )
    out_path = tmp_path / "state" / "program_candidate_state_target_missing_adj.json"

    state = build_program_candidate_state(
        manifest_path=candidate_root / "manifest.json",
        out_path=out_path,
        generation_fitness_results_path=fitness_path,
    )

    target = state["target_fidelity_state"]
    assert target["generation_fitness_results"]["status"] == "fitness_passed"
    assert target["target_protocol_fidelity_judgment"]["judgment"] == "missing"
    assert target["obsidian_review_adapter_materialization_allowed"] is False
    assert "target_protocol_fidelity_not_supported_by_adjudicator" in target["blockers"]
    assert state["truth_summary"]["target_protocol_adjudication_present"] is False


def test_program_candidate_state_includes_oracle_publication_ref_as_evidence_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root, candidate_root, paths = _materialize_candidate_state_inputs(
        tmp_path,
        monkeypatch,
    )
    receipt_path = _write_oracle_publication_receipt(
        candidate_root,
        tmp_path / "oracle" / "publication_receipt.json",
    )
    out_path = tmp_path / "state" / "program_candidate_state_with_publication.json"

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
            "--jury-results",
            str(paths["jury_results"]),
            "--comparison",
            str(paths["comparison"]),
            "--promotion-plan",
            str(paths["promotion_plan"]),
            "--export-preflight",
            str(paths["export_preflight"]),
            "--oracle-publication-receipt",
            str(receipt_path),
            "--out",
            str(out_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    publication = payload["evidence_state"]["oracle_publication_receipt"]
    assert publication["present"] is True
    assert publication["schema_version"] == (
        "program-oracle-shared-publication-receipt-v1"
    )
    assert publication["status"] == "published"
    assert publication["publication_id"].startswith("prog-oracle-pub-")
    assert publication["publication_label"] == "retained"
    assert publication["publication_label_class"] == "empirical"
    assert publication["shared_oracle_mutated"] is True
    assert publication["evidence_only"] is True
    assert publication["ak_called"] is False
    assert publication["governance_mutated"] is False
    assert publication["promotion_state_changed"] is False
    assert payload["truth_summary"]["oracle_publication_ref_present"] is True
    assert payload["truth_summary"]["promotion_applied"] is False
    assert payload["truth_summary"]["winner_selected"] is False
    assert payload["shared_oracle_publication"] == {
        "evidence_ref_present": True,
        "evidence_only": True,
        "activation_authority": False,
        "promotion_authority": False,
    }
    assert payload["non_authority"]["promotion_authority"] is False
    assert payload["non_authority"]["oracle_authority"] is False


def test_program_candidate_state_rejects_publication_receipt_authority_widening(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _source_root, candidate_root, _paths = _materialize_candidate_state_inputs(
        tmp_path,
        monkeypatch,
    )
    receipt_path = _write_oracle_publication_receipt(
        candidate_root,
        tmp_path / "oracle" / "publication_receipt.json",
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["non_authority"]["promotion_authority"] = True
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(ProgramCandidateStateError, match="promotion_authority"):
        build_program_candidate_state(
            manifest_path=candidate_root / "manifest.json",
            oracle_publication_receipt_path=receipt_path,
        )


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

    payload = build_program_candidate_state(
        manifest_path=program_root / "manifest.json"
    )

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
    assert payload["evidence_state"]["behavior_episode"] == {
        "present": False,
        "schema_version": None,
        "status": "insufficient_behavior_evidence",
        "source_count": 0,
        "example_count": 0,
        "status_counts": {},
        "sha256": None,
    }
    assert payload["promotion_state"]["decision"] == {
        "present": False,
        "status": "missing",
    }
    assert payload["promotion_state"]["jury_results"] == {
        "present": False,
        "status": "missing",
    }
    assert payload["promotion_state"]["external_authority_export_preflight"] == {
        "present": False,
        "status": "missing",
    }
    assert payload["truth_summary"]["behavior_evidence_present"] is False
    assert payload["truth_summary"]["external_authority_preflight_present"] is False
    assert (
        "capture_behavior_evidence" in payload["truth_summary"]["required_next_steps"]
    )
    assert payload["effect"]["local_state_written"] is False
    assert not (tmp_path / "oracle" / "coordinates.db").exists()
    assert _file_hashes(program_root) == before


def test_program_candidate_state_uses_behavior_episode_for_dataset_only_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    dataset_path = tmp_path / "data" / "tickets.jsonl"
    _write_jsonl(
        dataset_path,
        [
            {
                "inputs": {"ticket_text": f"ticket {index}"},
                "outputs": {"urgency": "high" if index % 2 else "low"},
            }
            for index in range(8)
        ],
    )
    artifact = materialize_program_from_intent(
        ProgramIntent(
            name="DatasetStateProgram",
            objective="Classify support ticket urgency.",
            inputs=["ticket_text"],
            outputs=["urgency"],
            metric="exact_match",
            dataset={
                "path": str(dataset_path),
                "input_fields": ["ticket_text"],
                "output_fields": ["urgency"],
                "split": {
                    "strategy": "ratio",
                    "train": 0.5,
                    "validation": 0.25,
                    "test": 0.25,
                    "seed": 7,
                },
            },
        ),
        outdir=tmp_path / "program",
    )
    program_root = Path(artifact.root_path)
    before = _file_hashes(program_root)
    behavior_episode = json.loads(
        (program_root / "behavior_episode.json").read_text(encoding="utf-8")
    )
    assert not (program_root / "behavior_results.json").exists()

    payload = build_program_candidate_state(
        manifest_path=program_root / "manifest.json"
    )

    assert payload["schema_version"] == "program-candidate-state-v1"
    assert payload["artifact_hashes"]["behavior_results_sha256"] is None
    assert payload["artifact_hashes"]["behavior_episode_sha256"] == _sha256(
        program_root / "behavior_episode.json"
    )
    assert payload["created_from"]["behavior_results_path"] is None
    assert payload["created_from"]["behavior_episode_path"] == str(
        (program_root / "behavior_episode.json").resolve()
    )
    assert payload["evidence_state"]["behavior"]["present"] is False
    episode_state = payload["evidence_state"]["behavior_episode"]
    assert episode_state["present"] is True
    assert episode_state["schema_version"] == "program-behavior-episode-v1"
    assert episode_state["status"] == behavior_episode["summary"]["status"]
    assert episode_state["source_count"] == behavior_episode["summary"]["source_count"]
    assert episode_state["example_count"] == behavior_episode["summary"]["total"]
    assert payload["truth_summary"]["behavior_evidence_present"] is True
    assert (
        "capture_behavior_evidence"
        not in payload["truth_summary"]["required_next_steps"]
    )
    assert _file_hashes(program_root) == before
    assert not (tmp_path / "generated" / "oracle" / "coordinates.db").exists()


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


def test_program_candidate_state_fails_closed_on_widened_jury_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root, candidate_root, paths = _materialize_candidate_state_inputs(
        tmp_path,
        monkeypatch,
    )
    bad_jury = json.loads(paths["jury_results"].read_text(encoding="utf-8"))
    bad_jury["non_authority"]["promotion_authority"] = True
    bad_jury_path = tmp_path / "promotion" / "bad-jury-results.json"
    _write_json(bad_jury_path, bad_jury)

    with pytest.raises(ProgramCandidateStateError, match="promotion_authority"):
        build_program_candidate_state(
            manifest_path=candidate_root / "manifest.json",
            source_manifest_path=source_root / "manifest.json",
            decision_record_path=paths["decision"],
            jury_results_path=bad_jury_path,
            comparison_path=paths["comparison"],
        )


def test_program_candidate_state_rejects_output_path_overwriting_candidate_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    artifact = materialize_program_from_intent(
        ProgramIntent(
            name="StateOverwriteGuardProgram",
            objective="Answer a question.",
            inputs=["question"],
            outputs=["answer"],
        ),
        outdir=tmp_path / "program",
    )
    program_root = Path(artifact.root_path)

    result = runner.invoke(
        app,
        [
            "program-promote",
            "status",
            "--manifest",
            str(program_root / "manifest.json"),
            "--out",
            str(program_root / "manifest.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "must not overwrite manifest.json" in result.output
    assert (
        json.loads((program_root / "manifest.json").read_text(encoding="utf-8"))[
            "schema_version"
        ]
        == "program-candidate-assembly-v1"
    )
