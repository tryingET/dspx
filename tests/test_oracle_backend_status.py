# summary: "Tests Oracle backend posture reporting, redaction, and no-effect status checks."
# read_when:
#   - "Changing Oracle backend diagnostics or publication configuration reporting."

from __future__ import annotations

from collections.abc import Iterator

import json
from pathlib import Path

import pytest

from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.coordinates import reset_embedding_engine
from dspx.coordinates.embeddings import EmbeddingBackendConfigurationError
from dspx.services.oracle_backend_status import build_oracle_backend_status

runner = CliRunner()


@pytest.fixture(autouse=True)
def _reset_embedding_backend_cache() -> Iterator[None]:
    reset_embedding_engine()
    yield
    reset_embedding_engine()


def test_oracle_backend_status_reports_local_sqlite_without_creating_index(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    index_path = tmp_path / "oracle" / "coordinates.db"
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "none")

    status = build_oracle_backend_status(index_path=index_path)

    assert status["schema_version"] == "oracle-backend-status-v2"
    assert status["status"] == "local_sqlite_default_shared_postgres_opt_in"
    assert status["coordinate_index"] == {
        "backend": "sqlite",
        "scope": "local_explicit_index_file",
        "path": str(index_path.resolve()),
        "path_source": "explicit_argument",
        "exists": False,
        "created_by_status_check": False,
    }
    assert status["embedding_backend"] == {
        "schema_version": "dspx-embedding-backend-identity-v2",
        "requested_backend": "none",
        "effective_backend": "none",
        "selection_source": "DSPX_ORACLE_EMBEDDING_BACKEND",
        "explicitly_selected": True,
        "available": False,
        "reason": "embedding backend explicitly disabled",
        "model": None,
        "dimension": None,
        "adapter": None,
        "semantic_class": "disabled",
        "semantic_claim": "no_embedding_backend_available",
        "production_semantic_claim_allowed": False,
    }
    shared = status["shared_postgres_backend"]
    assert shared["supported"] is True
    assert shared["adapter_available"] is True
    assert shared["scope"] == "explicit_curated_shared_publication"
    assert shared["production_ready"] is False
    assert shared["provisioned_by_default"] is False
    assert shared["default_for_program_gen"] is False
    assert shared["default_for_candidate_local_indexing"] is False
    infra_contract = shared["infra_contract"]
    assert infra_contract["owner"] == "softwareco/infra/ds1621-admin"
    assert infra_contract["deployment_status"] == (
        "pilot_deployed_health_ok_live_smoke_passed_not_production_ready"
    )
    assert infra_contract["dogfood_doc"] == (
        "docs/project/2026-05-09-oracle-production-readiness-gates-dogfood.md"
    )
    assert infra_contract["off_nas_coverage_status"] == (
        "remote_hyper_backup_success_after_latest_export_2026_05_09"
    )
    assert "not_proven" not in json.dumps(infra_contract)
    assert status["ds1621_mlflow_postgres"]["oracle_backend"] is False
    assert status["effects"] == {
        "oracle_index_mutated": False,
        "postgres_mutated": False,
        "mlflow_mutated": False,
        "ak_mutated": False,
        "governance_mutated": False,
    }
    assert not index_path.exists()


def test_oracle_backend_status_reports_explicit_mock_as_plumbing_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "mock")

    status = build_oracle_backend_status()

    embedding = status["embedding_backend"]
    assert embedding["effective_backend"] == "mock"
    assert embedding["explicitly_selected"] is True
    assert embedding["semantic_class"] == "deterministic_test_double"
    assert embedding["semantic_claim"] == "plumbing_only_not_production_semantics"
    assert embedding["production_semantic_claim_allowed"] is False
    assert not (tmp_path / "generated" / "oracle" / "coordinates.db").exists()


def test_oracle_backend_status_reports_selected_mdenseon_without_loading_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import dspx.coordinates.embeddings as embeddings

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "transformers-dense")
    monkeypatch.setattr(embeddings, "find_spec", lambda _name: object())

    status = build_oracle_backend_status()

    identity = status["embedding_backend"]
    assert identity["effective_backend"] == "transformers-dense"
    assert identity["model"] == "lightonai/mDenseOn"
    assert identity["dimension"] == 768
    assert identity["adapter"]["revision"] == (
        "a5fdb000f7a21da96c3bddde3a782ef777316df3"
    )
    assert identity["adapter"]["document_prompt"] == "document: "
    assert identity["adapter"]["query_prompt"] == "query: "
    assert identity["production_semantic_claim_allowed"] is False
    assert not (tmp_path / "generated" / "oracle" / "coordinates.db").exists()


