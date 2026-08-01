# summary: "Confines and validates all candidate-local Oracle rows for installed live semantic proof."
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
    root_descriptor: int, *, expected_records: Mapping[str, str]
) -> None:
    """Bind each confined SQLite row to one expected receipt and behavior hash."""

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
    if len(rows) != len(expected_records):
        raise InstalledCoreGoldenPathError("candidate-local Oracle row count drift")
    observed_receipts: set[str] = set()
    for run_id, run_kind, metadata_raw in rows:
        prefix = "program-oracle-evidence:"
        if run_kind != "program-oracle-evidence" or not str(run_id).startswith(prefix):
            raise InstalledCoreGoldenPathError(
                "candidate-local Oracle row identity drift"
            )
        receipt_bundle_id = str(run_id)[len(prefix) :]
        expected_hash = expected_records.get(receipt_bundle_id)
        if expected_hash is None or receipt_bundle_id in observed_receipts:
            raise InstalledCoreGoldenPathError(
                "candidate-local Oracle receipt identity drift"
            )
        observed_receipts.add(receipt_bundle_id)
        try:
            metadata = _mapping(
                json.loads(metadata_raw), "candidate-local Oracle metadata"
            )
        except (TypeError, json.JSONDecodeError) as exc:
            raise InstalledCoreGoldenPathError(
                "candidate-local Oracle metadata is invalid"
            ) from exc
        behavior = _mapping(metadata.get("behavior"), "candidate-local Oracle behavior")
        if behavior.get("result_hash") != expected_hash:
            raise InstalledCoreGoldenPathError(
                "candidate-local Oracle behavior hash drift"
            )
    if observed_receipts != set(expected_records):
        raise InstalledCoreGoldenPathError(
            "candidate-local Oracle receipt coverage drift"
        )
