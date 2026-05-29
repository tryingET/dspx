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
    "deployment_status": (
        "pilot_deployed_health_ok_live_smoke_passed_not_production_ready"
    ),
    "production_ready": False,
    "dogfood_doc": (
        "docs/project/2026-05-09-oracle-production-readiness-gates-dogfood.md"
    ),
    "publication_dogfood_status": "explicit_shared_publication_passed_2026_05_09",
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
        "remote_hyper_backup_success_after_latest_export_2026_05_09"
    ),
    "hyper_backup_share": "DspxOracleBackups",
    "hyper_backup_selection_status": (
        "dedicated_share_selected_in_remote_hyper_backup_task_2026_05_06"
    ),
    "hyper_backup_remote_task_status": (
        "task_3_hypterbackup2michy_success_after_latest_export_2026_05_09"
    ),
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
    DSPx Oracle has a local SQLite default plus an explicit opt-in Postgres/pgvector
    shared-publication backend; DS1621 MLflow Postgres remains a separate MLflow store.
    """

    resolved_index_path = (
        (index_path or get_default_index_path()).expanduser().resolve()
    )
    configured_postgres_keys = configured_postgres_env_keys()
    oracle_specific_keys = [
        key
        for key in ("DSPX_ORACLE_DATABASE_URL", "DSPX_ORACLE_POSTGRES_URL")
        if os.getenv(key)
    ]
    ambient_database_url = os.getenv("DATABASE_URL")
    postgres_config_present = bool(configured_postgres_keys)
    postgres_store_selected = os.getenv("DSPX_ORACLE_STORE", "").lower() in {
        "postgres",
        "postgres_pgvector",
        "pgvector",
    }
    oracle_specific_url = os.getenv("DSPX_ORACLE_DATABASE_URL") or os.getenv(
        "DSPX_ORACLE_POSTGRES_URL"
    )

    return {
        "schema_version": ORACLE_BACKEND_STATUS_SCHEMA,
        "status": "local_sqlite_default_shared_postgres_opt_in",
        "summary": (
            "DSPx Oracle has two coordinate-store surfaces: local SQLite remains "
            "the default/offline candidate index, while DS1621 Postgres/pgvector is "
            "an explicit opt-in shared empirical-memory backend for curated publication. "
            "MLflow Postgres is separate, and none of these stores is activation authority."
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
            "scope": "explicit_curated_shared_publication",
            "production_ready": False,
            "provisioned_by_default": False,
            "default_for_program_gen": False,
            "default_for_candidate_local_indexing": False,
            "pilot_service_live": True,
            "infra_contract": DS1621_ORACLE_INFRA_CONTRACT,
            "configured_env_present": postgres_config_present,
            "configured_env_keys": configured_postgres_keys,
            "configured_store_selected": postgres_store_selected,
            "configured_url_redacted": redact_database_url(
                oracle_specific_url or ambient_database_url
            ),
            "publication_config": {
                "oracle_specific_env_present": bool(oracle_specific_keys),
                "oracle_specific_env_keys": oracle_specific_keys,
                "oracle_specific_url_redacted": redact_database_url(
                    oracle_specific_url
                ),
                "ambient_database_url_present": bool(ambient_database_url),
                "ambient_database_url_redacted": redact_database_url(
                    ambient_database_url
                ),
                "publication_ready_configured": postgres_store_selected
                and bool(oracle_specific_keys),
            },
            "secret_values_reported": False,
            "reason": (
                "Postgres/pgvector is an explicit opt-in Oracle CoordinateStore "
                "adapter for curated shared empirical memory. It is separate from "
                "DS1621 MLflow Postgres; shared publication requires DSPX_ORACLE_STORE "
                "plus an Oracle-specific database URL, and remains non-authoritative."
            ),
        },
        "ds1621_mlflow_postgres": {
            "uri": "http://ds1621:50000",
            "role": "MLflow tracking backend store only",
            "oracle_backend": False,
            "note": (
                "The DS1621 MLflow Postgres service backs MLflow metadata; it is "
                "not the DS1621 Oracle Postgres/pgvector coordinate backend."
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
            "Use local SQLite indexing/reporting for candidate-local analysis. Use the "
            "explicit shared-publication preflight/publish path with DSPX_ORACLE_STORE="
            "postgres_pgvector and an Oracle-specific DB URL for curated shared empirical "
            "memory. Production activation still requires owning-domain/AK/governance authority."
        ),
    }