def test_oracle_backend_status_rejects_invalid_embedding_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "production")

    with pytest.raises(
        EmbeddingBackendConfigurationError,
        match="Invalid DSPX_ORACLE_EMBEDDING_BACKEND",
    ):
        build_oracle_backend_status()

    result = runner.invoke(app, ["oracle", "backend-status", "--json"])
    assert result.exit_code == 2
    assert "Invalid DSPX_ORACLE_EMBEDDING_BACKEND" in result.output


def test_oracle_backend_status_reports_postgres_env_without_secret_values(
    tmp_path: Path,
    monkeypatch,
) -> None:
    secret_url = "postgresql://user:super-secret@example.invalid/oracle"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DSPX_ORACLE_POSTGRES_URL", secret_url)
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql://other:ambient-secret@example.invalid/db"
    )

    status = build_oracle_backend_status()

    shared = status["shared_postgres_backend"]
    assert shared["supported"] is True
    assert shared["configured_env_present"] is True
    assert shared["configured_env_keys"] == ["DSPX_ORACLE_POSTGRES_URL", "DATABASE_URL"]
    assert shared["configured_store_selected"] is False
    assert shared["configured_url_redacted"] == (
        "postgresql://user:<redacted>@example.invalid/oracle"
    )
    assert shared["publication_config"] == {
        "oracle_specific_env_present": True,
        "oracle_specific_env_keys": ["DSPX_ORACLE_POSTGRES_URL"],
        "oracle_specific_url_redacted": "postgresql://user:<redacted>@example.invalid/oracle",
        "ambient_database_url_present": True,
        "ambient_database_url_redacted": "postgresql://other:<redacted>@example.invalid/db",
        "publication_ready_configured": False,
    }
    assert shared["secret_values_reported"] is False
    assert secret_url not in json.dumps(status)


def test_oracle_backend_status_separates_ambient_database_url_from_publication_config(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DSPX_ORACLE_STORE", "postgres_pgvector")
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql://ambient:ambient-secret@example.invalid/db"
    )

    status = build_oracle_backend_status()

    shared = status["shared_postgres_backend"]
    assert shared["configured_store_selected"] is True
    assert shared["configured_env_keys"] == ["DATABASE_URL"]
    assert shared["publication_config"]["oracle_specific_env_present"] is False
    assert shared["publication_config"]["ambient_database_url_present"] is True
    assert shared["publication_config"]["publication_ready_configured"] is False
    assert "ambient-secret" not in json.dumps(status)


def test_oracle_stats_does_not_require_operational_embedding_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "none")
    index_path = tmp_path / "oracle" / "coordinates.db"

    result = runner.invoke(
        app,
        ["oracle", "stats", "--index-path", str(index_path), "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["engine_backend"] == "none"
    assert payload["engine_dimension"] is None
    assert payload["embedding_backend"]["available"] is False
    assert payload["embedding_backend"]["semantic_claim"] == (
        "no_embedding_backend_available"
    )


def test_oracle_stats_reports_selected_mdenseon_without_model_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import dspx.coordinates.embeddings as embeddings

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "transformers-dense")
    monkeypatch.setattr(embeddings, "find_spec", lambda _name: object())
    index_path = tmp_path / "oracle" / "coordinates.db"

    result = runner.invoke(
        app,
        ["oracle", "stats", "--index-path", str(index_path), "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["engine_backend"] == "transformers-dense"
    assert payload["engine_dimension"] == 768
    assert payload["embedding_backend"]["model"] == "lightonai/mDenseOn"
    assert payload["embedding_backend"]["adapter"]["query_prompt"] == "query: "


def test_oracle_backend_status_cli_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    index_path = tmp_path / "oracle" / "coordinates.db"

    result = runner.invoke(
        app,
        [
            "oracle",
            "backend-status",
            "--index-path",
            str(index_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "local_sqlite_default_shared_postgres_opt_in"
    assert payload["coordinate_index"]["backend"] == "sqlite"
    assert payload["coordinate_index"]["path"] == str(index_path.resolve())
    assert payload["shared_postgres_backend"]["supported"] is True
    assert (
        payload["shared_postgres_backend"]["infra_contract"]["deployment_status"]
        == "pilot_deployed_health_ok_live_smoke_passed_not_production_ready"
    )
    assert not index_path.exists()
