from __future__ import annotations

from pathlib import Path

from dspx.tools.registry import _detect_sqlite_url


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
