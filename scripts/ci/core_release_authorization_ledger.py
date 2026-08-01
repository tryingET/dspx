#!/usr/bin/env python3
# ---
# summary: "Provides the durable fail-closed nonce ledger for Core release authorization."
# ---

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import stat
import threading
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


@dataclass(frozen=True)
class _PathIdentity:
    path: Path
    device: int
    inode: int
    owner: int
    mode: int


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _component_paths(path: Path) -> list[Path]:
    return list(reversed((path, *path.parents)))


def _secure_parent_identities(parent: Path) -> tuple[_PathIdentity, ...]:
    identities: list[_PathIdentity] = []
    current_uid = os.geteuid()
    for component in _component_paths(parent):
        try:
            observed = component.lstat()
        except OSError as exc:
            raise CoreReleaseEvidenceError(
                "authorization nonce ledger parent is unavailable"
            ) from exc
        permissions = stat.S_IMODE(observed.st_mode)
        if (
            stat.S_ISLNK(observed.st_mode)
            or not stat.S_ISDIR(observed.st_mode)
            or observed.st_uid not in {0, current_uid}
            or permissions & 0o022
        ):
            raise CoreReleaseEvidenceError(
                "authorization nonce ledger parent component is unsafe"
            )
        identities.append(
            _PathIdentity(
                path=component,
                device=observed.st_dev,
                inode=observed.st_ino,
                owner=observed.st_uid,
                mode=permissions,
            )
        )
    leaf = identities[-1]
    if leaf.owner != current_uid or leaf.mode & 0o077:
        raise CoreReleaseEvidenceError(
            "authorization nonce ledger parent is not owner-only"
        )
    return tuple(identities)


def _regular_identity(path: Path) -> _PathIdentity:
    try:
        observed = path.lstat()
    except OSError as exc:
        raise CoreReleaseEvidenceError(
            "authorization nonce ledger path is unavailable"
        ) from exc
    permissions = stat.S_IMODE(observed.st_mode)
    if (
        stat.S_ISLNK(observed.st_mode)
        or not stat.S_ISREG(observed.st_mode)
        or observed.st_uid != os.geteuid()
        or permissions != 0o600
    ):
        raise CoreReleaseEvidenceError("authorization nonce ledger path is unsafe")
    return _PathIdentity(
        path=path,
        device=observed.st_dev,
        inode=observed.st_ino,
        owner=observed.st_uid,
        mode=permissions,
    )


def _same_identity(expected: _PathIdentity) -> bool:
    try:
        observed = expected.path.lstat()
    except OSError:
        return False
    return (
        stat.S_ISDIR(observed.st_mode)
        and observed.st_dev == expected.device
        and observed.st_ino == expected.inode
        and observed.st_uid == expected.owner
        and stat.S_IMODE(observed.st_mode) == expected.mode
    )


class NonceLedger:
    """Linearizes one nonce through one verified SQLite file lifecycle."""

    def __init__(self, path: Path) -> None:
        self.path = _absolute(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._parent_identities = _secure_parent_identities(self.path.parent)
        if self.path.is_symlink() or (
            self.path.exists()
            and not stat.S_ISREG(self.path.stat(follow_symlinks=False).st_mode)
        ):
            raise CoreReleaseEvidenceError("authorization nonce ledger path is unsafe")
        if self.path.exists():
            if self.path.stat(follow_symlinks=False).st_uid != os.geteuid():
                raise CoreReleaseEvidenceError(
                    "authorization nonce ledger path is unsafe"
                )
            os.chmod(self.path, 0o600, follow_symlinks=False)
        self._connection = sqlite3.connect(
            self.path, timeout=5.0, isolation_level=None, check_same_thread=False
        )
        self._lock = threading.Lock()
        try:
            os.chmod(self.path, 0o600, follow_symlinks=False)
            self._database_identity = _regular_identity(self.path)
            self._configure()
            self._initialize()
            self._verify_identity()
        except Exception:
            self._connection.close()
            raise

    def _configure(self) -> None:
        journal = cast(
            str, self._connection.execute("PRAGMA journal_mode=WAL").fetchone()[0]
        )
        self._connection.execute("PRAGMA synchronous=FULL")
        synchronous = cast(
            int, self._connection.execute("PRAGMA synchronous").fetchone()[0]
        )
        self._connection.execute("PRAGMA busy_timeout=5000")
        self._connection.execute("PRAGMA trusted_schema=OFF")
        if journal.lower() != "wal" or synchronous != 2:
            raise CoreReleaseEvidenceError("authorization ledger durability drift")

    def _initialize(self) -> None:
        connection = self._connection
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
            self._validate_schema()
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise

    def _validate_schema(self) -> None:
        connection = self._connection
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

    def _verify_identity(self) -> None:
        if not all(_same_identity(item) for item in self._parent_identities):
            raise CoreReleaseEvidenceError(
                "authorization nonce ledger parent identity changed"
            )
        current = _regular_identity(self.path)
        if (
            current.device,
            current.inode,
            current.owner,
            current.mode,
        ) != (
            self._database_identity.device,
            self._database_identity.inode,
            self._database_identity.owner,
            self._database_identity.mode,
        ):
            raise CoreReleaseEvidenceError(
                "authorization nonce ledger database identity changed"
            )

    def reserve(
        self,
        *,
        owner_selector_ref: str,
        fingerprint: str,
        nonce: str,
        payload_sha256: str,
        now: datetime,
    ) -> None:
        with self._lock:
            self._verify_identity()
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                self._validate_schema()
                self._connection.execute(
                    "INSERT INTO authorizations VALUES (?, ?, ?, ?, 'pending', ?, NULL)",
                    (
                        owner_selector_ref,
                        fingerprint,
                        nonce,
                        payload_sha256,
                        now.astimezone(timezone.utc).isoformat(),
                    ),
                )
                self._connection.execute("COMMIT")
            except sqlite3.IntegrityError as exc:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise CoreReleaseEvidenceError(
                    "authorization nonce is already reserved or consumed"
                ) from exc
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise
            self._verify_identity()

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
        with self._lock:
            self._verify_identity()
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                self._validate_schema()
                cursor = self._connection.execute(
                    "UPDATE authorizations SET status='committed', receipt_json=? "
                    "WHERE owner_selector_ref=? AND fingerprint=? AND nonce=? "
                    "AND payload_sha256=? AND status='pending'",
                    (raw, owner_selector_ref, fingerprint, nonce, payload_sha256),
                )
                if cursor.rowcount != 1:
                    raise CoreReleaseEvidenceError(
                        "authorization nonce finalization drift"
                    )
                self._connection.execute("COMMIT")
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise
            self._verify_identity()

    def status(
        self, *, owner_selector_ref: str, fingerprint: str, nonce: str
    ) -> str | None:
        with self._lock:
            self._verify_identity()
            try:
                self._connection.execute("BEGIN")
                self._validate_schema()
                row = self._connection.execute(
                    "SELECT status FROM authorizations WHERE owner_selector_ref=? "
                    "AND fingerprint=? AND nonce=?",
                    (owner_selector_ref, fingerprint, nonce),
                ).fetchone()
                self._connection.execute("COMMIT")
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise
            self._verify_identity()
        return None if row is None else cast(str, row[0])

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def __del__(self) -> None:
        connection = getattr(self, "_connection", None)
        if connection is not None:
            connection.close()
