from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest
from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.coordinates import CoordinateStore, ExecutionEmbedding, reset_embedding_engine
from dspx.services.program_intent import ProgramIntent
from dspx.services.program_oracle_publication import (
    PROGRAM_ORACLE_PUBLICATION_RECEIPT_SCHEMA,
    PROGRAM_ORACLE_PUBLICATION_RECORD_SCHEMA,
    PROGRAM_ORACLE_PUBLICATION_RUN_KIND,
    ProgramOraclePublicationError,
    publish_program_oracle_preflight,
    write_program_oracle_publication_receipt,
)
from dspx.services.program_oracle_publication_preflight import (
    build_program_oracle_publication_preflight,
    write_program_oracle_publication_preflight,
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


def _materialize_example_program(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "mock")
    reset_embedding_engine()
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
    )
    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "program")
    return Path(artifact.root_path)


def _write_preflight(
    root: Path,
    out: Path,
    **overrides: Any,
) -> Path:
    kwargs: dict[str, Any] = {
        "manifest_path": root / "manifest.json",
        "target": "shared-postgres",
        "publication_label": "retained",
        "publisher_id": "pi-session-test",
        "publisher_role": "operator",
        "publisher_assertion": "share synthetic behavior evidence for future Oracle retrieval",
        "redaction_status": "checked",
        "retention_class": "retained_behavior_memory",
    }
    kwargs.update(overrides)
    packet = build_program_oracle_publication_preflight(**kwargs)
    write_program_oracle_publication_preflight(packet, out)
    return out


def test_program_oracle_publish_writes_shared_record_and_local_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _materialize_example_program(tmp_path, monkeypatch)
    preflight_path = _write_preflight(root, tmp_path / "preflight.json")
    store = FakeSharedOracleStore()

    receipt = publish_program_oracle_preflight(
        preflight_path=preflight_path,
        store=cast(CoordinateStore, store),
    )
    receipt_path = tmp_path / "publication" / "receipt.json"
    payload = write_program_oracle_publication_receipt(receipt, receipt_path)

    assert payload["schema_version"] == PROGRAM_ORACLE_PUBLICATION_RECEIPT_SCHEMA
    assert payload["status"] == "published"
    assert payload["effect"] == {
        "local_receipt_written": True,
        "oracle_index_mutated": False,
        "shared_oracle_mutated": True,
        "ak_called": False,
        "governance_mutated": False,
        "mlflow_mutated": False,
        "program_files_mutated": False,
        "promotion_state_changed": False,
    }
    assert payload["non_authority"]["oracle_authority"] is False
    assert payload["non_authority"]["automatic_promotion"] is False
    assert payload["target"]["database_url_redacted"] == (
        "postgresql://dspx_oracle:<redacted>@example.invalid:5432/dspx_oracle"
    )
    assert len(store.records) == 1
    record = next(iter(store.records.values()))
    assert record.run_id == payload["run_id"]
    assert record.run_kind == PROGRAM_ORACLE_PUBLICATION_RUN_KIND
    assert record.template_version == PROGRAM_ORACLE_PUBLICATION_RECORD_SCHEMA
    assert record.metadata["publication_id"] == payload["publication_id"]
    assert record.metadata["publication_label"] == "retained"
    assert record.metadata["publication_label_class"] == "empirical"
    assert record.metadata["non_authority"] == {
        "oracle_ranking": False,
        "oracle_pruning": False,
        "oracle_promotion": False,
        "governance_authority": False,
        "external_mutation": False,
    }
    assert receipt_path.exists()


def test_program_oracle_publish_is_idempotent_by_publication_run_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _materialize_example_program(tmp_path, monkeypatch)
    preflight_path = _write_preflight(root, tmp_path / "preflight.json")
    store = FakeSharedOracleStore()

    first = publish_program_oracle_preflight(
        preflight_path=preflight_path,
        store=cast(CoordinateStore, store),
    )
    second = publish_program_oracle_preflight(
        preflight_path=preflight_path,
        store=cast(CoordinateStore, store),
    )

    assert first["publication_id"] == second["publication_id"]
    assert first["run_id"] == second["run_id"]
    assert len(store.records) == 1
    assert store.upsert_calls == 2
    assert second["idempotency"]["safe_to_retry"] is True


