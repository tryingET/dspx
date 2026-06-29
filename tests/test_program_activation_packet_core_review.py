from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from dspx.cli.dspx import app
from program_activation_packet_shared import (
    _candidate_identity,
    _file_hashes,
    _materialize_program,
    _materialize_review_chain,
    _write_json,
    _write_obsidian_adapter_receipt,
    _write_target_aware_candidate_state,
    runner,
)

pytestmark = pytest.mark.slow


def _write_model_jury_results(
    root: Path,
    out: Path,
    *,
    authority_drift: bool = False,
    promotion_authority: bool = False,
    status: str = "executed",
) -> Path:
    identity = _candidate_identity(root)
    if authority_drift:
        identity = {**identity, "candidate_id": "wrong-candidate"}
    manifest_path = root / "manifest.json"
    _write_json(
        out,
        {
            "schema_version": "program-model-jury-results-v1",
            "status": status,
            "identity": identity,
            "created_from": {
                "manifest_path": str(manifest_path.resolve()),
                "manifest_sha256": hashlib.sha256(
                    manifest_path.read_bytes()
                ).hexdigest(),
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
            "juror_results": [
                {
                    "juror_id": "authority_agent",
                    "status": "judged",
                    "judgment": {"outcome": "request_more_evidence"},
                }
            ],
            "aggregate": {
                "judgment_counts": {"request_more_evidence": 1},
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
    return out


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
    assert "jury_evidence" in payload["missing_required_evidence"]
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


def test_program_promote_activation_packet_rejects_stale_jury_result_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, jury_path, review_path, decision_path = (
        _materialize_review_chain(tmp_path, monkeypatch)
    )
    bad_jury = json.loads(jury_path.read_text(encoding="utf-8"))
    bad_jury["created_from"] = {
        **bad_jury["created_from"],
        "behavior_results_sha256": "0" * 64,
    }
    bad_jury_path = tmp_path / "promotion" / "bad_jury_results.json"
    _write_json(bad_jury_path, bad_jury)

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
            str(bad_jury_path),
            "--review",
            str(review_path),
            "--decision-record",
            str(decision_path),
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
    assert (
        "jury_results behavior results sha256 does not match current file"
        in result.output
    )


@pytest.mark.parametrize(
    ("effect_patch", "expected_error"),
    [
        ({"program_files_mutated": True}, "jury_results widens effect flags"),
        (
            {"local_jury_evidence_only": False},
            "jury_results must be local jury evidence only",
        ),
    ],
)
def test_program_promote_activation_packet_rejects_spoofed_jury_effect_flags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    effect_patch: dict[str, object],
    expected_error: str,
) -> None:
    program_root, report_path, jury_path, review_path, decision_path = (
        _materialize_review_chain(tmp_path, monkeypatch)
    )
    before_hashes = _file_hashes(program_root)
    bad_jury = json.loads(jury_path.read_text(encoding="utf-8"))
    bad_jury["effect"] = {**bad_jury["effect"], **effect_patch}
    bad_jury_path = tmp_path / "promotion" / "bad_jury_effect.json"
    _write_json(bad_jury_path, bad_jury)
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
            str(bad_jury_path),
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

    assert result.exit_code == 2
    assert expected_error in result.output
    assert not out_path.exists()
    assert _file_hashes(program_root) == before_hashes


def test_program_promote_activation_packet_rejects_output_over_protected_or_input_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_program(tmp_path, monkeypatch)
    manifest_path = program_root / "manifest.json"
    manifest_before = manifest_path.read_bytes()

    protected_result = runner.invoke(
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
            "--out",
            str(manifest_path),
            "--json",
        ],
    )
    assert protected_result.exit_code != 0
    assert (
        "activation packet must not overwrite manifest.json" in protected_result.output
    )
    assert manifest_path.read_bytes() == manifest_before

    root_sidecar_result = runner.invoke(
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
            "--out",
            str(program_root / "activation_packet.json"),
            "--json",
        ],
    )
    assert root_sidecar_result.exit_code != 0
    assert (
        "activation packet output must not be written inside a protected artifact root"
        in root_sidecar_result.output
    )
    assert not (program_root / "activation_packet.json").exists()

    model_jury_path = _write_model_jury_results(
        program_root, tmp_path / "promotion" / "provider_jury.json"
    )
    model_jury_before = model_jury_path.read_bytes()
    input_overwrite_result = runner.invoke(
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
            "--model-jury-results",
            str(model_jury_path),
            "--out",
            str(model_jury_path),
            "--json",
        ],
    )
    assert input_overwrite_result.exit_code != 0
    assert (
        "activation packet output must not overwrite an input artifact"
        in input_overwrite_result.output
    )
    assert model_jury_path.read_bytes() == model_jury_before
    assert not (program_root / "activation_packet.json").exists()


