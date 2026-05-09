from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest
from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.coordinates import CoordinateStore, ExecutionEmbedding, reset_embedding_engine
from dspx.services.program_adjudication_publication import (
    ADJUDICATION_TRACE_PUBLICATION_PREFLIGHT_SCHEMA,
    ADJUDICATION_TRACE_PUBLICATION_RECEIPT_SCHEMA,
    ADJUDICATION_TRACE_PUBLICATION_RECORD_SCHEMA,
    ADJUDICATION_TRACE_PUBLICATION_RUN_KIND,
    ProgramAdjudicationPublicationError,
    build_adjudication_trace_publication_preflight,
    publish_adjudication_trace_preflight,
    write_adjudication_trace_publication_preflight,
    write_adjudication_trace_publication_receipt,
)
from dspx.services.program_intent import ProgramIntent
from dspx.services.program_meta_adjudication import (
    build_program_adjudication_behavior_trace,
    build_program_adjudicator_delegation,
    build_program_adjudicator_formation,
    build_program_adjudicator_verification,
    build_program_evidence_adjudication,
    build_program_jury_requirements,
    build_program_jury_verification,
    build_program_meta_jury_selection,
    write_program_adjudication_behavior_trace,
    write_program_adjudicator_delegation,
    write_program_adjudicator_formation,
    write_program_adjudicator_verification,
    write_program_evidence_adjudication,
    write_program_jury_requirements,
    write_program_jury_verification,
    write_program_meta_jury_selection,
)
from dspx.services.program_promotion_decision import (
    build_generated_program_adjudicator_decision_record,
    write_program_promotion_decision_record,
)
from dspx.services.program_service import materialize_program_from_intent

runner = CliRunner()


class FakeSharedOracleStore:
    backend_name = "fake_shared_oracle"
    redacted_database_url = (
        "postgresql://dspx_oracle:<redacted>@example.invalid:5432/dspx_oracle"
    )

    def __init__(self) -> None:
        self.records: dict[str, ExecutionEmbedding] = {}
        self.upsert_calls = 0

    def upsert(self, embedding: ExecutionEmbedding) -> bool:
        self.upsert_calls += 1
        self.records[embedding.run_id] = embedding
        return True


def _setup_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "mock")
    reset_embedding_engine()


def _materialize_candidate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    _setup_env(tmp_path, monkeypatch)
    intent = ProgramIntent(
        name="TicketProgram",
        objective="Classify support ticket urgency for human review queue.",
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
            "adjudicator": {"kind": "ai_agent", "id": "dspx_program_adjudicator_v1"}
        },
    )
    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "program")
    return Path(artifact.root_path)


