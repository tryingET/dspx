from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Dict, Optional


def get_db_url() -> str:
    return (
        os.getenv("SIXE_DB_URL")
        or os.getenv("DATABASE_URL")
        or "sqlite:///generated/sixe.db"
    )


def _parse_sqlite_url(url: str) -> Optional[Path]:
    if not url.startswith("sqlite:///"):
        return None
    path = url[len("sqlite:///") :]
    return Path(path)


def ensure_schema(url: str | None = None) -> None:
    url = url or get_db_url()
    p = _parse_sqlite_url(url)
    if p is None:
        # Only sqlite is supported out of the box
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sixe (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow TEXT,
                node_id TEXT,
                node_label TEXT,
                constraints TEXT,
                boundaries TEXT,
                edges TEXT,
                assumptions TEXT,
                dependencies TEXT,
                exceptions TEXT,
                source_input TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def insert_six_e(
    *,
    workflow: str,
    node_id: str,
    node_label: str,
    record: Dict[str, str],
    source_input: str = "",
    url: str | None = None,
) -> None:
    url = url or get_db_url()
    p = _parse_sqlite_url(url)
    if p is None:
        # Only sqlite is supported without extra deps
        return
    conn = sqlite3.connect(str(p))
    try:
        conn.execute(
            """
            INSERT INTO sixe (
                workflow, node_id, node_label,
                constraints, boundaries, edges, assumptions, dependencies, exceptions,
                source_input
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                workflow,
                node_id,
                node_label,
                record.get("constraints", ""),
                record.get("boundaries", ""),
                record.get("edges", ""),
                record.get("assumptions", ""),
                record.get("dependencies", ""),
                record.get("exceptions", ""),
                source_input,
            ),
        )
        conn.commit()
    finally:
        conn.close()
