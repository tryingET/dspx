# summary: "Explicit opt-in Postgres and pgvector backend for Oracle coordinate storage and search."
# read_when:
#   - "Changing shared coordinate persistence, pgvector queries, database configuration, or redaction."

"""Postgres + pgvector coordinate store scaffold for Oracle.

The dependency is intentionally optional in this slice.  SQLite remains the default
store; selecting this backend without an installed driver fails closed with
redacted diagnostics rather than silently falling back or leaking secrets.
"""

from __future__ import annotations

import importlib
import json
import os
import re
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator
from urllib.parse import urlsplit, urlunsplit

from .embeddings import EMBEDDING_VERSION, ExecutionEmbedding
from .metrics import semantic_distance
from .storage import CoordinateRecord, SearchResult, StoreHealth

_POSTGRES_ENV_KEYS = (
    "DSPX_ORACLE_DATABASE_URL",
    "DSPX_ORACLE_POSTGRES_URL",
    "DATABASE_URL",
)
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class StoreUnavailableError(RuntimeError):
    """Raised when an explicitly selected shared coordinate store is unavailable."""


class StoreConfigurationError(ValueError):
    """Raised when shared store configuration is missing or unsafe."""


def configured_postgres_env_keys() -> list[str]:
    """Return configured database env var names without exposing values."""

    return [key for key in _POSTGRES_ENV_KEYS if os.getenv(key)]


def get_postgres_database_url() -> str | None:
    """Return the first configured Oracle database URL value, if any."""

    for key in _POSTGRES_ENV_KEYS:
        value = os.getenv(key)
        if value:
            return value
    return None


def redact_database_url(value: str | None) -> str | None:
    """Redact a database URL for logs/JSON diagnostics."""

    if not value:
        return None
    try:
        parts = urlsplit(value)
    except ValueError:
        return "<redacted-invalid-url>"
    if not parts.scheme:
        return "<redacted>"
    host = parts.hostname or ""
    port = f":{parts.port}" if parts.port is not None else ""
    username = parts.username
    netloc = host + port
    if username:
        netloc = f"{username}:<redacted>@{netloc}"
    return urlunsplit((parts.scheme, netloc, parts.path, "", ""))


def _validate_identifier(value: str, *, field: str) -> str:
    if not _IDENTIFIER_RE.fullmatch(value):
        raise StoreConfigurationError(f"Invalid Postgres identifier for {field}")
    return value


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(format(float(item), ".17g") for item in vector) + "]"


