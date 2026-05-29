from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

import pytest
from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.coordinates import CoordinateStore, ExecutionEmbedding, reset_embedding_engine
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
from dspx.services.program_promotion_refinement import (
    build_program_promotion_refinement,
)
from dspx.services.program_refinement import build_program_refinement_proposal
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


def _file_hashes(root: Path) -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.iterdir())
        if path.is_file()
    }


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _candidate_identity(root: Path) -> dict[str, str | None]:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    candidate = manifest["candidate_assembly"]
    execution_episode = manifest["execution_episode"]
    receipt_bundle = manifest["receipt_bundle"]
    return {
        "request_id": candidate.get("request_id"),
        "candidate_id": candidate.get("candidate_id"),
        "assembly_id": candidate.get("assembly_id"),
        "episode_id": execution_episode.get("episode_id"),
        "receipt_bundle_id": receipt_bundle.get("receipt_bundle_id"),
    }


def _write_target_aware_candidate_state(root: Path, out: Path) -> Path:
    _write_json(
        out,
        {
            "schema_version": "program-candidate-state-v1",
            "status": "not_promoted_materialized",
            "candidate_identity": _candidate_identity(root),
            "target_fidelity_state": {
                "obsidian_review_adapter_materialization_allowed": True,
                "production_or_domain_activation_allowed": False,
                "canonical_mutation_allowed": False,
                "target_protocol_fidelity_judgment": {
                    "present": True,
                    "blocking": False,
                    "judgment": "supports_domain_review",
                },
            },
            "non_authority": {
                "agent_kernel_mutation": False,
                "apply_promotion": False,
                "automatic_promotion": False,
                "external_apply": False,
                "governance_authority": False,
                "oracle_authority": False,
                "promotion_authority": False,
                "winner_selection": False,
            },
        },
    )
    return out


def _write_canonical_binding_verification(
    decision_record_path: Path,
    out: Path,
    *,
    canonical_binding_ref: str = "ak://decision/123#accepted",
) -> Path:
    _write_json(
        out,
        {
            "schema_version": "program-canonical-binding-verification-v1",
            "status": "verified",
            "canonical_binding_ref": canonical_binding_ref,
            "binding_kind": "ak_decision",
            "decision_id": 123,
            "decision_record_sha256": hashlib.sha256(
                decision_record_path.read_bytes()
            ).hexdigest(),
            "ak_decision_state": "adr_recorded",
            "ak_decision_outcome": "accepted",
            "ak_decision_title": "Test decision",
            "authority_owner": "softwareco-program-governance",
            "effect": {
                "ak_read_only": True,
                "ak_mutated": False,
                "program_files_mutated": False,
                "external_authority_mutated": False,
                "production_activation_applied": False,
            },
            "non_authority": {
                "binding_verification_only": True,
                "production_activation_authority": False,
                "rollout_preflight_authority": False,
                "external_mutation": False,
            },
        },
    )
    return out


def _write_obsidian_adapter_receipt(candidate_state_path: Path, out: Path) -> Path:
    _write_json(
        out,
        {
            "schema_version": "dspy-pdf-transition-review-adapter-receipt-v1",
            "status": "materialized",
            "doc_id": "doc:test",
            "program_candidate_state_path": str(candidate_state_path.resolve()),
            "program_candidate_state_hash": "sha256:"
            + hashlib.sha256(candidate_state_path.read_bytes()).hexdigest(),
            "obsidian_review_adapter_materialization_allowed": True,
            "target_protocol_fidelity_judgment": "supports_domain_review",
            "canonical_mutation_performed": False,
            "wiki_mutation_performed": False,
            "atlas_mutation_performed": False,
            "zotero_mutation_performed": False,
            "source_package_mutation_performed": False,
            "puzzle_register_mutation_performed": False,
            "external_mutation_performed": False,
            "written_files": [
                "_System/review/proposals/pdf-transition/doc:test/review.html"
            ],
        },
    )
    return out


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
        root, out.parent / "oracle_publication_preflight.json"
    )
    receipt = publish_program_oracle_preflight(
        preflight_path=preflight_path,
        store=cast(CoordinateStore, FakeSharedOracleStore()),
    )
    write_program_oracle_publication_receipt(receipt, out)
    return out


def _write_candidate_state_with_publication_preflight(
    root: Path, preflight_path: Path, out: Path
) -> Path:
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    _write_json(
        out,
        {
            "schema_version": "program-candidate-state-v1",
            "status": "not_promoted_materialized",
            "candidate_identity": _candidate_identity(root),
            "evidence_state": {
                "oracle_publication_preflight": {
                    "present": True,
                    "schema_version": "program-oracle-shared-publication-preflight-v1",
                    "status": "ready_not_published",
                    "publication_id": preflight["publication_id"],
                    "ready_for_shared_publication": True,
                    "blocking_reasons": [],
                    "runtime_trace_semantics_valid": True,
                    "runtime_trace_hash_match": True,
                    "shared_oracle_mutated": False,
                    "preflight_only": True,
                },
                "oracle_publication_receipt": {"present": False, "status": "missing"},
            },
            "shared_oracle_publication": {
                "preflight_present": True,
                "preflight_ready": True,
                "evidence_ref_present": False,
                "evidence_only": True,
                "activation_authority": False,
                "promotion_authority": False,
            },
            "non_authority": {
                "agent_kernel_mutation": False,
                "apply_promotion": False,
                "automatic_promotion": False,
                "external_apply": False,
                "governance_authority": False,
                "oracle_authority": False,
                "promotion_authority": False,
                "winner_selection": False,
            },
        },
    )
    return out


