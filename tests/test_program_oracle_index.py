# summary: "Tests indexing program Oracle evidence into local coordinates with validation, idempotency, and non-authority preservation."
# read_when:
#   - "Changing Oracle indexing modes, program-evidence embeddings, receipt ingestion validation, limits, or authority safeguards."

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.coordinates import CoordinateIndex, reset_embedding_engine
from dspx.services.program_intent import ProgramIntent
from dspx.services.program_oracle_index import index_program_oracle_evidence_path
from dspx.services.program_service import materialize_program_from_intent

runner = CliRunner()


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


def test_oracle_index_from_program_evidence_cli_indexes_coordinate_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    root = _materialize_example_program(tmp_path, monkeypatch)
    assert (root / "oracle_evidence.json").exists()
    assert not (tmp_path / "generated" / "oracle" / "coordinates.db").exists()

    oracle_evidence = json.loads((root / "oracle_evidence.json").read_text())
    receipt_bundle_id = oracle_evidence["identity"]["receipt_bundle_id"]
    run_id = f"program-oracle-evidence:{receipt_bundle_id}"
    index_path = tmp_path / "oracle" / "coordinates.db"

    result = runner.invoke(
        app,
        [
            "oracle",
            "index",
            "--from-program-evidence",
            "--path",
            str(root),
            "--index-path",
            str(index_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["scanned"] == 1
    assert payload["indexed"] == 1
    assert payload["skipped"] == 0
    assert payload["errors"] == 0
    assert payload["error_details"] == []
    assert payload["index_path"] == str(index_path)
    assert payload["index_stats"]["total"] == 1
    assert payload["index_stats"]["by_run_kind"]["program-oracle-evidence"] == 1
    assert payload["backend"] == "mock"
    assert payload["dimension"] == 384
    assert payload["non_authority_confirmed"] is True

    index = CoordinateIndex(db_path=index_path)
    stats = index.stats()
    assert stats["total"] == 1
    assert stats["by_run_kind"]["program-oracle-evidence"] == 1

    embedding = index.get(run_id)
    assert embedding is not None
    assert embedding.run_kind == "program-oracle-evidence"
    assert embedding.provider == "program-gen"
    assert embedding.template_version == "program-oracle-evidence-v1"
    assert (
        "intent.objective=classify support ticket urgency"
        in embedding.input_text.lower()
    )
    assert (
        "authority=oracle_readability_only_non_authoritative" in embedding.config_text
    )
    assert embedding.metadata["identity"] == oracle_evidence["identity"]
    assert embedding.metadata["oracle_facets"] == oracle_evidence["oracle_facets"]
    assert embedding.metadata["behavior"] == oracle_evidence["behavior"]
    assert embedding.metadata["runtime_traces"] == oracle_evidence["runtime_traces"]
    assert "runtime_traces.status=" in embedding.config_text
    assert embedding.metadata["source_artifacts"] == oracle_evidence["source_artifacts"]
    assert embedding.metadata["non_authority"] == oracle_evidence["non_authority"]
    assert embedding.metadata["evidence_path"] == str(root / "oracle_evidence.json")
    assert embedding.metadata["evidence_hash"]
    assert embedding.metadata["non_authority"] == {
        "oracle_ranking": False,
        "oracle_pruning": False,
        "oracle_promotion": False,
        "governance_authority": False,
        "external_mutation": False,
    }

    results = index.search_by_text(
        "ticket urgency server down",
        run_kind="program-oracle-evidence",
    )
    assert results
    assert results[0].run_id == run_id

    second = runner.invoke(
        app,
        [
            "oracle",
            "index",
            "--from-program-evidence",
            "--path",
            str(root),
            "--index-path",
            str(index_path),
            "--json",
        ],
    )
    assert second.exit_code == 0, second.output
    second_payload = json.loads(second.stdout)
    assert second_payload["indexed"] == 1
    assert CoordinateIndex(db_path=index_path).stats()["total"] == 1
    assert not (tmp_path / "generated" / "oracle" / "coordinates.db").exists()


def test_oracle_index_combined_mode_does_not_confirm_non_authority_when_receipts_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    root = _materialize_example_program(tmp_path, monkeypatch)
    (root / "bad.meta.json").write_text("not json\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "oracle",
            "index",
            "--from-receipts",
            "--from-program-evidence",
            "--path",
            str(root),
            "--index-path",
            str(tmp_path / "combined" / "coordinates.db"),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["indexed"] >= 1
    assert payload["errors"] == 1
    assert payload["non_authority_confirmed"] is False


def test_oracle_index_from_receipts_rejects_unvalidated_receipt_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "mock")
    reset_embedding_engine()
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("SECRET_SENTINEL\n", encoding="utf-8")
    (receipts / "fake.meta.json").write_text(
        json.dumps(
            {
                "created_at": "2026-06-08T00:00:00Z",
                "run_kind": "signature-gen",
                "provider": "fake",
                "template_version": "fake",
                "output_path": str(outside),
                "replay_inputs": {"prompt": "x"},
                "cache_key": "fake",
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "oracle",
            "index",
            "--from-receipts",
            "--path",
            str(receipts),
            "--index-path",
            str(tmp_path / "oracle" / "coordinates.db"),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["scanned"] == 1
    assert payload["indexed"] == 0
    assert payload["errors"] == 1
    assert payload["error_details"][0]["error_type"] == "ValueError"
    assert "receipt_version must be v2" in payload["error_details"][0]["error"]
    assert payload["index_stats"]["total"] == 0


def test_oracle_index_from_mlflow_rejects_unvalidated_receipt_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "mock")
    reset_embedding_engine()
    run_dir = tmp_path / "mlruns" / "0" / "run-1"
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True)
    (run_dir / "meta.yaml").write_text("start_time: 1704067200000\n", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("SECRET_SENTINEL\n", encoding="utf-8")
    (artifacts / "fake.meta.json").write_text(
        json.dumps(
            {
                "created_at": "2026-06-08T00:00:00Z",
                "run_kind": "signature-gen",
                "provider": "fake",
                "template_version": "fake",
                "output_path": str(outside),
                "replay_inputs": {"prompt": "x"},
                "cache_key": "fake",
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "oracle",
            "index",
            "--from-mlflow",
            "--path",
            str(tmp_path / "mlruns"),
            "--index-path",
            str(tmp_path / "mlflow-oracle" / "coordinates.db"),
            "--since",
            "2023-01-01T00:00:00Z",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["scanned"] == 1
    assert payload["indexed"] == 0
    assert payload["errors"] == 1
    assert payload["error_details"][0]["error_type"] == "ValueError"
    assert "receipt_version must be v2" in payload["error_details"][0]["error"]
    assert payload["index_stats"]["total"] == 0


def test_oracle_index_rejects_negative_limit(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "oracle",
            "index",
            "--from-receipts",
            "--path",
            str(tmp_path),
            "--index-path",
            str(tmp_path / "coordinates.db"),
            "--limit",
            "-1",
            "--json",
        ],
    )

    assert result.exit_code == 2


def test_program_oracle_index_empty_scan_does_not_confirm_non_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "mock")
    reset_embedding_engine()
    empty_root = tmp_path / "empty"
    empty_root.mkdir()

    result = index_program_oracle_evidence_path(
        empty_root,
        index_path=tmp_path / "empty-index" / "coordinates.db",
    )

    assert result["scanned"] == 0
    assert result["indexed"] == 0
    assert result["errors"] == 0
    assert result["non_authority_confirmed"] is False


def test_oracle_index_does_not_read_runtime_trace_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _materialize_example_program(tmp_path, monkeypatch)
    traces_path = root / "program_runtime_traces.json"
    assert traces_path.exists()
    traces_path.write_text("not json\n", encoding="utf-8")

    result = index_program_oracle_evidence_path(
        root,
        index_path=tmp_path / "oracle" / "coordinates.db",
    )

    assert result["scanned"] == 1
    assert result["indexed"] == 1
    assert result["errors"] == 0
    index = CoordinateIndex(db_path=tmp_path / "oracle" / "coordinates.db")
    embeddings = index.list_all(run_kind="program-oracle-evidence")
    assert len(embeddings) == 1
    assert embeddings[0].metadata["runtime_traces"]["path"] == (
        "program_runtime_traces.json"
    )


def test_program_oracle_index_rejects_authority_widening(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _materialize_example_program(tmp_path, monkeypatch)
    evidence = json.loads((root / "oracle_evidence.json").read_text())
    evidence["non_authority"]["oracle_ranking"] = True
    bad_root = tmp_path / "bad"
    bad_root.mkdir()
    (bad_root / "oracle_evidence.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    result = index_program_oracle_evidence_path(
        bad_root,
        index_path=tmp_path / "bad-index" / "coordinates.db",
    )

    assert result["scanned"] == 1
    assert result["indexed"] == 0
    assert result["skipped"] == 0
    assert result["errors"] == 1
    assert result["non_authority_confirmed"] is False
    assert "oracle_ranking" in result["error_details"][0]["error"]
    assert result["index_stats"]["total"] == 0


def test_program_oracle_index_rejects_malformed_source_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _materialize_example_program(tmp_path, monkeypatch)
    evidence = json.loads((root / "oracle_evidence.json").read_text())
    evidence["source_artifacts"] = "not-a-list"
    bad_root = tmp_path / "bad-source-artifacts"
    bad_root.mkdir()
    (bad_root / "oracle_evidence.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    result = index_program_oracle_evidence_path(
        bad_root,
        index_path=tmp_path / "bad-source-artifacts-index" / "coordinates.db",
    )

    assert result["scanned"] == 1
    assert result["indexed"] == 0
    assert result["errors"] == 1
    assert "source_artifacts must be a list" in result["error_details"][0]["error"]


def test_oracle_index_requires_explicit_index_mode(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "oracle",
            "index",
            "--path",
            str(tmp_path),
            "--index-path",
            str(tmp_path / "coordinates.db"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "--from-program-evidence" in (result.stdout + result.stderr)
    assert not (tmp_path / "coordinates.db").exists()