class PostgresPgvectorCoordinateStore:
    """Explicit opt-in Postgres + pgvector Oracle coordinate store.

    This class is importable without a Postgres driver so config/status tests remain
    service-free. Runtime operations require `psycopg` to be installed and an
    explicit Oracle database URL to be configured.
    """

    backend_name = "postgres_pgvector"

    def __init__(
        self,
        database_url: str | None = None,
        *,
        schema: str | None = None,
        connect_timeout: int = 5,
    ):
        self.database_url = database_url or get_postgres_database_url()
        if not self.database_url:
            raise StoreConfigurationError(
                "DSPX_ORACLE_DATABASE_URL or DSPX_ORACLE_POSTGRES_URL is required "
                "when DSPX_ORACLE_STORE=postgres_pgvector"
            )
        self.schema = _validate_identifier(
            schema or os.getenv("DSPX_ORACLE_SCHEMA") or "dspx_oracle",
            field="schema",
        )
        self.connect_timeout = connect_timeout

    @property
    def redacted_database_url(self) -> str | None:
        return redact_database_url(self.database_url)

    def _load_psycopg(self) -> Any:
        try:
            return importlib.import_module("psycopg")
        except ModuleNotFoundError as exc:
            raise StoreUnavailableError(
                "Postgres Oracle store requires optional dependency 'psycopg'. "
                "Install a Postgres driver before enabling postgres_pgvector."
            ) from exc

    @contextmanager
    def _conn(self) -> Iterator[Any]:
        psycopg = self._load_psycopg()
        conn = psycopg.connect(
            self.database_url,
            connect_timeout=self.connect_timeout,
        )
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _qualified(self, table: str) -> str:
        _validate_identifier(table, field="table")
        return f'"{self.schema}"."{table}"'

    def _ensure_schema(self, dimension: int | None = None) -> None:
        vector_type = "vector" if dimension is None else f"vector({int(dimension)})"
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                cur.execute(f'CREATE SCHEMA IF NOT EXISTS "{self.schema}"')
                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {self._qualified("oracle_records")} (
                        run_id TEXT PRIMARY KEY,
                        vector {vector_type} NOT NULL,
                        input_text TEXT,
                        output_text TEXT,
                        config_text TEXT,
                        run_kind TEXT,
                        provider TEXT,
                        template_version TEXT,
                        created_at TIMESTAMPTZ,
                        dimension INTEGER NOT NULL,
                        source_path TEXT,
                        metadata JSONB NOT NULL,
                        indexed_at TIMESTAMPTZ NOT NULL,
                        embedding_version INTEGER NOT NULL DEFAULT 1
                    )
                    """
                )
                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {self._qualified("oracle_store_meta")} (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    )
                    """
                )
                cur.execute(
                    f"""
                    INSERT INTO {self._qualified("oracle_store_meta")} (key, value)
                    VALUES ('schema_version', '1')
                    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                    """
                )

    def upsert(self, embedding: ExecutionEmbedding) -> bool:
        record = CoordinateRecord.from_embedding(embedding)
        self._ensure_schema(dimension=embedding.dimension)
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    INSERT INTO {self._qualified("oracle_records")} (
                        run_id, vector, input_text, output_text, config_text,
                        run_kind, provider, template_version, created_at, dimension,
                        source_path, metadata, indexed_at, embedding_version
                    ) VALUES (%s, %s::vector, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
                    ON CONFLICT (run_id) DO UPDATE SET
                        vector = EXCLUDED.vector,
                        input_text = EXCLUDED.input_text,
                        output_text = EXCLUDED.output_text,
                        config_text = EXCLUDED.config_text,
                        run_kind = EXCLUDED.run_kind,
                        provider = EXCLUDED.provider,
                        template_version = EXCLUDED.template_version,
                        created_at = EXCLUDED.created_at,
                        dimension = EXCLUDED.dimension,
                        source_path = EXCLUDED.source_path,
                        metadata = EXCLUDED.metadata,
                        indexed_at = EXCLUDED.indexed_at,
                        embedding_version = EXCLUDED.embedding_version
                    """,
                    (
                        record.run_id,
                        _vector_literal(embedding.vector),
                        record.input_text,
                        record.output_text,
                        record.config_text,
                        record.run_kind,
                        record.provider,
                        record.template_version,
                        record.created_at,
                        record.dimension,
                        record.source_path,
                        record.metadata_json,
                        record.indexed_at,
                        record.embedding_version,
                    ),
                )
        return True

    def upsert_batch(self, embeddings: list[ExecutionEmbedding]) -> int:
        indexed = 0
        for embedding in embeddings:
            if self.upsert(embedding):
                indexed += 1
        return indexed

    def get(self, run_id: str) -> ExecutionEmbedding | None:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT run_id, vector::text, input_text, output_text, config_text,
                           run_kind, provider, template_version, created_at, dimension,
                           source_path, metadata::text, indexed_at, embedding_version
                    FROM {self._qualified("oracle_records")}
                    WHERE run_id = %s
                    """,
                    (run_id,),
                )
                row = cur.fetchone()
        return self._row_to_embedding(row) if row else None

    def delete(self, run_id: str) -> bool:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"DELETE FROM {self._qualified('oracle_records')} WHERE run_id = %s",
                    (run_id,),
                )
                return int(cur.rowcount or 0) > 0

    def search(
        self,
        query_vector: list[float],
        *,
        top_k: int = 10,
        run_kind: str | None = None,
        provider: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        min_similarity: float = -1.0,
        embedding_version: int | None = EMBEDDING_VERSION,
    ) -> list[SearchResult]:
        where = ["dimension = %s"]
        where_params: list[Any] = [len(query_vector)]
        if run_kind:
            where.append("run_kind = %s")
            where_params.append(run_kind)
        if provider:
            where.append("provider = %s")
            where_params.append(provider)
        if since:
            where.append("created_at >= %s")
            where_params.append(since)
        if until:
            where.append("created_at <= %s")
            where_params.append(until)
        if embedding_version is not None:
            where.append("embedding_version = %s")
            where_params.append(embedding_version)
        query_literal = _vector_literal(query_vector)
        params = [query_literal, *where_params, query_literal, max(top_k, 0)]
        sql = f"""
            SELECT run_id, vector::text, input_text, output_text, config_text,
                   run_kind, provider, template_version, created_at, dimension,
                   source_path, metadata::text, indexed_at, embedding_version,
                   (1 - (vector <=> %s::vector)) AS similarity
            FROM {self._qualified("oracle_records")}
            WHERE {" AND ".join(where)}
            ORDER BY vector <=> %s::vector, run_id ASC
            LIMIT %s
        """
        results: list[SearchResult] = []
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, tuple(params))
                for row in cur.fetchall():
                    embedding = self._row_to_embedding(row[:14])
                    if embedding is None:
                        continue
                    similarity = float(row[14])
                    if similarity < min_similarity:
                        continue
                    results.append(
                        SearchResult(
                            run_id=embedding.run_id,
                            similarity=similarity,
                            distance=semantic_distance(query_vector, embedding.vector),
                            embedding=embedding,
                        )
                    )
        return results

    def search_by_text(
        self,
        query_text: str,
        *,
        top_k: int = 10,
        run_kind: str | None = None,
        provider: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        min_similarity: float = -1.0,
    ) -> list[SearchResult]:
        from .embeddings import get_embedding_engine

        query_vector = get_embedding_engine().embed_text(query_text)
        return self.search(
            query_vector,
            top_k=top_k,
            run_kind=run_kind,
            provider=provider,
            since=since,
            until=until,
            min_similarity=min_similarity,
        )

    def get_neighbors(
        self,
        run_id: str,
        *,
        top_k: int = 10,
        same_kind: bool = False,
        same_provider: bool = False,
    ) -> list[SearchResult]:
        embedding = self.get(run_id)
        if embedding is None:
            return []
        results = self.search(
            embedding.vector,
            top_k=top_k + 1,
            run_kind=embedding.run_kind if same_kind else None,
            provider=embedding.provider if same_provider else None,
        )
        return [result for result in results if result.run_id != run_id][:top_k]

    def list_all(
        self,
        *,
        run_kind: str | None = None,
        provider: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        embedding_version: int | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[ExecutionEmbedding]:
        where = ["1=1"]
        params: list[Any] = []
        if run_kind:
            where.append("run_kind = %s")
            params.append(run_kind)
        if provider:
            where.append("provider = %s")
            params.append(provider)
        if since:
            where.append("created_at >= %s")
            params.append(since)
        if until:
            where.append("created_at <= %s")
            params.append(until)
        if embedding_version is not None:
            where.append("embedding_version = %s")
            params.append(embedding_version)
        params.extend([limit, offset])
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT run_id, vector::text, input_text, output_text, config_text,
                           run_kind, provider, template_version, created_at, dimension,
                           source_path, metadata::text, indexed_at, embedding_version
                    FROM {self._qualified("oracle_records")}
                    WHERE {" AND ".join(where)}
                    ORDER BY created_at DESC, run_id ASC
                    LIMIT %s OFFSET %s
                    """,
                    tuple(params),
                )
                rows = cur.fetchall()
        return [embedding for row in rows if (embedding := self._row_to_embedding(row))]

    def count(
        self,
        *,
        run_kind: str | None = None,
        provider: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        embedding_version: int | None = None,
    ) -> int:
        where = ["1=1"]
        params: list[Any] = []
        if run_kind:
            where.append("run_kind = %s")
            params.append(run_kind)
        if provider:
            where.append("provider = %s")
            params.append(provider)
        if since:
            where.append("created_at >= %s")
            params.append(since)
        if until:
            where.append("created_at <= %s")
            params.append(until)
        if embedding_version is not None:
            where.append("embedding_version = %s")
            params.append(embedding_version)
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT COUNT(*) FROM {self._qualified('oracle_records')} WHERE {' AND '.join(where)}",
                    tuple(params),
                )
                row = cur.fetchone()
        return int(row[0]) if row else 0

    def stats(self) -> dict[str, Any]:
        try:
            total = self.count()
        except StoreUnavailableError:
            raise
        return {
            "total": total,
            "backend": self.backend_name,
            "schema": self.schema,
            "database_url": self.redacted_database_url,
            "schema_version": 1,
            "current_embedding_version": EMBEDDING_VERSION,
        }

    def health(self) -> StoreHealth:
        try:
            with self._conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.fetchone()
                    cur.execute(
                        "SELECT extname FROM pg_extension WHERE extname = 'vector'"
                    )
                    vector_row = cur.fetchone()
            if not vector_row:
                return StoreHealth(
                    backend=self.backend_name,
                    status="unavailable",
                    available=False,
                    path=self.redacted_database_url,
                    error="missing_pgvector_extension",
                )
            return StoreHealth(
                backend=self.backend_name,
                status="ok",
                available=True,
                path=self.redacted_database_url,
            )
        except Exception as exc:
            return StoreHealth(
                backend=self.backend_name,
                status="unavailable",
                available=False,
                path=self.redacted_database_url,
                error=type(exc).__name__,
            )

    def _row_to_embedding(self, row: Any) -> ExecutionEmbedding | None:
        if row is None:
            return None
        vector_raw = row[1]
        if isinstance(vector_raw, str):
            vector = [float(item) for item in vector_raw.strip("[]").split(",") if item]
        else:
            vector = list(vector_raw)
        metadata_raw = row[11]
        metadata = (
            json.loads(metadata_raw) if isinstance(metadata_raw, str) else metadata_raw
        )
        created_at = row[8]
        return ExecutionEmbedding(
            run_id=str(row[0]),
            vector=vector,
            input_text=row[2] or "",
            output_text=row[3] or "",
            config_text=row[4] or "",
            run_kind=row[5] or "unknown",
            provider=row[6] or "unknown",
            template_version=row[7],
            created_at=created_at.isoformat()
            if hasattr(created_at, "isoformat")
            else str(created_at or ""),
            dimension=int(row[9]),
            source_path=row[10],
            metadata=metadata or {},
            embedding_version=int(row[13] or 1),
        )
