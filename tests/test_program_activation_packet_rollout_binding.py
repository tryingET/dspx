# summary: "Tests canonical binding verification and rollout-readiness gating for activation packets."
# read_when:
#   - "Changing activation-packet rollout ownership, canonical bindings, or rollout preflight transitions."

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dspx.cli.dspx import app
from dspx.services.program_activation_packet import (
    ProgramActivationPacketError,
    write_canonical_binding_verification,
)
from program_activation_packet_shared import (
    _materialize_review_chain,
    _write_canonical_binding_verification,
    _write_json,
    runner,
)

pytestmark = pytest.mark.slow


def test_canonical_binding_verification_rejects_output_inside_candidate_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, _report_path, _jury_path, _review_path, decision_path = (
        _materialize_review_chain(tmp_path, monkeypatch)
    )
    payload = {
        "schema_version": "program-canonical-binding-verification-v1",
        "status": "verified",
        "created_from": {
            "manifest_path": str((program_root / "manifest.json").resolve()),
            "decision_record_path": str(decision_path.resolve()),
        },
        "decision_record": {"path": str(decision_path.resolve())},
        "decision_record_sha256": "not-used-by-writer",
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
    }

    with pytest.raises(ProgramActivationPacketError, match="protected artifact root"):
        write_canonical_binding_verification(
            payload,
            program_root / "canonical_binding_verification.json",
        )

    assert not (program_root / "canonical_binding_verification.json").exists()


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