def _setup_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "mock")
    reset_embedding_engine()


def _materialize_program(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    _setup_env(tmp_path, monkeypatch)
    intent = ProgramIntent(
        name="ActivationTicketProgram",
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
    )
    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "program")
    return Path(artifact.root_path)


def _materialize_review_chain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path, Path, Path, Path]:
    program_root = _materialize_program(tmp_path, monkeypatch)

    index_path = tmp_path / "oracle" / "coordinates.db"
    index_result = index_program_oracle_evidence_path(
        program_root,
        index_path=index_path,
    )
    assert index_result["indexed"] == 1
    assert index_result["errors"] == 0
    report = build_program_oracle_evidence_report(index_path=index_path)
    report_path = tmp_path / "oracle" / "program-evidence-report.json"
    _write_json(report_path, report)

    jury_result = build_program_jury_execution_result(
        manifest_path=program_root / "manifest.json",
    )
    jury_path = tmp_path / "promotion" / "jury_results.json"
    write_program_jury_execution_result(jury_result, jury_path)

    proposal = build_program_refinement_proposal(
        manifest_path=program_root / "manifest.json",
        oracle_report_path=report_path,
    )
    proposal_path = tmp_path / "refinement" / "refinement_proposal.json"
    _write_json(proposal_path, proposal)

    refined_review = build_program_promotion_refinement(
        manifest_path=program_root / "manifest.json",
        oracle_report_path=report_path,
        refinement_proposal_path=proposal_path,
    )
    review_path = tmp_path / "promotion" / "promotion_review_refined.json"
    _write_json(review_path, refined_review)

    decision = build_program_promotion_decision_record(
        refined_review_path=review_path,
        outcome="request_more_evidence",
        decided_by="softwareco-program-governance",
        rationale="Dogfood activation remains blocked until a production domain accepts more evidence.",
    )
    decision_path = tmp_path / "promotion" / "promotion_decision_record.json"
    write_program_promotion_decision_record(decision, decision_path)

    return program_root, report_path, jury_path, review_path, decision_path


