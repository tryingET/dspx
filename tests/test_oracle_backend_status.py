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
    shared = status["shared_postgres_backend"]
    assert shared["supported"] is True
    assert shared["adapter_available"] is True
    assert shared["provisioned_by_default"] is False
    assert shared["infra_contract"] == {
        "owner": "softwareco/infra/ds1621-admin",
        "status": "pilot_deployed_not_production_ready",
        "deployment_status": (
            "pilot_deployed_health_ok_live_smoke_passed_not_production_ready"
        ),
        "machine_readable_contract": (
            "softwareco/infra/ds1621-admin/contracts/"
            "ds1621-oracle-coordinate-backend.env"
        ),
        "contract_doc": (
            "softwareco/infra/ds1621-admin/docs/project/"
            "ds1621-oracle-coordinate-backend-contract.md"
        ),
        "provisioned_service": True,
        "backup_restore_status": "verified_disposable_restore_2026_05_06",
        "retention_status": "pilot_14_day_policy_with_dry_run_prune_helper",
        "off_nas_coverage_status": (
            "latest_dump_exported_to_operator_confirmed_hyper_backup_selected_share_2026_05_06"
        ),
        "hyper_backup_share": "DspxOracleBackups",
    }
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
    assert (
        payload["shared_postgres_backend"]["infra_contract"]["deployment_status"]
        == "pilot_deployed_health_ok_live_smoke_passed_not_production_ready"
    )
    assert not index_path.exists()
