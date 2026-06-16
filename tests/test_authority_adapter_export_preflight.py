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
from dspx.services.program_external_authority_export import (
    ProgramExternalAuthorityExportError,
    build_program_external_authority_export_preflight,
)
from dspx.services.program_intent import ProgramIntent
from dspx.services.program_oracle_index import index_program_oracle_evidence_path
from dspx.services.program_oracle_report import build_program_oracle_evidence_report
from dspx.services.program_promotion_decision import (
    build_program_promotion_decision_record,
    write_program_promotion_decision_record,
)
from dspx.services.program_promotion_refinement import (
    build_program_promotion_refinement,
)
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


def _setup_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "mock")
    reset_embedding_engine()


def _materialize_external_authority_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path, Path, Path]:
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
    program_root = Path(artifact.root_path)
    assert (program_root / "eval_examples.py").exists()
    assert (program_root / "eval_behavior.py").exists()
    assert (program_root / "behavior_episode.json").exists()

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

    proposal = build_program_refinement_proposal(
        manifest_path=program_root / "manifest.json",
        oracle_report_path=report_path,
    )
    assert proposal["status"] == "proposed"
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
        decided_by="local_operator",
        rationale="Generate one bounded second candidate for observed mismatch.",
    )
    decision_path = tmp_path / "promotion" / "promotion_decision_record.json"
    write_program_promotion_decision_record(decision, decision_path)

    comparison_path = tmp_path / "refinement" / "candidate_comparison.json"
    workflow = materialize_and_compare_refinement_candidate(
        manifest_path=program_root / "manifest.json",
        refinement_proposal_path=proposal_path,
        decision_record_path=decision_path,
        outdir=tmp_path / "program-v2",
        comparison_out_path=comparison_path,
    )
    assert workflow["status"] == "materialized_and_compared"
    candidate_manifest = Path(
        workflow["generation"]["candidate"]["manifest_path"]
    ).resolve()
    assert candidate_manifest.exists()
    assert comparison_path.exists()
    assert (candidate_manifest.parent / "eval_behavior.py").exists()
    assert (candidate_manifest.parent / "behavior_episode.json").exists()
    return program_root, candidate_manifest.parent, decision_path, comparison_path


def test_activation_packet_can_carry_external_authority_export_preflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, candidate_root, decision_path, comparison_path = (
        _materialize_external_authority_path(tmp_path, monkeypatch)
    )
    source_hashes_before = _file_hashes(program_root)
    candidate_hashes_before = _file_hashes(candidate_root)
    preflight_out = tmp_path / "export" / "ak-export-preflight.json"
    activation_out = tmp_path / "activation" / "activation_packet.json"

    preflight_result = runner.invoke(
        app,
        [
            "adapters",
            "authority",
            "agent-kernel-export-preflight",
            "--manifest",
            str(program_root / "manifest.json"),
            "--external-ref",
            "AK-EXAMPLE",
            "--decision-record",
            str(decision_path),
            "--comparison",
            str(comparison_path),
            "--out",
            str(preflight_out),
            "--json",
        ],
    )
    assert preflight_result.exit_code == 0, preflight_result.output

    activation_result = runner.invoke(
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
            "--export-preflight",
            str(preflight_out),
            "--out",
            str(activation_out),
            "--json",
        ],
    )

    assert activation_result.exit_code == 0, activation_result.output
    payload = json.loads(activation_result.stdout)
    export_ref = payload["evidence"]["external_authority_export_preflight"]
    assert export_ref["path"] == str(preflight_out.resolve())
    assert (
        export_ref["schema_version"] == "program-external-authority-export-preflight-v1"
    )
    assert export_ref["status"] == "ready_not_applied"
    assert export_ref["target_system"] == "agent_kernel"
    assert export_ref["target_contract"] == "ak_task_evidence_attachment"
    assert export_ref["external_ref"] == "AK-EXAMPLE"
    assert export_ref["ready_for_future_apply"] is False
    assert export_ref["preflight_only"] is True
    assert export_ref["planned_not_exported"] is True
    assert (
        "external_apply_not_implemented"
        in export_ref["external_apply_blocking_reasons"]
    )
    assert payload["effect"]["ak_mutated"] is False
    assert payload["effect"]["external_authority_mutated"] is False
    assert payload["non_authority"]["external_mutation"] is False
    assert _file_hashes(program_root) == source_hashes_before
    assert _file_hashes(candidate_root) == candidate_hashes_before


