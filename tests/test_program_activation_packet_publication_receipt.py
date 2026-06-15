from __future__ import annotations

import json
from pathlib import Path

import pytest

from dspx.cli.dspx import app
from program_activation_packet_shared import (
    _materialize_program,
    _materialize_review_chain,
    _write_oracle_publication_receipt,
    runner,
)

pytestmark = pytest.mark.slow


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
    assert "jury_evidence" in payload["missing_required_evidence"]
    assert "refined_promotion_review" in payload["missing_required_evidence"]
    assert "rollout_owner" in payload["missing_required_evidence"]
    assert "rollback_plan" in payload["missing_required_evidence"]
    assert payload["effect"]["production_activation_applied"] is False


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
            "--oracle-publication-receipt",
            str(receipt_path),
            "--out",
            str(out_path),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "source.preflight_sha256 does not match supplied preflight" in result.output
    assert not out_path.exists()
    assert not out_path.parent.exists()


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