def test_program_promote_activation_packet_blocks_without_required_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_program(tmp_path, monkeypatch)
    before_hashes = _file_hashes(program_root)
    out_path = tmp_path / "activation" / "activation_packet.json"

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--out",
            str(out_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert json.loads(out_path.read_text(encoding="utf-8")) == payload
    assert payload["schema_version"] == (
        "generated-cognition-program-production-activation-packet-v1"
    )
    assert payload["transition_type"] == (
        "generated-cognition-program.production_activation"
    )
    assert payload["status"] == "blocked"
    assert payload["owning_domain"] == "softwareco/dspx-generated-program-governance"
    assert payload["activation_target"] == "local-dogfood-only"
    assert "oracle_report" in payload["missing_required_evidence"]
    assert "jury_results" in payload["missing_required_evidence"]
    assert "refined_promotion_review" in payload["missing_required_evidence"]
    assert "rollout_owner" in payload["missing_required_evidence"]
    assert "rollback_plan" in payload["missing_required_evidence"]
    assert payload["boundary_checks"] == {
        "mlflow_approval_authority": False,
        "oracle_promotion_authority": False,
        "oracle_publication_activation_authority": False,
        "jury_promotion_authority": False,
        "dspx_activation_authority": False,
        "requires_domain_governing_body": True,
        "requires_rollout_owner_before_rollout": True,
        "requires_rollback_plan_before_rollout": True,
        "requires_canonical_binding_before_rollout": True,
        "requires_obsidian_review_adapter_when_requested": False,
    }
    assert payload["non_authority"]["activation_packet_only"] is True
    assert payload["effect"]["production_activation_applied"] is False
    assert _file_hashes(program_root) == before_hashes
    assert not (program_root / "activation_packet.json").exists()


def test_program_promote_activation_packet_requires_obsidian_review_adapter_when_requested(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_program(tmp_path, monkeypatch)
    out_path = tmp_path / "activation" / "activation_packet.json"

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "obsidian/pdf-transition",
            "--activation-target",
            "obsidian-pdf-transition-generated-program-runtime",
            "--authority-owner",
            "obsidian-pdf-transition-governance",
            "--require-obsidian-review-adapter",
            "--out",
            str(out_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "blocked"
    assert (
        "target_aware_candidate_state_missing" in payload["missing_required_evidence"]
    )
    assert (
        "obsidian_review_adapter_receipt_missing"
        in payload["missing_required_evidence"]
    )
    assert payload["target_review_admission"] == {
        "candidate_state": None,
        "obsidian_review_adapter_receipt": None,
        "target_protocol_fidelity_judgment": None,
        "review_adapter_materialization_allowed": False,
        "review_packet_materialized": False,
        "review_only": True,
        "production_activation_authority": False,
        "canonical_mutation_authority": False,
        "canonical_mutation_allowed": False,
        "status": "blocked",
        "blockers": [
            "target_aware_candidate_state_missing",
            "obsidian_review_adapter_receipt_missing",
        ],
    }
    assert "domain_decision_record" in payload["remaining_activation_blockers"]
    assert "canonical_binding_ref" in payload["remaining_activation_blockers"]
    assert payload["effect"]["production_activation_applied"] is False


def test_program_promote_activation_packet_records_obsidian_review_admission_without_activation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_program(tmp_path, monkeypatch)
    candidate_state_path = _write_target_aware_candidate_state(
        program_root,
        tmp_path / "activation" / "program_candidate_state.json",
    )
    adapter_receipt_path = _write_obsidian_adapter_receipt(
        candidate_state_path,
        tmp_path / "activation" / "adapter-receipt.json",
    )
    out_path = tmp_path / "activation" / "activation_packet.json"

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "obsidian/pdf-transition",
            "--activation-target",
            "obsidian-pdf-transition-generated-program-runtime",
            "--authority-owner",
            "obsidian-pdf-transition-governance",
            "--candidate-state",
            str(candidate_state_path),
            "--obsidian-review-adapter-receipt",
            str(adapter_receipt_path),
            "--require-obsidian-review-adapter",
            "--out",
            str(out_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "blocked"
    assert (
        "target_aware_candidate_state_missing"
        not in payload["missing_required_evidence"]
    )
    assert (
        "obsidian_review_adapter_receipt_missing"
        not in payload["missing_required_evidence"]
    )
    assert payload["target_review_admission"]["status"] == "review_admitted"
    assert (
        payload["target_review_admission"]["target_protocol_fidelity_judgment"]
        == "supports_domain_review"
    )
    assert (
        payload["target_review_admission"]["review_adapter_materialization_allowed"]
        is True
    )
    assert payload["target_review_admission"]["review_packet_materialized"] is True
    assert (
        payload["target_review_admission"]["production_activation_authority"] is False
    )
    assert payload["target_review_admission"]["canonical_mutation_authority"] is False
    assert payload["target_review_admission"]["blockers"] == []
    assert (
        "target_aware_candidate_state_missing"
        not in payload["remaining_activation_blockers"]
    )
    assert (
        "obsidian_review_adapter_receipt_missing"
        not in payload["remaining_activation_blockers"]
    )
    assert "domain_decision_record" in payload["remaining_activation_blockers"]
    assert "canonical_binding_ref" in payload["remaining_activation_blockers"]
    assert payload["evidence"]["candidate_state"]["path"] == str(
        candidate_state_path.resolve()
    )
    assert payload["evidence"]["obsidian_review_adapter_receipt"]["path"] == str(
        adapter_receipt_path.resolve()
    )
    assert payload["effect"]["production_activation_applied"] is False


def test_program_promote_activation_packet_rejects_obsidian_adapter_authority_widening(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_program(tmp_path, monkeypatch)
    candidate_state_path = _write_target_aware_candidate_state(
        program_root,
        tmp_path / "activation" / "program_candidate_state.json",
    )
    adapter_receipt_path = _write_obsidian_adapter_receipt(
        candidate_state_path,
        tmp_path / "activation" / "adapter-receipt.json",
    )
    receipt = json.loads(adapter_receipt_path.read_text(encoding="utf-8"))
    receipt["wiki_mutation_performed"] = True
    adapter_receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "obsidian/pdf-transition",
            "--activation-target",
            "obsidian-pdf-transition-generated-program-runtime",
            "--authority-owner",
            "obsidian-pdf-transition-governance",
            "--candidate-state",
            str(candidate_state_path),
            "--obsidian-review-adapter-receipt",
            str(adapter_receipt_path),
            "--require-obsidian-review-adapter",
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "wiki_mutation_performed false" in result.output


def test_program_promote_activation_packet_rejects_obsidian_adapter_missing_candidate_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_program(tmp_path, monkeypatch)
    candidate_state_path = _write_target_aware_candidate_state(
        program_root,
        tmp_path / "activation" / "program_candidate_state.json",
    )
    adapter_receipt_path = _write_obsidian_adapter_receipt(
        candidate_state_path,
        tmp_path / "activation" / "adapter-receipt.json",
    )
    receipt = json.loads(adapter_receipt_path.read_text(encoding="utf-8"))
    del receipt["program_candidate_state_hash"]
    adapter_receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "obsidian/pdf-transition",
            "--activation-target",
            "obsidian-pdf-transition-generated-program-runtime",
            "--authority-owner",
            "obsidian-pdf-transition-governance",
            "--candidate-state",
            str(candidate_state_path),
            "--obsidian-review-adapter-receipt",
            str(adapter_receipt_path),
            "--require-obsidian-review-adapter",
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "program_candidate_state_hash is required" in result.output


def test_program_promote_activation_packet_dogfoods_review_chain_without_activation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, jury_path, review_path, decision_path = (
        _materialize_review_chain(tmp_path, monkeypatch)
    )
    before_hashes = _file_hashes(program_root)
    out_path = tmp_path / "activation" / "activation_packet.json"

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--oracle-report",
            str(report_path),
            "--jury-results",
            str(jury_path),
            "--review",
            str(review_path),
            "--decision-record",
            str(decision_path),
            "--rollout-owner",
            "softwareco-runtime-operator",
            "--rollback-plan",
            "Disable the generated-program route and restore the previous production program version.",
            "--out",
            str(out_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "blocked"
    assert payload["next_required_action"] == "resolve_decision_outcome"
    assert payload["missing_required_evidence"] == ["decision_outcome_not_promote"]
    assert payload["decision"] == {
        "outcome": "request_more_evidence",
        "promotion_state_after_decision": "not_promoted",
        "decided_by": "softwareco-program-governance",
    }
    assert payload["canonical_binding_ref"] is None
    assert payload["evidence"]["oracle_report"]["path"] == str(report_path.resolve())
    assert payload["evidence"]["jury_results"]["path"] == str(jury_path.resolve())
    assert payload["evidence"]["refined_review"]["path"] == str(review_path.resolve())
    assert payload["evidence"]["decision_record"]["path"] == str(
        decision_path.resolve()
    )
    assert payload["effect"] == {
        "activation_packet_written": True,
        "program_files_mutated": False,
        "oracle_index_mutated": False,
        "mlflow_mutated": False,
        "ak_mutated": False,
        "external_authority_mutated": False,
        "production_activation_applied": False,
    }
    assert _file_hashes(program_root) == before_hashes
    assert not (program_root / "activation_packet.json").exists()


def test_program_promote_activation_packet_includes_oracle_publication_preflight_as_readiness_evidence_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_program(tmp_path, monkeypatch)
    preflight_path = _write_oracle_publication_preflight(
        program_root,
        tmp_path / "oracle" / "publication_preflight.json",
    )
    out_path = tmp_path / "activation" / "activation_packet.json"

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--oracle-publication-preflight",
            str(preflight_path),
            "--out",
            str(out_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    preflight_ref = payload["evidence"]["oracle_publication_preflight"]
    assert preflight_ref["path"] == str(preflight_path.resolve())
    assert preflight_ref["schema_version"] == (
        "program-oracle-shared-publication-preflight-v1"
    )
    assert preflight_ref["publication_id"].startswith("prog-oracle-pub-")
    assert preflight_ref["ready_for_shared_publication"] is True
    assert preflight_ref["runtime_trace_semantics_valid"] is True
    assert preflight_ref["runtime_trace_hash_match"] is True
    assert preflight_ref["blocking_reasons"] == []
    assert preflight_ref["preflight_only"] is True
    assert preflight_ref["activation_authority"] is False
    assert preflight_ref["promotion_authority"] is False
    assert preflight_ref["shared_oracle_mutated"] is False
    assert payload["evidence"]["oracle_publication_receipt"] is None
    assert (
        payload["boundary_checks"]["oracle_publication_activation_authority"] is False
    )
    assert payload["status"] == "blocked"
    assert payload["effect"]["production_activation_applied"] is False
    assert payload["non_authority"]["oracle_promotion"] is False


def test_program_promote_activation_packet_rejects_publication_preflight_missing_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_program(tmp_path, monkeypatch)
    preflight_path = _write_oracle_publication_preflight(
        program_root,
        tmp_path / "oracle" / "publication_preflight.json",
    )
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    preflight.pop("identity")
    preflight_path.write_text(json.dumps(preflight, indent=2) + "\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--oracle-publication-preflight",
            str(preflight_path),
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "oracle_publication_preflight missing identity object" in result.output


def test_program_promote_activation_packet_rejects_publication_preflight_tampered_planned_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_program(tmp_path, monkeypatch)
    preflight_path = _write_oracle_publication_preflight(
        program_root,
        tmp_path / "oracle" / "publication_preflight.json",
    )
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    preflight["planned_record"]["candidate_id"] = "evil-candidate"
    preflight_path.write_text(json.dumps(preflight, indent=2) + "\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--oracle-publication-preflight",
            str(preflight_path),
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "planned_record does not match validated preflight fields" in result.output
    assert "candidate_id" in result.output


def test_program_promote_activation_packet_rejects_publication_preflight_failed_readiness_check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_program(tmp_path, monkeypatch)
    preflight_path = _write_oracle_publication_preflight(
        program_root,
        tmp_path / "oracle" / "publication_preflight.json",
    )
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    preflight["preflight"]["runtime_trace_hash_match"] = False
    preflight_path.write_text(json.dumps(preflight, indent=2) + "\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--oracle-publication-preflight",
            str(preflight_path),
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "runtime_trace_hash_match" in result.output


def test_program_promote_activation_packet_rejects_publication_preflight_target_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_program(tmp_path, monkeypatch)
    preflight_path = _write_oracle_publication_preflight(
        program_root,
        tmp_path / "oracle" / "publication_preflight.json",
    )
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    preflight["target"]["connection_attempted"] = True
    preflight_path.write_text(json.dumps(preflight, indent=2) + "\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--oracle-publication-preflight",
            str(preflight_path),
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "target.connection_attempted must be false" in result.output


def test_program_promote_activation_packet_rejects_publication_preflight_idempotency_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_program(tmp_path, monkeypatch)
    preflight_path = _write_oracle_publication_preflight(
        program_root,
        tmp_path / "oracle" / "publication_preflight.json",
    )
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    preflight["publication"]["publisher_id"] = "tampered-publisher"
    preflight["planned_record"]["publisher_id"] = "tampered-publisher"
    preflight_path.write_text(json.dumps(preflight, indent=2) + "\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--oracle-publication-preflight",
            str(preflight_path),
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "publication_id does not match recomputed idempotency key" in result.output


def test_program_promote_activation_packet_includes_oracle_publication_ref_as_evidence_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, jury_path, review_path, decision_path = (
        _materialize_review_chain(tmp_path, monkeypatch)
    )
    receipt_path = _write_oracle_publication_receipt(
        program_root,
        tmp_path / "oracle" / "publication_receipt.json",
    )
    out_path = tmp_path / "activation" / "activation_packet.json"

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--oracle-report",
            str(report_path),
            "--jury-results",
            str(jury_path),
            "--review",
            str(review_path),
            "--decision-record",
            str(decision_path),
            "--oracle-publication-receipt",
            str(receipt_path),
            "--rollout-owner",
            "softwareco-runtime-operator",
            "--rollback-plan",
            "Disable the generated-program route and restore the previous production program version.",
            "--out",
            str(out_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    publication_ref = payload["evidence"]["oracle_publication_receipt"]
    assert publication_ref["path"] == str(receipt_path.resolve())
    assert publication_ref["schema_version"] == (
        "program-oracle-shared-publication-receipt-v1"
    )
    assert publication_ref["publication_id"].startswith("prog-oracle-pub-")
    assert publication_ref["publication_label"] == "retained"
    assert publication_ref["evidence_only"] is True
    assert publication_ref["activation_authority"] is False
    assert publication_ref["promotion_authority"] is False
    assert (
        payload["boundary_checks"]["oracle_publication_activation_authority"] is False
    )
    assert payload["status"] == "blocked"
    assert payload["missing_required_evidence"] == ["decision_outcome_not_promote"]
    assert payload["effect"]["production_activation_applied"] is False
    assert payload["non_authority"]["oracle_promotion"] is False


def test_program_promote_activation_packet_publication_ref_cannot_approve_activation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_program(tmp_path, monkeypatch)
    receipt_path = _write_oracle_publication_receipt(
        program_root,
        tmp_path / "oracle" / "publication_receipt.json",
    )
    out_path = tmp_path / "activation" / "activation_packet.json"

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--oracle-publication-receipt",
            str(receipt_path),
            "--out",
            str(out_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["evidence"]["oracle_publication_receipt"]["evidence_only"] is True
    assert payload["status"] == "blocked"
    assert "oracle_report" in payload["missing_required_evidence"]
    assert "jury_results" in payload["missing_required_evidence"]
    assert "refined_promotion_review" in payload["missing_required_evidence"]
    assert "rollout_owner" in payload["missing_required_evidence"]
    assert "rollback_plan" in payload["missing_required_evidence"]
    assert payload["effect"]["production_activation_applied"] is False


def test_program_promote_activation_packet_cross_checks_candidate_state_publication_preflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_program(tmp_path, monkeypatch)
    preflight_path = _write_oracle_publication_preflight(
        program_root,
        tmp_path / "oracle" / "publication_preflight.json",
    )
    candidate_state_path = _write_candidate_state_with_publication_preflight(
        program_root,
        preflight_path,
        tmp_path / "state" / "program_candidate_state.json",
    )
    out_path = tmp_path / "activation" / "activation_packet.json"

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--oracle-publication-preflight",
            str(preflight_path),
            "--candidate-state",
            str(candidate_state_path),
            "--out",
            str(out_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    publication_id = payload["evidence"]["oracle_publication_preflight"][
        "publication_id"
    ]
    assert publication_id
    assert payload["evidence"]["candidate_state"]["path"] == str(
        candidate_state_path.resolve()
    )
    alignment = payload["evidence_alignment"]["oracle_publication"]
    assert alignment == {
        "candidate_state_present": True,
        "candidate_state_preflight_present": True,
        "candidate_state_receipt_present": False,
        "preflight_ref_supplied": True,
        "receipt_ref_supplied": False,
        "preflight_publication_id": publication_id,
        "receipt_publication_id": None,
        "candidate_state_preflight_publication_id": publication_id,
        "candidate_state_receipt_publication_id": None,
        "publication_ids_aligned": True,
        "evidence_only": True,
        "activation_authority": False,
        "promotion_authority": False,
    }
    assert payload["effect"]["production_activation_applied"] is False


def test_program_promote_activation_packet_rejects_mismatched_preflight_and_receipt_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_program(tmp_path, monkeypatch)
    preflight_path = _write_oracle_publication_preflight(
        program_root,
        tmp_path / "oracle" / "publication_preflight.json",
    )
    receipt_path = _write_oracle_publication_receipt(
        program_root,
        tmp_path / "oracle" / "publication_receipt.json",
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["publication_id"] = "prog-oracle-pub-mismatched"
    receipt["run_id"] = "program-oracle-publication:prog-oracle-pub-mismatched"
    receipt["idempotency"]["publication_id"] = "prog-oracle-pub-mismatched"
    receipt["idempotency"]["run_id"] = (
        "program-oracle-publication:prog-oracle-pub-mismatched"
    )
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--oracle-publication-preflight",
            str(preflight_path),
            "--oracle-publication-receipt",
            str(receipt_path),
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert (
        "oracle_publication_preflight/receipt publication_id mismatch" in result.output
    )


def test_program_promote_activation_packet_rejects_candidate_state_publication_preflight_omission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_program(tmp_path, monkeypatch)
    preflight_path = _write_oracle_publication_preflight(
        program_root,
        tmp_path / "oracle" / "publication_preflight.json",
    )
    candidate_state_path = _write_candidate_state_with_publication_preflight(
        program_root,
        preflight_path,
        tmp_path / "state" / "program_candidate_state.json",
    )

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--candidate-state",
            str(candidate_state_path),
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "candidate_state references oracle_publication_preflight" in result.output


def test_program_promote_activation_packet_rejects_publication_preflight_authority_widening(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_program(tmp_path, monkeypatch)
    preflight_path = _write_oracle_publication_preflight(
        program_root,
        tmp_path / "oracle" / "publication_preflight.json",
    )
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    preflight["effect"]["shared_oracle_mutated"] = True
    preflight_path.write_text(json.dumps(preflight, indent=2) + "\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--oracle-publication-preflight",
            str(preflight_path),
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "shared_oracle_mutated false" in result.output


def test_program_promote_activation_packet_rejects_publication_receipt_idempotency_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_program(tmp_path, monkeypatch)
    receipt_path = _write_oracle_publication_receipt(
        program_root,
        tmp_path / "oracle" / "publication_receipt.json",
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["idempotency"]["run_id"] = "program-oracle-publication:wrong"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--oracle-publication-receipt",
            str(receipt_path),
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "idempotency contract mismatch" in result.output
    assert "run_id" in result.output


def test_program_promote_activation_packet_rejects_publication_receipt_record_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_program(tmp_path, monkeypatch)
    receipt_path = _write_oracle_publication_receipt(
        program_root,
        tmp_path / "oracle" / "publication_receipt.json",
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["record"]["publication_label"] = "activated"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--oracle-publication-receipt",
            str(receipt_path),
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "record does not match publication fields" in result.output
    assert "publication_label" in result.output


def test_program_promote_activation_packet_rejects_publication_receipt_source_preflight_hash_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_program(tmp_path, monkeypatch)
    receipt_path = _write_oracle_publication_receipt(
        program_root,
        tmp_path / "oracle" / "publication_receipt.json",
    )
    preflight_path = receipt_path.parent / "oracle_publication_preflight.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["source"]["preflight_sha256"] = "0" * 64
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--oracle-publication-preflight",
            str(preflight_path),
            "--oracle-publication-receipt",
            str(receipt_path),
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "source.preflight_sha256 does not match supplied preflight" in result.output


def test_program_promote_activation_packet_rejects_publication_receipt_preflight_publication_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_program(tmp_path, monkeypatch)
    receipt_path = _write_oracle_publication_receipt(
        program_root,
        tmp_path / "oracle" / "publication_receipt.json",
    )
    preflight_path = receipt_path.parent / "oracle_publication_preflight.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["publication"]["retention_class"] = "activation_evidence_reference"
    receipt["record"]["retention_class"] = "activation_evidence_reference"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--oracle-publication-preflight",
            str(preflight_path),
            "--oracle-publication-receipt",
            str(receipt_path),
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "publication does not match supplied preflight" in result.output


def test_program_promote_activation_packet_rejects_publication_receipt_source_oracle_evidence_hash_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_program(tmp_path, monkeypatch)
    receipt_path = _write_oracle_publication_receipt(
        program_root,
        tmp_path / "oracle" / "publication_receipt.json",
    )
    preflight_path = receipt_path.parent / "oracle_publication_preflight.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["source"]["oracle_evidence_sha256"] = "0" * 64
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--oracle-publication-preflight",
            str(preflight_path),
            "--oracle-publication-receipt",
            str(receipt_path),
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert (
        "source.oracle_evidence_sha256 does not match supplied preflight"
        in result.output
    )


def test_program_promote_activation_packet_rejects_publication_receipt_unattempted_shared_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_program(tmp_path, monkeypatch)
    receipt_path = _write_oracle_publication_receipt(
        program_root,
        tmp_path / "oracle" / "publication_receipt.json",
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["target"]["shared_write_attempted"] = False
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--oracle-publication-receipt",
            str(receipt_path),
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "target.shared_write_attempted must be true" in result.output


def test_program_promote_activation_packet_rejects_publication_receipt_secret_bearing_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_program(tmp_path, monkeypatch)
    receipt_path = _write_oracle_publication_receipt(
        program_root,
        tmp_path / "oracle" / "publication_receipt.json",
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["target"]["database_url_redacted"] = (
        "postgresql://user:super-secret@example.invalid/db"
    )
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--oracle-publication-receipt",
            str(receipt_path),
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "must not expose secret-bearing credentials" in result.output
    assert "super-secret" not in result.output


def test_program_promote_activation_packet_rejects_publication_ref_authority_widening(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_program(tmp_path, monkeypatch)
    receipt_path = _write_oracle_publication_receipt(
        program_root,
        tmp_path / "oracle" / "publication_receipt.json",
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["effect"]["promotion_state_changed"] = True
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--oracle-publication-receipt",
            str(receipt_path),
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "promotion_state_changed false" in result.output


def test_program_promote_activation_packet_requires_rollout_owner_before_rollout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, jury_path, review_path, _decision_path = (
        _materialize_review_chain(tmp_path, monkeypatch)
    )
    promote_decision = json.loads(_decision_path.read_text(encoding="utf-8"))
    promote_decision["outcome"] = "promote"
    promote_decision["promotion_state_after_decision"] = "promoted"
    promote_decision["rationale"] = (
        "Domain adjudicator accepts the candidate for a bounded rollout."
    )
    decision_path = tmp_path / "promotion" / "promotion_decision_record_promote.json"
    _write_json(decision_path, promote_decision)
    out_path = tmp_path / "activation" / "activation_packet.json"

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--oracle-report",
            str(report_path),
            "--jury-results",
            str(jury_path),
            "--review",
            str(review_path),
            "--decision-record",
            str(decision_path),
            "--canonical-binding-ref",
            "ak://decision/123#accepted",
            "--rollback-plan",
            "Disable the generated-program route and restore the previous production program version.",
            "--out",
            str(out_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "blocked"
    assert payload["next_required_action"] == "collect_missing_evidence"
    assert payload["missing_required_evidence"] == ["rollout_owner"]
    assert payload["decision"]["outcome"] == "promote"
    assert payload["canonical_binding_ref"] == "ak://decision/123#accepted"
    assert payload["effect"]["production_activation_applied"] is False


def test_program_promote_activation_packet_requires_binding_verification_after_authority_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, jury_path, review_path, _decision_path = (
        _materialize_review_chain(tmp_path, monkeypatch)
    )
    promote_decision = json.loads(_decision_path.read_text(encoding="utf-8"))
    promote_decision["outcome"] = "promote"
    promote_decision["promotion_state_after_decision"] = "promoted"
    promote_decision["rationale"] = (
        "Domain adjudicator accepts the candidate for a bounded rollout."
    )
    decision_path = tmp_path / "promotion" / "promotion_decision_record_promote.json"
    _write_json(decision_path, promote_decision)
    out_path = tmp_path / "activation" / "activation_packet.json"

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--oracle-report",
            str(report_path),
            "--jury-results",
            str(jury_path),
            "--review",
            str(review_path),
            "--decision-record",
            str(decision_path),
            "--canonical-binding-ref",
            "ak://decision/123#accepted",
            "--rollout-owner",
            "softwareco-runtime-operator",
            "--rollback-plan",
            "Disable the generated-program route and restore the previous production program version.",
            "--out",
            str(out_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "ready_for_canonical_binding_verification"
    assert payload["next_required_action"] == (
        "verify_canonical_binding_ref_before_rollout_preflight"
    )
    assert payload["missing_required_evidence"] == []
    assert payload["remaining_activation_blockers"] == [
        "canonical_binding_verification"
    ]
    assert payload["rollout_owner"] == "softwareco-runtime-operator"
    assert payload["effect"]["production_activation_applied"] is False


def test_program_promote_activation_packet_reaches_rollout_preflight_after_verified_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, jury_path, review_path, _decision_path = (
        _materialize_review_chain(tmp_path, monkeypatch)
    )
    promote_decision = json.loads(_decision_path.read_text(encoding="utf-8"))
    promote_decision["outcome"] = "promote"
    promote_decision["promotion_state_after_decision"] = "promoted"
    promote_decision["rationale"] = (
        "Domain adjudicator accepts the candidate for a bounded rollout."
    )
    decision_path = tmp_path / "promotion" / "promotion_decision_record_promote.json"
    _write_json(decision_path, promote_decision)
    verification_path = _write_canonical_binding_verification(
        decision_path,
        tmp_path / "activation" / "canonical_binding_verification.json",
    )
    out_path = tmp_path / "activation" / "activation_packet.json"

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--oracle-report",
            str(report_path),
            "--jury-results",
            str(jury_path),
            "--review",
            str(review_path),
            "--decision-record",
            str(decision_path),
            "--canonical-binding-ref",
            "ak://decision/123#accepted",
            "--canonical-binding-verification",
            str(verification_path),
            "--rollout-owner",
            "softwareco-runtime-operator",
            "--rollback-plan",
            "Disable the generated-program route and restore the previous production program version.",
            "--out",
            str(out_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "ready_for_rollout_preflight"
    assert payload["next_required_action"] == "run_owner_approved_rollout_preflight"
    assert payload["missing_required_evidence"] == []
    assert payload["remaining_activation_blockers"] == []
    assert payload["evidence"]["canonical_binding_verification"]["path"] == str(
        verification_path.resolve()
    )
    assert payload["effect"]["production_activation_applied"] is False


def test_program_promote_activation_packet_rejects_binding_verification_missing_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, jury_path, review_path, _decision_path = (
        _materialize_review_chain(tmp_path, monkeypatch)
    )
    promote_decision = json.loads(_decision_path.read_text(encoding="utf-8"))
    promote_decision["outcome"] = "promote"
    promote_decision["promotion_state_after_decision"] = "promoted"
    decision_path = tmp_path / "promotion" / "promotion_decision_record_promote.json"
    _write_json(decision_path, promote_decision)
    verification_path = _write_canonical_binding_verification(
        decision_path,
        tmp_path / "activation" / "canonical_binding_verification.json",
    )
    verification = json.loads(verification_path.read_text(encoding="utf-8"))
    del verification["decision_record_sha256"]
    verification_path.write_text(json.dumps(verification, indent=2) + "\n")

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--oracle-report",
            str(report_path),
            "--jury-results",
            str(jury_path),
            "--review",
            str(review_path),
            "--decision-record",
            str(decision_path),
            "--canonical-binding-ref",
            "ak://decision/123#accepted",
            "--canonical-binding-verification",
            str(verification_path),
            "--rollout-owner",
            "softwareco-runtime-operator",
            "--rollback-plan",
            "Disable the generated-program route and restore the previous production program version.",
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "decision_record_sha256 is required" in result.output


def test_program_promote_activation_packet_rejects_binding_verification_hash_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, jury_path, review_path, _decision_path = (
        _materialize_review_chain(tmp_path, monkeypatch)
    )
    promote_decision = json.loads(_decision_path.read_text(encoding="utf-8"))
    promote_decision["outcome"] = "promote"
    promote_decision["promotion_state_after_decision"] = "promoted"
    decision_path = tmp_path / "promotion" / "promotion_decision_record_promote.json"
    _write_json(decision_path, promote_decision)
    verification_path = _write_canonical_binding_verification(
        decision_path,
        tmp_path / "activation" / "canonical_binding_verification.json",
    )
    verification = json.loads(verification_path.read_text(encoding="utf-8"))
    verification["decision_record_sha256"] = "wrong"
    verification_path.write_text(json.dumps(verification, indent=2) + "\n")

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--oracle-report",
            str(report_path),
            "--jury-results",
            str(jury_path),
            "--review",
            str(review_path),
            "--decision-record",
            str(decision_path),
            "--canonical-binding-ref",
            "ak://decision/123#accepted",
            "--canonical-binding-verification",
            str(verification_path),
            "--rollout-owner",
            "softwareco-runtime-operator",
            "--rollback-plan",
            "Disable the generated-program route and restore the previous production program version.",
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "decision_record_sha256 does not match" in result.output


def test_program_promote_activation_packet_rejects_widened_jury_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, jury_path, review_path, decision_path = (
        _materialize_review_chain(tmp_path, monkeypatch)
    )
    jury = json.loads(jury_path.read_text(encoding="utf-8"))
    jury["non_authority"]["promotion_authority"] = True
    jury_path.write_text(json.dumps(jury, indent=2) + "\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--oracle-report",
            str(report_path),
            "--jury-results",
            str(jury_path),
            "--review",
            str(review_path),
            "--decision-record",
            str(decision_path),
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "jury_results widens non-authority flags" in result.output
    assert "promotion_authority" in result.output


def test_program_promote_activation_packet_rejects_oracle_report_identity_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, jury_path, review_path, decision_path = (
        _materialize_review_chain(tmp_path, monkeypatch)
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["records"][0]["identity"]["candidate_id"] = "different-candidate"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--oracle-report",
            str(report_path),
            "--jury-results",
            str(jury_path),
            "--review",
            str(review_path),
            "--decision-record",
            str(decision_path),
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert (
        "oracle_report does not contain a record matching candidate identity"
        in result.output
    )


def test_program_promote_activation_packet_rejects_wrong_decision_authority_owner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, jury_path, review_path, decision_path = (
        _materialize_review_chain(tmp_path, monkeypatch)
    )

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "different-authority-owner",
            "--oracle-report",
            str(report_path),
            "--jury-results",
            str(jury_path),
            "--review",
            str(review_path),
            "--decision-record",
            str(decision_path),
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert (
        "decision_record decided_by must match activation authority_owner"
        in result.output
    )


def test_program_promote_activation_packet_rejects_blocking_target_judgment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_program(tmp_path, monkeypatch)
    candidate_state_path = _write_target_aware_candidate_state(
        program_root,
        tmp_path / "activation" / "program_candidate_state.json",
    )
    candidate_state = json.loads(candidate_state_path.read_text(encoding="utf-8"))
    judgment = candidate_state["target_fidelity_state"][
        "target_protocol_fidelity_judgment"
    ]
    judgment["blocking"] = True
    judgment["judgment"] = "needs_more_evidence"
    candidate_state_path.write_text(json.dumps(candidate_state, indent=2) + "\n")

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "obsidian/pdf-transition",
            "--activation-target",
            "obsidian-pdf-transition-generated-program-runtime",
            "--authority-owner",
            "obsidian-pdf-transition-governance",
            "--candidate-state",
            str(candidate_state_path),
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert (
        "target_protocol_fidelity_judgment must record blocking false" in result.output
    )


def test_program_promote_activation_packet_rejects_evidence_missing_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, jury_path, review_path, decision_path = (
        _materialize_review_chain(tmp_path, monkeypatch)
    )
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review.pop("identity", None)
    review_path.write_text(json.dumps(review, indent=2) + "\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--oracle-report",
            str(report_path),
            "--jury-results",
            str(jury_path),
            "--review",
            str(review_path),
            "--decision-record",
            str(decision_path),
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "refined_review missing identity object" in result.output


def test_program_promote_activation_packet_rejects_behavior_hash_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_program(tmp_path, monkeypatch)
    behavior = json.loads((program_root / "behavior_results.json").read_text())
    behavior["summary"]["status"] = "tampered"
    (program_root / "behavior_results.json").write_text(
        json.dumps(behavior, indent=2) + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert (
        "behavior_results.json hash does not match manifest declaration"
        in result.output
    )


def test_program_promote_activation_packet_rejects_corrupt_behavior_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_program(tmp_path, monkeypatch)
    (program_root / "behavior_results.json").write_text(
        json.dumps({"schema_version": "wrong"}) + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "behavior_results.json schema_version" in result.output
