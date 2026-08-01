#!/usr/bin/env python3
# ---
# summary: "Provides the durable fail-closed nonce ledger for Core release authorization."
# ---

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import stat
from typing import Any, cast

from core_release_evidence_io import CoreReleaseEvidenceError

APPLICATION_ID = 0x44535058
SCHEMA_VERSION = 1
_TABLE_SQL = """
    CREATE TABLE authorizations (
        owner_selector_ref TEXT NOT NULL,
        fingerprint TEXT NOT NULL,
        nonce TEXT NOT NULL,
        payload_sha256 TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('pending','committed')),
        reserved_at TEXT NOT NULL,
        receipt_json TEXT,
        PRIMARY KEY(owner_selector_ref, fingerprint, nonce)
    ) WITHOUT ROWID
"""
_EXPECTED_COLUMNS = [
    ("owner_selector_ref", "TEXT", 1, 1),
    ("fingerprint", "TEXT", 1, 2),
    ("nonce", "TEXT", 1, 3),
    ("payload_sha256", "TEXT", 1, 0),
    ("status", "TEXT", 1, 0),
    ("reserved_at", "TEXT", 1, 0),
    ("receipt_json", "TEXT", 0, 0),
]


class NonceLedger:
    """Linearizes nonce reservation before checks and durable receipt commit after."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if path.is_symlink() or (
            path.exists() and not stat.S_ISREG(path.stat(follow_symlinks=False).st_mode)
        ):
            raise CoreReleaseEvidenceError("authorization nonce ledger path is unsafe")
        connection = self._open(validate=False)
        try:
            connection.execute("BEGIN EXCLUSIVE")
            table = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='authorizations'"
            ).fetchone()
            application_id = cast(
                int, connection.execute("PRAGMA application_id").fetchone()[0]
            )
            schema_version = cast(
                int, connection.execute("PRAGMA user_version").fetchone()[0]
            )
            if table is None:
                if application_id != 0 or schema_version != 0:
                    raise CoreReleaseEvidenceError(
                        "authorization ledger identity drift"
                    )
                connection.execute(_TABLE_SQL)
                connection.execute(f"PRAGMA application_id={APPLICATION_ID}")
                connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
            self._validate_schema(connection)
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()
        os.chmod(path, 0o600, follow_symlinks=False)

    def _open(self, *, validate: bool = True) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0, isolation_level=None)
        try:
            journal = cast(
                str, connection.execute("PRAGMA journal_mode=WAL").fetchone()[0]
            )
            connection.execute("PRAGMA synchronous=FULL")
            synchronous = cast(
                int, connection.execute("PRAGMA synchronous").fetchone()[0]
            )
            connection.execute("PRAGMA busy_timeout=5000")
            connection.execute("PRAGMA trusted_schema=OFF")
            if journal.lower() != "wal" or synchronous != 2:
                raise CoreReleaseEvidenceError("authorization ledger durability drift")
            if validate:
                self._validate_schema(connection)
            return connection
        except Exception:
            connection.close()
            raise

    def _validate_schema(self, connection: sqlite3.Connection) -> None:
        application_id = cast(
            int, connection.execute("PRAGMA application_id").fetchone()[0]
        )
        schema_version = cast(
            int, connection.execute("PRAGMA user_version").fetchone()[0]
        )
        objects = connection.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name"
        ).fetchall()
        table = objects[0] if len(objects) == 1 else None
        columns = [
            (row[1], str(row[2]).upper(), row[3], row[5])
            for row in connection.execute(
                "PRAGMA table_info(authorizations)"
            ).fetchall()
        ]
        normalized_sql = (
            "" if table is None else "".join(cast(str, table[3]).upper().split())
        )
        expected_sql = "".join(_TABLE_SQL.upper().split())
        if (
            application_id != APPLICATION_ID
            or schema_version != SCHEMA_VERSION
            or table is None
            or table[:3] != ("table", "authorizations", "authorizations")
            or columns != _EXPECTED_COLUMNS
            or normalized_sql != expected_sql
        ):
            raise CoreReleaseEvidenceError("authorization ledger schema drift")

    def reserve(
        self,
        *,
        owner_selector_ref: str,
        fingerprint: str,
        nonce: str,
        payload_sha256: str,
        now: datetime,
    ) -> None:
        connection = self._open()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT INTO authorizations VALUES (?, ?, ?, ?, 'pending', ?, NULL)",
                (
                    owner_selector_ref,
                    fingerprint,
                    nonce,
                    payload_sha256,
                    now.astimezone(timezone.utc).isoformat(),
                ),
            )
            connection.execute("COMMIT")
        except sqlite3.IntegrityError as exc:
            connection.execute("ROLLBACK")
            raise CoreReleaseEvidenceError(
                "authorization nonce is already reserved or consumed"
            ) from exc
        finally:
            connection.close()

    def finalize(
        self,
        *,
        owner_selector_ref: str,
        fingerprint: str,
        nonce: str,
        payload_sha256: str,
        receipt: Mapping[str, Any],
    ) -> None:
        raw = json.dumps(dict(receipt), sort_keys=True, separators=(",", ":"))
        connection = self._open()
        try:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                "UPDATE authorizations SET status='committed', receipt_json=? "
                "WHERE owner_selector_ref=? AND fingerprint=? AND nonce=? "
                "AND payload_sha256=? AND status='pending'",
                (raw, owner_selector_ref, fingerprint, nonce, payload_sha256),
            )
            if cursor.rowcount != 1:
                raise CoreReleaseEvidenceError("authorization nonce finalization drift")
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def status(
        self, *, owner_selector_ref: str, fingerprint: str, nonce: str
    ) -> str | None:
        with self._open() as connection:
            row = connection.execute(
                "SELECT status FROM authorizations WHERE owner_selector_ref=? "
                "AND fingerprint=? AND nonce=?",
                (owner_selector_ref, fingerprint, nonce),
            ).fetchone()
        return None if row is None else cast(str, row[0])
