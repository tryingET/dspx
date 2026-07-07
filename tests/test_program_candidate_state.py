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
from dspx.services.program_activation_packet import (
    build_generated_program_activation_packet,
    write_generated_program_activation_packet,
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
from dspx.services.program_meta_adjudication import (
    build_program_meta_adjudication_plan,
    write_program_meta_adjudication_plan,
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
    path: Path,
    *,
    manifest_path: Path,
    generation_fitness_results_path: Path,
    judgment: str = "supports_domain_review",
) -> Path:
    blocking = (
        [] if judgment == "supports_domain_review" else ["target_protocol_fidelity"]
    )
    _write_json(
        path,
        {
            "schema_version": "program-evidence-adjudication-v1",
            "status": "evidence_adjudicated",
            "authority": "program_evidence_adjudication_evidence_only_non_authoritative",
            "identity": _identity_from_manifest_path(manifest_path),
            "manifest": _artifact_ref(manifest_path),
            "evidence_refs": {
                "behavior": None,
                "oracle_report": None,
                "activation_packet": None,
                "generation_traceability": None,
                "generation_fitness_results": _artifact_ref(
                    generation_fitness_results_path
                ),
            },
            "aggregate": {
                "ready_for_domain_decision": False,
                "recommendation": "revise_or_collect_missing_evidence",
                "activation_approved": False,
                "judgment_counts": {judgment: 1},
                "blocking_perspectives": blocking,
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
                    "activation_authority": False,
                    "model_backed": False,
                    "provider_called": False,
                }
            ],
            "non_authority": {
                "activation_authority": False,
                "promotion_authority": False,
                "oracle_authority": False,
                "governance_authority": False,
                "external_authority": False,
                "external_mutation": False,
            },
            "effect": {
                "candidate_files_mutated": False,
                "canonical_target_mutated": False,
                "ak_mutated": False,
                "governance_mutated": False,
                "oracle_index_mutated": False,
                "shared_oracle_mutated": False,
                "provider_called": False,
            },
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


def _identity_from_manifest_path(manifest_path: Path) -> dict[str, str | None]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    request = manifest.get("request") or {}
    candidate = manifest.get("candidate_assembly") or {}
    execution = manifest.get("execution_episode") or {}
    receipt = manifest.get("receipt_bundle") or {}
    return {
        "request_id": request.get("request_id")
        or candidate.get("request_id")
        or execution.get("request_id")
        or receipt.get("request_id"),
        "candidate_id": candidate.get("candidate_id")
        or execution.get("candidate_id")
        or receipt.get("candidate_id"),
        "assembly_id": candidate.get("assembly_id")
        or execution.get("assembly_id")
        or receipt.get("assembly_id"),
        "episode_id": execution.get("episode_id") or receipt.get("episode_id"),
        "receipt_bundle_id": receipt.get("receipt_bundle_id"),
    }


def _artifact_ref(path: Path) -> dict[str, object]:
    return {
        "path": str(path.resolve()),
        "sha256": _sha256(path),
        "schema_version": json.loads(path.read_text(encoding="utf-8")).get(
            "schema_version"
        ),
    }


def _write_model_jury_results(
    path: Path,
    *,
    manifest_path: Path,
    authority_drift: bool = False,
    promotion_authority: bool = False,
) -> Path:
    identity = _identity_from_manifest_path(manifest_path)
    if authority_drift:
        identity = {**identity, "candidate_id": "wrong-candidate"}
    root = manifest_path.parent
    jury_path = root / "jury.json"
    selection_path = root / "jury_selection.json"
    rubric_path = root / "jury_rubric.json"
    evidence_entries = [
        _artifact_ref(item)
        for item in (root / "behavior_results.json", root / "behavior_episode.json")
        if item.exists()
    ]
    _write_json(
        path,
        {
            "schema_version": "program-model-jury-results-v1",
            "status": "executed",
            "identity": identity,
            "created_from": {
                "manifest_path": str(manifest_path.resolve()),
                "manifest_sha256": _sha256(manifest_path),
                "jury_path": str(jury_path.resolve()),
                "jury_sha256": _sha256(jury_path),
                "jury_selection_path": str(selection_path.resolve()),
                "jury_selection_sha256": _sha256(selection_path),
                "jury_rubric_path": str(rubric_path.resolve()),
                "jury_rubric_sha256": _sha256(rubric_path),
            },
            "jury": {
                "execution_mode": "provider_backed_model",
                "provider_backed_model_calls": True,
                "selected_juror_count": 1,
                "selected_perspectives": ["authority_boundaries"],
            },
            "adjudicator": {
                "repo": "target-repo",
                "promotion_authority": promotion_authority,
            },
            "evidence": {
                "entry_count": len(evidence_entries),
                "entries": evidence_entries,
            },
            "juror_results": [
                {
                    "juror_id": "authority_agent",
                    "perspective": "authority_boundaries",
                    "status": "judged",
                    "judgment": {"outcome": "request_more_evidence"},
                }
            ],
            "aggregate": {
                "judgment_counts": {
                    "supports_review_evidence": 0,
                    "withhold": 0,
                    "reject": 0,
                    "request_more_evidence": 1,
                    "failed": 0,
                },
                "recommendation": "request_more_evidence",
                "unique_improvement_requests": ["collect target evidence"],
            },
            "interpretation": {"ready_for_promotion_decision": False},
            "effect": {
                "model_jury_evidence_only": True,
                "program_files_mutated": False,
                "promotion_review_mutated": False,
                "new_candidate_generated": False,
                "oracle_index_mutated": False,
                "external_authority_mutated": False,
                "ak_mutated": False,
                "governance_mutated": False,
            },
            "non_authority": {
                "promotion_approval": False,
                "ranking_or_winner_selection": False,
                "domain_acceptance": False,
                "external_authority_apply": False,
                "canonical_mutation": False,
            },
        },
    )
    return path


def _write_gepa_refinement_result(
    path: Path, *, manifest_path: Path, authority_drift: bool = False
) -> Path:
    identity = _identity_from_manifest_path(manifest_path)
    if authority_drift:
        identity = {**identity, "candidate_id": "wrong-candidate"}
    optimizer_root = path.parent / "gepa_optimizer_output"
    optimizer_root.mkdir(parents=True, exist_ok=True)
    optimizer_payload_path = optimizer_root / "optimizer_state.json"
    optimizer_payload_path.write_text('{"weights": [1]}\n', encoding="utf-8")
    optimizer_payload_file = {
        "path": "optimizer_state.json",
        "sha256": hashlib.sha256(optimizer_payload_path.read_bytes()).hexdigest(),
        "size_bytes": optimizer_payload_path.stat().st_size,
    }
    optimizer_tree_text = json.dumps(
        [optimizer_payload_file], sort_keys=True, separators=(",", ":")
    )
    optimizer_manifest_path = optimizer_root / "manifest.json"
    _write_json(
        optimizer_manifest_path,
        {
            "schema_version": "dspy-gepa-optimizer-output-manifest-v1",
            "program": {
                "path": str(manifest_path.parent / "program.py"),
                "sha256": hashlib.sha256(
                    (manifest_path.parent / "program.py").read_bytes()
                ).hexdigest(),
            },
            "output_payload": {
                "hash_algorithm": "sha256",
                "tree_hash": hashlib.sha256(
                    optimizer_tree_text.encode("utf-8")
                ).hexdigest(),
                "files": [optimizer_payload_file],
                "excludes": ["manifest.json"],
            },
        },
    )
    optimizer_manifest_hash = hashlib.sha256(
        optimizer_manifest_path.read_bytes()
    ).hexdigest()
    _write_json(
        path,
        {
            "schema_version": "program-refinement-gepa-result-v1",
            "status": "degraded",
            "source_identity": identity,
            "evidence_inputs": {
                "source": "inline_examples",
                "train_examples_count": 1,
                "validation_examples_count": 1,
                "held_out_validation": False,
                "limitations": ["test fixture"],
            },
            "gepa": {
                "attempted": True,
                "status": "completed",
                "metric": "exact_match",
                "optimizer_metric": "exact",
                "max_metric_calls": 2,
                "prepared_inputs": {
                    "train_csv_path": "/tmp/train.csv",
                    "train_csv_sha256": "a" * 64,
                    "validation_csv_path": "/tmp/validation.csv",
                    "validation_csv_sha256": "b" * 64,
                },
            },
            "gepa_output": {
                "root_path": str(optimizer_root),
                "manifest_path": str(optimizer_manifest_path),
                "manifest_present": True,
                "manifest_valid": True,
                "manifest_sha256": optimizer_manifest_hash,
                "manifest_schema_version": None,
                "manifest_kind": "dspy_gepa_optimizer_output_manifest",
                "candidate_assembly_manifest": False,
                "readiness": {
                    "status": "optimizer_output_hash_bound_not_candidate",
                    "ready_for_future_candidate_materializer": True,
                    "blockers": [
                        "no_program_candidate_assembly_materializer_in_this_command"
                    ],
                },
            },
            "candidate": None,
            "effect": {
                "local_gepa_candidate_generated": False,
                "source_program_files_mutated": False,
                "source_dataset_artifacts_mutated": False,
                "external_authority_mutated": False,
                "governance_mutated": False,
            },
            "non_authority": {
                "local_refinement_only": True,
                "automatic_promotion": False,
                "oracle_ranking": False,
                "oracle_pruning": False,
                "oracle_promotion": False,
                "winner_selection": False,
                "external_authority_export": False,
                "governance_authority": False,
                "external_mutation": False,
            },
        },
    )
    return path


def _write_oracle_publication_preflight(root: Path, out: Path) -> Path:
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
    write_program_oracle_publication_preflight(preflight, out)
    return out


def _write_oracle_publication_receipt(root: Path, out: Path) -> Path:
    preflight_path = _write_oracle_publication_preflight(
        root,
        out.parent / "oracle_publication_preflight.json",
    )
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
    model_jury_results_path = _write_model_jury_results(
        tmp_path / "promotion" / "model_jury_results.json",
        manifest_path=candidate_root / "manifest.json",
    )

    gepa_refinement_path = _write_gepa_refinement_result(
        tmp_path / "refinement" / "gepa_refinement_result.json",
        manifest_path=source_root / "manifest.json",
    )

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

    meta_adjudication_plan = build_program_meta_adjudication_plan(
        manifest_path=source_root / "manifest.json",
        oracle_report_path=oracle_report_path,
        jury_results_path=jury_results_path,
        review_path=review_path,
        decision_record_path=decision_path,
    )
    meta_adjudication_plan_path = tmp_path / "promotion" / "meta_adjudication_plan.json"
    write_program_meta_adjudication_plan(
        meta_adjudication_plan,
        meta_adjudication_plan_path,
    )

    paths = {
        "oracle_report": oracle_report_path,
        "proposal": proposal_path,
        "review": review_path,
        "decision": decision_path,
        "jury_results": jury_results_path,
        "model_jury_results": model_jury_results_path,
        "comparison": comparison_path,
        "gepa_refinement": gepa_refinement_path,
        "promotion_plan": promotion_plan_path,
        "export_preflight": export_preflight_path,
        "meta_adjudication_plan": meta_adjudication_plan_path,
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
            "--model-jury-results",
            str(paths["model_jury_results"]),
            "--comparison",
            str(paths["comparison"]),
            "--gepa-refinement",
            str(paths["gepa_refinement"]),
            "--promotion-plan",
            str(paths["promotion_plan"]),
            "--export-preflight",
            str(paths["export_preflight"]),
            "--meta-adjudication-plan",
            str(paths["meta_adjudication_plan"]),
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
        payload["artifact_hashes"]["model_jury_results_sha256"]
        == before_sidecars["model_jury_results"]
    )
    assert (
        payload["artifact_hashes"]["comparison_sha256"] == before_sidecars["comparison"]
    )
    assert (
        payload["artifact_hashes"]["gepa_refinement_sha256"]
        == before_sidecars["gepa_refinement"]
    )
    assert (
        payload["artifact_hashes"]["export_preflight_sha256"]
        == before_sidecars["export_preflight"]
    )
    assert (
        payload["artifact_hashes"]["meta_adjudication_plan_sha256"]
        == before_sidecars["meta_adjudication_plan"]
    )

    assert payload["created_from"]["behavior_episode_path"] == str(
        (candidate_root / "behavior_episode.json").resolve()
    )
    assert payload["created_from"]["model_jury_results_path"] == str(
        paths["model_jury_results"].resolve()
    )
    assert payload["created_from"]["meta_adjudication_plan_path"] == str(
        paths["meta_adjudication_plan"].resolve()
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
    assert evidence["optimizer_refinement"] == {
        "present": True,
        "schema_version": "program-refinement-gepa-result-v1",
        "status": "degraded",
        "manifest_role": "source",
        "evidence_source": "inline_examples",
        "held_out_validation": False,
        "train_examples_count": 1,
        "validation_examples_count": 1,
        "gepa_attempted": True,
        "gepa_status": "completed",
        "optimizer_metric": "exact",
        "output_manifest_present": True,
        "output_manifest_valid": True,
        "output_manifest_sha256": json.loads(
            paths["gepa_refinement"].read_text(encoding="utf-8")
        )["gepa_output"]["manifest_sha256"],
        "output_readiness_status": "optimizer_output_hash_bound_not_candidate",
        "ready_for_future_candidate_materializer": True,
        "readiness_blockers": [
            "no_program_candidate_assembly_materializer_in_this_command"
        ],
        "candidate_materialized": False,
        "winner_selected": False,
        "promotion_authority": False,
    }

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
    assert promotion["jury_results"]["schema_version"] == "program-jury-results-v2"
    assert promotion["jury_results"]["status"] == "executed"
    assert promotion["jury_results"]["manifest_role"] == "candidate"
    assert promotion["jury_results"]["selected_juror_count"] >= 1
    assert promotion["jury_results"]["provider_backed_model_calls"] is False
    assert promotion["jury_results"]["behavior_evidence_present"] is True
    assert promotion["jury_results"]["promotion_authority"] is False
    assert promotion["jury_results"]["ready_for_promotion_decision"] is False
    assert promotion["model_jury_results"] == {
        "present": True,
        "schema_version": "program-model-jury-results-v1",
        "status": "executed",
        "manifest_role": "candidate",
        "execution_mode": "provider_backed_model",
        "provider_backed_model_calls": True,
        "selected_juror_count": 1,
        "selected_perspectives": ["authority_boundaries"],
        "judgment_counts": {
            "supports_review_evidence": 0,
            "withhold": 0,
            "reject": 0,
            "request_more_evidence": 1,
            "failed": 0,
        },
        "recommendation": "request_more_evidence",
        "improvement_request_count": 1,
        "adjudicator_repo": "target-repo",
        "ready_for_promotion_decision": False,
        "promotion_authority": False,
        "winner_selected": False,
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
    assert promotion["meta_adjudication_plan"]["present"] is True
    assert promotion["meta_adjudication_plan"]["status"] == "planned_not_executed"
    assert promotion["meta_adjudication_plan"]["lifecycle_state"] == (
        "meta_adjudication_plan_ready"
    )
    assert promotion["meta_adjudication_plan"]["provider_called"] is False
    assert promotion["meta_adjudication_plan"]["ak_mutated"] is False
    assert promotion["meta_adjudication_plan"]["promotion_authority"] is False
    assert "jury_results" in promotion["meta_adjudication_plan"]["present_sidecars"]
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
    assert truth["model_jury_results_present"] is True
    assert truth["comparison_present"] is True
    assert truth["promotion_plan_present"] is True
    assert truth["external_authority_preflight_present"] is True
    assert truth["meta_adjudication_plan_present"] is True
    assert truth["gepa_refinement_present"] is True
    assert truth["gepa_output_ready_for_future_candidate_materializer"] is True
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
            "--model-jury-results",
            str(paths["model_jury_results"]),
            "--comparison",
            str(paths["comparison"]),
            "--gepa-refinement",
            str(paths["gepa_refinement"]),
            "--promotion-plan",
            str(paths["promotion_plan"]),
            "--export-preflight",
            str(paths["export_preflight"]),
            "--meta-adjudication-plan",
            str(paths["meta_adjudication_plan"]),
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


def test_program_promote_status_summarizes_activation_packet_without_activation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root, candidate_root, paths = _materialize_candidate_state_inputs(
        tmp_path,
        monkeypatch,
    )
    before_source = _file_hashes(source_root)
    before_candidate = _file_hashes(candidate_root)
    activation_packet = build_generated_program_activation_packet(
        manifest_path=source_root / "manifest.json",
        owning_domain="softwareco/dspx-generated-program-governance",
        activation_target="local-dogfood-only",
        authority_owner="softwareco-program-governance",
        oracle_report_path=paths["oracle_report"],
        external_authority_export_preflight_path=paths["export_preflight"],
    )
    activation_path = tmp_path / "activation" / "activation_packet.json"
    write_generated_program_activation_packet(activation_packet, activation_path)
    out_path = tmp_path / "state" / "program_candidate_state.activation.json"

    result = runner.invoke(
        app,
        [
            "program-promote",
            "status",
            "--manifest",
            str(source_root / "manifest.json"),
            "--oracle-report",
            str(paths["oracle_report"]),
            "--export-preflight",
            str(paths["export_preflight"]),
            "--activation-packet",
            str(activation_path),
            "--out",
            str(out_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "not_promoted_activation_evidence_packet_present"
    assert payload["artifact_hashes"]["activation_packet_sha256"] == _sha256(
        activation_path
    )
    assert payload["created_from"]["activation_packet_path"] == str(
        activation_path.resolve()
    )
    activation_summary = payload["promotion_state"]["activation_packet"]
    assert activation_summary["present"] is True
    assert activation_summary["schema_version"] == (
        "generated-cognition-program-production-activation-packet-v1"
    )
    assert activation_summary["status"] == "blocked"
    assert activation_summary["next_required_action"] == "collect_missing_evidence"
    assert activation_summary["owning_domain"] == (
        "softwareco/dspx-generated-program-governance"
    )
    assert activation_summary["activation_target"] == "local-dogfood-only"
    assert activation_summary["authority_owner"] == "softwareco-program-governance"
    assert activation_summary["rollback_plan_present"] is False
    assert activation_summary["canonical_binding_ref"] is None
    assert "jury_evidence" in activation_summary["missing_required_evidence"]
    assert (
        "domain_decision_record" in activation_summary["remaining_activation_blockers"]
    )
    assert (
        "external_authority_export_preflight"
        in activation_summary["evidence_keys_present"]
    )
    assert activation_summary["activation_packet_only"] is True
    assert activation_summary["production_activation_applied"] is False
    assert activation_summary["ak_mutated"] is False
    assert activation_summary["external_authority_mutated"] is False
    assert payload["truth_summary"]["activation_packet_present"] is True
    assert payload["truth_summary"]["promotion_applied"] is False
    assert payload["truth_summary"]["ak_called"] is False
    assert payload["truth_summary"]["external_authority_mutated"] is False
    assert "collect_missing_evidence" in payload["truth_summary"]["required_next_steps"]
    assert _file_hashes(source_root) == before_source
    assert _file_hashes(candidate_root) == before_candidate


def test_program_candidate_state_rejects_stale_comparison_candidate_behavior_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root, candidate_root, paths = _materialize_candidate_state_inputs(
        tmp_path,
        monkeypatch,
    )
    comparison = json.loads(paths["comparison"].read_text(encoding="utf-8"))
    comparison["created_from"]["candidate_behavior_results_hash"] = "0" * 64
    _write_json(paths["comparison"], comparison)

    with pytest.raises(
        ProgramCandidateStateError, match="candidate_behavior_results_hash"
    ):
        build_program_candidate_state(
            manifest_path=candidate_root / "manifest.json",
            source_manifest_path=source_root / "manifest.json",
            comparison_path=paths["comparison"],
        )


def test_program_candidate_state_revalidates_comparison_when_current_manifest_is_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root, _candidate_root, paths = _materialize_candidate_state_inputs(
        tmp_path,
        monkeypatch,
    )
    comparison = json.loads(paths["comparison"].read_text(encoding="utf-8"))
    comparison["created_from"]["source_behavior_results_hash"] = "0" * 64
    _write_json(paths["comparison"], comparison)

    with pytest.raises(
        ProgramCandidateStateError, match="source_behavior_results_hash"
    ):
        build_program_candidate_state(
            manifest_path=source_root / "manifest.json",
            comparison_path=paths["comparison"],
        )


def test_program_candidate_state_rejects_stale_promotion_plan_comparison_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root, candidate_root, paths = _materialize_candidate_state_inputs(
        tmp_path,
        monkeypatch,
    )
    promotion_plan = json.loads(paths["promotion_plan"].read_text(encoding="utf-8"))
    promotion_plan["evidence_hashes"]["comparison_hash"] = "0" * 64
    _write_json(paths["promotion_plan"], promotion_plan)

    with pytest.raises(ProgramCandidateStateError, match="comparison_hash"):
        build_program_candidate_state(
            manifest_path=candidate_root / "manifest.json",
            source_manifest_path=source_root / "manifest.json",
            decision_record_path=paths["decision"],
            comparison_path=paths["comparison"],
            promotion_plan_path=paths["promotion_plan"],
        )


def test_program_candidate_state_rejects_promotion_plan_effect_authority_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root, candidate_root, paths = _materialize_candidate_state_inputs(
        tmp_path,
        monkeypatch,
    )
    promotion_plan = json.loads(paths["promotion_plan"].read_text(encoding="utf-8"))
    promotion_plan["effect"]["external_authority_mutated"] = True
    _write_json(paths["promotion_plan"], promotion_plan)

    with pytest.raises(ProgramCandidateStateError, match="external_authority_mutated"):
        build_program_candidate_state(
            manifest_path=candidate_root / "manifest.json",
            source_manifest_path=source_root / "manifest.json",
            decision_record_path=paths["decision"],
            comparison_path=paths["comparison"],
            promotion_plan_path=paths["promotion_plan"],
        )


def test_program_candidate_state_rejects_activation_packet_authority_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root, _candidate_root, _paths = _materialize_candidate_state_inputs(
        tmp_path,
        monkeypatch,
    )
    activation_packet = build_generated_program_activation_packet(
        manifest_path=source_root / "manifest.json",
        owning_domain="softwareco/dspx-generated-program-governance",
        activation_target="local-dogfood-only",
        authority_owner="softwareco-program-governance",
    )
    activation_packet["effect"]["production_activation_applied"] = True
    activation_path = tmp_path / "activation" / "activation_packet.spoofed.json"
    _write_json(activation_path, activation_packet)

    with pytest.raises(
        ProgramCandidateStateError,
        match="activation packet must record production_activation_applied false",
    ):
        build_program_candidate_state(
            manifest_path=source_root / "manifest.json",
            activation_packet_path=activation_path,
        )

    activation_packet["effect"]["production_activation_applied"] = False
    activation_packet["identity"] = {
        **activation_packet["identity"],
        "candidate_id": "drifted",
    }
    _write_json(activation_path, activation_packet)
    with pytest.raises(
        ProgramCandidateStateError,
        match="activation packet identity does not match candidate/source identity",
    ):
        build_program_candidate_state(
            manifest_path=source_root / "manifest.json",
            activation_packet_path=activation_path,
        )


def test_program_candidate_state_rejects_activation_packet_unsupported_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root, _candidate_root, _paths = _materialize_candidate_state_inputs(
        tmp_path,
        monkeypatch,
    )
    activation_packet = build_generated_program_activation_packet(
        manifest_path=source_root / "manifest.json",
        owning_domain="softwareco/dspx-generated-program-governance",
        activation_target="local-dogfood-only",
        authority_owner="softwareco-program-governance",
    )
    activation_packet["status"] = "activated"
    activation_path = tmp_path / "activation" / "activation_packet.status.json"
    _write_json(activation_path, activation_packet)

    with pytest.raises(
        ProgramCandidateStateError,
        match="activation packet status is unsupported",
    ):
        build_program_candidate_state(
            manifest_path=source_root / "manifest.json",
            activation_packet_path=activation_path,
        )


def test_program_candidate_state_rejects_stale_activation_packet_manifest_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root, _candidate_root, _paths = _materialize_candidate_state_inputs(
        tmp_path,
        monkeypatch,
    )
    manifest_path = source_root / "manifest.json"
    activation_packet = build_generated_program_activation_packet(
        manifest_path=manifest_path,
        owning_domain="softwareco/dspx-generated-program-governance",
        activation_target="local-dogfood-only",
        authority_owner="softwareco-program-governance",
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["stale_marker"] = "manifest changed after activation packet"
    _write_json(manifest_path, manifest)
    activation_path = tmp_path / "activation" / "activation_packet.stale.json"
    _write_json(activation_path, activation_packet)

    with pytest.raises(
        ProgramCandidateStateError,
        match="activation packet candidate manifest hash does not match current manifest",
    ):
        build_program_candidate_state(
            manifest_path=manifest_path,
            activation_packet_path=activation_path,
        )


def test_program_candidate_state_rejects_stale_activation_packet_evidence_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root, _candidate_root, paths = _materialize_candidate_state_inputs(
        tmp_path,
        monkeypatch,
    )
    activation_packet = build_generated_program_activation_packet(
        manifest_path=source_root / "manifest.json",
        owning_domain="softwareco/dspx-generated-program-governance",
        activation_target="local-dogfood-only",
        authority_owner="softwareco-program-governance",
        oracle_report_path=paths["oracle_report"],
    )
    paths["oracle_report"].write_text(
        paths["oracle_report"].read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )
    activation_path = tmp_path / "activation" / "activation_packet.stale_evidence.json"
    _write_json(activation_path, activation_packet)

    with pytest.raises(
        ProgramCandidateStateError,
        match="activation packet evidence hash does not match supplied oracle_report",
    ):
        build_program_candidate_state(
            manifest_path=source_root / "manifest.json",
            oracle_report_path=paths["oracle_report"],
            activation_packet_path=activation_path,
        )


def test_program_candidate_state_rejects_stale_export_preflight_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root, candidate_root, paths = _materialize_candidate_state_inputs(
        tmp_path,
        monkeypatch,
    )
    decision = json.loads(paths["decision"].read_text(encoding="utf-8"))
    decision["stale_marker"] = "decision changed after export preflight"
    _write_json(paths["decision"], decision)

    with pytest.raises(
        ProgramCandidateStateError,
        match="external authority export preflight decision_record_sha256 does not match supplied decision record",
    ):
        build_program_candidate_state(
            manifest_path=candidate_root / "manifest.json",
            source_manifest_path=source_root / "manifest.json",
            decision_record_path=paths["decision"],
            comparison_path=paths["comparison"],
            export_preflight_path=paths["export_preflight"],
        )


def test_program_candidate_state_rejects_export_preflight_idempotency_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root, candidate_root, paths = _materialize_candidate_state_inputs(
        tmp_path,
        monkeypatch,
    )
    preflight = json.loads(paths["export_preflight"].read_text(encoding="utf-8"))
    preflight["idempotency"]["artifact_hashes_fingerprint"] = "drifted"
    drifted_preflight_path = tmp_path / "export" / "ak-export-preflight.drifted.json"
    _write_json(drifted_preflight_path, preflight)

    with pytest.raises(
        ProgramCandidateStateError,
        match="external authority export preflight idempotency fingerprint mismatch",
    ):
        build_program_candidate_state(
            manifest_path=candidate_root / "manifest.json",
            source_manifest_path=source_root / "manifest.json",
            decision_record_path=paths["decision"],
            comparison_path=paths["comparison"],
            export_preflight_path=drifted_preflight_path,
        )


def test_program_candidate_state_rejects_activation_packet_missing_supplied_evidence_ref(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root, _candidate_root, paths = _materialize_candidate_state_inputs(
        tmp_path,
        monkeypatch,
    )
    activation_packet = build_generated_program_activation_packet(
        manifest_path=source_root / "manifest.json",
        owning_domain="softwareco/dspx-generated-program-governance",
        activation_target="local-dogfood-only",
        authority_owner="softwareco-program-governance",
        oracle_report_path=paths["oracle_report"],
    )
    activation_packet["evidence"].pop("oracle_report")
    activation_path = tmp_path / "activation" / "activation_packet.missing_ref.json"
    _write_json(activation_path, activation_packet)

    with pytest.raises(
        ProgramCandidateStateError,
        match="activation packet is missing supplied oracle_report evidence ref",
    ):
        build_program_candidate_state(
            manifest_path=source_root / "manifest.json",
            oracle_report_path=paths["oracle_report"],
            activation_packet_path=activation_path,
        )


def test_program_candidate_state_rejects_meta_adjudication_plan_identity_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root, candidate_root, paths = _materialize_candidate_state_inputs(
        tmp_path,
        monkeypatch,
    )
    bad_plan = json.loads(paths["meta_adjudication_plan"].read_text(encoding="utf-8"))
    bad_plan["identity"] = {**bad_plan["identity"], "candidate_id": "wrong"}
    bad_path = tmp_path / "promotion" / "bad_meta_adjudication_plan.json"
    _write_json(bad_path, bad_plan)

    with pytest.raises(
        ProgramCandidateStateError, match="meta-adjudication plan identity"
    ):
        build_program_candidate_state(
            manifest_path=candidate_root / "manifest.json",
            source_manifest_path=source_root / "manifest.json",
            meta_adjudication_plan_path=bad_path,
        )


def test_program_candidate_state_rejects_meta_adjudication_plan_authority_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root, candidate_root, paths = _materialize_candidate_state_inputs(
        tmp_path,
        monkeypatch,
    )
    bad_plan = json.loads(paths["meta_adjudication_plan"].read_text(encoding="utf-8"))
    bad_plan["non_authority"] = {
        **bad_plan["non_authority"],
        "promotion_authority": True,
    }
    bad_path = tmp_path / "promotion" / "bad_meta_authority.json"
    _write_json(bad_path, bad_plan)

    with pytest.raises(ProgramCandidateStateError, match="meta-adjudication plan"):
        build_program_candidate_state(
            manifest_path=candidate_root / "manifest.json",
            source_manifest_path=source_root / "manifest.json",
            meta_adjudication_plan_path=bad_path,
        )

    bad_plan = json.loads(paths["meta_adjudication_plan"].read_text(encoding="utf-8"))
    bad_plan["effect"] = {**bad_plan["effect"], "provider_called": True}
    bad_path = tmp_path / "promotion" / "bad_meta_effect.json"
    _write_json(bad_path, bad_plan)

    with pytest.raises(ProgramCandidateStateError, match="provider_called false"):
        build_program_candidate_state(
            manifest_path=candidate_root / "manifest.json",
            source_manifest_path=source_root / "manifest.json",
            meta_adjudication_plan_path=bad_path,
        )


def test_program_candidate_state_rejects_meta_adjudication_plan_stale_manifest_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root, candidate_root, paths = _materialize_candidate_state_inputs(
        tmp_path,
        monkeypatch,
    )
    bad_plan = json.loads(paths["meta_adjudication_plan"].read_text(encoding="utf-8"))
    bad_plan["manifest"] = {**bad_plan["manifest"], "sha256": "0" * 64}
    bad_path = tmp_path / "promotion" / "bad_meta_manifest_hash.json"
    _write_json(bad_path, bad_plan)

    with pytest.raises(ProgramCandidateStateError, match="manifest sha256"):
        build_program_candidate_state(
            manifest_path=candidate_root / "manifest.json",
            source_manifest_path=source_root / "manifest.json",
            meta_adjudication_plan_path=bad_path,
        )


def test_program_candidate_state_rejects_meta_adjudication_plan_stale_sidecar_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root, candidate_root, paths = _materialize_candidate_state_inputs(
        tmp_path,
        monkeypatch,
    )
    paths["jury_results"].write_text(
        paths["jury_results"].read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ProgramCandidateStateError,
        match="meta-adjudication plan jury_results sidecar sha256",
    ):
        build_program_candidate_state(
            manifest_path=candidate_root / "manifest.json",
            source_manifest_path=source_root / "manifest.json",
            jury_results_path=paths["jury_results"],
            meta_adjudication_plan_path=paths["meta_adjudication_plan"],
        )


def test_program_candidate_state_rejects_stale_jury_behavior_results_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root, candidate_root, paths = _materialize_candidate_state_inputs(
        tmp_path,
        monkeypatch,
    )
    bad_jury = json.loads(paths["jury_results"].read_text(encoding="utf-8"))
    bad_jury["created_from"] = {
        **bad_jury["created_from"],
        "behavior_results_sha256": "0" * 64,
    }
    bad_jury_path = tmp_path / "promotion" / "bad_jury_results_hash.json"
    _write_json(bad_jury_path, bad_jury)

    with pytest.raises(
        ProgramCandidateStateError,
        match="program jury results behavior results sha256",
    ):
        build_program_candidate_state(
            manifest_path=candidate_root / "manifest.json",
            source_manifest_path=source_root / "manifest.json",
            jury_results_path=bad_jury_path,
        )


def test_program_candidate_state_rejects_legacy_unbound_jury_results_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root, candidate_root, paths = _materialize_candidate_state_inputs(
        tmp_path,
        monkeypatch,
    )
    legacy_jury = json.loads(paths["jury_results"].read_text(encoding="utf-8"))
    legacy_jury["schema_version"] = "program-jury-results-v1"
    legacy_jury["created_from"].pop("manifest_sha256", None)
    legacy_jury_path = tmp_path / "promotion" / "legacy_jury_results.json"
    _write_json(legacy_jury_path, legacy_jury)

    with pytest.raises(
        ProgramCandidateStateError,
        match="program jury results schema_version must be program-jury-results-v2",
    ):
        build_program_candidate_state(
            manifest_path=candidate_root / "manifest.json",
            source_manifest_path=source_root / "manifest.json",
            jury_results_path=legacy_jury_path,
        )


def test_program_candidate_state_rejects_jury_paths_outside_bound_manifest_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root, candidate_root, paths = _materialize_candidate_state_inputs(
        tmp_path,
        monkeypatch,
    )
    bad_jury = json.loads(paths["jury_results"].read_text(encoding="utf-8"))
    bad_jury["created_from"] = {
        **bad_jury["created_from"],
        "jury_path": str((source_root / "jury.json").resolve()),
        "jury_sha256": _sha256(source_root / "jury.json"),
    }
    bad_jury_path = tmp_path / "promotion" / "bad_jury_path.json"
    _write_json(bad_jury_path, bad_jury)

    with pytest.raises(
        ProgramCandidateStateError,
        match="program jury results planned jury path is outside the bound manifest root",
    ):
        build_program_candidate_state(
            manifest_path=candidate_root / "manifest.json",
            source_manifest_path=source_root / "manifest.json",
            jury_results_path=bad_jury_path,
        )


def test_program_candidate_state_rejects_meta_adjudication_schema_mismatch_sidecar(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root, candidate_root, paths = _materialize_candidate_state_inputs(
        tmp_path,
        monkeypatch,
    )
    bad_plan = json.loads(paths["meta_adjudication_plan"].read_text(encoding="utf-8"))
    bad_plan["sidecars"]["jury_results"] = {
        **bad_plan["sidecars"]["jury_results"],
        "status": "schema_mismatch",
        "schema_version": "wrong-schema",
    }
    bad_plan_path = tmp_path / "promotion" / "bad_meta_schema_mismatch.json"
    _write_json(bad_plan_path, bad_plan)

    with pytest.raises(
        ProgramCandidateStateError,
        match="meta-adjudication plan jury_results sidecar must have present status",
    ):
        build_program_candidate_state(
            manifest_path=candidate_root / "manifest.json",
            source_manifest_path=source_root / "manifest.json",
            meta_adjudication_plan_path=bad_plan_path,
        )


def test_program_candidate_state_rejects_model_jury_identity_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _source_root, candidate_root, _paths = _materialize_candidate_state_inputs(
        tmp_path,
        monkeypatch,
    )
    bad_model_jury = _write_model_jury_results(
        tmp_path / "promotion" / "bad_model_jury_results.json",
        manifest_path=candidate_root / "manifest.json",
        authority_drift=True,
    )

    with pytest.raises(
        ProgramCandidateStateError,
        match="program model jury results identity does not match candidate/source identity",
    ):
        build_program_candidate_state(
            manifest_path=candidate_root / "manifest.json",
            model_jury_results_path=bad_model_jury,
        )


def test_program_candidate_state_rejects_model_jury_promotion_authority_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _source_root, candidate_root, _paths = _materialize_candidate_state_inputs(
        tmp_path,
        monkeypatch,
    )
    bad_model_jury = _write_model_jury_results(
        tmp_path / "promotion" / "bad_model_jury_results.json",
        manifest_path=candidate_root / "manifest.json",
        promotion_authority=True,
    )

    with pytest.raises(ProgramCandidateStateError, match="promotion authority"):
        build_program_candidate_state(
            manifest_path=candidate_root / "manifest.json",
            model_jury_results_path=bad_model_jury,
        )


def test_program_candidate_state_rejects_unjudged_model_jury_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _source_root, candidate_root, paths = _materialize_candidate_state_inputs(
        tmp_path,
        monkeypatch,
    )
    bad_payload = json.loads(paths["model_jury_results"].read_text(encoding="utf-8"))
    bad_payload["juror_results"] = [{"juror_id": "authority_agent", "status": "failed"}]
    bad_model_jury = tmp_path / "promotion" / "bad_model_jury_results.json"
    _write_json(bad_model_jury, bad_payload)

    with pytest.raises(ProgramCandidateStateError, match="judged juror"):
        build_program_candidate_state(
            manifest_path=candidate_root / "manifest.json",
            model_jury_results_path=bad_model_jury,
        )


def test_program_candidate_state_rejects_source_gepa_without_source_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _source_root, candidate_root, paths = _materialize_candidate_state_inputs(
        tmp_path,
        monkeypatch,
    )

    with pytest.raises(
        ProgramCandidateStateError,
        match="program GEPA refinement identity does not match candidate/source identity",
    ):
        build_program_candidate_state(
            manifest_path=candidate_root / "manifest.json",
            gepa_refinement_path=paths["gepa_refinement"],
        )


def test_program_candidate_state_rejects_gepa_refinement_identity_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _source_root, candidate_root, _paths = _materialize_candidate_state_inputs(
        tmp_path,
        monkeypatch,
    )
    bad_gepa = _write_gepa_refinement_result(
        tmp_path / "refinement" / "bad_gepa_refinement_result.json",
        manifest_path=candidate_root / "manifest.json",
        authority_drift=True,
    )

    with pytest.raises(
        ProgramCandidateStateError,
        match="program GEPA refinement identity does not match candidate/source identity",
    ):
        build_program_candidate_state(
            manifest_path=candidate_root / "manifest.json",
            gepa_refinement_path=bad_gepa,
        )


def test_program_candidate_state_rejects_spoofed_gepa_readiness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root, candidate_root, paths = _materialize_candidate_state_inputs(
        tmp_path,
        monkeypatch,
    )
    bad_payload = json.loads(paths["gepa_refinement"].read_text(encoding="utf-8"))
    bad_payload["status"] = "gepa_output_unverified"
    bad_payload["gepa_output"]["manifest_valid"] = False
    bad_payload["gepa_output"]["readiness"][
        "ready_for_future_candidate_materializer"
    ] = True
    bad_gepa = tmp_path / "refinement" / "bad_gepa_readiness.json"
    _write_json(bad_gepa, bad_payload)

    with pytest.raises(
        ProgramCandidateStateError,
        match="readiness conflicts with unverified status",
    ):
        build_program_candidate_state(
            manifest_path=candidate_root / "manifest.json",
            source_manifest_path=source_root / "manifest.json",
            gepa_refinement_path=bad_gepa,
        )


def test_program_candidate_state_rejects_gepa_refinement_candidate_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _source_root, candidate_root, paths = _materialize_candidate_state_inputs(
        tmp_path,
        monkeypatch,
    )
    bad_payload = json.loads(paths["gepa_refinement"].read_text(encoding="utf-8"))
    bad_payload["candidate"] = {"manifest_path": "fake-manifest.json"}
    bad_payload["effect"]["local_gepa_candidate_generated"] = True
    bad_gepa = tmp_path / "refinement" / "bad_gepa_candidate_claim.json"
    _write_json(bad_gepa, bad_payload)

    with pytest.raises(
        ProgramCandidateStateError,
        match="program GEPA refinement result must keep candidate null",
    ):
        build_program_candidate_state(
            manifest_path=candidate_root / "manifest.json",
            source_manifest_path=_source_root / "manifest.json",
            gepa_refinement_path=bad_gepa,
        )


def test_program_candidate_state_rejects_stale_gepa_optimizer_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root, candidate_root, paths = _materialize_candidate_state_inputs(
        tmp_path,
        monkeypatch,
    )
    bad_payload = json.loads(paths["gepa_refinement"].read_text(encoding="utf-8"))
    optimizer_manifest = Path(bad_payload["gepa_output"]["manifest_path"])
    manifest_payload = json.loads(optimizer_manifest.read_text(encoding="utf-8"))
    manifest_payload["program"]["sha256"] = "0" * 64
    _write_json(optimizer_manifest, manifest_payload)
    bad_payload["gepa_output"]["manifest_sha256"] = hashlib.sha256(
        optimizer_manifest.read_bytes()
    ).hexdigest()
    bad_gepa = tmp_path / "refinement" / "bad_gepa_optimizer_manifest.json"
    _write_json(bad_gepa, bad_payload)

    with pytest.raises(
        ProgramCandidateStateError,
        match="source program hash does not match source candidate",
    ):
        build_program_candidate_state(
            manifest_path=candidate_root / "manifest.json",
            source_manifest_path=source_root / "manifest.json",
            gepa_refinement_path=bad_gepa,
        )


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
    manifest_path = candidate_root / "manifest.json"
    adjudication_path = _write_program_evidence_adjudication(
        tmp_path / "target" / "program_evidence_adjudication.json",
        manifest_path=manifest_path,
        generation_fitness_results_path=fitness_path,
    )
    out_path = tmp_path / "state" / "program_candidate_state_target_ready.json"

    result = runner.invoke(
        app,
        [
            "program-promote",
            "status",
            "--manifest",
            str(manifest_path),
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


def test_program_promote_status_rejects_stale_target_adjudication_fitness_ref(
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
    manifest_path = candidate_root / "manifest.json"
    adjudication_path = _write_program_evidence_adjudication(
        tmp_path / "target" / "program_evidence_adjudication.json",
        manifest_path=manifest_path,
        generation_fitness_results_path=fitness_path,
    )
    payload = json.loads(adjudication_path.read_text(encoding="utf-8"))
    payload["evidence_refs"]["generation_fitness_results"]["sha256"] = "0" * 64
    _write_json(adjudication_path, payload)

    with pytest.raises(
        ProgramCandidateStateError,
        match="generation_fitness_results ref sha256 does not match current evidence",
    ):
        build_program_candidate_state(
            manifest_path=manifest_path,
            generation_fitness_results_path=fitness_path,
            program_evidence_adjudication_path=adjudication_path,
        )


def test_program_promote_status_rejects_wrong_candidate_target_adjudication(
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
    manifest_path = candidate_root / "manifest.json"
    adjudication_path = _write_program_evidence_adjudication(
        tmp_path / "target" / "program_evidence_adjudication.json",
        manifest_path=manifest_path,
        generation_fitness_results_path=fitness_path,
    )
    payload = json.loads(adjudication_path.read_text(encoding="utf-8"))
    payload["identity"]["candidate_id"] = "wrong-candidate"
    _write_json(adjudication_path, payload)

    with pytest.raises(
        ProgramCandidateStateError,
        match="identity does not match current manifest: candidate_id",
    ):
        build_program_candidate_state(
            manifest_path=manifest_path,
            generation_fitness_results_path=fitness_path,
            program_evidence_adjudication_path=adjudication_path,
        )


def test_program_promote_status_rejects_target_adjudication_authority_spoof(
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
    manifest_path = candidate_root / "manifest.json"
    adjudication_path = _write_program_evidence_adjudication(
        tmp_path / "target" / "program_evidence_adjudication.json",
        manifest_path=manifest_path,
        generation_fitness_results_path=fitness_path,
    )
    payload = json.loads(adjudication_path.read_text(encoding="utf-8"))
    payload["non_authority"]["promotion_authority"] = True
    payload["effect"]["provider_called"] = True
    _write_json(adjudication_path, payload)

    with pytest.raises(
        ProgramCandidateStateError,
        match="widens non-authority flags: promotion_authority",
    ):
        build_program_candidate_state(
            manifest_path=manifest_path,
            generation_fitness_results_path=fitness_path,
            program_evidence_adjudication_path=adjudication_path,
        )


def test_program_promote_status_binds_activation_packet_target_adjudication_refs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _source_root, candidate_root, _paths = _materialize_candidate_state_inputs(
        tmp_path,
        monkeypatch,
    )
    manifest_path = candidate_root / "manifest.json"
    fitness_path = _write_generation_fitness_results(
        tmp_path / "target" / "generation_fitness_results.json"
    )
    adjudication_path = _write_program_evidence_adjudication(
        tmp_path / "target" / "program_evidence_adjudication.json",
        manifest_path=manifest_path,
        generation_fitness_results_path=fitness_path,
    )
    activation_packet = build_generated_program_activation_packet(
        manifest_path=manifest_path,
        owning_domain="softwareco/dspx-generated-program-governance",
        activation_target="local-dogfood-only",
        authority_owner="softwareco-program-governance",
        generation_fitness_results_path=fitness_path,
        program_evidence_adjudication_path=adjudication_path,
    )
    activation_path = tmp_path / "activation" / "activation_packet.json"
    write_generated_program_activation_packet(activation_packet, activation_path)

    state = build_program_candidate_state(
        manifest_path=manifest_path,
        generation_fitness_results_path=fitness_path,
        program_evidence_adjudication_path=adjudication_path,
        activation_packet_path=activation_path,
    )

    assert state["promotion_state"]["activation_packet"]["present"] is True
    assert state["artifact_hashes"]["generation_fitness_results_sha256"] == _sha256(
        fitness_path
    )
    assert state["artifact_hashes"]["program_evidence_adjudication_sha256"] == _sha256(
        adjudication_path
    )


def test_program_promote_status_rejects_activation_packet_target_adjudication_hash_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _source_root, candidate_root, _paths = _materialize_candidate_state_inputs(
        tmp_path,
        monkeypatch,
    )
    manifest_path = candidate_root / "manifest.json"
    fitness_path = _write_generation_fitness_results(
        tmp_path / "target" / "generation_fitness_results.json"
    )
    adjudication_path = _write_program_evidence_adjudication(
        tmp_path / "target" / "program_evidence_adjudication.json",
        manifest_path=manifest_path,
        generation_fitness_results_path=fitness_path,
    )
    activation_packet = build_generated_program_activation_packet(
        manifest_path=manifest_path,
        owning_domain="softwareco/dspx-generated-program-governance",
        activation_target="local-dogfood-only",
        authority_owner="softwareco-program-governance",
        generation_fitness_results_path=fitness_path,
        program_evidence_adjudication_path=adjudication_path,
    )
    activation_packet["evidence"]["program_evidence_adjudication"]["sha256"] = "0" * 64
    activation_path = tmp_path / "activation" / "activation_packet.json"
    _write_json(activation_path, activation_packet)

    with pytest.raises(
        ProgramCandidateStateError,
        match="activation packet evidence hash does not match supplied program_evidence_adjudication",
    ):
        build_program_candidate_state(
            manifest_path=manifest_path,
            generation_fitness_results_path=fitness_path,
            program_evidence_adjudication_path=adjudication_path,
            activation_packet_path=activation_path,
        )


def test_program_promote_status_rejects_activation_packet_missing_target_adjudication_ref(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _source_root, candidate_root, _paths = _materialize_candidate_state_inputs(
        tmp_path,
        monkeypatch,
    )
    manifest_path = candidate_root / "manifest.json"
    fitness_path = _write_generation_fitness_results(
        tmp_path / "target" / "generation_fitness_results.json"
    )
    adjudication_path = _write_program_evidence_adjudication(
        tmp_path / "target" / "program_evidence_adjudication.json",
        manifest_path=manifest_path,
        generation_fitness_results_path=fitness_path,
    )
    activation_packet = build_generated_program_activation_packet(
        manifest_path=manifest_path,
        owning_domain="softwareco/dspx-generated-program-governance",
        activation_target="local-dogfood-only",
        authority_owner="softwareco-program-governance",
        generation_fitness_results_path=fitness_path,
        program_evidence_adjudication_path=adjudication_path,
    )
    activation_packet["evidence"].pop("program_evidence_adjudication")
    activation_path = tmp_path / "activation" / "activation_packet.json"
    _write_json(activation_path, activation_packet)

    with pytest.raises(
        ProgramCandidateStateError,
        match="activation packet is missing supplied program_evidence_adjudication evidence ref",
    ):
        build_program_candidate_state(
            manifest_path=manifest_path,
            generation_fitness_results_path=fitness_path,
            program_evidence_adjudication_path=adjudication_path,
            activation_packet_path=activation_path,
        )


def test_program_promote_status_rejects_activation_packet_target_fitness_hash_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _source_root, candidate_root, _paths = _materialize_candidate_state_inputs(
        tmp_path,
        monkeypatch,
    )
    manifest_path = candidate_root / "manifest.json"
    fitness_path = _write_generation_fitness_results(
        tmp_path / "target" / "generation_fitness_results.json"
    )
    adjudication_path = _write_program_evidence_adjudication(
        tmp_path / "target" / "program_evidence_adjudication.json",
        manifest_path=manifest_path,
        generation_fitness_results_path=fitness_path,
    )
    activation_packet = build_generated_program_activation_packet(
        manifest_path=manifest_path,
        owning_domain="softwareco/dspx-generated-program-governance",
        activation_target="local-dogfood-only",
        authority_owner="softwareco-program-governance",
        generation_fitness_results_path=fitness_path,
        program_evidence_adjudication_path=adjudication_path,
    )
    activation_packet["evidence"]["generation_fitness_results"]["sha256"] = "0" * 64
    activation_path = tmp_path / "activation" / "activation_packet.json"
    _write_json(activation_path, activation_packet)

    with pytest.raises(
        ProgramCandidateStateError,
        match="activation packet evidence hash does not match supplied generation_fitness_results",
    ):
        build_program_candidate_state(
            manifest_path=manifest_path,
            generation_fitness_results_path=fitness_path,
            program_evidence_adjudication_path=adjudication_path,
            activation_packet_path=activation_path,
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
        "preflight_present": False,
        "preflight_ready": False,
        "publication_id": publication["publication_id"],
        "evidence_ref_present": True,
        "evidence_only": True,
        "activation_authority": False,
        "promotion_authority": False,
    }
    assert payload["non_authority"]["promotion_authority"] is False
    assert payload["non_authority"]["oracle_authority"] is False


def test_program_candidate_state_includes_oracle_publication_preflight_for_activation_alignment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _source_root, candidate_root, _paths = _materialize_candidate_state_inputs(
        tmp_path,
        monkeypatch,
    )
    preflight_path = _write_oracle_publication_preflight(
        candidate_root,
        tmp_path / "oracle" / "publication_preflight.json",
    )
    fitness_path = _write_generation_fitness_results(
        tmp_path / "target" / "generation_fitness_results.json"
    )
    adjudication_path = _write_program_evidence_adjudication(
        tmp_path / "target" / "program_evidence_adjudication.json",
        manifest_path=candidate_root / "manifest.json",
        generation_fitness_results_path=fitness_path,
    )
    out_path = tmp_path / "state" / "program_candidate_state_with_preflight.json"

    result = runner.invoke(
        app,
        [
            "program-promote",
            "status",
            "--manifest",
            str(candidate_root / "manifest.json"),
            "--oracle-publication-preflight",
            str(preflight_path),
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
    preflight = payload["evidence_state"]["oracle_publication_preflight"]
    assert preflight["present"] is True
    assert (
        preflight["schema_version"] == "program-oracle-shared-publication-preflight-v1"
    )
    assert preflight["status"] == "ready_not_published"
    assert preflight["ready_for_shared_publication"] is True
    assert payload["shared_oracle_publication"]["preflight_present"] is True
    assert payload["shared_oracle_publication"]["preflight_ready"] is True
    assert payload["truth_summary"]["oracle_publication_preflight_present"] is True

    packet = build_generated_program_activation_packet(
        manifest_path=candidate_root / "manifest.json",
        owning_domain="test-domain",
        activation_target="test-target",
        authority_owner="test-authority",
        candidate_state_path=out_path,
        oracle_publication_preflight_path=preflight_path,
        generation_fitness_results_path=fitness_path,
        program_evidence_adjudication_path=adjudication_path,
    )

    assert (
        packet["evidence"]["oracle_publication_preflight"]["sha256"]
        == hashlib.sha256(preflight_path.read_bytes()).hexdigest()
    )
    alignment = packet["evidence_alignment"]["oracle_publication"]
    assert alignment["candidate_state_preflight_present"] is True
    assert alignment["preflight_ref_supplied"] is True
    assert alignment["receipt_ref_supplied"] is False
    assert alignment["publication_ids_aligned"] is True
    assert alignment["activation_authority"] is False


def test_program_candidate_state_rejects_oracle_publication_preflight_receipt_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _source_root, candidate_root, _paths = _materialize_candidate_state_inputs(
        tmp_path,
        monkeypatch,
    )
    preflight_path = _write_oracle_publication_preflight(
        candidate_root,
        tmp_path / "oracle" / "publication_preflight.json",
    )
    receipt_preflight_path = (
        tmp_path / "oracle" / "publication_preflight_for_receipt.json"
    )
    receipt_preflight = build_program_oracle_publication_preflight(
        manifest_path=candidate_root / "manifest.json",
        target="shared-postgres",
        publication_label="local_observed",
        publisher_id="pi-test",
        publisher_role="operator",
        publisher_assertion="share synthetic behavior evidence for future Oracle retrieval",
        redaction_status="checked",
        retention_class="retained_behavior_memory",
    )
    write_program_oracle_publication_preflight(
        receipt_preflight, receipt_preflight_path
    )
    receipt = publish_program_oracle_preflight(
        preflight_path=receipt_preflight_path,
        store=cast(CoordinateStore, FakeSharedOracleStore()),
    )
    receipt_path = tmp_path / "oracle" / "publication_receipt.json"
    write_program_oracle_publication_receipt(receipt, receipt_path)

    with pytest.raises(ProgramCandidateStateError, match="publication_id mismatch"):
        build_program_candidate_state(
            manifest_path=candidate_root / "manifest.json",
            oracle_publication_preflight_path=preflight_path,
            oracle_publication_receipt_path=receipt_path,
        )


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


def test_program_candidate_state_rejects_publication_receipt_record_authority_widening(
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
    receipt["record"]["non_authority"]["external_mutation"] = True
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(ProgramCandidateStateError, match="record widens non-authority"):
        build_program_candidate_state(
            manifest_path=candidate_root / "manifest.json",
            oracle_publication_receipt_path=receipt_path,
        )


def test_program_candidate_state_rejects_publication_receipt_record_drift(
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
    receipt["record"]["publication_label"] = "tampered"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(
        ProgramCandidateStateError,
        match="record does not match publication fields",
    ):
        build_program_candidate_state(
            manifest_path=candidate_root / "manifest.json",
            oracle_publication_receipt_path=receipt_path,
        )


def test_program_candidate_state_rejects_publication_receipt_preflight_hash_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _source_root, candidate_root, _paths = _materialize_candidate_state_inputs(
        tmp_path,
        monkeypatch,
    )
    preflight_path = _write_oracle_publication_preflight(
        candidate_root,
        tmp_path / "oracle" / "publication_preflight.json",
    )
    receipt = publish_program_oracle_preflight(
        preflight_path=preflight_path,
        store=cast(CoordinateStore, FakeSharedOracleStore()),
    )
    receipt_path = tmp_path / "oracle" / "publication_receipt.json"
    write_program_oracle_publication_receipt(receipt, receipt_path)
    receipt_payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt_payload["source"]["preflight_sha256"] = "0" * 64
    receipt_path.write_text(
        json.dumps(receipt_payload, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ProgramCandidateStateError, match="preflight_sha256"):
        build_program_candidate_state(
            manifest_path=candidate_root / "manifest.json",
            oracle_publication_preflight_path=preflight_path,
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


def test_program_candidate_state_rejects_noncanonical_output_inside_candidate_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    artifact = materialize_program_from_intent(
        ProgramIntent(
            name="StateRootGuardProgram",
            objective="Answer a question.",
            inputs=["question"],
            outputs=["answer"],
        ),
        outdir=tmp_path / "program",
    )
    program_root = Path(artifact.root_path)
    before = _file_hashes(program_root)

    result = runner.invoke(
        app,
        [
            "program-promote",
            "status",
            "--manifest",
            str(program_root / "manifest.json"),
            "--out",
            str(program_root / "state.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert (
        "candidate state output must not be written inside a protected artifact root"
        in result.output
    )
    assert not (program_root / "state.json").exists()
    assert _file_hashes(program_root) == before


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
