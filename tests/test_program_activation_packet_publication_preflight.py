from __future__ import annotations

import json
from pathlib import Path

import pytest

from dspx.cli.dspx import app
from program_activation_packet_shared import (
    _materialize_program,
    _write_candidate_state_with_publication_preflight,
    _write_oracle_publication_preflight,
    _write_oracle_publication_receipt,
    runner,
)

pytestmark = pytest.mark.slow


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
    assert "publication_id mismatch with supplied preflight" in result.output


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