def test_program_promote_activation_packet_accepts_model_jury_as_jury_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, _jury_path, review_path, _decision_path = (
        _materialize_review_chain(tmp_path, monkeypatch)
    )
    before_hashes = _file_hashes(program_root)
    model_jury_path = _write_model_jury_results(
        program_root,
        tmp_path / "promotion" / "model_jury_results.json",
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
            "--model-jury-results",
            str(model_jury_path),
            "--review",
            str(review_path),
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
    assert payload["status"] == "ready_for_domain_adjudication"
    assert payload["next_required_action"] == "record_domain_decision"
    assert payload["missing_required_evidence"] == []
    assert payload["remaining_activation_blockers"] == [
        "domain_decision_record",
        "canonical_binding_ref",
    ]
    assert payload["evidence"]["jury_results"] is None
    assert payload["evidence"]["model_jury_results"]["path"] == str(
        model_jury_path.resolve()
    )
    assert payload["decision"] == {
        "outcome": None,
        "promotion_state_after_decision": None,
        "decided_by": None,
    }
    assert payload["effect"]["production_activation_applied"] is False
    assert payload["effect"]["external_authority_mutated"] is False
    assert payload["non_authority"]["activation_packet_only"] is True
    assert payload["non_authority"]["program_activation_applied"] is False
    assert _file_hashes(program_root) == before_hashes
    assert not (program_root / "activation_packet.json").exists()


def test_program_promote_activation_packet_rejects_stale_model_jury_manifest_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, _jury_path, review_path, _decision_path = (
        _materialize_review_chain(tmp_path, monkeypatch)
    )
    model_jury = json.loads(
        _write_model_jury_results(
            program_root,
            tmp_path / "promotion" / "model_jury_results.json",
        ).read_text(encoding="utf-8")
    )
    model_jury["created_from"] = {
        **model_jury["created_from"],
        "manifest_sha256": "0" * 64,
    }
    model_jury_path = tmp_path / "promotion" / "stale_model_jury_results.json"
    _write_json(model_jury_path, model_jury)
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
            "--model-jury-results",
            str(model_jury_path),
            "--review",
            str(review_path),
            "--rollout-owner",
            "softwareco-runtime-operator",
            "--rollback-plan",
            "Disable the generated-program route and restore the previous production program version.",
            "--out",
            str(out_path),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "model_jury_results manifest sha256 does not match" in result.output
    assert not out_path.exists()


def test_program_promote_activation_packet_rejects_model_jury_identity_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, _jury_path, review_path, _decision_path = (
        _materialize_review_chain(tmp_path, monkeypatch)
    )
    model_jury_path = _write_model_jury_results(
        program_root,
        tmp_path / "promotion" / "model_jury_results.json",
        authority_drift=True,
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
            "--oracle-report",
            str(report_path),
            "--model-jury-results",
            str(model_jury_path),
            "--review",
            str(review_path),
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
    assert "model_jury_results identity does not match" in result.output


def test_program_promote_activation_packet_rejects_model_jury_invalid_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, _jury_path, review_path, _decision_path = (
        _materialize_review_chain(tmp_path, monkeypatch)
    )
    model_jury_path = _write_model_jury_results(
        program_root,
        tmp_path / "promotion" / "model_jury_results.json",
        status="not_executed",
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
            "--oracle-report",
            str(report_path),
            "--model-jury-results",
            str(model_jury_path),
            "--review",
            str(review_path),
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
    assert "status executed or executed_with_failures" in result.output


def test_program_promote_activation_packet_rejects_model_jury_authority_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, _jury_path, review_path, _decision_path = (
        _materialize_review_chain(tmp_path, monkeypatch)
    )
    model_jury_path = _write_model_jury_results(
        program_root,
        tmp_path / "promotion" / "model_jury_results.json",
        promotion_authority=True,
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
            "--oracle-report",
            str(report_path),
            "--model-jury-results",
            str(model_jury_path),
            "--review",
            str(review_path),
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
    assert "promotion authority" in result.output
