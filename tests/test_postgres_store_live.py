from __future__ import annotations

import importlib.util
import json
import os
import uuid
from datetime import datetime, timezone

import pytest

from dspx.coordinates.embeddings import ExecutionEmbedding
from dspx.coordinates.postgres_store import PostgresPgvectorCoordinateStore


pytestmark = [pytest.mark.live, pytest.mark.network, pytest.mark.postgres]


def _require_live_postgres() -> str:
    if os.getenv("DSPX_ORACLE_LIVE_POSTGRES") != "1":
        pytest.skip("set DSPX_ORACLE_LIVE_POSTGRES=1 for live Postgres/pgvector smoke")
    database_url = os.getenv("DSPX_ORACLE_DATABASE_URL") or os.getenv(
        "DSPX_ORACLE_POSTGRES_URL"
    )
    if not database_url:
        pytest.skip("set DSPX_ORACLE_DATABASE_URL for live Postgres/pgvector smoke")
    if importlib.util.find_spec("psycopg") is None:
        pytest.skip("install optional extra: dspx-core[oracle-postgres]")
    return database_url


def _embedding(run_id: str, vector: list[float]) -> ExecutionEmbedding:
    return ExecutionEmbedding(
        run_id=run_id,
        vector=vector,
        input_text=f"input for {run_id}",
        output_text=f"output for {run_id}",
        config_text="live-gated oracle postgres smoke",
        run_kind="oracle-postgres-live-smoke",
        provider="pytest",
        template_version="live-smoke-v1",
        created_at=datetime.now(timezone.utc).isoformat(),
        dimension=len(vector),
        source_path="tests/test_postgres_store_live.py",
        metadata={"non_authority": True, "test": "live-postgres-smoke"},
    )


def test_postgres_pgvector_store_live_round_trip() -> None:
    """Live-gated smoke for the explicit Postgres/pgvector Oracle store.

    This test is skipped by default so local/CI runs stay service-free. When enabled,
    it proves the adapter can health-check pgvector, create an isolated schema, upsert,
    retrieve, search, list, count, delete, and report redacted diagnostics.
    """

    database_url = _require_live_postgres()
    schema = f"dspx_oracle_live_{uuid.uuid4().hex[:12]}"
    store = PostgresPgvectorCoordinateStore(database_url=database_url, schema=schema)

    try:
        health = store.health().to_dict()
        assert health["backend"] == "postgres_pgvector"
        assert health["available"] is True
        assert "password" not in json.dumps(health).lower()
        assert database_url not in json.dumps(health)

        first = _embedding("live-smoke-a", [1.0, 0.0, 0.0])
        second = _embedding("live-smoke-b", [0.9, 0.1, 0.0])

        assert store.upsert(first) is True
        assert store.upsert(second) is True
        assert store.count(run_kind="oracle-postgres-live-smoke") == 2

        retrieved = store.get("live-smoke-a")
        assert retrieved is not None
        assert retrieved.run_id == "live-smoke-a"
        assert retrieved.dimension == 3

        results = store.search([1.0, 0.0, 0.0], top_k=2)
        assert [result.run_id for result in results] == [
            "live-smoke-a",
            "live-smoke-b",
        ]
        assert results[0].similarity >= results[1].similarity

        listed = store.list_all(run_kind="oracle-postgres-live-smoke", limit=10)
        assert {embedding.run_id for embedding in listed} == {
            "live-smoke-a",
            "live-smoke-b",
        }

        stats = store.stats()
        assert stats["backend"] == "postgres_pgvector"
        assert stats["schema"] == schema
        assert database_url not in json.dumps(stats)

        assert store.delete("live-smoke-a") is True
        assert store.get("live-smoke-a") is None
    finally:
        with store._conn() as conn:  # live cleanup for the isolated smoke schema
            with conn.cursor() as cur:
                cur.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
