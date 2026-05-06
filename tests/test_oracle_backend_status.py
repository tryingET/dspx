from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.services.oracle_backend_status import build_oracle_backend_status

runner = CliRunner()


def test_oracle_backend_status_reports_local_sqlite_without_creating_index(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    index_path = tmp_path / "oracle" / "coordinates.db"

    status = build_oracle_backend_status(index_path=index_path)

    assert status["schema_version"] == "oracle-backend-status-v1"
    assert status["status"] == "local_sqlite_default"
    assert status["coordinate_index"] == {
        "backend": "sqlite",
        "scope": "local_explicit_index_file",
        "path": str(index_path.resolve()),
        "path_source": "explicit_argument",
        "exists": False,
        "created_by_status_check": False,
    }
    assert status["shared_postgres_backend"]["supported"] is True
    assert status["shared_postgres_backend"]["adapter_available"] is True
    assert status["shared_postgres_backend"]["provisioned_by_default"] is False
    assert status["ds1621_mlflow_postgres"]["oracle_backend"] is False
    assert status["effects"] == {
        "oracle_index_mutated": False,
        "postgres_mutated": False,
        "mlflow_mutated": False,
        "ak_mutated": False,
        "governance_mutated": False,
    }
    assert not index_path.exists()


def test_oracle_backend_status_reports_postgres_env_without_secret_values(
    tmp_path: Path,
    monkeypatch,
) -> None:
    secret_url = "postgresql://user:super-secret@example.invalid/oracle"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DSPX_ORACLE_POSTGRES_URL", secret_url)
    monkeypatch.setenv("DATABASE_URL", "postgresql://other-secret@example.invalid/db")

    status = build_oracle_backend_status()

    shared = status["shared_postgres_backend"]
    assert shared["supported"] is True
    assert shared["configured_env_present"] is True
    assert shared["configured_env_keys"] == ["DSPX_ORACLE_POSTGRES_URL", "DATABASE_URL"]
    assert shared["configured_store_selected"] is False
    assert shared["configured_url_redacted"] == (
        "postgresql://user:<redacted>@example.invalid/oracle"
    )
    assert shared["secret_values_reported"] is False
    assert secret_url not in json.dumps(status)


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
    assert payload["status"] == "local_sqlite_default"
    assert payload["coordinate_index"]["backend"] == "sqlite"
    assert payload["coordinate_index"]["path"] == str(index_path.resolve())
    assert payload["shared_postgres_backend"]["supported"] is True
    assert not index_path.exists()
