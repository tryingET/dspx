from __future__ import annotations

import sqlite3
from pathlib import Path

from dspx.tools.registry import _db_schema, _detect_sqlite_url


def test_detect_sqlite_url_preserves_relative_sqlite_paths() -> None:
    assert _detect_sqlite_url("sqlite:///generated/sixe.db") == Path(
        "generated/sixe.db"
    )


def test_detect_sqlite_url_preserves_absolute_sqlite_paths() -> None:
    assert _detect_sqlite_url("sqlite:////tmp/sixe.db") == Path("/tmp/sixe.db")


def test_detect_sqlite_url_uses_database_url_env_with_standard_prefix(
    monkeypatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite:///generated/from-env.db")
    monkeypatch.delenv("SIXE_DB_URL", raising=False)

    assert _detect_sqlite_url(None) == Path("generated/from-env.db")


def test_detect_sqlite_url_prefers_sixe_db_url_over_database_url(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/example")
    monkeypatch.setenv("SIXE_DB_URL", "sqlite:///generated/from-sixe.db")

    assert _detect_sqlite_url(None) == Path("generated/from-sixe.db")


def test_db_schema_bounds_negative_sample_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "schema.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE items (id integer)")
        conn.execute("INSERT INTO items VALUES (1)")
        conn.commit()
    finally:
        conn.close()

    schema = _db_schema(f"sqlite:///{db_path}", sample_rows=-1)

    assert "sample_rows: []" in schema
    assert "sample_rows: [(1,)]" not in schema


def test_db_schema_quotes_valid_sqlite_table_identifiers(tmp_path: Path) -> None:
    db_path = tmp_path / "schema.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute('CREATE TABLE "weird-name" (id integer)')
        conn.execute('INSERT INTO "weird-name" VALUES (1)')
        conn.commit()
    finally:
        conn.close()

    schema = _db_schema(f"sqlite:///{db_path}")

    assert "## table: weird-name" in schema
    assert "columns: id:INTEGER" in schema
    assert "sample_rows: [(1,)]" in schema
    assert "sample_rows: <error>" not in schema