def test_activation_packet_rejects_stale_external_authority_export_preflight_hashes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, _candidate_root, decision_path, comparison_path = (
        _materialize_external_authority_path(tmp_path, monkeypatch)
    )
    manifest_path = program_root / "manifest.json"
    packet = build_program_external_authority_export_preflight(
        manifest_path=manifest_path,
        external_ref="AK-EXAMPLE",
        decision_record_path=decision_path,
        comparison_path=comparison_path,
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["stale_marker"] = "manifest changed after preflight"
    _write_json(manifest_path, manifest)
    preflight_out = tmp_path / "export" / "stale-preflight.json"
    _write_json(preflight_out, packet)
    activation_out = tmp_path / "activation" / "activation_packet.json"

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(manifest_path),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--export-preflight",
            str(preflight_out),
            "--out",
            str(activation_out),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "manifest_sha256 does not match current manifest" in result.output
    assert not activation_out.exists()


def test_activation_packet_rejects_spoofed_external_authority_export_preflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, _candidate_root, decision_path, comparison_path = (
        _materialize_external_authority_path(tmp_path, monkeypatch)
    )
    packet = build_program_external_authority_export_preflight(
        manifest_path=program_root / "manifest.json",
        external_ref="AK-EXAMPLE",
        decision_record_path=decision_path,
        comparison_path=comparison_path,
    )
    packet["effect"]["ak_called"] = True
    preflight_out = tmp_path / "export" / "spoofed-preflight.json"
    _write_json(preflight_out, packet)
    activation_out = tmp_path / "activation" / "activation_packet.json"

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
            "--export-preflight",
            str(preflight_out),
            "--out",
            str(activation_out),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "ak_called false" in result.output
    assert not activation_out.exists()


def test_activation_packet_rejects_identity_drifted_external_authority_export_preflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, _candidate_root, decision_path, comparison_path = (
        _materialize_external_authority_path(tmp_path, monkeypatch)
    )
    packet = build_program_external_authority_export_preflight(
        manifest_path=program_root / "manifest.json",
        external_ref="AK-EXAMPLE",
        decision_record_path=decision_path,
        comparison_path=comparison_path,
    )
    packet["identity"] = {**packet["identity"], "candidate_id": "drifted"}
    preflight_out = tmp_path / "export" / "identity-drift-preflight.json"
    _write_json(preflight_out, packet)
    activation_out = tmp_path / "activation" / "activation_packet.json"

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
            "--export-preflight",
            str(preflight_out),
            "--out",
            str(activation_out),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "identity does not match candidate identity" in result.output
    assert not activation_out.exists()


def test_agent_kernel_export_preflight_cli_writes_preflight_without_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, candidate_root, decision_path, comparison_path = (
        _materialize_external_authority_path(tmp_path, monkeypatch)
    )
    source_hashes_before = _file_hashes(program_root)
    candidate_hashes_before = _file_hashes(candidate_root)
    decision_hash_before = hashlib.sha256(decision_path.read_bytes()).hexdigest()
    comparison_hash_before = hashlib.sha256(comparison_path.read_bytes()).hexdigest()
    out = tmp_path / "export" / "ak-export-preflight.json"

    def forbid_subprocess_run(
        *_args: object, **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        raise AssertionError(
            "external authority preflight must not invoke subprocesses"
        )

    monkeypatch.setattr(subprocess, "run", forbid_subprocess_run)

    result = runner.invoke(
        app,
        [
            "adapters",
            "authority",
            "agent-kernel-export-preflight",
            "--manifest",
            str(program_root / "manifest.json"),
            "--external-ref",
            "AK-EXAMPLE",
            "--decision-record",
            str(decision_path),
            "--comparison",
            str(comparison_path),
            "--out",
            str(out),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert out.exists()
    assert json.loads(out.read_text(encoding="utf-8")) == payload
    assert payload["schema_version"] == "program-external-authority-export-preflight-v1"
    assert payload["status"] == "ready_not_applied"
    assert payload["target"] == {
        "system": "agent_kernel",
        "external_ref": "AK-EXAMPLE",
        "target_contract": "ak_task_evidence_attachment",
        "mutation_supported": False,
        "apply_command_available": False,
    }
    assert payload["export_id"].startswith("prog-ext-export-")
    assert payload["created_from"]["manifest_schema_version"] == (
        "program-candidate-assembly-v1"
    )
    assert payload["created_from"]["decision_record_schema_version"] == (
        "program-promotion-decision-record-v1"
    )
    assert payload["created_from"]["comparison_schema_version"] == (
        "program-refinement-candidate-comparison-v1"
    )
    assert payload["identity"]["request_id"]
    assert payload["identity"]["candidate_id"]
    assert payload["identity"]["assembly_id"]
    assert payload["identity"]["episode_id"]
    assert payload["identity"]["receipt_bundle_id"]
    assert payload["artifact_hashes"] == {
        "manifest_sha256": hashlib.sha256(
            (program_root / "manifest.json").read_bytes()
        ).hexdigest(),
        "decision_record_sha256": decision_hash_before,
        "comparison_sha256": comparison_hash_before,
    }
    assert payload["preflight"]["manifest_valid"] is True
    assert payload["preflight"]["target_ref_present"] is True
    assert (
        payload["preflight"]["target_ref_matches_manifest_external_authority_refs"]
        is True
    )
    assert payload["preflight"]["decision_record_present"] is True
    assert payload["preflight"]["decision_record_identity_matches_manifest"] is True
    assert payload["preflight"]["comparison_present"] is True
    assert payload["preflight"]["comparison_mentions_manifest_identity"] is True
    assert payload["preflight"]["promotion_not_applied"] is True
    assert payload["preflight"]["external_mutation_supported"] is False
    assert payload["preflight"]["external_mutation_requested"] is False
    assert payload["preflight"]["ready_for_future_apply"] is False
    assert payload["preflight"]["blocking_reasons"] == []
    assert (
        "external_apply_not_implemented"
        in payload["preflight"]["external_apply_blocking_reasons"]
    )
    assert (
        "target_contract_not_bound_to_ak_runtime"
        in payload["preflight"]["external_apply_blocking_reasons"]
    )
    assert payload["planned_payload"]["kind"] == "ak_task_evidence_attachment"
    assert payload["planned_payload"]["target_ref"] == "AK-EXAMPLE"
    assert [ref["kind"] for ref in payload["planned_payload"]["evidence_refs"]] == [
        "program_manifest",
        "promotion_decision_record",
        "candidate_comparison",
    ]
    assert payload["idempotency"]["export_id"] == payload["export_id"]
    assert payload["idempotency"]["safe_to_recompute"] is True
    assert (
        payload["idempotency"]["repeated_preflight_same_inputs_same_export_id"] is True
    )
    assert payload["idempotency"]["external_duplicate_check_performed"] is False
    assert payload["idempotency"]["external_duplicate_check_reason"] == (
        "AK was not called."
    )
    assert payload["effect"] == {
        "local_preflight_written": True,
        "external_authority_mutated": False,
        "ak_called": False,
        "governance_mutated": False,
        "program_files_mutated": False,
        "promotion_state_changed": False,
    }
    assert payload["non_authority"] == {
        "preflight_only": True,
        "planned_not_exported": True,
        "external_apply": False,
        "agent_kernel_mutation": False,
        "governance_authority": False,
        "promotion_authority": False,
        "oracle_authority": False,
        "winner_selection": False,
        "automatic_promotion": False,
    }
    assert payload["failure_model"] == {
        "states": [
            "planned",
            "attempted",
            "applied",
            "partial",
            "failed",
            "rolled_back",
        ],
        "current_state": "planned",
        "apply_receipt_required_for_state_change": True,
    }

    second = tmp_path / "export" / "ak-export-preflight-again.json"
    repeated = runner.invoke(
        app,
        [
            "adapters",
            "authority",
            "agent-kernel-export-preflight",
            "--manifest",
            str(program_root / "manifest.json"),
            "--external-ref",
            "AK-EXAMPLE",
            "--decision-record",
            str(decision_path),
            "--comparison",
            str(comparison_path),
            "--out",
            str(second),
            "--json",
        ],
    )
    assert repeated.exit_code == 0, repeated.output
    repeated_payload = json.loads(repeated.stdout)
    assert repeated_payload["export_id"] == payload["export_id"]
    assert (
        repeated_payload["idempotency"]["artifact_hashes_fingerprint"]
        == (payload["idempotency"]["artifact_hashes_fingerprint"])
    )

    assert _file_hashes(program_root) == source_hashes_before
    assert _file_hashes(candidate_root) == candidate_hashes_before
    assert (
        hashlib.sha256(decision_path.read_bytes()).hexdigest() == decision_hash_before
    )
    assert (
        hashlib.sha256(comparison_path.read_bytes()).hexdigest()
        == comparison_hash_before
    )
    assert not (program_root / "ak-export-preflight.json").exists()
    assert (program_root / "eval_behavior.py").exists()
    assert (candidate_root / "eval_behavior.py").exists()
    assert (program_root / "behavior_episode.json").exists()
    assert (candidate_root / "behavior_episode.json").exists()
    assert not (tmp_path / "generated" / "oracle" / "coordinates.db").exists()


def test_agent_kernel_export_preflight_degrades_without_optional_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    artifact = materialize_program_from_intent(
        ProgramIntent(
            name="AuthorityOnlyProgram",
            objective="Answer with portable local evidence.",
            inputs=["question"],
            outputs=["answer"],
            promotion={
                "external_authority": {
                    "refs": [
                        {
                            "system": "agent_kernel",
                            "ref": "AK-EXAMPLE",
                            "role": "optional_authority_export_target",
                        }
                    ]
                }
            },
        ),
        outdir=tmp_path / "program",
    )
    program_root = Path(artifact.root_path)
    before = _file_hashes(program_root)

    payload = build_program_external_authority_export_preflight(
        manifest_path=program_root / "manifest.json",
        external_ref="AK-EXAMPLE",
    )

    assert payload["schema_version"] == "program-external-authority-export-preflight-v1"
    assert payload["status"] == "incomplete_preflight"
    assert (
        payload["preflight"]["target_ref_matches_manifest_external_authority_refs"]
        is True
    )
    assert payload["preflight"]["decision_record_present"] is False
    assert payload["preflight"]["decision_record_identity_matches_manifest"] is False
    assert payload["preflight"]["comparison_present"] is False
    assert payload["preflight"]["comparison_mentions_manifest_identity"] is False
    assert "missing_decision_record" in payload["preflight"]["blocking_reasons"]
    assert "missing_candidate_comparison" in payload["preflight"]["blocking_reasons"]
    assert payload["artifact_hashes"]["decision_record_sha256"] is None
    assert payload["artifact_hashes"]["comparison_sha256"] is None
    assert payload["effect"]["local_preflight_written"] is False
    assert payload["effect"]["ak_called"] is False
    assert payload["effect"]["external_authority_mutated"] is False
    assert payload["effect"]["governance_mutated"] is False
    assert _file_hashes(program_root) == before
    assert not (tmp_path / "oracle" / "coordinates.db").exists()


def test_agent_kernel_export_preflight_not_ready_when_promotion_already_applied(
    tmp_path: Path,
) -> None:
    identity = {
        "request_id": "req-1",
        "candidate_id": "cand-1",
        "assembly_id": "asm-1",
        "episode_id": "episode-1",
        "receipt_bundle_id": "bundle-1",
    }
    manifest = {
        "schema_version": "program-candidate-assembly-v1",
        "request": {"request_id": identity["request_id"]},
        "candidate_assembly": {
            "artifact_kind": "program",
            "candidate_id": identity["candidate_id"],
            "assembly_id": identity["assembly_id"],
        },
        "execution_episode": {"episode_id": identity["episode_id"]},
        "receipt_bundle": {"receipt_bundle_id": identity["receipt_bundle_id"]},
        "program_promotion_review": {
            "promotion_state": "promoted",
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
    }
    decision = {
        "schema_version": "program-promotion-decision-record-v1",
        "status": "recorded",
        "outcome": "request_more_evidence",
        "promotion_state_after_decision": "not_promoted",
        "identity": identity,
        "effect": {
            "external_authority_mutated": False,
            "governance_mutated": False,
        },
        "non_authority": {
            "local_decision_record_only": True,
            "automatic_promotion": False,
            "oracle_ranking": False,
            "oracle_pruning": False,
            "oracle_promotion": False,
            "program_mutation": False,
            "refined_review_mutation": False,
            "new_candidate_generation": False,
            "governance_authority": False,
            "external_mutation": False,
        },
    }
    comparison = {
        "schema_version": "program-refinement-candidate-comparison-v1",
        "source_identity": identity,
        "candidate_identity": identity,
        "non_authority": {
            "local_comparison_only": True,
            "oracle_ranking": False,
            "oracle_pruning": False,
            "oracle_promotion": False,
            "winner_selection": False,
            "automatic_promotion": False,
            "program_mutation": False,
            "new_candidate_generation": False,
            "governance_authority": False,
            "external_mutation": False,
        },
    }
    manifest_path = tmp_path / "manifest.json"
    decision_path = tmp_path / "decision.json"
    comparison_path = tmp_path / "comparison.json"
    _write_json(manifest_path, manifest)
    _write_json(decision_path, decision)
    _write_json(comparison_path, comparison)

    payload = build_program_external_authority_export_preflight(
        manifest_path=manifest_path,
        external_ref="AK-EXAMPLE",
        decision_record_path=decision_path,
        comparison_path=comparison_path,
    )

    assert payload["status"] == "incomplete_preflight"
    assert (
        payload["preflight"]["target_ref_matches_manifest_external_authority_refs"]
        is True
    )
    assert payload["preflight"]["decision_record_present"] is True
    assert payload["preflight"]["comparison_present"] is True
    assert payload["preflight"]["promotion_not_applied"] is False
    assert (
        "promotion_already_applied_or_state_not_not_promoted"
        in payload["preflight"]["blocking_reasons"]
    )


def test_agent_kernel_export_preflight_fails_closed_on_authority_widened_sidecars(
    tmp_path: Path,
) -> None:
    identity = {
        "request_id": "req-1",
        "candidate_id": "cand-1",
        "assembly_id": "asm-1",
        "episode_id": "episode-1",
        "receipt_bundle_id": "bundle-1",
    }
    manifest = {
        "schema_version": "program-candidate-assembly-v1",
        "request": {"request_id": identity["request_id"]},
        "candidate_assembly": {
            "artifact_kind": "program",
            "candidate_id": identity["candidate_id"],
            "assembly_id": identity["assembly_id"],
        },
        "execution_episode": {"episode_id": identity["episode_id"]},
        "receipt_bundle": {"receipt_bundle_id": identity["receipt_bundle_id"]},
        "program_promotion_review": {
            "promotion_state": "not_promoted",
            "external_authority": {
                "refs": [{"system": "agent_kernel", "ref": "AK-EXAMPLE"}]
            },
        },
    }
    decision = {
        "schema_version": "program-promotion-decision-record-v1",
        "status": "recorded",
        "outcome": "promote",
        "promotion_state_after_decision": "local_promotion_decision_recorded",
        "identity": identity,
        "effect": {
            "external_authority_mutated": False,
            "governance_mutated": False,
        },
        "non_authority": {
            "local_decision_record_only": True,
            "automatic_promotion": False,
            "oracle_ranking": False,
            "oracle_pruning": False,
            "oracle_promotion": False,
            "program_mutation": False,
            "refined_review_mutation": False,
            "new_candidate_generation": False,
            "governance_authority": True,
            "external_mutation": True,
        },
    }
    comparison = {
        "schema_version": "program-refinement-candidate-comparison-v1",
        "source_identity": identity,
        "non_authority": {
            "local_comparison_only": True,
            "oracle_ranking": False,
            "oracle_pruning": False,
            "oracle_promotion": False,
            "winner_selection": False,
            "automatic_promotion": False,
            "program_mutation": False,
            "new_candidate_generation": False,
            "governance_authority": False,
            "external_mutation": False,
        },
    }
    manifest_path = tmp_path / "manifest.json"
    decision_path = tmp_path / "decision.json"
    comparison_path = tmp_path / "comparison.json"
    _write_json(manifest_path, manifest)
    _write_json(decision_path, decision)
    _write_json(comparison_path, comparison)

    with pytest.raises(
        ProgramExternalAuthorityExportError,
        match="widens non-authority flags",
    ):
        build_program_external_authority_export_preflight(
            manifest_path=manifest_path,
            external_ref="AK-EXAMPLE",
            decision_record_path=decision_path,
            comparison_path=comparison_path,
        )

    promoting_decision = json.loads(decision_path.read_text(encoding="utf-8"))
    promoting_decision["non_authority"]["governance_authority"] = False
    promoting_decision["non_authority"]["external_mutation"] = False
    _write_json(decision_path, promoting_decision)
    with pytest.raises(
        ProgramExternalAuthorityExportError,
        match="promotion_state_after_decision must be not_promoted",
    ):
        build_program_external_authority_export_preflight(
            manifest_path=manifest_path,
            external_ref="AK-EXAMPLE",
            decision_record_path=decision_path,
            comparison_path=comparison_path,
        )

    safe_decision = json.loads(decision_path.read_text(encoding="utf-8"))
    safe_decision["outcome"] = "request_more_evidence"
    safe_decision["promotion_state_after_decision"] = "not_promoted"
    _write_json(decision_path, safe_decision)
    comparison_without_contract = json.loads(
        comparison_path.read_text(encoding="utf-8")
    )
    comparison_without_contract.pop("non_authority")
    _write_json(comparison_path, comparison_without_contract)
    with pytest.raises(
        ProgramExternalAuthorityExportError,
        match="program refinement candidate comparison must be local-only",
    ):
        build_program_external_authority_export_preflight(
            manifest_path=manifest_path,
            external_ref="AK-EXAMPLE",
            decision_record_path=decision_path,
            comparison_path=comparison_path,
        )


def test_agent_kernel_export_preflight_fails_closed_on_identity_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, _candidate_root, decision_path, comparison_path = (
        _materialize_external_authority_path(tmp_path, monkeypatch)
    )
    bad_decision = json.loads(decision_path.read_text(encoding="utf-8"))
    bad_decision["identity"]["candidate_id"] = "prog-cand-other"
    bad_decision_path = tmp_path / "promotion" / "bad_decision.json"
    _write_json(bad_decision_path, bad_decision)

    with pytest.raises(ProgramExternalAuthorityExportError, match="candidate_id"):
        build_program_external_authority_export_preflight(
            manifest_path=program_root / "manifest.json",
            external_ref="AK-EXAMPLE",
            decision_record_path=bad_decision_path,
            comparison_path=comparison_path,
        )

    bad_comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
    bad_comparison["source_identity"]["candidate_id"] = "prog-cand-other"
    bad_comparison["candidate_identity"]["candidate_id"] = "prog-cand-another"
    bad_comparison_path = tmp_path / "refinement" / "bad_comparison.json"
    _write_json(bad_comparison_path, bad_comparison)

    with pytest.raises(
        ProgramExternalAuthorityExportError,
        match="must mention manifest identity",
    ):
        build_program_external_authority_export_preflight(
            manifest_path=program_root / "manifest.json",
            external_ref="AK-EXAMPLE",
            decision_record_path=decision_path,
            comparison_path=bad_comparison_path,
        )
