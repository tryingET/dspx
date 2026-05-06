from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dspx.coordinates.postgres_store import (
    configured_postgres_env_keys,
    redact_database_url,
)
from dspx.coordinates.storage import get_default_index_path

ORACLE_BACKEND_STATUS_SCHEMA = "oracle-backend-status-v1"
DS1621_ORACLE_INFRA_CONTRACT = {
    "owner": "softwareco/infra/ds1621-admin",
    "status": "pilot_deployed_not_production_ready",
    "deployment_status": "pilot_deployed_health_ok_live_smoke_passed_not_production_ready",
    "machine_readable_contract": (
        "softwareco/infra/ds1621-admin/contracts/ds1621-oracle-coordinate-backend.env"
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
    "monitoring_status": "systemd_user_timer_enabled_ntfy_alert_path_verified_2026_05_06",
    "monitoring_command": "./scripts/oracle/monitor-ds1621-oracle.sh",
    "monitoring_schedule": "systemd_user_timer_daily_05_30_persistent_randomized_15m",
    "monitoring_alert_target": "http://ds1621:2586/dspx-oracle-alerts",
    "monitoring_last_verified_at": "2026-05-06",
    "rotation_status": "manual_rotation_exercised_and_verified_2026_05_06",
    "rotation_last_verified_at": "2026-05-06",
    "rotation_next_review": "2026-08-04",
}


def _index_path_source(index_path: Path | None) -> str:
    if index_path is not None:
        return "explicit_argument"
    if os.getenv("DSPX_ORACLE_INDEX_PATH"):
        return "DSPX_ORACLE_INDEX_PATH"
    return "cwd_default"


def build_oracle_backend_status(*, index_path: Path | None = None) -> dict[str, Any]:
    """Return the truthful current Oracle storage/backend posture.

    This is intentionally read-only: it must not instantiate CoordinateIndex because doing
    so creates a sqlite database on disk. The report makes the current boundary explicit:
    DSPx Oracle coordinates are local sqlite only; DS1621 Postgres currently belongs to
    MLflow, not Oracle.
    """

    resolved_index_path = (
        (index_path or get_default_index_path()).expanduser().resolve()
    )
    configured_postgres_keys = configured_postgres_env_keys()
    postgres_config_present = bool(configured_postgres_keys)

    return {
        "schema_version": ORACLE_BACKEND_STATUS_SCHEMA,
        "status": "local_sqlite_default",
        "summary": (
            "DSPx Oracle defaults to an explicit local SQLite CoordinateStore. "
            "A Postgres/pgvector store scaffold exists behind explicit opt-in, but "
            "no shared Oracle service is provisioned by default."
        ),
        "coordinate_index": {
            "backend": "sqlite",
            "scope": "local_explicit_index_file",
            "path": str(resolved_index_path),
            "path_source": _index_path_source(index_path),
            "exists": resolved_index_path.exists(),
            "created_by_status_check": False,
        },
        "shared_postgres_backend": {
            "supported": True,
            "adapter_available": True,
            "provisioned_by_default": False,
            "pilot_service_live": True,
            "infra_contract": DS1621_ORACLE_INFRA_CONTRACT,
            "configured_env_present": postgres_config_present,
            "configured_env_keys": configured_postgres_keys,
            "configured_store_selected": os.getenv("DSPX_ORACLE_STORE", "").lower()
            in {"postgres", "postgres_pgvector", "pgvector"},
            "configured_url_redacted": redact_database_url(
                os.getenv("DSPX_ORACLE_DATABASE_URL")
                or os.getenv("DSPX_ORACLE_POSTGRES_URL")
                or os.getenv("DATABASE_URL")
            ),
            "secret_values_reported": False,
            "reason": (
                "Postgres/pgvector is an explicit opt-in Oracle CoordinateStore "
                "adapter. It is separate from DS1621 MLflow Postgres and requires "
                "a provisioned Oracle database plus driver/runtime validation."
            ),
        },
        "ds1621_mlflow_postgres": {
            "uri": "http://ds1621:50000",
            "role": "MLflow tracking backend store only",
            "oracle_backend": False,
            "note": (
                "The DS1621 Postgres service discussed so far backs MLflow metadata; "
                "it is not a shared Oracle coordinate store."
            ),
        },
        "effects": {
            "oracle_index_mutated": False,
            "postgres_mutated": False,
            "mlflow_mutated": False,
            "ak_mutated": False,
            "governance_mutated": False,
        },
        "authority": {
            "oracle_authority": False,
            "promotion_authority": False,
            "production_activation_authority": False,
        },
        "next_required_action": (
            "Provision and validate a separate shared Oracle backend before treating "
            "Oracle as a production shared evidence substrate."
        ),
    }
