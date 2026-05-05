from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dspx.coordinates.storage import get_default_index_path

ORACLE_BACKEND_STATUS_SCHEMA = "oracle-backend-status-v1"

_POSTGRES_ENV_KEYS = (
    "DSPX_ORACLE_POSTGRES_URL",
    "DSPX_ORACLE_DATABASE_URL",
    "DATABASE_URL",
)


def _index_path_source(index_path: Path | None) -> str:
    if index_path is not None:
        return "explicit_argument"
    if os.getenv("DSPX_ORACLE_INDEX_PATH"):
        return "DSPX_ORACLE_INDEX_PATH"
    return "cwd_default"


def _configured_postgres_env_keys() -> list[str]:
    return [key for key in _POSTGRES_ENV_KEYS if os.getenv(key)]


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
    configured_postgres_keys = _configured_postgres_env_keys()
    postgres_config_present = bool(configured_postgres_keys)

    return {
        "schema_version": ORACLE_BACKEND_STATUS_SCHEMA,
        "status": "local_sqlite_only",
        "summary": (
            "DSPx Oracle currently uses an explicit local SQLite CoordinateIndex. "
            "No shared Oracle Postgres/pgvector backend is implemented or provisioned."
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
            "supported": False,
            "configured_env_present": postgres_config_present,
            "configured_env_keys": configured_postgres_keys,
            "configuration_used_by_oracle": False,
            "secret_values_reported": False,
            "reason": (
                "CoordinateIndex is SQLite-backed in this repo. Postgres environment "
                "variables, if present, are not consumed by Oracle indexing/search."
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
            "Define, provision, and validate a separate shared Oracle backend contract "
            "before treating Oracle as a production shared evidence substrate."
        ),
    }
