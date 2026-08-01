# summary: "Confines and validates the candidate-local Oracle row for installed live semantic proof."
# read_when:
#   - "Changing installed live Oracle SQLite identity or behavior-hash binding."

from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Mapping, cast

from installed_core_proof_io import (
    InstalledCoreGoldenPathError,
    open_relative_regular,
)


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InstalledCoreGoldenPathError(f"{label} must be an object")
    return cast(Mapping[str, Any], value)


def verify_oracle_sqlite(
    root_descriptor: int, *, receipt_bundle_id: str, behavior_results_sha256: str
) -> None:
    """Read the exact confined SQLite inode and bind its sole row to behavior."""

    database_descriptor = open_relative_regular(
        root_descriptor,
        Path("oracle/coordinates.db"),
        label="candidate-local Oracle index",
    )
    connection = sqlite3.connect(
        f"file:/proc/self/fd/{database_descriptor}?mode=ro&immutable=1",
        uri=True,
    )
    try:
        rows = connection.execute(
            "SELECT run_id, run_kind, metadata_json FROM coordinates ORDER BY run_id"
        ).fetchall()
    except sqlite3.DatabaseError as exc:
        raise InstalledCoreGoldenPathError(
            "candidate-local Oracle index is invalid"
        ) from exc
    finally:
        connection.close()
        os.close(database_descriptor)
    if len(rows) != 1:
        raise InstalledCoreGoldenPathError("candidate-local Oracle row count drift")
    run_id, run_kind, metadata_raw = rows[0]
    expected_identity = (
        f"program-oracle-evidence:{receipt_bundle_id}",
        "program-oracle-evidence",
    )
    if (run_id, run_kind) != expected_identity:
        raise InstalledCoreGoldenPathError("candidate-local Oracle row identity drift")
    try:
        metadata = _mapping(json.loads(metadata_raw), "candidate-local Oracle metadata")
    except (TypeError, json.JSONDecodeError) as exc:
        raise InstalledCoreGoldenPathError(
            "candidate-local Oracle metadata is invalid"
        ) from exc
    behavior = _mapping(metadata.get("behavior"), "candidate-local Oracle behavior")
    if behavior.get("result_hash") != behavior_results_sha256:
        raise InstalledCoreGoldenPathError("candidate-local Oracle behavior hash drift")
