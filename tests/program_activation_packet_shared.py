# summary: "Shared builders for materialized program evidence chains used by activation-packet contract tests."
# read_when:
#   - "Testing activation packets, canonical binding, Oracle publication, or review-chain evidence."

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import cast

import pytest
from typer.testing import CliRunner

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

_MATERIALIZED_PROGRAM_TEMPLATE: Path | None = None


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


def _manifest_hash(root: Path) -> str:
    return hashlib.sha256((root / "manifest.json").read_bytes()).hexdigest()


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
            "artifact_hashes": {"manifest_sha256": _manifest_hash(root)},
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
            "artifact_hashes": {"manifest_sha256": _manifest_hash(root)},
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


def _materialized_program_template(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    global _MATERIALIZED_PROGRAM_TEMPLATE
    if _MATERIALIZED_PROGRAM_TEMPLATE is not None:
        return _MATERIALIZED_PROGRAM_TEMPLATE

    template_root = Path(tempfile.mkdtemp(prefix="dspx-activation-packet-template-"))
    _setup_env(template_root, monkeypatch)
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
    artifact = materialize_program_from_intent(intent, outdir=template_root / "program")
    _MATERIALIZED_PROGRAM_TEMPLATE = Path(artifact.root_path)
    return _MATERIALIZED_PROGRAM_TEMPLATE


def _materialize_program(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    template = _materialized_program_template(tmp_path, monkeypatch)
    _setup_env(tmp_path, monkeypatch)
    program_root = tmp_path / "program"
    shutil.copytree(template, program_root)
    return program_root


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