def test_program_oracle_publish_rejects_tampered_artifact_after_preflight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _materialize_example_program(tmp_path, monkeypatch)
    preflight_path = _write_preflight(root, tmp_path / "preflight.json")
    evidence_path = root / "oracle_evidence.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["oracle_text"] += "\ntampered after preflight"
    evidence_path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(ProgramOraclePublicationError, match="hash no longer matches"):
        publish_program_oracle_preflight(
            preflight_path=preflight_path,
            store=cast(CoordinateStore, FakeSharedOracleStore()),
        )


def test_program_oracle_publish_rejects_runtime_trace_artifact_drift_after_preflight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _materialize_example_program(tmp_path, monkeypatch)
    preflight_path = _write_preflight(root, tmp_path / "preflight.json")
    traces_path = root / "program_runtime_traces.json"
    traces = json.loads(traces_path.read_text(encoding="utf-8"))
    traces["status"] = "tampered"
    traces_path.write_text(json.dumps(traces, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(
        ProgramOraclePublicationError,
        match="runtime traces hash no longer matches",
    ):
        publish_program_oracle_preflight(
            preflight_path=preflight_path,
            store=cast(CoordinateStore, FakeSharedOracleStore()),
        )


def test_program_oracle_publish_rejects_runtime_trace_preflight_summary_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _materialize_example_program(tmp_path, monkeypatch)
    preflight_path = _write_preflight(root, tmp_path / "preflight.json")
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    traces = json.loads(
        (root / "program_runtime_traces.json").read_text(encoding="utf-8")
    )
    traces["status"] = "alternate"
    alternate = tmp_path / "alternate_runtime_traces.json"
    alternate.write_text(json.dumps(traces, indent=2) + "\n", encoding="utf-8")
    preflight["created_from"]["runtime_traces_path"] = str(alternate)
    preflight["artifact_hashes"]["runtime_traces_sha256"] = hashlib.sha256(
        alternate.read_bytes()
    ).hexdigest()
    preflight_path.write_text(json.dumps(preflight, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(
        ProgramOraclePublicationError,
        match="runtime traces hash does not match program Oracle evidence summary",
    ):
        publish_program_oracle_preflight(
            preflight_path=preflight_path,
            store=cast(CoordinateStore, FakeSharedOracleStore()),
        )


def test_program_oracle_publish_rejects_tampered_runtime_trace_planned_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _materialize_example_program(tmp_path, monkeypatch)
    preflight_path = _write_preflight(root, tmp_path / "preflight.json")
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    preflight["planned_record"]["runtime_traces"]["module_calls"] = [
        {"leak": "raw-trace"}
    ]
    preflight_path.write_text(json.dumps(preflight, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(ProgramOraclePublicationError, match="runtime_traces"):
        publish_program_oracle_preflight(
            preflight_path=preflight_path,
            store=cast(CoordinateStore, FakeSharedOracleStore()),
        )


def test_program_oracle_publish_rejects_failed_preflight_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _materialize_example_program(tmp_path, monkeypatch)
    preflight_path = _write_preflight(root, tmp_path / "preflight.json")
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    preflight["preflight"]["redaction_status_eligible"] = False
    preflight_path.write_text(json.dumps(preflight, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(
        ProgramOraclePublicationError, match="redaction_status_eligible"
    ):
        publish_program_oracle_preflight(
            preflight_path=preflight_path,
            store=cast(CoordinateStore, FakeSharedOracleStore()),
        )


def test_program_oracle_publish_cli_fails_closed_without_shared_backend_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _materialize_example_program(tmp_path, monkeypatch)
    preflight_path = _write_preflight(root, tmp_path / "preflight.json")
    monkeypatch.delenv("DSPX_ORACLE_STORE", raising=False)
    monkeypatch.delenv("DSPX_ORACLE_DATABASE_URL", raising=False)
    monkeypatch.delenv("DSPX_ORACLE_POSTGRES_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    receipt_path = tmp_path / "receipt.json"

    result = runner.invoke(
        app,
        [
            "oracle",
            "program-evidence",
            "publish",
            "--preflight",
            str(preflight_path),
            "--receipt-out",
            str(receipt_path),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "configured and available Postgres/pgvector Oracle backend" in result.output
    assert not receipt_path.exists()


def test_program_oracle_publish_cli_rejects_invalid_preflight_schema(
    tmp_path: Path,
) -> None:
    preflight_path = tmp_path / "preflight.json"
    preflight_path.write_text(
        json.dumps({"schema_version": "not-the-schema"}) + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "oracle",
            "program-evidence",
            "publish",
            "--preflight",
            str(preflight_path),
            "--receipt-out",
            str(tmp_path / "receipt.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "preflight schema_version" in result.output


def test_program_oracle_publish_rejects_tampered_publication_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _materialize_example_program(tmp_path, monkeypatch)
    preflight_path = _write_preflight(root, tmp_path / "preflight.json")
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    preflight["publication"]["redaction_status"] = "contains_sensitive_material"
    preflight["planned_record"]["redaction_status"] = "contains_sensitive_material"
    preflight_path.write_text(json.dumps(preflight, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(ProgramOraclePublicationError, match="redaction_status"):
        publish_program_oracle_preflight(
            preflight_path=preflight_path,
            store=cast(CoordinateStore, FakeSharedOracleStore()),
        )


def test_program_oracle_publish_rejects_tampered_publisher_assertion_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _materialize_example_program(tmp_path, monkeypatch)
    preflight_path = _write_preflight(root, tmp_path / "preflight.json")
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    preflight["publication"]["publisher_assertion"] = "password=leaked-secret"
    preflight_path.write_text(json.dumps(preflight, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(ProgramOraclePublicationError, match="secret"):
        publish_program_oracle_preflight(
            preflight_path=preflight_path,
            store=cast(CoordinateStore, FakeSharedOracleStore()),
        )


def test_program_oracle_publish_rejects_tampered_publication_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _materialize_example_program(tmp_path, monkeypatch)
    preflight_path = _write_preflight(root, tmp_path / "preflight.json")
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    preflight["publication_id"] = "prog-oracle-pub-tampered"
    preflight_path.write_text(json.dumps(preflight, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(ProgramOraclePublicationError, match="idempotency"):
        publish_program_oracle_preflight(
            preflight_path=preflight_path,
            store=cast(CoordinateStore, FakeSharedOracleStore()),
        )


def test_program_oracle_publish_rejects_widened_planned_record_non_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _materialize_example_program(tmp_path, monkeypatch)
    preflight_path = _write_preflight(root, tmp_path / "preflight.json")
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    preflight["planned_record"]["non_authority"]["oracle_promotion"] = True
    preflight_path.write_text(json.dumps(preflight, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(ProgramOraclePublicationError, match="oracle_promotion"):
        publish_program_oracle_preflight(
            preflight_path=preflight_path,
            store=cast(CoordinateStore, FakeSharedOracleStore()),
        )


def test_program_oracle_publish_cli_rejects_receipt_protected_artifact_overwrite_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _materialize_example_program(tmp_path, monkeypatch)
    preflight_path = _write_preflight(root, tmp_path / "preflight.json")
    program_path = root / "program.py"
    original_program = program_path.read_bytes()
    monkeypatch.delenv("DSPX_ORACLE_STORE", raising=False)
    monkeypatch.delenv("DSPX_ORACLE_DATABASE_URL", raising=False)
    monkeypatch.delenv("DSPX_ORACLE_POSTGRES_URL", raising=False)

    result = runner.invoke(
        app,
        [
            "oracle",
            "program-evidence",
            "publish",
            "--preflight",
            str(preflight_path),
            "--receipt-out",
            str(program_path),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "must not overwrite program.py" in result.output
    assert "DSPX_ORACLE_STORE=postgres_pgvector" not in result.output
    assert program_path.read_bytes() == original_program


def test_program_oracle_publish_cli_rejects_receipt_preflight_overwrite_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _materialize_example_program(tmp_path, monkeypatch)
    preflight_path = _write_preflight(root, tmp_path / "preflight.json")
    original_preflight = preflight_path.read_bytes()
    monkeypatch.delenv("DSPX_ORACLE_STORE", raising=False)
    monkeypatch.delenv("DSPX_ORACLE_DATABASE_URL", raising=False)
    monkeypatch.delenv("DSPX_ORACLE_POSTGRES_URL", raising=False)

    result = runner.invoke(
        app,
        [
            "oracle",
            "program-evidence",
            "publish",
            "--preflight",
            str(preflight_path),
            "--receipt-out",
            str(preflight_path),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "must not overwrite an input artifact" in result.output
    assert "DSPX_ORACLE_STORE=postgres_pgvector" not in result.output
    assert preflight_path.read_bytes() == original_preflight


def test_program_oracle_publish_cli_rejects_ambient_database_url_without_oracle_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _materialize_example_program(tmp_path, monkeypatch)
    preflight_path = _write_preflight(root, tmp_path / "preflight.json")
    monkeypatch.delenv("DSPX_ORACLE_STORE", raising=False)
    monkeypatch.delenv("DSPX_ORACLE_DATABASE_URL", raising=False)
    monkeypatch.delenv("DSPX_ORACLE_POSTGRES_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:password@example/db")
    receipt_path = tmp_path / "receipt.json"

    result = runner.invoke(
        app,
        [
            "oracle",
            "program-evidence",
            "publish",
            "--preflight",
            str(preflight_path),
            "--receipt-out",
            str(receipt_path),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "DSPX_ORACLE_STORE=postgres_pgvector" in result.output
    assert not receipt_path.exists()


def test_program_oracle_publish_preserves_redacted_secret_refs_without_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _materialize_example_program(tmp_path, monkeypatch)
    preflight_path = _write_preflight(
        root,
        tmp_path / "preflight.json",
        publisher_secret_refs=["op://Private/DSPx-Oracle/password"],
    )
    store = FakeSharedOracleStore()

    receipt = publish_program_oracle_preflight(
        preflight_path=preflight_path,
        store=cast(CoordinateStore, store),
    )

    refs = receipt["publication"]["publisher_secret_refs"]
    assert refs[0]["ref_redacted"] == "op://<redacted>/<redacted>/password"
    assert refs[0]["secret_value_persisted"] is False
    record = next(iter(store.records.values()))
    assert record.metadata["publication"]["publisher_secret_refs"] == refs
    assert "DSPx-Oracle" not in json.dumps(receipt)
    assert "Private" not in json.dumps(record.metadata)


def test_program_oracle_publish_rejects_tampered_secret_ref_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _materialize_example_program(tmp_path, monkeypatch)
    preflight_path = _write_preflight(
        root,
        tmp_path / "preflight.json",
        publisher_secret_refs=["op://Private/DSPx-Oracle/password"],
    )
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    preflight["publication"]["publisher_secret_refs"][0]["resolved_value"] = (
        "plaintext-secret"
    )
    preflight["planned_record"]["publisher_secret_refs"] = preflight["publication"][
        "publisher_secret_refs"
    ]
    preflight_path.write_text(json.dumps(preflight, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(ProgramOraclePublicationError, match="resolved secret values"):
        publish_program_oracle_preflight(
            preflight_path=preflight_path,
            store=cast(CoordinateStore, FakeSharedOracleStore()),
        )
