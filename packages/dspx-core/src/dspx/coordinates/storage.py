"""Storage layer for semantic coordinate index.

Provides SQLite-based persistence for execution embeddings with
efficient similarity search using vector operations.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Iterator, Protocol, runtime_checkable

from .embeddings import ExecutionEmbedding, EMBEDDING_VERSION
from .metrics import cosine_similarity, semantic_distance

logger = logging.getLogger(__name__)

# Schema version - bump when changing DB schema
SCHEMA_VERSION = 2  # Bumped for embedding_version column


def get_default_index_path() -> Path:
    """Get default path for coordinate index database."""
    base = os.getenv("DSPX_ORACLE_INDEX_PATH")
    if base:
        return Path(base)
    return Path.cwd() / "generated" / "oracle" / "coordinates.db"


@dataclass
class StoreHealth:
    """Read-only health/status payload for a coordinate store backend."""

    backend: str
    status: str
    available: bool
    path: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "backend": self.backend,
            "status": self.status,
            "available": self.available,
        }
        if self.path is not None:
            payload["path"] = self.path
        if self.error is not None:
            payload["error"] = self.error
        return payload


@dataclass
class StoreStats:
    """Small wrapper for store statistics with backend identity."""

    backend: str
    stats: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"backend": self.backend, **self.stats}


@dataclass
class SearchResult:
    """Result from a similarity search."""

    run_id: str
    similarity: float
    distance: float
    embedding: ExecutionEmbedding

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "similarity": self.similarity,
            "distance": self.distance,
            "embedding": self.embedding.to_dict(),
        }


@dataclass
class CoordinateRecord:
    """A record in the coordinate index."""

    run_id: str
    vector_json: str
    input_text: str
    output_text: str
    config_text: str
    run_kind: str
    provider: str
    template_version: str | None
    created_at: str
    dimension: int
    source_path: str | None
    metadata_json: str
    indexed_at: str
    embedding_version: int

    @classmethod
    def from_embedding(
        cls, emb: ExecutionEmbedding, indexed_at: str | None = None
    ) -> "CoordinateRecord":
        return cls(
            run_id=emb.run_id,
            vector_json=json.dumps(emb.vector),
            input_text=emb.input_text,
            output_text=emb.output_text,
            config_text=emb.config_text,
            run_kind=emb.run_kind,
            provider=emb.provider,
            template_version=emb.template_version,
            created_at=emb.created_at,
            dimension=emb.dimension,
            source_path=emb.source_path,
            metadata_json=json.dumps(emb.metadata),
            indexed_at=indexed_at or datetime.now(timezone.utc).isoformat(),
            embedding_version=emb.embedding_version,
        )

    def to_embedding(self) -> ExecutionEmbedding:
        return ExecutionEmbedding(
            run_id=self.run_id,
            vector=json.loads(self.vector_json),
            input_text=self.input_text,
            output_text=self.output_text,
            config_text=self.config_text,
            run_kind=self.run_kind,
            provider=self.provider,
            template_version=self.template_version,
            created_at=self.created_at,
            dimension=self.dimension,
            source_path=self.source_path,
            metadata=json.loads(self.metadata_json) if self.metadata_json else {},
            embedding_version=self.embedding_version,
        )


@runtime_checkable
class CoordinateStore(Protocol):
    """Storage boundary for Oracle coordinate records.

    The first implementation is intentionally backed by the existing SQLite
    ``CoordinateIndex``.  This protocol gives future shared stores (for example
    Postgres + pgvector) a contract to implement without changing callers or
    making local development depend on a network service.
    """

    def upsert(self, embedding: ExecutionEmbedding) -> bool: ...

    def upsert_batch(self, embeddings: list[ExecutionEmbedding]) -> int: ...

    def get(self, run_id: str) -> ExecutionEmbedding | None: ...

    def delete(self, run_id: str) -> bool: ...

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
    ) -> list[SearchResult]: ...

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
    ) -> list[SearchResult]: ...

    def get_neighbors(
        self,
        run_id: str,
        *,
        top_k: int = 10,
        same_kind: bool = False,
        same_provider: bool = False,
    ) -> list[SearchResult]: ...

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
    ) -> list[ExecutionEmbedding]: ...

    def count(
        self,
        *,
        run_kind: str | None = None,
        provider: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        embedding_version: int | None = None,
    ) -> int: ...

    def stats(self) -> dict[str, Any]: ...

    def health(self) -> StoreHealth: ...


class SchemaVersionError(Exception):
    """Raised when database schema version is incompatible."""

    def __init__(self, stored_version: int, expected_version: int):
        self.stored_version = stored_version
        self.expected_version = expected_version
        super().__init__(
            f"Database schema version {stored_version} is incompatible with "
            f"expected version {expected_version}. "
            f"Rebuild the index with 'dspx oracle index --force-rebuild' or use a new database."
        )


class ParseSinceError(ValueError):
    """Raised when a since string cannot be parsed."""

    pass


class CoordinateIndex:
    """SQLite-backed index for semantic coordinates.

    Provides:
    - Storage and retrieval of execution embeddings
    - Similarity search using brute-force vector comparison
    - Filtering by run_kind, provider, date range
    - Incremental updates
    - Schema versioning and migration

    For larger scale, consider replacing with sqlite-vss or a dedicated
    vector database (Chroma, Qdrant, etc.).
    """

    backend_name = "sqlite"

    def __init__(self, db_path: Path | str | None = None, *, auto_migrate: bool = True):
        self.db_path = Path(db_path) if db_path else get_default_index_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        # BUG 18 FIX: Check schema version before creating indexes on migrated columns.
        self._check_schema_version(auto_migrate=auto_migrate)
        self._ensure_indexes()

    def _init_db(self) -> None:
        """Initialize database schema without masking older on-disk versions."""
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS coordinates (
                    run_id TEXT PRIMARY KEY,
                    vector_json TEXT NOT NULL,
                    input_text TEXT,
                    output_text TEXT,
                    config_text TEXT,
                    run_kind TEXT,
                    provider TEXT,
                    template_version TEXT,
                    created_at TEXT,
                    dimension INTEGER NOT NULL,
                    source_path TEXT,
                    metadata_json TEXT,
                    indexed_at TEXT NOT NULL,
                    embedding_version INTEGER NOT NULL DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS index_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );
                """
            )
            row = conn.execute(
                "SELECT value FROM index_meta WHERE key = 'schema_version'"
            ).fetchone()
            if row is None:
                columns = {
                    str(column[1])
                    for column in conn.execute("PRAGMA table_info(coordinates)")
                }
                initial_version = (
                    SCHEMA_VERSION if "embedding_version" in columns else 1
                )
                conn.execute(
                    "INSERT INTO index_meta (key, value) VALUES (?, ?)",
                    ("schema_version", str(initial_version)),
                )

    def _ensure_indexes(self) -> None:
        """Create indexes after any required schema migration has completed."""
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE INDEX IF NOT EXISTS idx_coordinates_run_kind
                    ON coordinates(run_kind);
                CREATE INDEX IF NOT EXISTS idx_coordinates_provider
                    ON coordinates(provider);
                CREATE INDEX IF NOT EXISTS idx_coordinates_created_at
                    ON coordinates(created_at);
                CREATE INDEX IF NOT EXISTS idx_coordinates_indexed_at
                    ON coordinates(indexed_at);
                CREATE INDEX IF NOT EXISTS idx_coordinates_embedding_version
                    ON coordinates(embedding_version);
                """
            )

    def _check_schema_version(self, *, auto_migrate: bool) -> None:
        """Check and optionally migrate schema version.

        BUG 18 FIX: Validate schema version on init.
        """
        with self._conn() as conn:
            row = conn.execute(
                "SELECT value FROM index_meta WHERE key = 'schema_version'"
            ).fetchone()
            if row is None:
                # New database, set version
                conn.execute(
                    "INSERT OR REPLACE INTO index_meta (key, value) VALUES (?, ?)",
                    ("schema_version", str(SCHEMA_VERSION)),
                )
                return

            stored_version = int(row["value"])
            if stored_version < SCHEMA_VERSION:
                if auto_migrate:
                    self._migrate_schema(stored_version, SCHEMA_VERSION)
                else:
                    raise SchemaVersionError(stored_version, SCHEMA_VERSION)
            elif stored_version > SCHEMA_VERSION:
                # Future version - can't read
                raise SchemaVersionError(stored_version, SCHEMA_VERSION)

    def _migrate_schema(self, from_version: int, to_version: int) -> None:
        """Migrate database schema between versions."""
        logger.info(f"Migrating index schema from v{from_version} to v{to_version}")

        with self._conn() as conn:
            # Migration 1->2: Add embedding_version column
            if from_version < 2:
                try:
                    conn.execute(
                        "ALTER TABLE coordinates ADD COLUMN embedding_version INTEGER NOT NULL DEFAULT 1"
                    )
                except sqlite3.OperationalError:
                    # Column already exists
                    pass

            # Update schema version
            conn.execute(
                "INSERT OR REPLACE INTO index_meta (key, value) VALUES (?, ?)",
                ("schema_version", str(to_version)),
            )

        logger.info(f"Schema migration complete: v{from_version} -> v{to_version}")

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        """Get database connection with context management."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    @contextmanager
    def _read_conn(self) -> Iterator[sqlite3.Connection]:
        """Get read-only connection (no commit on exit).

        BUG 15 FIX: Separate read connection that doesn't commit.
        """
        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def upsert(self, embedding: ExecutionEmbedding) -> bool:
        """Insert or update an embedding in the index.

        Returns:
            True if inserted/updated, False on error
        """
        record = CoordinateRecord.from_embedding(embedding)
        try:
            with self._conn() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO coordinates (
                        run_id, vector_json, input_text, output_text, config_text,
                        run_kind, provider, template_version, created_at, dimension,
                        source_path, metadata_json, indexed_at, embedding_version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.run_id,
                        record.vector_json,
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
        except Exception as e:
            logger.error(f"Failed to upsert embedding {record.run_id}: {e}")
            return False

    def upsert_batch(self, embeddings: list[ExecutionEmbedding]) -> int:
        """Insert or update multiple embeddings transactionally.

        BUG 19 FIX: Proper transaction handling - all-or-nothing.

        Returns:
            Number of successfully indexed embeddings (all or none)
        """
        if not embeddings:
            return 0

        now = datetime.now(timezone.utc).isoformat()
        records = [
            CoordinateRecord.from_embedding(emb, indexed_at=now) for emb in embeddings
        ]

        try:
            with self._conn() as conn:
                # Start explicit transaction
                conn.execute("BEGIN IMMEDIATE")

                try:
                    for record in records:
                        conn.execute(
                            """
                            INSERT OR REPLACE INTO coordinates (
                                run_id, vector_json, input_text, output_text, config_text,
                                run_kind, provider, template_version, created_at, dimension,
                                source_path, metadata_json, indexed_at, embedding_version
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                record.run_id,
                                record.vector_json,
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
                    # Transaction commits on successful context exit
                    return len(records)
                except Exception as e:
                    conn.execute("ROLLBACK")
                    logger.error(f"Batch upsert failed, rolled back: {e}")
                    return 0
        except Exception as e:
            logger.error(f"Failed to start batch transaction: {e}")
            return 0

    def get(self, run_id: str) -> ExecutionEmbedding | None:
        """Get embedding by run_id."""
        try:
            with self._read_conn() as conn:
                row = conn.execute(
                    "SELECT * FROM coordinates WHERE run_id = ?", (run_id,)
                ).fetchone()
                if row:
                    return self._row_to_embedding(row)
        except sqlite3.OperationalError:
            # Database doesn't exist yet
            pass
        return None

    def delete(self, run_id: str) -> bool:
        """Delete embedding by run_id."""
        with self._conn() as conn:
            cursor = conn.execute("DELETE FROM coordinates WHERE run_id = ?", (run_id,))
            return cursor.rowcount > 0

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
        """Search for similar embeddings.

        BUG 13 FIX: Log dimension mismatch instead of silent skip.

        Args:
            query_vector: Query embedding vector
            top_k: Maximum results to return
            run_kind: Filter by run kind
            provider: Filter by provider
            since: Filter by creation date (after)
            until: Filter by creation date (before)
            min_similarity: Minimum similarity threshold
            embedding_version: Filter by embedding version (default: current)

        Returns:
            List of SearchResult sorted by similarity (descending)
        """
        results = []
        dimension_mismatch_count = 0

        # Build query with filters
        sql = "SELECT * FROM coordinates WHERE 1=1"
        params: list[Any] = []

        if run_kind:
            sql += " AND run_kind = ?"
            params.append(run_kind)
        if provider:
            sql += " AND provider = ?"
            params.append(provider)
        if since:
            sql += " AND created_at >= ?"
            params.append(since.isoformat())
        if until:
            sql += " AND created_at <= ?"
            params.append(until.isoformat())
        if embedding_version is not None:
            sql += " AND embedding_version = ?"
            params.append(embedding_version)

        try:
            with self._read_conn() as conn:
                rows = conn.execute(sql, params).fetchall()

                for row in rows:
                    try:
                        emb = self._row_to_embedding(row)
                    except (json.JSONDecodeError, ValueError) as e:
                        logger.warning(
                            f"Failed to parse embedding {row['run_id']}: {e}"
                        )
                        continue

                    if emb.dimension != len(query_vector):
                        dimension_mismatch_count += 1
                        continue

                    similarity = cosine_similarity(query_vector, emb.vector)
                    if similarity < min_similarity:
                        continue

                    distance = semantic_distance(query_vector, emb.vector)
                    results.append(
                        SearchResult(
                            run_id=emb.run_id,
                            similarity=similarity,
                            distance=distance,
                            embedding=emb,
                        )
                    )
        except sqlite3.OperationalError:
            # Database doesn't exist yet
            pass

        # BUG 13 FIX: Warn about dimension mismatches
        if dimension_mismatch_count > 0:
            logger.warning(
                f"Skipped {dimension_mismatch_count} embeddings due to dimension mismatch "
                f"(query: {len(query_vector)}d, stored embeddings may have different dimension)"
            )

        # Sort by similarity descending
        results.sort(key=lambda r: r.similarity, reverse=True)
        return results[:top_k]

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
        """Search by text query (will be embedded).

        Args:
            query_text: Text to embed and search for
            top_k: Maximum results to return
            run_kind: Filter by run kind
            provider: Filter by provider
            since: Filter by creation date (after)
            until: Filter by creation date (before)
            min_similarity: Minimum similarity threshold

        Returns:
            List of SearchResult sorted by similarity (descending)
        """
        from .embeddings import get_embedding_engine

        engine = get_embedding_engine()
        query_vector = engine.embed_text(query_text)
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
        """Find semantic neighbors of a specific run.

        Args:
            run_id: Run ID to find neighbors for
            top_k: Number of neighbors to return
            same_kind: Only return runs of the same kind
            same_provider: Only return runs from the same provider

        Returns:
            List of SearchResult (excluding the query run itself)
        """
        emb = self.get(run_id)
        if emb is None:
            return []

        run_kind = emb.run_kind if same_kind else None
        provider = emb.provider if same_provider else None

        # Search with one extra to account for self
        results = self.search(
            emb.vector,
            top_k=top_k + 1,
            run_kind=run_kind,
            provider=provider,
        )

        # Filter out the query run itself
        return [r for r in results if r.run_id != run_id][:top_k]

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
        """List all embeddings with optional filters."""
        sql = "SELECT * FROM coordinates WHERE 1=1"
        params: list[Any] = []

        if run_kind:
            sql += " AND run_kind = ?"
            params.append(run_kind)
        if provider:
            sql += " AND provider = ?"
            params.append(provider)
        if since:
            sql += " AND created_at >= ?"
            params.append(since.isoformat())
        if until:
            sql += " AND created_at <= ?"
            params.append(until.isoformat())
        if embedding_version is not None:
            sql += " AND embedding_version = ?"
            params.append(embedding_version)

        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        embeddings = []
        try:
            with self._read_conn() as conn:
                rows = conn.execute(sql, params).fetchall()
                for row in rows:
                    try:
                        embeddings.append(self._row_to_embedding(row))
                    except (json.JSONDecodeError, ValueError) as e:
                        logger.warning(
                            f"Failed to parse embedding {row['run_id']}: {e}"
                        )
        except sqlite3.OperationalError:
            pass

        return embeddings

    def count(
        self,
        *,
        run_kind: str | None = None,
        provider: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        embedding_version: int | None = None,
    ) -> int:
        """Count embeddings matching filters."""
        sql = "SELECT COUNT(*) FROM coordinates WHERE 1=1"
        params: list[Any] = []

        if run_kind:
            sql += " AND run_kind = ?"
            params.append(run_kind)
        if provider:
            sql += " AND provider = ?"
            params.append(provider)
        if since:
            sql += " AND created_at >= ?"
            params.append(since.isoformat())
        if until:
            sql += " AND created_at <= ?"
            params.append(until.isoformat())
        if embedding_version is not None:
            sql += " AND embedding_version = ?"
            params.append(embedding_version)

        try:
            with self._read_conn() as conn:
                return conn.execute(sql, params).fetchone()[0]
        except sqlite3.OperationalError:
            return 0

    def stats(self) -> dict[str, Any]:
        """Get index statistics."""
        try:
            with self._read_conn() as conn:
                total = conn.execute("SELECT COUNT(*) FROM coordinates").fetchone()[0]

                # Get run_kind distribution
                kind_rows = conn.execute(
                    "SELECT run_kind, COUNT(*) as cnt FROM coordinates GROUP BY run_kind"
                ).fetchall()
                by_kind = {row["run_kind"]: row["cnt"] for row in kind_rows}

                # Get provider distribution
                provider_rows = conn.execute(
                    "SELECT provider, COUNT(*) as cnt FROM coordinates GROUP BY provider"
                ).fetchall()
                by_provider = {row["provider"]: row["cnt"] for row in provider_rows}

                # Get embedding version distribution
                version_rows = conn.execute(
                    "SELECT embedding_version, COUNT(*) as cnt FROM coordinates GROUP BY embedding_version"
                ).fetchall()
                by_version = {
                    row["embedding_version"]: row["cnt"] for row in version_rows
                }

                # Get dimension info
                dim_row = conn.execute(
                    "SELECT MIN(dimension), MAX(dimension), GROUP_CONCAT(DISTINCT dimension) FROM coordinates"
                ).fetchone()

                return {
                    "total": total,
                    "by_run_kind": by_kind,
                    "by_provider": by_provider,
                    "by_embedding_version": by_version,
                    "dimensions": dim_row[2].split(",") if dim_row[2] else [],
                    "dimension_range": [dim_row[0], dim_row[1]]
                    if dim_row[0] is not None
                    else [],
                    "schema_version": SCHEMA_VERSION,
                    "current_embedding_version": EMBEDDING_VERSION,
                }
        except sqlite3.OperationalError:
            return {
                "total": 0,
                "by_run_kind": {},
                "by_provider": {},
                "by_embedding_version": {},
                "dimensions": [],
                "dimension_range": [],
                "schema_version": SCHEMA_VERSION,
                "current_embedding_version": EMBEDDING_VERSION,
            }

    def health(self) -> StoreHealth:
        """Return read-only backend health without mutating store contents."""
        try:
            with self._read_conn() as conn:
                row = conn.execute(
                    "SELECT value FROM index_meta WHERE key = 'schema_version'"
                ).fetchone()
            schema_status = str(row["value"]) if row is not None else "unknown"
            return StoreHealth(
                backend=self.backend_name,
                status=f"ok:schema_v{schema_status}",
                available=True,
                path=str(self.db_path),
            )
        except sqlite3.OperationalError as exc:
            return StoreHealth(
                backend=self.backend_name,
                status="unavailable",
                available=False,
                path=str(self.db_path),
                error=str(exc),
            )

    def vacuum(self) -> None:
        """Vacuum the database to reclaim space."""
        with self._conn() as conn:
            conn.execute("VACUUM")

    def _row_to_embedding(self, row: sqlite3.Row) -> ExecutionEmbedding:
        """Convert database row to ExecutionEmbedding.

        BUG 17 FIX: Handle JSON parse errors with context.
        """
        run_id = row["run_id"]

        try:
            vector = json.loads(row["vector_json"])
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid vector JSON for run {run_id}: {e}")

        try:
            metadata = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
        except json.JSONDecodeError as e:
            logger.warning(f"Invalid metadata JSON for run {run_id}, using empty: {e}")
            metadata = {}

        return ExecutionEmbedding(
            run_id=run_id,
            vector=vector,
            input_text=row["input_text"] or "",
            output_text=row["output_text"] or "",
            config_text=row["config_text"] or "",
            run_kind=row["run_kind"] or "unknown",
            provider=row["provider"] or "unknown",
            template_version=row["template_version"],
            created_at=row["created_at"] or "",
            dimension=row["dimension"],
            source_path=row["source_path"],
            metadata=metadata,
            embedding_version=row["embedding_version"]
            if "embedding_version" in row.keys()
            else 1,
        )


def open_coordinate_store(
    *,
    store: str | None = None,
    db_path: Path | str | None = None,
    auto_migrate: bool = True,
) -> CoordinateStore:
    """Open a coordinate store using the current explicit backend contract.

    ``sqlite`` remains the default local/offline backend.  ``postgres_pgvector`` is
    available only behind explicit Oracle shared-store configuration and must not be
    selected implicitly by candidate-local program evidence indexing/reporting.
    """

    store_name = (store or os.getenv("DSPX_ORACLE_STORE") or "sqlite").strip().lower()
    if store_name in {"sqlite", "local_sqlite"}:
        return CoordinateIndex(db_path=db_path, auto_migrate=auto_migrate)
    if store_name in {"postgres", "postgres_pgvector", "pgvector"}:
        from .postgres_store import PostgresPgvectorCoordinateStore

        return PostgresPgvectorCoordinateStore()
    raise ValueError(
        f"Unsupported DSPx Oracle coordinate store '{store_name}'. "
        "Supported: sqlite, postgres_pgvector"
    )


def parse_since(since_str: str) -> datetime:
    """Parse a 'since' string like '30d', '7d', '1h' into a datetime.

    BUG 14 FIX: Raise ParseSinceError with helpful message on invalid input.

    Args:
        since_str: Duration string (e.g., '30d', '7d', '24h', '1w', '30m')
                  or ISO 8601 date string

    Returns:
        Datetime that many units ago from now

    Raises:
        ParseSinceError: If the string cannot be parsed
    """
    original_since_str = since_str.strip()
    since_str_lower = original_since_str.lower()

    if not original_since_str:
        raise ParseSinceError("Empty since string")

    try:
        if since_str_lower.endswith("d"):
            days = int(original_since_str[:-1])
            return datetime.now(timezone.utc) - timedelta(days=days)
        elif since_str_lower.endswith("h"):
            hours = int(original_since_str[:-1])
            return datetime.now(timezone.utc) - timedelta(hours=hours)
        elif since_str_lower.endswith("w"):
            weeks = int(original_since_str[:-1])
            return datetime.now(timezone.utc) - timedelta(weeks=weeks)
        elif since_str_lower.endswith("m"):
            minutes = int(original_since_str[:-1])
            return datetime.now(timezone.utc) - timedelta(minutes=minutes)
        else:
            # Try parsing as ISO date while preserving case-sensitive T/Z separators.
            try:
                dt = datetime.fromisoformat(original_since_str.replace("Z", "+00:00"))
                # Ensure timezone-aware
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                raise ParseSinceError(
                    f"Invalid since string '{original_since_str}'. "
                    f"Expected format: NNd, NNh, NNw, NNm (e.g., '30d', '24h') "
                    f"or ISO 8601 date (e.g., '2024-01-15', '2024-01-15T10:00:00Z')"
                )
    except (ValueError, TypeError) as e:
        raise ParseSinceError(f"Invalid since string '{original_since_str}': {e}")