def _write_activation_packet(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "generated-cognition-program-production-activation-packet-v1",
                "canonical_binding_ref": "AK-TEST-BINDING",
                "boundary_checks": {
                    "dspx_activation_authority": False,
                    "jury_promotion_authority": False,
                    "oracle_promotion_authority": False,
                },
                "effect": {"production_activation_applied": False},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _write_trace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = _materialize_candidate(tmp_path, monkeypatch)
    requirements_path = tmp_path / "jury_requirements.json"
    selection_path = tmp_path / "meta_jury_selection.json"
    jury_verification_path = tmp_path / "jury_verification.json"
    formation_path = tmp_path / "program_adjudicator_formation.json"
    adjudicator_verification_path = tmp_path / "program_adjudicator_verification.json"
    delegation_path = tmp_path / "program_adjudicator_delegation.json"
    adjudication_path = tmp_path / "program_evidence_adjudication.json"
    decision_path = tmp_path / "promotion_decision_record.json"
    trace_path = tmp_path / "adjudication_behavior_trace.json"
    activation_packet_path = root / "activation_packet.json"

    requirements = build_program_jury_requirements(manifest_path=root / "manifest.json")
    write_program_jury_requirements(requirements, requirements_path)
    selection = build_program_meta_jury_selection(
        jury_requirements_path=requirements_path
    )
    write_program_meta_jury_selection(selection, selection_path)
    jury_verification = build_program_jury_verification(
        jury_selection_path=selection_path
    )
    write_program_jury_verification(jury_verification, jury_verification_path)
    formation = build_program_adjudicator_formation(
        jury_verification_path=jury_verification_path
    )
    write_program_adjudicator_formation(formation, formation_path)
    adjudicator_verification = build_program_adjudicator_verification(
        adjudicator_formation_path=formation_path
    )
    write_program_adjudicator_verification(
        adjudicator_verification, adjudicator_verification_path
    )
    delegation = build_program_adjudicator_delegation(
        manifest_path=root / "manifest.json",
        adjudicator_verification_path=adjudicator_verification_path,
    )
    write_program_adjudicator_delegation(delegation, delegation_path)
    _write_activation_packet(activation_packet_path)
    adjudication = build_program_evidence_adjudication(
        adjudicator_verification_path=adjudicator_verification_path,
        manifest_path=root / "manifest.json",
        activation_packet_path=activation_packet_path,
    )
    write_program_evidence_adjudication(adjudication, adjudication_path)
    decision = build_generated_program_adjudicator_decision_record(
        evidence_adjudication_path=adjudication_path,
        adjudicator_delegation_path=delegation_path,
    )
    write_program_promotion_decision_record(decision, decision_path)
    trace = build_program_adjudication_behavior_trace(
        evidence_adjudication_path=adjudication_path,
        adjudicator_delegation_path=delegation_path,
        decision_record_path=decision_path,
    )
    write_program_adjudication_behavior_trace(trace, trace_path)
    return trace_path


def _preflight_kwargs(trace_path: Path) -> dict[str, Any]:
    return {
        "trace_path": trace_path,
        "target": "shared-postgres",
        "publication_label": "adjudication_behavior_trace",
        "publisher_id": "pi-session-test",
        "publisher_role": "operator",
        "publisher_assertion": "share checked adjudication trace for future Oracle retrieval and GEPA analysis",
        "redaction_status": "checked",
        "retention_class": "retained_behavior_memory",
    }


def test_adjudication_trace_publication_preflight_cli_writes_local_packet_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trace_path = _write_trace(tmp_path, monkeypatch)
    monkeypatch.setenv("DSPX_ORACLE_STORE", "postgres_pgvector")
    monkeypatch.setenv(
        "DSPX_ORACLE_DATABASE_URL",
        "postgresql://dspx_oracle:super-secret-password@ds1621:55432/dspx_oracle",
    )
    out = tmp_path / "publication" / "preflight.json"

    result = runner.invoke(
        app,
        [
            "oracle",
            "adjudication-trace",
            "publish-preflight",
            "--trace",
            str(trace_path),
            "--target",
            "shared-postgres",
            "--publisher-id",
            "pi-session-test",
            "--publisher-role",
            "operator",
            "--publisher-assertion",
            "share checked adjudication trace for future Oracle retrieval and GEPA analysis",
            "--redaction-status",
            "checked",
            "--out",
            str(out),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "super-secret-password" not in result.stdout
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == ADJUDICATION_TRACE_PUBLICATION_PREFLIGHT_SCHEMA
    assert payload["status"] == "ready_not_published"
    assert payload["publication"]["publication_label"] == "adjudication_behavior_trace"
    assert payload["preflight"]["ready_for_shared_publication"] is True
    assert payload["preflight"]["blocking_reasons"] == []
    assert payload["effect"]["shared_oracle_mutated"] is False
    assert payload["non_authority"]["activation_authority"] is False
    assert "super-secret-password" not in out.read_text(encoding="utf-8")


def test_adjudication_trace_publication_preflight_fails_closed_on_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trace_path = _write_trace(tmp_path, monkeypatch)
    kwargs = _preflight_kwargs(trace_path)
    kwargs["redaction_status"] = "unknown"

    with pytest.raises(ProgramAdjudicationPublicationError, match="redaction_status"):
        build_adjudication_trace_publication_preflight(**kwargs)

    kwargs = _preflight_kwargs(trace_path)
    kwargs["publication_label"] = "activated"
    with pytest.raises(ProgramAdjudicationPublicationError, match="authority_ref"):
        build_adjudication_trace_publication_preflight(**kwargs)

    kwargs = _preflight_kwargs(trace_path)
    kwargs["publisher_assertion"] = "password=super-secret-value"
    with pytest.raises(ProgramAdjudicationPublicationError, match="secret"):
        build_adjudication_trace_publication_preflight(**kwargs)


def test_adjudication_trace_publish_writes_shared_record_and_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trace_path = _write_trace(tmp_path, monkeypatch)
    preflight = build_adjudication_trace_publication_preflight(
        **_preflight_kwargs(trace_path)
    )
    preflight_path = tmp_path / "preflight.json"
    write_adjudication_trace_publication_preflight(preflight, preflight_path)
    store = FakeSharedOracleStore()

    receipt = publish_adjudication_trace_preflight(
        preflight_path=preflight_path,
        store=cast(CoordinateStore, store),
    )
    receipt_path = tmp_path / "receipt.json"
    payload = write_adjudication_trace_publication_receipt(receipt, receipt_path)

    assert payload["schema_version"] == ADJUDICATION_TRACE_PUBLICATION_RECEIPT_SCHEMA
    assert payload["status"] == "published"
    assert payload["effect"]["shared_oracle_mutated"] is True
    assert payload["effect"]["local_receipt_written"] is True
    assert payload["non_authority"]["oracle_authority"] is False
    assert payload["non_authority"]["activation_authority"] is False
    assert len(store.records) == 1
    record = next(iter(store.records.values()))
    assert record.run_id == payload["run_id"]
    assert record.run_kind == ADJUDICATION_TRACE_PUBLICATION_RUN_KIND
    assert record.template_version == ADJUDICATION_TRACE_PUBLICATION_RECORD_SCHEMA
    assert record.metadata["publication_label"] == "adjudication_behavior_trace"
    assert record.metadata["non_authority"]["activation_authority"] is False
    trace_summary = record.metadata["planned_record"]["trace_summary"]
    assert trace_summary["has_program_adjudicator_delegation"] is True
    assert trace_summary["has_generated_program_adjudicator_decision"] is True
    assert trace_summary["meta_adjudicator_id"] == "dspx_meta_adjudicator_v1"
    assert trace_summary["generated_program_adjudicator_id"] == (
        "dspx_program_adjudicator_v1"
    )
    assert record.metadata["judging_behavior"]["generated_program_adjudicator_id"] == (
        "dspx_program_adjudicator_v1"
    )
    assert "program_adjudicator_delegation" in record.metadata["linked_artifact_refs"]
    assert (
        "generated_program_adjudicator_decision"
        in record.metadata["linked_artifact_refs"]
    )
    assert '"path"' not in json.dumps(record.metadata["linked_artifact_refs"])
    assert receipt_path.exists()


def test_adjudication_trace_publish_rejects_tampered_trace_after_preflight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trace_path = _write_trace(tmp_path, monkeypatch)
    preflight = build_adjudication_trace_publication_preflight(
        **_preflight_kwargs(trace_path)
    )
    preflight_path = tmp_path / "preflight.json"
    write_adjudication_trace_publication_preflight(preflight, preflight_path)
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    trace["status"] = "tampered"
    trace_path.write_text(json.dumps(trace, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(ProgramAdjudicationPublicationError, match="hash"):
        publish_adjudication_trace_preflight(
            preflight_path=preflight_path,
            store=cast(CoordinateStore, FakeSharedOracleStore()),
        )


def test_adjudication_trace_publish_cli_fails_without_shared_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trace_path = _write_trace(tmp_path, monkeypatch)
    preflight = build_adjudication_trace_publication_preflight(
        **_preflight_kwargs(trace_path)
    )
    preflight_path = tmp_path / "preflight.json"
    write_adjudication_trace_publication_preflight(preflight, preflight_path)
    monkeypatch.delenv("DSPX_ORACLE_STORE", raising=False)
    monkeypatch.delenv("DSPX_ORACLE_DATABASE_URL", raising=False)
    monkeypatch.delenv("DSPX_ORACLE_POSTGRES_URL", raising=False)

    result = runner.invoke(
        app,
        [
            "oracle",
            "adjudication-trace",
            "publish",
            "--preflight",
            str(preflight_path),
            "--receipt-out",
            str(tmp_path / "receipt.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "Postgres/pgvector Oracle backend" in result.output
